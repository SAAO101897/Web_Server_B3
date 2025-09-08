import socket
import threading
import json
import psycopg2
import os
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS

# --- 1. CONFIGURACIÓN DEL SERVIDOR ---
HOST = '0.0.0.0'
UDP_PORT = 5001
WEB_PORT = 80 # Puerto HTTP para la API

# --- Configuración de la base de datos PostgreSQL para tu RDS ---
# En un entorno de producción avanzado, se recomienda usar variables de entorno.
DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASS"),
    "host": os.environ.get("DB_HOST"),
    "port": os.environ.get("DB_PORT")
}

# --- 2. CONEXIÓN Y CONFIGURACIÓN DE POSTGRESQL ---

def get_db_connection():
    """Crea y devuelve una nueva conexión a la base de datos."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ CRÍTICO: No se pudo conectar a PostgreSQL. Verifica los datos de conexión y las reglas del Security Group de RDS.")
        print(f"   Error: {e}")
        return None

def setup_database():
    """Se asegura de que la tabla 'locations' exista en la base de datos."""
    conn = get_db_connection()
    if conn is None:
        exit()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    id SERIAL PRIMARY KEY,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    app_timestamp TIMESTAMP WITH TIME ZONE,
                    server_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    full_data JSONB
                );
            """)
            conn.commit()
            print("✅ Tabla 'locations' verificada/creada exitosamente.")
    except Exception as e:
        print(f"❌ Error al configurar la tabla en la base de datos: {e}")
    finally:
        if conn:
            conn.close()

# --- 3. "SNIFFER" UDP ---

def save_location_data(data_str):
    """Parsea el JSON y guarda los datos relevantes en PostgreSQL."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        data = json.loads(data_str)
        lat = data.get('lat')
        lon = data.get('lon')
        app_time_ms = data.get('time')

        if lat is None or lon is None or app_time_ms is None:
            print(f"⚠️  Dato JSON recibido pero sin lat/lon/time. Descartado: {data_str}")
            return

        app_timestamp = datetime.fromtimestamp(app_time_ms / 1000.0)

        with conn.cursor() as cur:
            sql = """
                INSERT INTO locations (latitude, longitude, app_timestamp, full_data)
                VALUES (%s, %s, %s, %s);
            """
            cur.execute(sql, (lat, lon, app_timestamp, json.dumps(data)))
            conn.commit()
        print(f"📍 [UDP] Dato guardado en PostgreSQL: Lat {lat}, Lon {lon}")

    except json.JSONDecodeError:
        print(f"⚠️  Dato recibido por UDP no es un JSON válido: {data_str}")
    except Exception as e:
        print(f"❌ Error al guardar en PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()


def udp_listener():
    """Hilo para escuchar paquetes UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((HOST, UDP_PORT))
        print(f"🚀 Servidor UDP (Sniffer) escuchando en el puerto {UDP_PORT}...")
        while True:
            data, _ = s.recvfrom(1024)
            if data:
                save_location_data(data.decode('utf-8'))

# --- 4. SERVIDOR WEB FLASK (API) ---

app = Flask(__name__)
CORS(app) # Habilita CORS para todas las rutas

@app.route('/api/latest_location', methods=['GET'])
def get_latest_location():
    """Endpoint que devuelve la última ubicación de la BD en formato JSON."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT latitude, longitude, app_timestamp FROM locations ORDER BY id DESC LIMIT 1;")
            latest_record = cur.fetchone()

        if latest_record:
            data_dict = {
                "latitude": latest_record[0],
                "longitude": latest_record[1],
                "timestamp": latest_record[2].isoformat()
            }
            return jsonify(data_dict)
        else:
            return jsonify({"message": "Esperando la primera transmisión de datos..."}), 404
    except Exception as e:
        return jsonify({"error": f"Error al consultar la base de datos: {e}"}), 500
    finally:
        if conn:
            conn.close()

# --- 5. ARRANQUE DEL SERVIDOR ---

if __name__ == '__main__':
    print("Iniciando servicios de Pantera...")
    setup_database()

    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()

    print(f"🌍 Servidor API listo. Endpoint disponible en http://{HOST}:{WEB_PORT}/api/latest_location")
    app.run(host=HOST, port=WEB_PORT, debug=False)