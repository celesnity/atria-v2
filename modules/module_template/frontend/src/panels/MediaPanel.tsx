import { useEffect, useState } from 'react';

export function MediaPanel({ apiBase }: { apiBase: string }) {
  const [items, setItems] = useState<any[]>([]);
  const load = () => fetch(`${apiBase}/connector/media`).then(r => r.json())
    .then(d => setItems(d.media || [])).catch(() => {});
  useEffect(() => { load(); }, [apiBase]);
  const upload = async (file: File) => {
    const b64 = btoa(String.fromCharCode(...new Uint8Array(await file.arrayBuffer())));
    await fetch(`${apiBase}/connector/media/upload`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, content_b64: b64, content_type: file.type }),
    });
    load();
  };
  return (
    <div>
      <h3>Media</h3>
      <input type="file" onChange={e => e.target.files && upload(e.target.files[0])} />
      <ul>{items.map(m => <li key={m.id}><a href={m.url} target="_blank">{m.filename}</a> ({m.size}b)</li>)}</ul>
    </div>
  );
}
