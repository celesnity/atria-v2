import { useBlackboardStore } from '../stores/blackboardStore';

export function BlackboardPage() {
  const requests = useBlackboardStore((s) => s.requests);
  const order = useBlackboardStore((s) => s.order);
  const clear = useBlackboardStore((s) => s.clear);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto bg-canvas">
      <main>
        <div className="max-w-content mx-auto px-6 py-8">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-xl font-semibold">Blackboard</h1>
            {order.length > 0 && (
              <button className="text-sm text-text-secondary hover:text-text" onClick={clear}>
                Clear
              </button>
            )}
          </div>
          {order.length === 0 && (
            <p className="text-text-secondary text-sm">
              No requests yet. When the agent posts a help request, helpers bid here.
            </p>
          )}
          <div className="space-y-4">
            {order.map((id) => {
              const r = requests[id];
              if (!r) return null;
              return (
                <div key={id} className="rounded-lg border border-hairline-soft/25 p-4">
                  <div className="flex items-center justify-between">
                    <div className="font-mono text-sm">{r.prompt}</div>
                    <span className="text-xs text-text-secondary">{r.status}</span>
                  </div>
                  <div className="mt-3">
                    <div className="text-xs uppercase text-text-secondary mb-1">Bids</div>
                    <ul className="space-y-1">
                      {r.bids.map((b) => (
                        <li key={b.responder} className="text-sm flex items-center gap-2">
                          <span className={b.volunteered ? 'text-semantic-success' : 'text-text-secondary'}>
                            {b.volunteered ? '✓' : '✗'}
                          </span>
                          <span className="font-medium">{b.responder}</span>
                          <span className="text-text-secondary">
                            ({b.confidence.toFixed(2)}) {b.reason}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  {r.responses.length > 0 && (
                    <div className="mt-3">
                      <div className="text-xs uppercase text-text-secondary mb-1">Responses</div>
                      <ul className="space-y-2">
                        {r.responses.map((resp) => (
                          <li key={resp.responder} className="text-sm">
                            <span className="font-medium">{resp.responder}:</span>{' '}
                            <span className="text-text-secondary">{resp.content}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
