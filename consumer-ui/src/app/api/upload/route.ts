import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const formData = await req.formData();
    // Assuming backend is running on 8042
    const fastApiUrl = 'http://127.0.0.1:8042/api/process-document-async';
    // Tell the backend to send the webhook here
    const webhookUrl = 'http://127.0.0.1:3042/api/webhook';
    
    formData.append('webhook_url', webhookUrl);

    const response = await fetch(fastApiUrl, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status} ${await response.text()}`);
    }
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
