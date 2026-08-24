# Briefcast Frontend

This is the React + Vite frontend for the Briefcast system.

## Setup
1. Ensure Node.js (v18+) is installed.
2. Copy the environment variables template:
   ```bash
   cp .env.example .env.local
   ```
   *Note: Ensure `VITE_API_BASE_URL` points to your running backend (defaults to http://localhost:8000).*

3. Install dependencies:
   ```bash
   npm install
   ```

4. Start the development server:
   ```bash
   npm run dev
   ```

5. Build for production:
   ```bash
   npm run build
   ```
