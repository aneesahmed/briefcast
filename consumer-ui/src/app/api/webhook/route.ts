import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const DB_FILE = path.join(process.cwd(), 'webhook.json');

export async function POST(req: Request) {
  try {
    const data = await req.json();
    let records = [];
    if (fs.existsSync(DB_FILE)) {
      records = JSON.parse(fs.readFileSync(DB_FILE, 'utf-8'));
    }
    records.push({ ...data, receivedAt: new Date().toISOString() });
    fs.writeFileSync(DB_FILE, JSON.stringify(records, null, 2));
    
    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to process webhook' }, { status: 500 });
  }
}
