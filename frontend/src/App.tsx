import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import ApiSearch from './components/ApiSearch';

export default function App() {
  const [activeTab, setActiveTab] = useState<'monitoring' | 'search'>('monitoring');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'Inter, system-ui, sans-serif', background: '#f8fafc' }}>
      <header style={{ background: '#0f172a', color: '#fff', padding: '.9rem 2rem', fontWeight: 800, letterSpacing: '.01em', display: 'flex', alignItems: 'center', gap: '2rem' }}>
        <div>Briefcast</div>
        <nav style={{ display: 'flex', gap: '1rem', fontSize: '.9rem', fontWeight: 600 }}>
          <button 
            onClick={() => setActiveTab('monitoring')}
            style={{ background: 'transparent', border: 'none', color: activeTab === 'monitoring' ? '#fff' : '#94a3b8', cursor: 'pointer', padding: 0 }}
          >
            Monitoring
          </button>
          <button 
            onClick={() => setActiveTab('search')}
            style={{ background: 'transparent', border: 'none', color: activeTab === 'search' ? '#fff' : '#94a3b8', cursor: 'pointer', padding: 0 }}
          >
            API & Search
          </button>
        </nav>
      </header>
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        {activeTab === 'monitoring' ? <Dashboard /> : <ApiSearch />}
      </div>
    </div>
  );
}
