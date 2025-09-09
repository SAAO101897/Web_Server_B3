import socket
import threading
import json
import psycopg2
import os
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. CONFIGURACIÓN DEL SERVIDOR ---
HOST = '0.0.0.0'
UDP_PORT = 5001
WEB_PORT = 5000  # Usar puerto 5000 que ya tienes abierto

# --- Configuración de la base de datos PostgreSQL ---
DB_CONFIG = {
    "dbname": "datos_gps",
    "user": "postgres", 
    "password": "Samir0712.",
    "host": "database-1.c69okc2a6bg9.us-east-1.rds.amazonaws.com",
    "port": "5432"
}

# --- 2. CONEXIÓN Y CONFIGURACIÓN DE POSTGRESQL ---

def get_db_connection():
    """Crea y devuelve una nueva conexión a la base de datos."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"❌ CRÍTICO: No se pudo conectar a PostgreSQL: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error inesperado al conectar a PostgreSQL: {e}")
        return None

def setup_database():
    """Se asegura de que la tabla 'locations' exista en la base de datos."""
    conn = get_db_connection()
    if conn is None:
        logger.error("❌ No se pudo establecer conexión para configurar la base de datos")
        return False
    
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
            logger.info("✅ Tabla 'locations' verificada/creada exitosamente.")
            return True
    except Exception as e:
        logger.error(f"❌ Error al configurar la tabla en la base de datos: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- 3. "SNIFFER" UDP ---

def save_location_data(data_str):
    """Parsea el JSON y guarda los datos relevantes en PostgreSQL."""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ No se pudo conectar a la BD para guardar datos")
        return

    try:
        data = json.loads(data_str)
        lat = data.get('lat')
        lon = data.get('lon')
        app_time_ms = data.get('time')

        if lat is None or lon is None or app_time_ms is None:
            logger.warning(f"⚠️ Dato JSON recibido pero sin lat/lon/time. Descartado: {data_str}")
            return

        app_timestamp = datetime.fromtimestamp(app_time_ms / 1000.0)

        with conn.cursor() as cur:
            sql = """
                INSERT INTO locations (latitude, longitude, app_timestamp, full_data)
                VALUES (%s, %s, %s, %s);
            """
            cur.execute(sql, (lat, lon, app_timestamp, json.dumps(data)))
            conn.commit()
        logger.info(f"🎯 [UDP] Dato guardado en PostgreSQL: Lat {lat}, Lon {lon}")

    except json.JSONDecodeError:
        logger.warning(f"⚠️ Dato recibido por UDP no es un JSON válido: {data_str}")
    except Exception as e:
        logger.error(f"❌ Error al guardar en PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()

def udp_listener():
    """Hilo para escuchar paquetes UDP."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind((HOST, UDP_PORT))
            logger.info(f"🚀 Servidor UDP (Sniffer) escuchando en el puerto {UDP_PORT}...")
            while True:
                data, _ = s.recvfrom(1024)
                if data:
                    save_location_data(data.decode('utf-8'))
    except Exception as e:
        logger.error(f"❌ Error en UDP listener: {e}")

# --- 4. SERVIDOR WEB FLASK (API) ---

app = Flask(__name__)
CORS(app)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint simple para verificar que la API funciona."""
    return jsonify({
        "status": "OK", 
        "message": "Pantera API funcionando correctamente",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/db_test', methods=['GET']) 
def test_database():
    """Endpoint para probar la conexión a la base de datos."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            result = cur.fetchone()
        return jsonify({"status": "OK", "message": "Conexión a BD exitosa", "result": result[0]})
    except Exception as e:
        return jsonify({"error": f"Error al probar la BD: {e}"}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/latest_location', methods=['GET'])
def get_latest_location():
    """Endpoint que devuelve la última ubicación de la BD en formato JSON."""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ No se pudo conectar a la base de datos en latest_location")
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
            logger.info(f"✅ Ubicación más reciente enviada: {data_dict}")
            return jsonify(data_dict)
        else:
            logger.info("📍 No hay datos de ubicación disponibles")
            return jsonify({"message": "Esperando la primera transmisión de datos..."}), 404
            
    except Exception as e:
        logger.error(f"❌ Error al consultar la base de datos: {e}")
        return jsonify({"error": f"Error al consultar la base de datos: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

# --- 5. ARRANQUE DEL SERVIDOR ---

if __name__ == '__main__':
    logger.info("🐾 Iniciando servicios de Pantera...")
    
    # Verificar conexión a BD antes de iniciar
    if not setup_database():
        logger.error("❌ No se pudo configurar la base de datos. Abortando...")
        exit(1)
    
    # Iniciar UDP listener
    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()

    logger.info(f"🌐 Servidor API listo. Endpoints disponibles:")
    logger.info(f"   - Health check: http://{HOST}:{WEB_PORT}/api/health")
    logger.info(f"   - DB test: http://{HOST}:{WEB_PORT}/api/db_test")
    logger.info(f"   - Latest location: http://{HOST}:{WEB_PORT}/api/latest_location")
    
    # Arrancar Flask
    app.run(
        host=HOST, 
        port=WEB_PORT, 
        debug=False,
        threaded=True,
        use_reloader=False
    )