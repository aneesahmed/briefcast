import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const DB_FILE = path.join(process.cwd(), 'webhook.json');

export async function GET() {
  try {
    let records = [];
    if (fs.existsSync(DB_FILE)) {
      records = JSON.parse(fs.readFileSync(DB_FILE, 'utf-8'));
    }
    // Sort descending by receivedAt
    records.sort((a: any, b: any) => new Date(b.receivedAt).getTime() - new Date(a.receivedAt).getTime());
    return NextResponse.json({ records });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to read status' }, { status: 500 });
  }
}
