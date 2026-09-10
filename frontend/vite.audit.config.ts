import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

const PROCESSED_DIR = path.resolve(__dirname, '../processed_files');

// Pricing in USD per million tokens
const PRICING = {
  input_per_million: 0.075,
  output_per_million: 0.30,
};

// Fallback logic for token count
function estimateTokens(text) {
  if (!text) return 0;
  const isUrdu = /[\u0600-\u06FF]/.test(text);
  const multiplier = isUrdu ? 0.8 : 0.25;
  return Math.round(text.length * multiplier);
}

function auditApiPlugin() {
  return {
    name: 'audit-api',
    configureServer(server) {
      server.middlewares.use('/api/audit-stats', (req, res) => {
        try {
          const files = fs.readdirSync(PROCESSED_DIR).filter(f => f.endsWith('_manifest.json'));
          
          let totalTokens = 0;
          let totalCostUsd = 0;
          const records = [];

          files.forEach(filename => {
            try {
              const filePath = path.join(PROCESSED_DIR, filename);
              const manifest = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
              
              const originalName = manifest.original_filename || 'Unknown';
              const pdfPath = path.join(PROCESSED_DIR, originalName);
              const sizeMb = fs.existsSync(pdfPath) ? fs.statSync(pdfPath).size / (1024 * 1024) : 0;
              
              const engText = manifest.english_summary || '';
              const urduText = manifest.urdu_summary || '';
              
              const tokens = estimateTokens(engText) + estimateTokens(urduText);
              // Estimating 50% input / 50% output for simplicity in dashboard
              const costUsd = (tokens / 1000000) * ((PRICING.input_per_million + PRICING.output_per_million) / 2);
              
              totalTokens += tokens;
              totalCostUsd += costUsd;
              
              records.push({
                filename: originalName,
                company: manifest.company_name || 'Unknown',
                completedAt: manifest.completed_at || '',
                sizeMb: sizeMb,
                tokens: tokens,
                costUsd: costUsd
              });
            } catch (e) {
              console.error(`Error processing ${filename}:`, e);
            }
          });

          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ totalTokens, totalCostUsd, records }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: String(e) }));
        }
      });
    }
  };
}

export default defineConfig({
  plugins: [react(), auditApiPlugin()],
  server: {
    port: 82,
    open: '/audit.html'
  }
});
