import React from 'react';
import Dashboard from './components/Dashboard';

export default function App() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'Inter, system-ui, sans-serif', background: '#f8fafc' }}>
      <header style={{ background: '#0f172a', color: '#fff', padding: '.9rem 2rem', fontWeight: 800, letterSpacing: '.01em' }}>
        Briefcast
      </header>
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        <Dashboard />
      </div>
    </div>
  );
}
