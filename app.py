from flask import Flask, render_template, request, jsonify, redirect, url_for
import psycopg2
import logging
import os
import re
from datetime import datetime, timedelta

app = Flask(__name__, static_url_path='/static')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DB_CONFIG = {"dbname": "puntiautostrade", "user": "postgres", "password": "root", "host": "localhost", "port": 5432}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_table_from_punto(strada):
    strada_upper = strada.upper()
    if 'A90' in strada_upper:
        return 'datia90'
    elif 'SS51' in strada_upper:
        return 'datiss51'
    elif 'SS675' in strada_upper:
        return 'datiss675'
    else:
        return None


# Funzione di normalizzazione robusta per i nomi dei tratti
def normalize_key(name):
    if not name: return ""
    return re.sub(r"[\s._()-]", "", name).lower()


@app.route("/")
def index(): return redirect(url_for('previsionale'))


@app.route("/previsionale")
def previsionale(): return render_template("previsionale.html")


@app.route("/storico")
def storico(): return render_template("storico.html")


@app.route("/api/previsionale_dato")
def previsionale_dato():
    variabile, strada = request.args.get('variabile'), request.args.get('strada')
    if not variabile or not strada: return jsonify({"errore": "Parametri mancanti"}), 400
    tabella = get_table_from_punto(strada)
    if not tabella: return jsonify({"errore": "Strada non supportata"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT MAX(downloaded_at) FROM {tabella} WHERE tratto ILIKE %s", (f"%{strada}%",))
        start_dt = cursor.fetchone()[0]
        if not start_dt: return jsonify({"times": [], "data": {}})

        end_dt = start_dt + timedelta(hours=72)
        cursor.execute(
            f"SELECT tratto, time, {variabile} FROM {tabella} WHERE tratto ILIKE %s AND downloaded_at = %s AND time >= %s AND time < %s ORDER BY tratto, time",
            (f"%{strada}%", start_dt, start_dt, end_dt)
        )
        rows = cursor.fetchall()

        risultati, orari_set = {}, set()
        for tratto, time_val, misura in rows:
            norm_tratto = normalize_key(tratto)
            orari_set.add(time_val.isoformat())
            if norm_tratto not in risultati: risultati[norm_tratto] = []

            valore_finale = misura * 3.6 if variabile == 'windspeed' and misura is not None else misura
            # Includiamo il nome originale per il tooltip nel frontend
            risultati[norm_tratto].append(
                {"time": time_val.isoformat(), "valore": valore_finale, "tratto_originale": tratto})

        return jsonify({"times": sorted(list(orari_set)), "data": risultati})
    except Exception as e:
        logging.error(f"Errore in previsionale_dato: {e}", exc_info=True)
        return jsonify({"errore": "Errore interno"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route("/api/historico_orario")
def storico_orario():
    variabili, strada = request.args.getlist('variabile'), request.args.get('strada')
    start_date, end_date = request.args.get('start_date'), request.args.get('end_date')
    tratto_selezionato = request.args.get('tratto')

    if not variabili or not strada or not tratto_selezionato: return jsonify({"errore": "Parametri mancanti"}), 400
    tabella = get_table_from_punto(strada)
    if not tabella: return jsonify({"errore": "Strada non supportata"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        safe_columns = [col for col in variabili if
                        col in ['temperature', 'windspeed', 'precipitation', 'precipitation_probability']]
        if not safe_columns: return jsonify({"errore": "Variabili non valide"}), 400

        select_clause = ", ".join(safe_columns)
        query = f"SELECT time, {select_clause} FROM {tabella} WHERE tratto = %s"
        params = [tratto_selezionato]

        if start_date: query += " AND time >= %s"; params.append(start_date)
        if end_date: query += " AND time <= %s"; params.append(end_date + " 23:59:59")
        query += " ORDER BY time"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        risultati = []
        for row in rows:
            record = {"time": row[0].isoformat()}
            for i, col_name in enumerate(safe_columns):
                val = row[i + 1]
                record[col_name] = val * 3.6 if col_name == 'windspeed' and val is not None else val
            risultati.append(record)

        return jsonify({"data": risultati})
    except Exception as e:
        logging.error(f"Errore in storico_orario: {e}", exc_info=True)
        return jsonify({"errore": "Errore interno"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route("/grafico.html")
def grafico_page(): return "Pagina dei grafici (da implementare)"


if __name__ == "__main__":
    app.run(debug=True, port=5000)