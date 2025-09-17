import socket
import threading
import json
import psycopg2
import traceback
import os
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS

# --- 1. CONFIGURACIÓN CON VARIABLES DE ENTORNO ---
HOST = os.getenv('HOST', '0.0.0.0')
UDP_PORT = int(os.getenv('UDP_PORT', 5001))

DB_CONFIG = {
    "dbname": os.getenv('DB_NAME', 'datos_gps'),
    "user": os.getenv('DB_USER', 'postgres'),
    "password": os.getenv('DB_PASSWORD'),
    "host": os.getenv('DB_HOST'),
    "port": os.getenv('DB_PORT', '5432')
}

# Validar que las variables críticas estén definidas
if not DB_CONFIG['password'] or not DB_CONFIG['host']:
    raise ValueError("❌ ERROR: DB_PASSWORD y DB_HOST deben estar definidas en las variables de entorno")

# --- 2. FUNCIONES DE BASE DE DATOS Y UDP ---

def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ CRÍTICO: No se pudo conectar a PostgreSQL. Error: {e}")
        return None

def setup_database():
    conn = get_db_connection()
    if conn is None: 
        return
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
        print(f"❌ Error configurando base de datos: {e}")
    finally:
        if conn: 
            conn.close()

def save_location_data(data_str):
    conn = get_db_connection()
    if not conn: 
        return
    try:
        data = json.loads(data_str)
        lat, lon, app_time_ms = data.get('lat'), data.get('lon'), data.get('time')
        if lat is None or lon is None or app_time_ms is None: 
            return
        app_timestamp = datetime.fromtimestamp(app_time_ms / 1000.0)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO locations (latitude, longitude, app_timestamp, full_data) VALUES (%s, %s, %s, %s);",
                (lat, lon, app_timestamp, json.dumps(data))
            )
            conn.commit()
        print(f"📍 [UDP] Dato guardado en PostgreSQL: Lat {lat}, Lon {lon}")
    except Exception as e:
        print(f"❌ Error guardando datos: {e}")
        traceback.print_exc()
    finally:
        if conn: 
            conn.close()

def udp_listener():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind((HOST, UDP_PORT))
            print(f"🚀 Servidor UDP (Sniffer) escuchando en {HOST}:{UDP_PORT}...")
            while True:
                data, _ = s.recvfrom(1024)
                if data:
                    save_location_data(data.decode('utf-8'))
    except Exception as e:
        print(f"❌ Error en UDP listener: {e}")
        traceback.print_exc()

# --- 3. INICIALIZACIÓN DE LA APLICACIÓN FLASK ---

app = Flask(__name__)
CORS(app)

@app.route('/api/latest_location', methods=['GET'])
def get_latest_location():
    conn = get_db_connection()
    if not conn: 
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT latitude, longitude, app_timestamp FROM locations ORDER BY id DESC LIMIT 1;")
            latest_record = cur.fetchone()
        if latest_record:
            return jsonify({
                "latitude": latest_record[0], 
                "longitude": latest_record[1],
                "timestamp": latest_record[2].isoformat()
            })
        else:
            return jsonify({"message": "Esperando la primera transmisión de datos..."}), 404
    except Exception as e:
        print(f"❌ Error consultando base de datos: {e}")
        traceback.print_exc()
        return jsonify({"error": "Error al consultar la base de datos"}), 500
    finally:
        if conn: 
            conn.close()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar salud del servicio"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return jsonify({"status": "healthy", "database": "connected"}), 200
        else:
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 500
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# --- 4. ARRANQUE DE SERVICIOS ---

if __name__ == '__main__':
    print(f"🔧 Configuración:")
    print(f"   Host: {HOST}")
    print(f"   Puerto UDP: {UDP_PORT}")
    print(f"   Base de datos: {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    
    # Verificamos y creamos la tabla al iniciar
    setup_database()

    # Iniciamos el hilo del sniffer UDP en segundo plano
    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()
    
    # Para desarrollo local
    app.run(host='0.0.0.0', port=8000, debug=False)
else:
    # Para producción con Gunicorn
    print(f"🚀 Iniciando en modo producción...")
    print(f"   Host: {HOST}")
    print(f"   Puerto UDP: {UDP_PORT}")
    print(f"   Base de datos: {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    
    # Verificamos y creamos la tabla al iniciar
    setup_database()

    # Iniciamos el hilo del sniffer UDP en segundo plano
    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()