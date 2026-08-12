// src/components/Studio.tsx
import React, { useState, useRef, useEffect } from 'react';
import type { GlobalSettings } from '../types';

interface StudioProps {
  API_BASE_URL?: string;
  onProcessingComplete: () => void;
}

export default function Studio({ API_BASE_URL, onProcessingComplete }: StudioProps) {
  const API_URL = API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [studioError, setStudioError] = useState<string | null>(null);

  const [currentFile, setCurrentFile] = useState<string>('');
  const [englishSummary, setEnglishSummary] = useState<string>('');
  const [urduTranslation, setUrduTranslation] = useState<string>('');
  const [audioUrl, setAudioUrl] = useState<string>('');
  const [activeStep, setActiveStep] = useState<string | null>(null);

  // Metrics states for each step
  const [summaryMeta, setSummaryMeta] = useState<any>(null);
  const [translationMeta, setTranslationMeta] = useState<any>(null);
  const [audioMeta, setAudioMeta] = useState<any>(null);

  const [config, setConfig] = useState({
    gender: 'Male',
    speed: '1.0',
    tone: 'Announcement',
    summary_provider: import.meta.env.VITE_DEFAULT_SUMMARY_PROVIDER || 'cloud',
    summary_model: import.meta.env.VITE_DEFAULT_SUMMARY_MODEL || 'gemini-2.5-flash',
    translation_provider: import.meta.env.VITE_DEFAULT_TRANSLATION_PROVIDER || 'cloud',
    translation_model: import.meta.env.VITE_DEFAULT_TRANSLATION_MODEL || 'gemini-2.5-flash',
    audio_provider: import.meta.env.VITE_DEFAULT_AUDIO_PROVIDER || 'cloud',
    audio_model: import.meta.env.VITE_DEFAULT_AUDIO_MODEL || 'gemini-2.5-flash-preview-tts',
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await fetch(`${API_URL}/api/settings`);
        if (response.ok) {
          const settings: GlobalSettings = await response.json();
          setConfig((prev) => ({ ...prev, ...settings }));
        }
      } catch (err) {
        console.error('Failed to load global settings:', err);
      }
    };
    fetchSettings();
  }, [API_URL]);

  const handleFileUpload = async () => {
    if (!selectedFiles || selectedFiles.length === 0) return;
    setIsUploading(true);
    setUploadMessage(null);
    setStudioError(null);

    const formData = new FormData();
    for (let i = 0; i < selectedFiles.length; i++) {
      formData.append('files', selectedFiles[i]);
    }

    try {
      const response = await fetch(`${API_URL}/api/upload-docs`, { method: 'POST', body: formData });
      if (!response.ok) throw new Error(`Upload failed: ${response.statusText}`);
      const data = await response.json();
      setUploadMessage(data.message);
      setSelectedFiles(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      
      setCurrentFile('');
      setEnglishSummary('');
      setUrduTranslation('');
      setAudioUrl('');
      setSummaryMeta(null);
      setTranslationMeta(null);
      setAudioMeta(null);
    } catch (err: any) {
      setStudioError(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleRunSummary = async (force: boolean = false) => {
    setActiveStep('summary');
    setStudioError(null);
    try {
      const res = await fetch(`${API_URL}/api/step/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: currentFile, config, force }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setEnglishSummary(data.english_summary);
      setCurrentFile(data.filename);
      setSummaryMeta(data);
    } catch (err: any) {
      setStudioError(`Summary failed: ${err.message}`);
    } finally {
      setActiveStep(null);
    }
  };

  const handleRunTranslation = async (force: boolean = false) => {
    if (!englishSummary.trim()) {
      setStudioError('Please generate or enter an English summary first.');
      return;
    }
    setActiveStep('translation');
    setStudioError(null);
    try {
      const res = await fetch(`${API_URL}/api/step/translation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: currentFile, english_summary: englishSummary, config, force }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setUrduTranslation(data.urdu_summary);
      setTranslationMeta(data);
    } catch (err: any) {
      setStudioError(`Translation failed: ${err.message}`);
    } finally {
      setActiveStep(null);
    }
  };

  const handleRunAudio = async (force: boolean = false) => {
    if (!urduTranslation.trim()) {
      setStudioError('Please generate or enter Urdu text first.');
      return;
    }
    setActiveStep('audio');
    setStudioError(null);
    try {
      const res = await fetch(`${API_URL}/api/step/audio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: currentFile, urdu_summary: urduTranslation, config, force }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAudioUrl(`${API_URL}${data.download_url}`);
      setAudioMeta(data);
      onProcessingComplete();
    } catch (err: any) {
      setStudioError(`Audio generation failed: ${err.message}`);
    } finally {
      setActiveStep(null);
    }
  };

  const renderEngineSelect = (
    label: string, providerKey: string, modelKey: string, localOptions: string[], cloudOptions: string[]
  ) => {
    const isCloud = (config as any)[providerKey] === 'cloud';
    const activeOptions = isCloud ? cloudOptions : localOptions;

    return (
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <select 
          value={(config as any)[providerKey]} 
          onChange={(e) => {
            const isLocal = e.target.value === 'local';
            setConfig({ ...config, [providerKey]: e.target.value, [modelKey]: isLocal ? localOptions[0] : cloudOptions[0] });
          }}
          style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', flex: 1, backgroundColor: '#ffffff', color: '#1e293b' }}
        >
          <option value="cloud">Cloud API</option>
          <option value="local">Local Air-Gapped</option>
        </select>
        <select 
          value={(config as any)[modelKey]} 
          onChange={(e) => setConfig({ ...config, [modelKey]: e.target.value })}
          style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', flex: 1, backgroundColor: '#ffffff', color: '#1e293b' }}
        >
          {activeOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      </div>
    );
  };

  const renderMetricsBox = (meta: any) => {
    if (!meta) return null;
    const usage = meta.metrics?.usage || meta.metrics || {};
    const costEst = meta.cost?.pricing_estimation || {};
    return (
      <div style={{ marginTop: '0.75rem', padding: '0.75rem', backgroundColor: '#f1f5f9', borderRadius: '6px', fontSize: '0.85rem', color: '#334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span><strong>Tokens:</strong> Input: {usage.input_tokens || 0} | Output: {usage.output_tokens || 0} | Total: {usage.total_tokens || 0}</span>
        </div>
        <div>
          <span style={{ color: '#059669', fontWeight: 'bold' }}>Cost: {costEst.total_cost_usd || '$0.000000'} ({costEst.total_cost_pkr || 'Rs. 0.0000'})</span>
        </div>
      </div>
    );
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1100px', margin: '0 auto', width: '100%', height: '100vh', overflowY: 'auto', boxSizing: 'border-box', paddingBottom: '6rem' }}>
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', padding: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem' }}>
        <h3 style={{ margin: '0 0 1rem 0', color: '#1f2937' }}>1. Document Staging</h3>
        <div style={{ display: 'flex', gap: '0.5rem', maxWidth: '600px' }}>
          <input
            type="file" multiple ref={fileInputRef}
            onChange={(e) => setSelectedFiles(e.target.files)}
            disabled={isUploading || activeStep !== null}
            style={{ padding: '0.5rem', border: '1px dashed #cbd5e1', borderRadius: '6px', flex: 1 }}
          />
          <button
            onClick={handleFileUpload}
            disabled={!selectedFiles || isUploading || activeStep !== null}
            style={{ padding: '0.5rem 1.5rem', backgroundColor: '#10b981', color: '#ffffff', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
          >
            {isUploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
        {uploadMessage && <div style={{ color: '#059669', marginTop: '0.5rem', fontSize: '0.9rem' }}>✓ {uploadMessage}</div>}
      </div>

      {studioError && (
        <div style={{ padding: '1rem', backgroundColor: '#fee2e2', color: '#b91c1c', borderRadius: '6px', marginBottom: '1.5rem' }}>
          <strong>Error:</strong> {studioError}
        </div>
      )}

      {/* Step 1: Summarization */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', padding: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, color: '#1f2937' }}>Step 1: Summarization {currentFile && <span style={{ fontSize: '0.9rem', color: '#64748b' }}>({currentFile})</span>}</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => handleRunSummary(true)} disabled={activeStep !== null} style={{ padding: '0.5rem 1rem', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>Force Regenerate</button>
            <button onClick={() => handleRunSummary(false)} disabled={activeStep !== null} style={{ padding: '0.5rem 1rem', backgroundColor: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}>{activeStep === 'summary' ? 'Summarizing...' : '▶ Run Step 1'}</button>
          </div>
        </div>
        {renderEngineSelect('Summary Engine', 'summary_provider', 'summary_model', ['llama3', 'llama3.1', 'qwen2.5'], ['gemini-2.5-flash'])}
        <textarea
          rows={4}
          value={englishSummary}
          onChange={(e) => setEnglishSummary(e.target.value)}
          placeholder="Summary output will appear here..."
          style={{ width: '100%', padding: '0.75rem', borderRadius: '6px', border: '1px solid #cbd5e1', boxSizing: 'border-box' }}
        />
        {renderMetricsBox(summaryMeta)}
      </div>

      {/* Step 2: Translation */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', padding: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, color: '#1f2937' }}>Step 2: Urdu Translation</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => handleRunTranslation(true)} disabled={activeStep !== null || !englishSummary.trim()} style={{ padding: '0.5rem 1rem', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>Force Regenerate</button>
            <button onClick={() => handleRunTranslation(false)} disabled={activeStep !== null || !englishSummary.trim()} style={{ padding: '0.5rem 1rem', backgroundColor: (!englishSummary.trim() || activeStep !== null) ? '#94a3b8' : '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}>{activeStep === 'translation' ? 'Translating...' : '▶ Run Step 2'}</button>
          </div>
        </div>
        {renderEngineSelect('Translation Engine', 'translation_provider', 'translation_model', ['llama3', 'qwen2.5', 'aya'], ['gemini-2.5-flash'])}
        <textarea
          rows={4}
          value={urduTranslation}
          onChange={(e) => setUrduTranslation(e.target.value)}
          placeholder="Urdu translation will appear here..."
          style={{ width: '100%', padding: '0.75rem', borderRadius: '6px', border: '1px solid #cbd5e1', boxSizing: 'border-box', direction: 'rtl', textAlign: 'right', fontFamily: '"Noto Nastaliq Urdu", serif', fontSize: '1.2rem' }}
        />
        {renderMetricsBox(translationMeta)}
      </div>

      {/* Step 3: Audio Generation */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', padding: '1.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, color: '#1f2937' }}>Step 3: Audio Generation</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => handleRunAudio(true)} disabled={activeStep !== null || !urduTranslation.trim()} style={{ padding: '0.5rem 1rem', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>Force Regenerate</button>
            <button onClick={() => handleRunAudio(false)} disabled={activeStep !== null || !urduTranslation.trim()} style={{ padding: '0.5rem 1rem', backgroundColor: (!urduTranslation.trim() || activeStep !== null) ? '#94a3b8' : '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}>{activeStep === 'audio' ? 'Synthesizing...' : '▶ Run Step 3'}</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#64748b', display: 'block', marginBottom: '0.25rem' }}>Voice Gender</label>
            <select value={config.gender} onChange={(e) => setConfig({ ...config, gender: e.target.value })} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#64748b', display: 'block', marginBottom: '0.25rem' }}>Speech Tone</label>
            <select value={config.tone} onChange={(e) => setConfig({ ...config, tone: e.target.value })} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}>
              <option value="Announcement">Announcement</option>
              <option value="Neutral">Neutral</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#64748b', display: 'block', marginBottom: '0.25rem' }}>Speed Scale</label>
            <select value={config.speed} onChange={(e) => setConfig({ ...config, speed: e.target.value })} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}>
              <option value="0.9">0.9x (Slower)</option>
              <option value="1.0">1.0x (Normal)</option>
              <option value="1.3">1.3x (Faster)</option>
            </select>
          </div>
        </div>

        {renderEngineSelect('Audio Engine', 'audio_provider', 'audio_model', ['facebook/mms-tts-urd-script_arabic'], ['gemini-2.5-flash-preview-tts'])}
        
        {renderMetricsBox(audioMeta)}

        {audioUrl && (
          <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', color: '#4b5563' }}>🎙️ Output Speech</h4>
            <audio controls src={audioUrl} style={{ width: '100%' }} />
          </div>
        )}
      </div>
    </div>
  );
}
