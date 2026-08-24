'use client';
import { useState, useEffect } from 'react';

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>('');
  const [records, setRecords] = useState<any[]>([]);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000); // poll every 3 seconds
    return () => clearInterval(interval);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setStatus('Uploading...');
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setStatus(`Success: ${data.message || 'Queued'}`);
      } else {
        setStatus(`Error: ${data.error}`);
      }
    } catch (err: any) {
      setStatus(`Error: ${err.message}`);
    }
  };

  return (
    <main className="p-8 max-w-4xl mx-auto font-sans">
      <h1 className="text-3xl font-bold mb-6 text-gray-800">Briefcast Consumer UI</h1>
      <p className="mb-8 text-gray-600">
        This is an isolated Next.js client that tests the async processing pipeline. 
        It sends a document to the FastAPI backend, which will process it in the background 
        and POST the results back to our webhook endpoint.
      </p>
      
      <div className="bg-white border rounded-lg p-6 shadow-sm mb-8">
        <h2 className="text-xl font-semibold mb-4 text-gray-800">Upload Document for Processing</h2>
        <input 
          type="file" 
          onChange={(e) => setFile(e.target.files?.[0] || null)} 
          className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
        />
        <button 
          onClick={handleUpload}
          disabled={!file}
          className="mt-4 px-4 py-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Send to Backend (Async)
        </button>
        {status && <p className="mt-4 text-sm font-medium p-3 bg-gray-50 rounded border">{status}</p>}
      </div>

      <div>
        <h2 className="text-xl font-semibold mb-4 text-gray-800 flex items-center justify-between">
          Webhook Callbacks 
          <span className="text-xs font-normal bg-green-100 text-green-800 px-2 py-1 rounded">Auto-refreshing</span>
        </h2>
        {records.length === 0 ? (
          <p className="text-gray-500 text-sm italic">No webhooks received yet. Upload a document to start.</p>
        ) : (
          <div className="space-y-4">
            {records.map((rec, i) => (
              <div key={i} className="border rounded-lg p-5 shadow-sm bg-gray-50 text-sm overflow-hidden">
                <div className="flex justify-between items-center mb-3">
                  <span className="font-bold text-lg text-gray-800">{rec.filename}</span>
                  <span className={`px-3 py-1 rounded-full text-xs font-bold text-white ${rec.status === 'success' ? 'bg-green-500' : 'bg-red-500'}`}>
                    {rec.status.toUpperCase()}
                  </span>
                </div>
                <div className="text-xs text-gray-500 mb-4">{new Date(rec.receivedAt).toLocaleString()}</div>
                
                <div className="bg-gray-900 rounded p-4 overflow-x-auto">
                  <pre className="text-xs text-green-400 font-mono">
                    {JSON.stringify(rec, null, 2)}
                  </pre>
                </div>

                {rec.status === 'success' && rec.download_url && (
                  <div className="mt-5 p-4 bg-white border rounded-lg">
                    <p className="font-bold text-gray-800 mb-2">Listen to Output:</p>
                    <audio controls src={`http://127.0.0.1:8000${rec.download_url}`} className="w-full h-10" />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
