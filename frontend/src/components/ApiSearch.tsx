import React, { useCallback, useEffect, useState } from 'react';
import type { ProcessedRecord, RecordSearchFilters } from '../types';
import { api } from '../services/api';

const panel: React.CSSProperties = {
  background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12,
  padding: '1.25rem', boxShadow: '0 1px 3px rgba(15,23,42,.06)',
};
const field: React.CSSProperties = {
  padding: '.65rem .75rem', border: '1px solid #cbd5e1', borderRadius: 7,
  background: '#fff', color: '#0f172a', minWidth: 0,
};
const date = (value?: string | null) => value
  ? new Date(value.replace(' ', 'T')).toLocaleString()
  : '—';

export default function ApiSearch() {
  const [records, setRecords] = useState<ProcessedRecord[]>([]);
  const [filters, setFilters] = useState<RecordSearchFilters>({ status: 'completed' });
  const [error, setError] = useState('');
  const [endpointUrl, setEndpointUrl] = useState('');

  const runSearch = useCallback(async (criteria: RecordSearchFilters) => {
    try {
      const query = new URLSearchParams();
      Object.entries(criteria).forEach(([key, value]) => {
        if (value !== undefined && value !== '') query.set(key, String(value));
      });
      
      const fullUrl = `${window.location.origin}/api/records?${query.toString()}`;
      setEndpointUrl(fullUrl);

      setRecords(await api.searchRecords(criteria));
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Search failed');
    }
  }, []);

  useEffect(() => {
    runSearch({ status: 'completed' });
  }, [runSearch]);

  const handleCopy = () => {
    navigator.clipboard.writeText(endpointUrl);
    alert('Endpoint URL copied to clipboard!');
  };

  return (
    <main style={{ width: '100%', overflowY: 'auto', padding: '2rem', boxSizing: 'border-box' }}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ marginBottom: '1.5rem' }}>
          <h1 style={{ margin: 0, color: '#0f172a', fontSize: '1.8rem' }}>API & Search</h1>
          <p style={{ margin: '.35rem 0 0', color: '#64748b' }}>Search processed records and generate API endpoints for your own applications.</p>
        </div>

        {error && <div role="alert" style={{ marginBottom: '1rem', padding: '.8rem 1rem', background: '#fee2e2', color: '#991b1b', borderRadius: 8 }}>{error}</div>}

        <section style={{ ...panel, marginBottom: '1.5rem' }}>
          <h2 style={{ margin: '0 0 .85rem', fontSize: '1.1rem', color: '#0f172a' }}>Filter Records</h2>
          <form onSubmit={event => { event.preventDefault(); runSearch(filters); }} style={{ display: 'grid', gridTemplateColumns: 'minmax(170px,1.4fr) minmax(100px,.7fr) repeat(2,minmax(135px,1fr)) minmax(110px,.7fr) auto', gap: '.6rem' }}>
            <input aria-label="Name" placeholder="File or company name" value={filters.name || ''} onChange={e => setFilters({ ...filters, name: e.target.value })} style={field} />
            <input aria-label="Symbol" placeholder="Symbol" value={filters.symbol || ''} onChange={e => setFilters({ ...filters, symbol: e.target.value })} style={field} />
            <input aria-label="From date" type="date" value={filters.date_from || ''} onChange={e => setFilters({ ...filters, date_from: e.target.value })} style={field} />
            <input aria-label="To date" type="date" value={filters.date_to || ''} onChange={e => setFilters({ ...filters, date_to: e.target.value })} style={field} />
            <input aria-label="Last days" type="number" min="1" placeholder="Last N days" value={filters.last_n_days || ''} onChange={e => setFilters({ ...filters, last_n_days: e.target.value ? Number(e.target.value) : undefined })} style={field} />
            <button type="submit" style={{ padding: '.65rem 1rem', border: 0, borderRadius: 7, background: '#0f172a', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>Search</button>
          </form>

          <div style={{ marginTop: '1.25rem', padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '.85rem', fontWeight: 600, color: '#475569', marginBottom: '.5rem' }}>Generated API Endpoint</div>
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <input readOnly value={endpointUrl} style={{ ...field, flex: 1, fontFamily: 'monospace', fontSize: '.85rem', background: '#fff' }} onClick={e => e.currentTarget.select()} />
              <button type="button" onClick={handleCopy} style={{ padding: '0 1rem', border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff', color: '#334155', fontWeight: 600, cursor: 'pointer' }}>Copy URL</button>
            </div>
            <div style={{ fontSize: '.8rem', color: '#64748b', marginTop: '.5rem' }}>You can use this exact GET request in your own application to fetch these records as JSON.</div>
          </div>
        </section>

        <section style={{ display: 'grid', gap: '1rem' }}>
          {records.length ? records.map(record => <article key={record.job_id} style={panel}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', marginBottom: '.8rem' }}>
              <div><h3 style={{ margin: 0, color: '#0f172a' }}>{record.filename}</h3><div style={{ marginTop: '.25rem', color: '#64748b', fontSize: '.8rem' }}>{[record.company_name, record.symbol, date(record.completed_at)].filter(Boolean).join(' · ')}</div></div>
              <span style={{ color: record.status === 'completed' ? '#047857' : '#b91c1c', fontWeight: 700, textTransform: 'capitalize' }}>{record.status}</span>
            </div>
            {record.summary && <div style={{ marginBottom: '.8rem' }}><strong style={{ color: '#475569' }}>Summary</strong><p style={{ color: '#334155', lineHeight: 1.55, margin: '.3rem 0 0' }}>{record.summary}</p></div>}
            {record.translation && <div style={{ marginBottom: '.8rem' }}><strong style={{ color: '#475569' }}>Urdu translation</strong><p dir="rtl" style={{ color: '#334155', lineHeight: 2, fontSize: '1.15rem', margin: '.3rem 0 0', textAlign: 'right' }}>{record.translation}</p></div>}
            {record.audio_url && <audio controls preload="none" src={api.getAudioUrl(record.audio_url)} style={{ width: '100%' }} />}
            {record.error && <div style={{ color: '#b91c1c' }}>{record.error}</div>}
          </article>) : <div style={{ ...panel, color: '#94a3b8', textAlign: 'center' }}>No processed records match the search.</div>}
        </section>
      </div>
    </main>
  );
}
