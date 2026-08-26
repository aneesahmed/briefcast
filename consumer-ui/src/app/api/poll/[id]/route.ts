import { NextResponse } from 'next/server';

export async function GET(req: Request, { params }: { params: { id: string } }) {
  try {
    const jobId = params.id;
    const fastApiUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8042/api/process-document';
    
    // Instead of using the old GET /job-status, we hit the combined POST endpoint
    // by providing the job_id as form data.
    const formData = new FormData();
    formData.append('job_id', jobId);

    const response = await fetch(fastApiUrl, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status}`);
    }
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

