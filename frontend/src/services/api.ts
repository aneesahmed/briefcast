import type { DashboardData, GlobalSettings, ProcessedRecord, ProcessResult, PublicConfig, RecordSearchFilters, ScannerStatus, SourceInventory } from '../types';

// FastAPI serves this compiled UI, so all API and audio requests use the same origin.
const API_BASE_URL = '';

export const api = {
  getAppConfig: async (): Promise<PublicConfig> => {
    const res = await fetch(`${API_BASE_URL}/api/config`);
    if (!res.ok) throw new Error('Failed to load application configuration');
    return res.json();
  },

  getHistory: async (): Promise<ProcessResult[]> => {
    const res = await fetch(`${API_BASE_URL}/api/history`);
    if (!res.ok) throw new Error('Failed to fetch history');
    const data = await res.json();
    return data.history || [];
  },

  getDashboard: async (): Promise<DashboardData> => {
    const res = await fetch(`${API_BASE_URL}/api/dashboard`);
    if (!res.ok) throw new Error('Failed to load dashboard');
    return res.json();
  },

  getLogs: async (lines: number = 100): Promise<string[]> => {
    const res = await fetch(`${API_BASE_URL}/api/logs?lines=${lines}`);
    if (!res.ok) throw new Error('Failed to load logs');
    const data = await res.json();
    return data.logs || [];
  },

  searchRecords: async (filters: RecordSearchFilters = {}): Promise<ProcessedRecord[]> => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value));
    });
    const res = await fetch(`${API_BASE_URL}/api/records?${query.toString()}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    return data.records || [];
  },

  getSettings: async (): Promise<GlobalSettings> => {
    const res = await fetch(`${API_BASE_URL}/api/settings`);
    if (!res.ok) throw new Error('Failed to load global settings');
    return res.json();
  },

  uploadDocs: async (files: FileList): Promise<{ message: string; filenames: string[] }> => {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    const res = await fetch(`${API_BASE_URL}/api/upload-docs`, { method: 'POST', body: formData });
    if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
    return res.json();
  },

  getSourceFiles: async (): Promise<SourceInventory> => {
    const res = await fetch(`${API_BASE_URL}/api/source-files`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  scanSourceFolder: async (): Promise<{ message: string; files: SourceInventory['files'] }> => {
    const res = await fetch(`${API_BASE_URL}/api/scanner/scan`, { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  getScannerStatus: async (): Promise<ScannerStatus> => {
    const res = await fetch(`${API_BASE_URL}/api/scanner/status`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  startScanner: async (config: any): Promise<ScannerStatus> => {
    const res = await fetch(`${API_BASE_URL}/api/scanner/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  stopScanner: async (): Promise<ScannerStatus> => {
    const res = await fetch(`${API_BASE_URL}/api/scanner/stop`, { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  runSummary: async (filename: string, config: any, force: boolean = false) => {
    const res = await fetch(`${API_BASE_URL}/api/step/summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, config, force }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  runTranslation: async (filename: string, englishSummary: string, config: any, force: boolean = false) => {
    const res = await fetch(`${API_BASE_URL}/api/step/translation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, english_summary: englishSummary, config, force }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  runAudio: async (filename: string, urduSummary: string, config: any, force: boolean = false) => {
    const res = await fetch(`${API_BASE_URL}/api/step/audio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, urdu_summary: urduSummary, config, force }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  getAudioUrl: (downloadPath: string) => {
    return `${API_BASE_URL}${downloadPath}`;
  }
};
