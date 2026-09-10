import express from 'express';
import { Pool } from 'pg';
import cors from 'cors';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const port = 82;

app.use(cors());
app.use(express.json());

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  user: process.env.DB_USER || 'briefcast',
  password: process.env.DB_PASSWORD || 'briefcast_password',
  database: process.env.DB_NAME || 'briefcast_audit',
  port: parseInt(process.env.DB_PORT || '5432'),
});

app.get('/api/audit/records', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM audit_records ORDER BY completed_at DESC');
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.get('/api/audit/daily', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM audit_daily_summary ORDER BY audit_date DESC');
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

app.listen(port, () => {
  console.log(`Audit API listening on port ${port}`);
});
