import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';
import React from 'react';

// Mock the api service so we don't make real network requests in tests
vi.mock('./services/api', () => ({
  api: {
    getHistory: vi.fn().mockResolvedValue([]),
    getSettings: vi.fn().mockResolvedValue({}),
  }
}));

describe('App', () => {
  it('renders the dashboard by default', async () => {
    render(<App />);
    
    // We expect the navigation bar to exist
    expect(screen.getByText('Briefcast Enterprise')).toBeInTheDocument();
    
    // We expect the Dashboard component to render
    expect(await screen.findByText('Briefcast Operations Hub')).toBeInTheDocument();
  });
});
