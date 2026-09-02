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
  const [logs, setLogs] = useState<string[]>([]);
  const [files, setFiles] = useState<FileList | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const picker = useRef<HTMLInputElement>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [dashData, logsData] = await Promise.all([
        api.getDashboard(),
        api.getLogs(100)
      ]);
      setDashboard(dashData);
      setLogs(logsData);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dashboard request failed');
    }
  }, []);

  // Auto-scroll logs to bottom when they update
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    refresh();
    api.getAppConfig().then(setAppConfig).catch(() => undefined);
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

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
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <button onClick={refresh} style={{ padding: '.45rem .75rem', borderRadius: 999, border: '1px solid #cbd5e1', background: '#fff', color: '#0f172a', fontSize: '.8rem', fontWeight: 600, cursor: 'pointer' }}>
              ↻ Refresh
            </button>
            <span style={{ padding: '.45rem .75rem', borderRadius: 999, fontSize: '.8rem', fontWeight: 700, background: dashboard?.scanner.running ? '#dcfce7' : '#fef3c7', color: dashboard?.scanner.running ? '#166534' : '#92400e' }}>
              {dashboard?.scanner.running ? `Scanner active · ${dashboard.scanner.interval_seconds}s` : 'Scanner paused'}
            </span>
          </div>
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
              <span style={{ color: '#64748b', whiteSpace: 'nowrap' }}>{size(item.size_bytes)}</span>
            </div>) : <div style={{ color: '#94a3b8' }}>No files waiting in the input folder.</div>}
          </div>
          <div style={panel}>
            <h2 style={{ margin: '0 0 .75rem', fontSize: '1.05rem', color: '#0f172a' }}>Processed folder</h2>
            {dashboard?.processed_files.length ? dashboard.processed_files.slice(0, 8).map(item => <div key={item.filename} style={{ padding: '.7rem 0', borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
              <span style={{ color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.filename}</span>
              <span style={{ color: '#64748b', whiteSpace: 'nowrap' }}>{date(item.modified_at)}</span>
            </div>) : <div style={{ color: '#94a3b8' }}>No processed files.</div>}
          </div>
          <div style={panel}>
            <h2 style={{ margin: '0 0 .75rem', fontSize: '1.05rem', color: '#0f172a' }}>Failed folder</h2>
            {dashboard?.failed_files.length ? dashboard.failed_files.slice(0, 8).map(item => <div key={item.filename} style={{ padding: '.7rem 0', borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
              <span style={{ color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.filename}</span>
              <span style={{ color: '#64748b', whiteSpace: 'nowrap' }}>{date(item.modified_at)}</span>
            </div>) : <div style={{ color: '#94a3b8' }}>No failed files.</div>}
          </div>
        </section>

        <section style={{ ...panel, marginBottom: '2rem' }}>
          <h2 style={{ margin: '0 0 .75rem', fontSize: '1.05rem', color: '#0f172a' }}>Server Logs</h2>
          <div 
            ref={logContainerRef}
            style={{ 
              background: '#1e293b', 
              color: '#e2e8f0', 
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', 
              fontSize: '.85rem', 
              lineHeight: 1.5, 
              padding: '1rem', 
              borderRadius: 8,
              height: 300,
              overflowY: 'auto'
            }}
          >
            {logs.length ? (
              logs.map((line, i) => (
                <div key={i} style={{ wordBreak: 'break-all' }}>{line}</div>
              ))
            ) : (
              <div style={{ color: '#94a3b8' }}>No logs available yet...</div>
            )}
          </div>
        </section>

      </div>
    </main>
  );
}
