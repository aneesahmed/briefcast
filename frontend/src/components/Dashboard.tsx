import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { DashboardData, ProcessedRecord, PublicConfig, RecordSearchFilters } from '../types';
import { api } from '../services/api';

const panel: React.CSSProperties = {
  background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12,
  padding: '1.25rem', boxShadow: '0 1px 3px rgba(15,23,42,.06)',
};
const field: React.CSSProperties = {
  padding: '.65rem .75rem', border: '1px solid #cbd5e1', borderRadius: 7,
  background: '#fff', color: '#0f172a', minWidth: 0,
};
const size = (bytes: number) => bytes < 1048576
  ? `${(bytes / 1024).toFixed(1)} KB`
  : `${(bytes / 1048576).toFixed(1)} MB`;
const date = (value?: string | null) => value
  ? new Date(value.replace(' ', 'T')).toLocaleString()
  : '—';

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [appConfig, setAppConfig] = useState<PublicConfig | null>(null);
  const [records, setRecords] = useState<ProcessedRecord[]>([]);
  const [filters, setFilters] = useState<RecordSearchFilters>({ status: 'completed' });
  const [files, setFiles] = useState<FileList | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const picker = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDashboard(await api.getDashboard());
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dashboard request failed');
    }
  }, []);

  const runSearch = useCallback(async (criteria: RecordSearchFilters) => {
    try {
      setRecords(await api.searchRecords(criteria));
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Search failed');
    }
  }, []);

  useEffect(() => {
    refresh();
    runSearch({ status: 'completed' });
    api.getAppConfig().then(setAppConfig).catch(() => undefined);
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [refresh, runSearch]);

  const upload = async () => {
    if (!files?.length) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.uploadDocs(files);
      setMessage(`${result.message} Automatic processing will begin shortly.`);
      setFiles(null);
      if (picker.current) picker.current.value = '';
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  const counts = [
    ['Processing now', dashboard?.counts.processing ?? 0, '#7c3aed'],
    ['Files in input', dashboard?.counts.input_files ?? 0, '#0369a1'],
    ['Completed', dashboard?.counts.completed ?? 0, '#047857'],
    ['Failed', dashboard?.counts.failed ?? 0, '#b91c1c'],
  ] as const;

  return (
    <main style={{ width: '100%', overflowY: 'auto', padding: '2rem', boxSizing: 'border-box' }}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
          <div>
            <h1 style={{ margin: 0, color: '#0f172a', fontSize: '1.8rem' }}>Briefcast Operations</h1>
            <p style={{ margin: '.35rem 0 0', color: '#64748b' }}>Upload a document. Briefcast summarizes, translates, and creates Urdu audio automatically.</p>
          </div>
          <span style={{ padding: '.45rem .75rem', borderRadius: 999, fontSize: '.8rem', fontWeight: 700, background: dashboard?.scanner.running ? '#dcfce7' : '#fef3c7', color: dashboard?.scanner.running ? '#166534' : '#92400e' }}>
            {dashboard?.scanner.running ? `Scanner active · ${dashboard.scanner.interval_seconds}s` : 'Scanner paused'}
          </span>
        </div>

        {error && <div role="alert" style={{ marginBottom: '1rem', padding: '.8rem 1rem', background: '#fee2e2', color: '#991b1b', borderRadius: 8 }}>{error}</div>}
        {dashboard?.scanner.configuration_error && <div style={{ marginBottom: '1rem', padding: '.8rem 1rem', background: '#fef3c7', color: '#92400e', borderRadius: 8 }}>{dashboard.scanner.configuration_error}</div>}

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          {counts.map(([label, value, color]) => <div key={label} style={panel}>
            <div style={{ color: '#64748b', fontSize: '.75rem', fontWeight: 700, textTransform: 'uppercase' }}>{label}</div>
            <div style={{ color, fontSize: '2rem', fontWeight: 800, marginTop: '.25rem' }}>{value}</div>
          </div>)}
        </section>

        <section style={{ ...panel, marginBottom: '1rem' }}>
          <h2 style={{ margin: '0 0 .35rem', fontSize: '1.1rem', color: '#0f172a' }}>Add documents</h2>
          <div style={{ color: '#64748b', fontSize: '.8rem', marginBottom: '.85rem' }}>Input: {dashboard?.scanner.source_directory || 'briefing_source'}</div>
          <div style={{ display: 'flex', gap: '.75rem', flexWrap: 'wrap' }}>
            <input ref={picker} type="file" multiple accept={appConfig?.supported_extensions.join(',')} onChange={event => setFiles(event.target.files)} style={{ ...field, flex: '1 1 420px' }} />
            <button onClick={upload} disabled={!files?.length || busy} style={{ padding: '.65rem 1.2rem', border: 0, borderRadius: 7, background: busy ? '#94a3b8' : '#2563eb', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>
              {busy ? 'Uploading…' : 'Upload document'}
            </button>
          </div>
          {message && <div style={{ color: '#047857', fontSize: '.85rem', marginTop: '.65rem' }}>{message}</div>}
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <div style={panel}>
            <h2 style={{ margin: '0 0 .75rem', fontSize: '1.05rem', color: '#0f172a' }}>Currently processing</h2>
            {dashboard?.processing.length ? dashboard.processing.map(item => <div key={item.job_id} style={{ padding: '.7rem 0', borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
              <span style={{ color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.filename}</span>
              <strong style={{ color: '#7c3aed', textTransform: 'capitalize' }}>{item.status}</strong>
            </div>) : <div style={{ color: '#94a3b8' }}>No document is processing.</div>}
          </div>
          <div style={panel}>
            <h2 style={{ margin: '0 0 .75rem', fontSize: '1.05rem', color: '#0f172a' }}>Input folder</h2>
            {dashboard?.input_files.length ? dashboard.input_files.slice(0, 8).map(item => <div key={item.filename} style={{ padding: '.7rem 0', borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
              <span style={{ color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.filename}</span>
              <span style={{ color: '#64748b', whiteSpace: 'nowrap' }}>{size(item.size_bytes)} · {item.status}</span>
            </div>) : <div style={{ color: '#94a3b8' }}>No files waiting in the input folder.</div>}
          </div>
        </section>

        <section style={{ ...panel, marginBottom: '1rem' }}>
          <h2 style={{ margin: '0 0 .85rem', fontSize: '1.1rem', color: '#0f172a' }}>Find processed broadcasts</h2>
          <form onSubmit={event => { event.preventDefault(); runSearch(filters); }} style={{ display: 'grid', gridTemplateColumns: 'minmax(170px,1.4fr) minmax(100px,.7fr) repeat(2,minmax(135px,1fr)) minmax(110px,.7fr) auto', gap: '.6rem' }}>
            <input aria-label="Name" placeholder="File or company name" value={filters.name || ''} onChange={e => setFilters({ ...filters, name: e.target.value })} style={field} />
            <input aria-label="Symbol" placeholder="Symbol" value={filters.symbol || ''} onChange={e => setFilters({ ...filters, symbol: e.target.value })} style={field} />
            <input aria-label="From date" type="date" value={filters.date_from || ''} onChange={e => setFilters({ ...filters, date_from: e.target.value })} style={field} />
            <input aria-label="To date" type="date" value={filters.date_to || ''} onChange={e => setFilters({ ...filters, date_to: e.target.value })} style={field} />
            <input aria-label="Last days" type="number" min="1" placeholder="Last N days" value={filters.last_n_days || ''} onChange={e => setFilters({ ...filters, last_n_days: e.target.value ? Number(e.target.value) : undefined })} style={field} />
            <button type="submit" style={{ padding: '.65rem 1rem', border: 0, borderRadius: 7, background: '#0f172a', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>Search</button>
          </form>
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
