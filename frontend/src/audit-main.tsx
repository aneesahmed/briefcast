import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

interface AuditRecord {
  filename: string;
  company: string;
  completedAt: string;
  sizeMb: number;
  tokens: number;
  costUsd: number;
}

interface AuditStats {
  totalTokens: number;
  totalCostUsd: number;
  records: AuditRecord[];
}

function AuditDashboard() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/audit-stats')
      .then(r => {
        if (!r.ok) throw new Error('Failed to fetch stats');
        return r.json();
      })
      .then(data => {
        // Sort records by completedAt descending
        data.records.sort((a, b) => new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime());
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div style={{ padding: '2rem' }}>Loading audit stats...</div>;
  if (error) return <div style={{ padding: '2rem', color: 'red' }}>Error: {error}</div>;
  if (!stats) return null;

  return (
    <div>
      <header style={{ background: '#0f172a', color: '#fff', padding: '1rem 2rem', fontWeight: 800 }}>
        🎙️ Briefcast Audit Dashboard
      </header>
      
      <main style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
          <div style={{ background: '#fff', padding: '1.5rem', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '0.875rem', color: '#64748b', fontWeight: 600 }}>Files Processed</div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#0f172a', marginTop: '0.5rem' }}>{stats.records.length}</div>
          </div>
          
          <div style={{ background: '#fff', padding: '1.5rem', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '0.875rem', color: '#64748b', fontWeight: 600 }}>Est. Tokens Consumed</div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#0f172a', marginTop: '0.5rem' }}>{stats.totalTokens.toLocaleString()}</div>
          </div>
          
          <div style={{ background: '#fff', padding: '1.5rem', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ fontSize: '0.875rem', color: '#64748b', fontWeight: 600 }}>Total Est. Cost</div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#0f172a', marginTop: '0.5rem' }}>${stats.totalCostUsd.toFixed(4)}</div>
          </div>
        </div>

        <div style={{ background: '#fff', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead style={{ background: '#f1f5f9', borderBottom: '2px solid #e2e8f0' }}>
              <tr>
                <th style={{ padding: '1rem', fontWeight: 600 }}>Filename</th>
                <th style={{ padding: '1rem', fontWeight: 600 }}>Company</th>
                <th style={{ padding: '1rem', fontWeight: 600 }}>Completed</th>
                <th style={{ padding: '1rem', fontWeight: 600 }}>Size (MB)</th>
                <th style={{ padding: '1rem', fontWeight: 600 }}>Est. Tokens</th>
                <th style={{ padding: '1rem', fontWeight: 600 }}>Est. Cost</th>
              </tr>
            </thead>
            <tbody>
              {stats.records.map((r, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #e2e8f0' }}>
                  <td style={{ padding: '1rem' }}>{r.filename}</td>
                  <td style={{ padding: '1rem' }}>{r.company}</td>
                  <td style={{ padding: '1rem' }}>{new Date(r.completedAt).toLocaleString()}</td>
                  <td style={{ padding: '1rem' }}>{r.sizeMb.toFixed(2)}</td>
                  <td style={{ padding: '1rem' }}>{r.tokens.toLocaleString()}</td>
                  <td style={{ padding: '1rem' }}>${r.costUsd.toFixed(4)}</td>
                </tr>
              ))}
              {stats.records.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
                    No processed files found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

const root = createRoot(document.getElementById('root')!);
root.render(<AuditDashboard />);
