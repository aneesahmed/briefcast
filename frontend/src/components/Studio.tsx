// src/components/Studio.tsx
import React, { useState, useRef, useEffect } from 'react';
import type { PublicConfig, ScannerStatus, SourceInventory } from '../types';
import { api } from '../services/api';

interface StudioProps {
  onProcessingComplete: () => void;
}

export default function Studio({ onProcessingComplete }: StudioProps) {
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [studioError, setStudioError] = useState<string | null>(null);
  const [sourceInventory, setSourceInventory] = useState<SourceInventory | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [scannerStatus, setScannerStatus] = useState<ScannerStatus | null>(null);
  const [isChangingScanner, setIsChangingScanner] = useState(false);

  const [currentFile, setCurrentFile] = useState<string>('');
  const [englishSummary, setEnglishSummary] = useState<string>('');
  const [urduTranslation, setUrduTranslation] = useState<string>('');
  const [audioUrl, setAudioUrl] = useState<string>('');
  const [activeStep, setActiveStep] = useState<string | null>(null);

  // Metrics states for each step
  const [summaryMeta, setSummaryMeta] = useState<any>(null);
  const [translationMeta, setTranslationMeta] = useState<any>(null);
  const [audioMeta, setAudioMeta] = useState<any>(null);

  const [appConfig, setAppConfig] = useState<PublicConfig | null>(null);
  const [config, setConfig] = useState<Record<string, string | number>>({});

  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshSourceFiles = async () => {
    try {
      setSourceInventory(await api.getSourceFiles());
    } catch (err: any) {
      setStudioError(`Could not read briefing_source: ${err.message}`);
    }
  };

  const refreshScannerStatus = async () => {
    try {
      setScannerStatus(await api.getScannerStatus());
    } catch (err: any) {
      setStudioError(`Could not read scanner status: ${err.message}`);
    }
  };

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const [applicationConfig, settings] = await Promise.all([
          api.getAppConfig(),
          api.getSettings(),
        ]);
        setAppConfig(applicationConfig);
        setConfig({ ...applicationConfig.pipeline_defaults, ...settings });
      } catch (err) {
        setStudioError(`Failed to load application configuration: ${err}`);
      }
    };
    fetchSettings();
    refreshSourceFiles();
    refreshScannerStatus();
    const statusTimer = window.setInterval(() => {
      refreshScannerStatus();
      refreshSourceFiles();
    }, 3000);
    return () => window.clearInterval(statusTimer);
  }, []);

  const handleScannerToggle = async () => {
    setIsChangingScanner(true);
    setStudioError(null);
    try {
      const status = scannerStatus?.running
        ? await api.stopScanner()
        : await api.startScanner(config);
      setScannerStatus(status);
      setUploadMessage(status.running
        ? 'Automatic scanner started. Stable files will be processed one at a time.'
        : 'Automatic scanner stopped. Active processing is allowed to finish.');
      await refreshSourceFiles();
    } catch (err: any) {
      setStudioError(`Could not change scanner state: ${err.message}`);
    } finally {
      setIsChangingScanner(false);
    }
  };

  const handleScan = async () => {
    setIsScanning(true);
    setStudioError(null);
    try {
      const result = await api.scanSourceFolder();
      setUploadMessage(result.message);
      await refreshSourceFiles();
    } catch (err: any) {
      setStudioError(`Folder scan failed: ${err.message}`);
    } finally {
      setIsScanning(false);
    }
  };

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
      const data = await api.uploadDocs(selectedFiles);
      setUploadMessage(data.message);
      if (data.filenames.length > 0) setCurrentFile(data.filenames[0]);
      setSelectedFiles(null);
      if (fileInputRef.current) fileInputRef.current.value = '';

      setEnglishSummary('');
      setUrduTranslation('');
      setAudioUrl('');
      setSummaryMeta(null);
      setTranslationMeta(null);
      setAudioMeta(null);
      await refreshSourceFiles();
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
      const data = await api.runSummary(currentFile, config, force);
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
      const data = await api.runTranslation(currentFile, englishSummary, config, force);
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
      const data = await api.runAudio(currentFile, urduTranslation, config, force);
      setAudioUrl(api.getAudioUrl(data.download_url));
      setAudioMeta(data);
      onProcessingComplete();
    } catch (err: any) {
      setStudioError(`Audio generation failed: ${err.message}`);
    } finally {
      setActiveStep(null);
    }
  };

  const renderModelSelect = (
    label: string,
    stage: keyof PublicConfig['model_options'],
    modelKey: 'summary_model' | 'translation_model' | 'audio_model',
  ) => {
    const options = appConfig?.model_options[stage] || [];
    return (
      <div style={{ marginBottom: '0.75rem', textAlign: 'left' }}>
        <label style={{ display: 'block', marginBottom: '0.25rem', color: '#64748b', fontSize: '0.75rem', fontWeight: 'bold' }}>{label}</label>
        <select 
          value={String(config[modelKey] || '')}
          onChange={(e) => setConfig({ ...config, [modelKey]: e.target.value })}
          disabled={!options.length}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}
        >
          {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <h3 style={{ margin: 0, color: '#1f2937' }}>Document Intake</h3>
              <span style={{ padding: '0.15rem 0.5rem', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 'bold', backgroundColor: scannerStatus?.running ? '#d1fae5' : '#e2e8f0', color: scannerStatus?.running ? '#047857' : '#475569' }}>
                {scannerStatus?.running ? '● Automatic scanner running' : '○ Automatic scanner stopped'}
              </span>
            </div>
            <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.25rem', textAlign: 'left' }}>
              Watching: {sourceInventory?.source_directory || 'briefing_source'}
            </div>
            {!!scannerStatus?.active_files.length && (
              <div style={{ color: '#7c3aed', fontSize: '0.75rem', marginTop: '0.25rem', textAlign: 'left' }}>
                Processing: {scannerStatus.active_files.join(', ')}
              </div>
            )}
            {scannerStatus && !scannerStatus.configuration_ready && (
              <div style={{ color: '#b45309', fontSize: '0.75rem', marginTop: '0.25rem', textAlign: 'left' }}>
                Scanner unavailable: {scannerStatus.configuration_error}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={handleScan}
              disabled={isScanning || activeStep !== null}
              style={{ padding: '0.5rem 1rem', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
            >
              {isScanning ? 'Scanning…' : '↻ Scan Folder'}
            </button>
            <button
              onClick={handleScannerToggle}
              disabled={isChangingScanner || activeStep !== null || (!scannerStatus?.running && scannerStatus?.configuration_ready === false)}
              style={{ padding: '0.5rem 1rem', backgroundColor: scannerStatus?.running ? '#fee2e2' : '#0f766e', color: scannerStatus?.running ? '#b91c1c' : '#fff', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
            >
              {isChangingScanner ? 'Please wait…' : scannerStatus?.running ? 'Stop Scanner' : 'Start Scanner'}
            </button>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', maxWidth: '760px' }}>
          <input
            type="file" multiple accept={appConfig?.supported_extensions.join(',')} ref={fileInputRef}
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

        <div style={{ marginTop: '1.25rem', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) 120px 150px 110px', gap: '0.75rem', padding: '0.65rem 0.8rem', backgroundColor: '#f8fafc', color: '#64748b', fontSize: '0.75rem', fontWeight: 'bold', textAlign: 'left' }}>
            <span>Source file</span><span>Size</span><span>Status</span><span>Action</span>
          </div>
          {sourceInventory?.files.length ? sourceInventory.files.map((file) => (
            <div key={file.filename} style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) 120px 150px 110px', gap: '0.75rem', alignItems: 'center', padding: '0.7rem 0.8rem', borderTop: '1px solid #e2e8f0', textAlign: 'left', fontSize: '0.85rem', backgroundColor: currentFile === file.filename ? '#eff6ff' : '#fff' }}>
              <span style={{ color: '#1e293b', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>{file.filename}</span>
              <span style={{ color: '#64748b' }}>{(file.size_bytes / 1024).toFixed(1)} KB</span>
              <span style={{ color: file.status === 'ready' ? '#0369a1' : '#047857', textTransform: 'capitalize' }}>{file.status}</span>
              <button
                onClick={() => {
                  setCurrentFile(file.filename);
                  setEnglishSummary('');
                  setUrduTranslation('');
                  setAudioUrl('');
                }}
                style={{ padding: '0.4rem 0.65rem', border: '1px solid #93c5fd', borderRadius: '5px', backgroundColor: currentFile === file.filename ? '#2563eb' : '#fff', color: currentFile === file.filename ? '#fff' : '#1d4ed8', cursor: 'pointer' }}
              >
                {currentFile === file.filename ? 'Selected' : 'Select'}
              </button>
            </div>
          )) : (
            <div style={{ padding: '1rem', color: '#64748b', fontSize: '0.85rem' }}>No supported documents found.</div>
          )}
        </div>
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
        {renderModelSelect('Online summary model', 'summary', 'summary_model')}
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
        {renderModelSelect('Online translation model', 'translation', 'translation_model')}
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
            <select value={String(config.gender || '')} onChange={(e) => setConfig({ ...config, gender: e.target.value })} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}>
              {appConfig?.voice_options.genders.map(value => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#64748b', display: 'block', marginBottom: '0.25rem' }}>Speech Tone</label>
            <select value={String(config.tone || '')} onChange={(e) => setConfig({ ...config, tone: e.target.value })} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}>
              {appConfig?.voice_options.tones.map(value => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#64748b', display: 'block', marginBottom: '0.25rem' }}>Speed Scale</label>
            <select value={String(config.speed || '')} onChange={(e) => setConfig({ ...config, speed: e.target.value })} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#1e293b' }}>
              {appConfig?.voice_options.speeds.map(value => <option key={value} value={value}>{value}x</option>)}
            </select>
          </div>
        </div>

        {renderModelSelect('Online audio model', 'audio', 'audio_model')}
        
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
