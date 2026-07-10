export function BarChart({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map(d => d.value));
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', height: 120 }}>
      {data.map(d => (
        <div key={d.label} style={{ textAlign: 'center', flex: 1 }}>
          <div style={{ height: `${(d.value / max) * 100}px`, background: '#6366f1', borderRadius: 4 }} />
          <div style={{ fontSize: 11 }}>{d.label}</div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>{d.value}</div>
        </div>
      ))}
    </div>
  );
}
