import { useEffect, useState } from 'react';
import { getHealth, type HealthResponse } from './api/client';

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div style={{ padding: '2rem', fontFamily: 'monospace', background: '#0a0a0a', color: '#e0e0e0', minHeight: '100vh' }}>
      <h1 style={{ color: '#4ade80' }}>Polyfast</h1>
      <p style={{ color: '#888' }}>Polymarket 5M Trading Bot</p>

      {error && (
        <div style={{ color: '#ef4444', marginTop: '1rem' }}>
          Backend connection failed: {error}
        </div>
      )}

      {health && (
        <div style={{ marginTop: '1rem', padding: '1rem', background: '#1a1a1a', borderRadius: '8px' }}>
          <p>Status: <span style={{ color: '#4ade80' }}>{health.status}</span></p>
          <p>Version: {health.version}</p>
          <p>Uptime: {health.uptime_seconds}s</p>
        </div>
      )}

      {!health && !error && (
        <p style={{ color: '#888', marginTop: '1rem' }}>Connecting to backend...</p>
      )}
    </div>
  );
}

export default App;
