import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

// --- CONFIGURACIÓN ---
// URL de la API que se ejecuta en tu instancia EC2.
const API_URL = 'http://34.238.221.207/api/latest_location';
const REFRESH_INTERVAL_MS = 5000; // Refrescar los datos cada 5 segundos

function App() {
  const [locationData, setLocationData] = useState({
    latitude: 51.505, // Valor inicial por defecto
    longitude: -0.09,
    timestamp: 'Cargando...',
  });
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      const response = await fetch(API_URL);
      if (!response.ok) {
        throw new Error(`Error en la petición: ${response.statusText}`);
      }
      const data = await response.json();
      if (data.latitude && data.longitude) {
        setLocationData({
          latitude: data.latitude,
          longitude: data.longitude,
          timestamp: new Date(data.timestamp).toLocaleString(),
        });
        setError(null); // Limpiar errores si la petición es exitosa
      }
    } catch (err) {
      console.error("Error al obtener los datos:", err);
      setError("No se pudo cargar la última ubicación.");
    }
  };

  useEffect(() => {
    // Primera carga de datos
    fetchData();

    // Establecer un intervalo para refrescar los datos
    const intervalId = setInterval(fetchData, REFRESH_INTERVAL_MS);

    // Limpiar el intervalo cuando el componente se desmonte
    return () => clearInterval(intervalId);
  }, []); // El array vacío asegura que esto se ejecute solo una vez al montar el componente

  const position = [locationData.latitude, locationData.longitude];

  return (
    <div className='min-w-screen min-h-screen bg-black'>
      <header className='p-8 text-center'>
        <h1 className='text-white font-bold text-6xl'>PANTERA</h1>
      </header>

      <div className='grid grid-cols-1 md:grid-cols-3 mx-auto gap-8 max-w-[90%]'>
        <div className='w-full md:col-span-2 p-4 bg-white/20 rounded-3xl'>
          {/* Usamos una key para forzar el rerender del mapa si la posición cambia drásticamente */}
          <MapContainer center={position} zoom={16} key={`${position[0]}-${position[1]}`} style={{ height: '35rem', borderRadius: '1rem' }}>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <Marker position={position}>
              <Popup>
                Última ubicación registrada.
              </Popup>
            </Marker>
          </MapContainer>
        </div>
        <div className='bg-white/20 text-white inline-block py-8 px-8 w-full rounded-3xl'>
          <div className='flex justify-center'>
            <img className='rounded-full size-100 mb-8 shadow-2xl' src="logo.png" alt="Logo Pantera" />
          </div>
          <h2 className='text-3xl font-bold text-center'>Coordenadas</h2>
          {error ? (
            <p className='mt-4 text-l text-red-400 text-center'>{error}</p>
          ) : (
            <>
              <p className='mt-4 text-l'>Latitud: <span>{locationData.latitude}</span></p>
              <p className='mt-4 text-l'>Longitud: <span>{locationData.longitude}</span></p>
              <p className='mt-4 text-l'>Timestamp: <span>{locationData.timestamp}</span></p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;