import { useEffect, useState } from 'react';

export function JobsPanel({ apiBase }: { apiBase: string }) {
  const [jobs, setJobs] = useState<any[]>([]);
  const load = () => fetch(`${apiBase}/connector/jobs`).then(r => r.json())
    .then(d => setJobs(d.jobs || [])).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [apiBase]);
  return (
    <div>
      <h3>Jobs</h3>
      <table><thead><tr><th>id</th><th>kind</th><th>status</th><th>pct</th></tr></thead>
        <tbody>{jobs.map(j => (
          <tr key={j.id}><td>{j.id}</td><td>{j.kind}</td><td>{j.status}</td><td>{j.pct}%</td></tr>
        ))}</tbody></table>
    </div>
  );
}
