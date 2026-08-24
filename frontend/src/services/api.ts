import type { GlobalSettings, ProcessResult } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const api = {
  getHistory: async (): Promise<ProcessResult[]> => {
    const res = await fetch(`${API_BASE_URL}/api/history`);
    if (!res.ok) throw new Error('Failed to fetch history');
    const data = await res.json();
    return data.history || [];
  },

  getSettings: async (): Promise<GlobalSettings> => {
    const res = await fetch(`${API_BASE_URL}/api/settings`);
    if (!res.ok) throw new Error('Failed to load global settings');
    return res.json();
  },

  uploadDocs: async (files: FileList): Promise<{ message: string }> => {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    const res = await fetch(`${API_BASE_URL}/api/upload-docs`, { method: 'POST', body: formData });
    if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
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
