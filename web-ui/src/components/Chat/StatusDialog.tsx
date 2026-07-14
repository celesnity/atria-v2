import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chat';
import { apiClient } from '../../api/client';

interface StatusDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

interface MCPServer {
  name: string;
  status: string;
  config: { enabled: boolean };
  tools_count: number;
}

export function StatusDialog({ isOpen, onClose }: StatusDialogProps) {
  const { t } = useTranslation('chat');
  const status = useChatStore(state => state.status);
  const currentSessionId = useChatStore(state => state.currentSessionId);
  const sessionMessages = useChatStore(state => {
    const sid = state.currentSessionId;
    return sid ? state.sessionStates[sid]?.messages?.length ?? 0 : 0;
  });

  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    apiClient.get<{ servers: MCPServer[] }>('/mcp/servers')
      .then(data => setMcpServers(data?.servers || []))
      .catch(() => setMcpServers([]))
      .finally(() => setLoading(false));
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        className="relative w-full max-w-md bg-bg-000 border border-border-300/30 rounded-xl shadow-modal overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-300/20">
          <h2 className="text-sm font-semibold text-text-000">{t('statusDialog.title')}</h2>
          <button onClick={onClose} aria-label={t('statusDialog.close')} className="text-text-400 hover:text-text-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-4 py-3 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Model Info */}
          <section>
            <h3 className="text-xs font-semibold uppercase text-text-400 mb-2">{t('statusDialog.sectionModel')}</h3>
            <div className="text-sm text-text-200 space-y-1">
              <div className="flex justify-between">
                <span className="text-text-400">{t('statusDialog.model')}</span>
                <span className="font-mono">{status?.model || '—'}</span>
              </div>
            </div>
          </section>

          {/* Session Info */}
          <section>
            <h3 className="text-xs font-semibold uppercase text-text-400 mb-2">{t('statusDialog.sectionSession')}</h3>
            <div className="text-sm text-text-200 space-y-1">
              <div className="flex justify-between">
                <span className="text-text-400">{t('statusDialog.sessionId')}</span>
                <span className="font-mono">{currentSessionId || '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-400">{t('statusDialog.messages')}</span>
                <span>{sessionMessages}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-400">{t('statusDialog.mode')}</span>
                <span className="capitalize">{status?.mode || '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-400">{t('statusDialog.autonomy')}</span>
                <span>{status?.autonomy_level || '—'}</span>
              </div>
              {status?.session_cost != null && (
                <div className="flex justify-between">
                  <span className="text-text-400">{t('statusDialog.cost')}</span>
                  <span className="font-mono">
                    {status.session_cost < 0.01
                      ? `$${status.session_cost.toFixed(4)}`
                      : `$${status.session_cost.toFixed(2)}`}
                  </span>
                </div>
              )}
              {status?.context_usage_pct != null && (
                <div className="flex justify-between">
                  <span className="text-text-400">{t('statusDialog.contextUsage')}</span>
                  <span>{Math.round(status.context_usage_pct)}%</span>
                </div>
              )}
            </div>
          </section>

          {/* MCP Servers */}
          <section>
            <h3 className="text-xs font-semibold uppercase text-text-400 mb-2">{t('statusDialog.sectionMcp')}</h3>
            {loading ? (
              <div className="text-sm text-text-400">{t('statusDialog.loading')}</div>
            ) : mcpServers.length === 0 ? (
              <div className="text-sm text-text-400">{t('statusDialog.noMcpServers')}</div>
            ) : (
              <div className="space-y-1.5">
                {mcpServers.map(server => (
                  <div key={server.name} className="flex items-center gap-2 text-sm">
                    <span className="text-text-200 font-mono">{server.name}</span>
                    <span className="text-text-400 text-xs">
                      {server.status === 'connected' ? t('statusDialog.mcpConnected', { count: server.tools_count }) : t('statusDialog.mcpDisconnected')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Working Directory */}
          {status?.working_dir && (
            <section>
              <h3 className="text-xs font-semibold uppercase text-text-400 mb-2">{t('statusDialog.sectionWorkingDir')}</h3>
              <div className="text-sm text-text-200 font-mono break-all">{status.working_dir}</div>
              {status.git_branch && (
                <div className="text-sm text-text-400 mt-1">{t('statusDialog.branch', { branch: status.git_branch })}</div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
