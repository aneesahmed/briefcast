// src/App.tsx
import React, { useState, useEffect } from 'react';
import type { ProcessResult } from './types';
import Dashboard from './components/Dashboard';
import Studio from './components/Studio';
import Audit from './components/Audit';

export default function App() {
  const [activeView, setActiveView] = useState<'dashboard' | 'studio' | 'audit'>('dashboard');
  const [history, setHistory] = useState<ProcessResult[]>([]);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/history`);
      if (response.ok) {
        const data = await response.json();
        setHistory(data.history || []);
      }
    } catch (err) {
      console.error('Failed to load history', err);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <>
      <style>
        {`@import url('https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400;700&display=swap');
          body { margin: 0; padding: 0; background-color: #f3f4f6; }
        `}
      </style>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'system-ui, sans-serif' }}>
        {/* TOP NAVIGATION BAR */}
        <div style={{ backgroundColor: '#1e293b', color: 'white', padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
          <div onClick={() => setActiveView('dashboard')} style={{ fontSize: '1.25rem', fontWeight: 'bold', cursor: 'pointer' }}>
            Briefcast Enterprise
          </div>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button
              onClick={() => setActiveView('dashboard')}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                fontWeight: 'bold',
                cursor: 'pointer',
                border: 'none',
                backgroundColor: activeView === 'dashboard' ? '#3b82f6' : 'transparent',
                color: activeView === 'dashboard' ? 'white' : '#cbd5e1',
              }}
            >
              🏠 Dashboard
            </button>
            <button
              onClick={() => setActiveView('studio')}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                fontWeight: 'bold',
                cursor: 'pointer',
                border: 'none',
                backgroundColor: activeView === 'studio' ? '#3b82f6' : 'transparent',
                color: activeView === 'studio' ? 'white' : '#cbd5e1',
              }}
            >
              🎙️ Studio
            </button>
            <button
              onClick={() => setActiveView('audit')}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                fontWeight: 'bold',
                cursor: 'pointer',
                border: 'none',
                backgroundColor: activeView === 'audit' ? '#3b82f6' : 'transparent',
                color: activeView === 'audit' ? 'white' : '#cbd5e1',
              }}
            >
              📊 Audit
            </button>
          </div>
        </div>

        {/* VIEW ROUTER */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
          {activeView === 'dashboard' && <Dashboard history={history} setActiveView={setActiveView} />}
          {activeView === 'studio' && <Studio API_BASE_URL={API_BASE_URL} onProcessingComplete={fetchHistory} />}
          {activeView === 'audit' && <Audit history={history} API_BASE_URL={API_BASE_URL} />}
        </div>
      </div>
    </>
  );
}