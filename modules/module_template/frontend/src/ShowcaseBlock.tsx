export default function ShowcaseBlock(props: any) {
  const { kind = 'block', topic = 'demo', results = [], pct, done, bridge } = props;
  return (
    <div className="bg-bg-000 border border-border-300/15 rounded-lg p-4 space-y-2">
      <div className="text-xs font-mono text-text-300">module_template · {kind}</div>
      {typeof pct === 'number' ? (
        <div>
          <div className="text-sm text-text-100 mb-1">{done ? 'Done' : `Working… ${pct}%`}</div>
          <div className="h-2 rounded bg-bg-200 overflow-hidden">
            <div className="h-full bg-accent-secondary-100" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : (
        <>
          <div className="text-sm text-text-100">Results for <b>{topic}</b>:</div>
          <ul className="text-sm text-text-200 list-disc pl-5">
            {results.map((r: any, i: number) => (
              <li key={i}>{r.title} <span className="text-text-400">({r.score})</span></li>
            ))}
          </ul>
          <div className="flex gap-2 pt-1">
            <button className="px-2 py-1 rounded bg-bg-200 text-xs"
                    onClick={() => bridge?.toast?.('Hello from ShowcaseBlock', 'success')}>
              bridge.toast
            </button>
            <button className="px-2 py-1 rounded bg-bg-200 text-xs"
                    onClick={() => bridge?.sendMessage?.(`Tell me more about ${topic}`)}>
              bridge.sendMessage
            </button>
          </div>
        </>
      )}
    </div>
  );
}
