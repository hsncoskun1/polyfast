import { useEffect, useState } from 'react';
import { getHealth, type HealthResponse } from './api/client';
import DashboardPreview from './DashboardPreview';

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(true);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, []);

  // Preview mode — yeni dashboard goster
  if (showPreview) {
    return (
      <div>
        <div style={{
          position: 'fixed', top: 0, right: 0, zIndex: 999,
          padding: '0.25rem 0.75rem', background: '#1a1a1a',
          border: '1px solid #333', borderRadius: '0 0 0 6px',
          fontSize: '0.7rem', color: '#888', cursor: 'pointer',
        }} onClick={() => setShowPreview(false)}>
          Exit Preview
        </div>
        <DashboardPreview />
      </div>
    );
  }

  // Eski dashboard (korunuyor)
  return (
    <div style={{ padding: '2rem', fontFamily: 'monospace', background: '#0a0a0a', color: '#e0e0e0', minHeight: '100vh' }}>
      <h1 style={{ color: '#4ade80' }}>Polyfast</h1>
      <p style={{ color: '#888' }}>Polymarket 5M Trading Bot</p>

      <button
        onClick={() => setShowPreview(true)}
        style={{
          marginTop: '1rem', padding: '0.5rem 1rem',
          background: '#1a1a1a', color: '#4ade80', border: '1px solid #333',
          borderRadius: '6px', cursor: 'pointer', fontFamily: 'monospace',
        }}
      >
        Open Dashboard Preview
      </button>

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
