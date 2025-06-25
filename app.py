from flask import Flask, render_template, request, jsonify, redirect, url_for
import psycopg2
import logging
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === CONFIG DB ===
DB_CONFIG = {
    "dbname": "puntiautostrade",
    "user": "postgres",
    "password": "root",
    "host": "localhost",
    "port": 5432
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_table_from_punto(strada):
    if 'A90' in strada:
        return 'datia90'
    elif 'SS51' in strada:
        return 'datiss51'
    elif 'SS675' in strada:
        return 'datiss675'
    else:
        return None


# === ENDPOINT PER SERVIRE LE PAGINE HTML ===
@app.route("/")
def index():
    # La pagina di default sarà il previsionale
    return redirect(url_for('previsionale'))


@app.route("/previsionale")
def previsionale():
    # Serve il file previsionale.html dalla cartella /templates
    return render_template("previsionale.html")


@app.route("/storico")
def storico():
    # Serve il file storico.html dalla cartella /templates
    return render_template("storico.html")


# === API PER I DATI PREVISIONALI ===
@app.route("/api/previsionale_dato")
def previsionale_dato():
    variabile = request.args.get('variabile')
    strada = request.args.get('strada')
    if not variabile or not strada:
        return jsonify({"errore": "Parametri 'variabile' e 'strada' obbligatori"}), 400

    tabella = get_table_from_punto(strada)
    if not tabella:
        return jsonify({"errore": f"Strada '{strada}' non supportata"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT MAX(downloaded_at) FROM {tabella} WHERE tratto LIKE %s",
            (f"{strada}%",)
        )
        start_dt = cursor.fetchone()[0]

        if not start_dt:
            return jsonify({"times": [], "data": {}})

        ultimo_scarico = start_dt
        end_dt = start_dt + timedelta(hours=72)

        cursor.execute(
            f"""
            SELECT tratto, time, {variabile}
            FROM {tabella}
            WHERE tratto LIKE %s
              AND downloaded_at = %s
              AND time >= %s AND time < %s
            ORDER BY tratto, time
            """,
            (f"{strada}%", ultimo_scarico, start_dt, end_dt)
        )
        rows = cursor.fetchall()

        risultati = {}
        orari_set = set()
        for tratto, time_val, misura in rows:
            iso = time_val.isoformat()
            orari_set.add(iso)
            if tratto not in risultati:
                risultati[tratto] = []

            valore_finale = misura
            if variabile == 'windspeed' and misura is not None:
                valore_finale = misura * 3.6

            risultati[tratto].append({"time": iso, "valore": valore_finale})

        orari = sorted(list(orari_set))
        return jsonify({"times": orari, "data": risultati})

    except Exception as e:
        logging.error(f"Errore in previsionale_dato: {e}", exc_info=True)
        return jsonify({"errore": "Errore interno"}), 500
    finally:
        cursor.close()
        conn.close()


# === API PER I DATI STORICI ===
@app.route("/api/historico_orario")
def storico_orario():
    variabile = request.args.get('variabile')
    strada = request.args.get('strada')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not variabile or not strada or not start_date or not end_date:
        return jsonify({"errore": "Parametri mancanti"}), 400

    tabella = get_table_from_punto(strada)
    if not tabella:
        return jsonify({"errore": f"Strada '{strada}' non supportata"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            SELECT tratto, time, {variabile}
            FROM {tabella}
            WHERE tratto LIKE %s
              AND time >= %s
              AND time <= %s
            ORDER BY time
        """, (f"{strada}%", start_date, end_date + " 23:59:59"))
        rows = cursor.fetchall()
        data = {}
        times = set()
        for tratto, t, val in rows:
            iso = t.isoformat()
            times.add(iso)

            valore_finale = val
            if variabile == 'windspeed' and val is not None:
                valore_finale = val * 3.6

            data.setdefault(tratto, []).append({"time": iso, "valore": valore_finale})

        return jsonify({"times": sorted(times), "data": data})
    except Exception as e:
        logging.error(f"Errore in storico_orario: {e}", exc_info=True)
        return jsonify({"errore": "Errore interno"}), 500
    finally:
        cursor.close()
        conn.close()


# Endpoint per la pagina dei grafici
@app.route("/grafico.html")
def grafico_page():
    # Assumendo che esista un template 'grafico.html'
    return render_template("grafico.html")


if __name__ == "__main__":
    app.run(debug=True)