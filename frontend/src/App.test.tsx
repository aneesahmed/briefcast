import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';
import React from 'react';

// Mock the api service so we don't make real network requests in tests
vi.mock('./services/api', () => ({
  api: {
    getDashboard: vi.fn().mockResolvedValue({
      scanner: { running: true, interval_seconds: 10, configuration_error: null, source_directory: 'briefing_source' },
      counts: { processing: 0, input_files: 0, completed: 0, failed: 0 },
      processing: [], input_files: [], processed_files: [], failed_files: [],
    }),
    searchRecords: vi.fn().mockResolvedValue([]),
    getAppConfig: vi.fn().mockResolvedValue({ supported_extensions: ['.txt', '.pdf', '.docx'] }),
    uploadDocs: vi.fn(),
    getAudioUrl: vi.fn((path: string) => path),
  }
}));

describe('App', () => {
  it('renders the dashboard by default', async () => {
    render(<App />);
    
    // We expect the navigation bar to exist
    expect(screen.getByText('Briefcast')).toBeInTheDocument();
    
    // We expect the Dashboard component to render
    expect(await screen.findByText('Briefcast Operations')).toBeInTheDocument();
  });
});
