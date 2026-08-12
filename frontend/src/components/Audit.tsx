// src/components/Audit.tsx
import React, { useState } from 'react';
import type { ProcessResult } from '../types';

interface AuditProps {
  history: ProcessResult[];
  API_BASE_URL?: string;
}

export default function Audit({ history, API_BASE_URL }: AuditProps) {
  const [selectedAuditDoc, setSelectedAuditDoc] = useState<ProcessResult | null>(null);

  const API_URL = API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  return (
    <div style={{ display: 'flex', height: '100%', width: '100%' }}>
      {/* Sidebar List */}
      <div style={{ width: '350px', backgroundColor: '#ffffff', borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '1.5rem', borderBottom: '1px solid #e5e7eb', backgroundColor: '#f8fafc' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', color: '#1f2937' }}>Transaction Ledger</h2>
          <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.25rem' }}>{history.length} records found</div>
        </div>

        <div style={{ overflowY: 'auto', flex: 1, padding: '1rem' }}>
          {history.map((doc, idx) => (
            <div
              key={doc.id || idx}
              onClick={() => setSelectedAuditDoc(doc)}
              style={{
                padding: '1rem',
                marginBottom: '0.5rem',
                borderRadius: '8px',
                cursor: 'pointer',
                backgroundColor: selectedAuditDoc?.id === doc.id ? '#eff6ff' : '#ffffff',
                border: selectedAuditDoc?.id === doc.id ? '1px solid #bfdbfe' : '1px solid #f1f5f9',
              }}
            >
              <div style={{ fontWeight: '600', fontSize: '0.9rem', wordBreak: 'break-word', color: selectedAuditDoc?.id === doc.id ? '#1e40af' : '#334155' }}>
                {doc.filename}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.35rem' }}>{doc.timestamp}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Detail Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '2rem' }}>
        {selectedAuditDoc ? (
          <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', padding: '2.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ borderBottom: '1px solid #e5e7eb', paddingBottom: '2rem', marginBottom: '2rem' }}>
              <h1 style={{ marginTop: 0, color: '#0f172a', fontSize: '1.5rem' }}>{selectedAuditDoc.filename}</h1>

              {selectedAuditDoc.telemetry && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginTop: '1.5rem' }}>
                  <div style={{ padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Engine Provider</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 'bold', color: '#0f172a', textTransform: 'capitalize' }}>
                      {selectedAuditDoc.telemetry.provider || 'cloud'}
                    </div>
                  </div>
                  <div style={{ padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Text Model</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 'bold', color: '#0f172a' }}>
                      {selectedAuditDoc.telemetry.text_model || selectedAuditDoc.cost_metrics?.pricing_estimation?.model_name || 'N/A'}
                    </div>
                  </div>
                  <div style={{ padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Summary Tokens</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#0f172a' }}>{selectedAuditDoc.telemetry.summary_phase?.total_tokens || 0}</div>
                  </div>
                  <div style={{ padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>Translation Tokens</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#0f172a' }}>{selectedAuditDoc.telemetry.translation_phase?.total_tokens || 0}</div>
                  </div>
                  <div style={{ padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 'bold' }}>TTS Characters</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#0f172a' }}>{selectedAuditDoc.telemetry.tts_characters || 0}</div>
                  </div>
                  <div style={{ padding: '1rem', backgroundColor: '#f0fdf4', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#166534', textTransform: 'uppercase', fontWeight: 'bold' }}>Est. Cost (PKR)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#15803d' }}>
                      {selectedAuditDoc.cost_metrics?.pricing_estimation?.total_cost_pkr || 'Rs. 0.00'}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              <div>
                <h3 style={{ color: '#4b5563', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.75rem' }}>🎙️ Processed Audio</h3>
                <audio controls src={`${API_URL}${selectedAuditDoc.download_url}`} style={{ width: '100%', height: '40px' }} />
              </div>
              <div>
                <h3 style={{ color: '#4b5563', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.75rem' }}>Urdu Translation</h3>
                <div
                  style={{
                    fontFamily: '"Noto Nastaliq Urdu", serif',
                    lineHeight: '2.5',
                    fontSize: '1.35rem',
                    direction: 'rtl',
                    textAlign: 'right',
                    backgroundColor: '#f8fafc',
                    padding: '1.5rem',
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  {selectedAuditDoc.urdu_summary}
                </div>
              </div>
              <div>
                <h3 style={{ color: '#4b5563', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.75rem' }}>English Summary</h3>
                <p style={{ lineHeight: '1.6', backgroundColor: '#f8fafc', padding: '1.5rem', borderRadius: '8px', border: '1px solid #e2e8f0', margin: 0 }}>
                  {selectedAuditDoc.english_summary}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>
            Select a document from the transaction ledger to view its audit trail.
          </div>
        )}
      </div>
    </div>
  );
}