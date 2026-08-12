// src/components/Dashboard.tsx
import React, { useState, useMemo } from 'react';
import type { ProcessResult } from '../types';

interface DashboardProps {
  history: ProcessResult[];
  setActiveView: (view: 'dashboard' | 'studio' | 'audit') => void;
}

export default function Dashboard({ history, setActiveView }: DashboardProps) {
  const [timeframe, setTimeframe] = useState<'day' | 'week' | 'month' | '3months'>('day');

  // Filter history based on the selected timeframe
  const filteredCount = useMemo(() => {
    const now = new Date();
    
    return history.filter(doc => {
      // Convert "YYYY-MM-DD HH:MM:SS" to a valid Date object
      const docDate = new Date(doc.timestamp.replace(' ', 'T'));
      const diffTime = Math.abs(now.getTime() - docDate.getTime());
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

      switch (timeframe) {
        case 'day':
          // Check if it's the exact same calendar day
          return docDate.toDateString() === now.toDateString();
        case 'week':
          return diffDays <= 7;
        case 'month':
          return diffDays <= 30;
        case '3months':
          return diffDays <= 90;
        default:
          return true;
      }
    }).length;
  }, [history, timeframe]);

  return (
    <div style={{ padding: '3rem', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', padding: '3rem', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)', textAlign: 'center' }}>
        
        <h1 style={{ color: '#1f2937', marginTop: 0, fontSize: '2rem' }}>Briefcast Operations Hub</h1>
        <p style={{ color: '#64748b', fontSize: '1.1rem', marginBottom: '3rem' }}>Enterprise document automation and broadcast pipeline.</p>
        
        {/* Metric Card */}
        <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '2rem', display: 'inline-block', minWidth: '300px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ margin: 0, color: '#475569', textTransform: 'uppercase', fontSize: '0.85rem' }}>Documents Processed</h3>
            <select 
              value={timeframe} 
              onChange={(e) => setTimeframe(e.target.value as any)}
              style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b', cursor: 'pointer' }}
            >
              <option value="day">Today</option>
              <option value="week">Past 7 Days</option>
              <option value="month">Past 30 Days</option>
              <option value="3months">Past 3 Months</option>
            </select>
          </div>
          <div style={{ fontSize: '4rem', fontWeight: 'bold', color: '#2563eb', lineHeight: '1' }}>
            {filteredCount}
          </div>
        </div>

        {/* Quick Links */}
        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginTop: '3rem' }}>
          <button 
            onClick={() => setActiveView('studio')}
            style={{ padding: '1rem 2rem', backgroundColor: '#1e293b', color: 'white', border: 'none', borderRadius: '6px', fontSize: '1.1rem', fontWeight: 'bold', cursor: 'pointer' }}
          >
            Launch Studio
          </button>
          <button 
            onClick={() => setActiveView('audit')}
            style={{ padding: '1rem 2rem', backgroundColor: '#ffffff', color: '#1e293b', border: '1px solid #cbd5e1', borderRadius: '6px', fontSize: '1.1rem', fontWeight: 'bold', cursor: 'pointer' }}
          >
            View Audit Ledger
          </button>
        </div>

      </div>
    </div>
  );
}