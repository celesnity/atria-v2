/**
 * MCP Server Card Component
 *
 * Displays an MCP server with its status, configuration, and available actions.
 * Follows SRP by focusing solely on server presentation and user interactions.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';
import type { MCPServer } from '../../types/mcp';

interface MCPServerCardProps {
  server: MCPServer;
  onConnect: (name: string) => Promise<void>;
  onDisconnect: (name: string) => Promise<void>;
  onTest: (name: string) => Promise<void>;
  onViewTools: (name: string) => void;
  onEdit: (server: MCPServer) => void;
  onDelete: (name: string) => void;
}

export function MCPServerCard({
  server,
  onConnect,
  onDisconnect,
  onTest,
  onViewTools,
  onEdit,
  onDelete,
}: MCPServerCardProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleConnectionToggle = async () => {
    setIsProcessing(true);
    try {
      if (server.status === 'connected') {
        await onDisconnect(server.name);
      } else {
        await onConnect(server.name);
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleTest = async () => {
    setIsProcessing(true);
    try {
      await onTest(server.name);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="bg-canvas rounded-md border border-hairline-soft hover:border-hairline transition-colors">
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3 flex-1">
          <StatusIndicator status={server.status} isProcessing={isProcessing} />

          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-medium text-ink truncate">{server.name}</h4>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-text-muted">
                {server.status === 'connected'
                  ? <ToolsCountDisplay count={server.tools_count} />
                  : <NotConnectedDisplay />}
              </span>
              <span className="text-xs text-text-muted">•</span>
              <span className="text-xs text-text-muted capitalize">{server.config_location}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <ConnectionButton
            status={server.status}
            isProcessing={isProcessing}
            onClick={handleConnectionToggle}
          />

          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-text-muted hover:text-text-secondary hover:bg-surface-soft rounded transition-colors"
          >
            <ChevronDown className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`} />
          </button>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-4 pb-3 border-t border-hairline-soft">
          <ServerDetails server={server} />

          <ActionButtons
            server={server}
            isProcessing={isProcessing}
            onTest={handleTest}
            onViewTools={onViewTools}
            onEdit={onEdit}
            onDelete={onDelete}
          />
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Sub-components (Single Responsibility Principle)
// ============================================================================

function ToolsCountDisplay({ count }: { count: number }) {
  const { t } = useTranslation('settings');
  return <>{t('mcp.toolsCount', { count })}</>;
}

function NotConnectedDisplay() {
  const { t } = useTranslation('settings');
  return <>{t('mcp.notConnected')}</>;
}

interface StatusIndicatorProps {
  status: MCPServer['status'];
  isProcessing: boolean;
}

function StatusIndicator({ status, isProcessing }: StatusIndicatorProps) {
  const { t } = useTranslation('settings');

  if (isProcessing) {
    return (
      <div className="flex items-center justify-center w-8 h-8">
        <div className="w-4 h-4 border-2 border-hairline-soft border-t-gray-900 rounded-md animate-spin" />
      </div>
    );
  }

  const statusConfig = {
    connected: { color: 'bg-green-500', label: t('mcp.statusConnected') },
    disconnected: { color: 'bg-gray-400', label: t('mcp.statusDisconnected') },
    connecting: { color: 'bg-yellow-500', label: t('mcp.statusConnecting') },
    error: { color: 'bg-semantic-danger', label: t('mcp.statusError') },
  };

  const config = statusConfig[status];

  return (
    <span className={`text-[10px] font-mono uppercase tracking-wide ${config.color.replace('bg-', 'text-')}`}>
      {config.label}
    </span>
  );
}

interface ConnectionButtonProps {
  status: MCPServer['status'];
  isProcessing: boolean;
  onClick: () => void;
}

function ConnectionButton({ status, isProcessing, onClick }: ConnectionButtonProps) {
  const { t } = useTranslation('settings');
  const isConnected = status === 'connected';

  return (
    <button
      onClick={onClick}
      disabled={isProcessing}
      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
        isConnected
          ? 'text-text-secondary bg-surface-soft hover:bg-surface-soft'
          : 'text-white bg-gradient-brand hover:brightness-110'
      } disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {isProcessing ? t('mcp.processing') : isConnected ? t('mcp.disconnectButton') : t('mcp.connectButton')}
    </button>
  );
}

interface ServerDetailsProps {
  server: MCPServer;
}

function ServerDetails({ server }: ServerDetailsProps) {
  const { t } = useTranslation('settings');
  const { config } = server;

  return (
    <div className="mt-3 space-y-2 text-xs">
      <DetailRow label={t('mcp.commandDetail')} value={config.command} mono />

      {config.args.length > 0 && (
        <DetailRow label={t('mcp.argsDetail')} value={config.args.join(' ')} mono />
      )}

      {Object.keys(config.env).length > 0 && (
        <div>
          <span className="text-text-muted font-medium">{t('mcp.environmentDetail')}</span>
          <div className="mt-1 space-y-1">
            {Object.entries(config.env).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-text-secondary">
                <span className="font-mono font-medium">{key}=</span>
                <span className="font-mono text-text-secondary">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-4">
        <DetailRow
          label={t('mcp.autoStartDetail')}
          value={config.auto_start ? t('mcp.autoStartEnabled') : t('mcp.autoStartDisabled')}
          valueColor={config.auto_start ? 'text-green-600' : 'text-text-muted'}
        />
        <DetailRow
          label={t('mcp.enabledDetail')}
          value={config.enabled ? 'Yes' : 'No'}
          valueColor={config.enabled ? 'text-green-600' : 'text-text-muted'}
        />
      </div>
    </div>
  );
}

interface DetailRowProps {
  label: string;
  value: string;
  mono?: boolean;
  valueColor?: string;
}

function DetailRow({ label, value, mono = false, valueColor = 'text-text-secondary' }: DetailRowProps) {
  return (
    <div className="flex gap-2">
      <span className="text-text-muted font-medium">{label}:</span>
      <span className={`${valueColor} ${mono ? 'font-mono' : ''} break-all`}>{value}</span>
    </div>
  );
}

interface ActionButtonsProps {
  server: MCPServer;
  isProcessing: boolean;
  onTest: () => void;
  onViewTools: (name: string) => void;
  onEdit: (server: MCPServer) => void;
  onDelete: (name: string) => void;
}

function ActionButtons({
  server,
  isProcessing,
  onTest,
  onViewTools,
  onEdit,
  onDelete,
}: ActionButtonsProps) {
  const { t } = useTranslation('settings');

  return (
    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-hairline-soft">
      {server.status === 'connected' && (
        <ActionButton
          onClick={() => onViewTools(server.name)}
          disabled={isProcessing}
          variant="secondary"
        >
          {t('mcp.viewTools', { count: server.tools_count })}
        </ActionButton>
      )}

      <ActionButton
        onClick={onTest}
        disabled={isProcessing}
        variant="secondary"
      >
        {t('mcp.testConnection')}
      </ActionButton>

      <ActionButton
        onClick={() => onEdit(server)}
        disabled={isProcessing}
        variant="secondary"
      >
        {t('mcp.actionEdit')}
      </ActionButton>

      <div className="flex-1" />

      <ActionButton
        onClick={() => onDelete(server.name)}
        disabled={isProcessing}
        variant="danger"
      >
        {t('mcp.actionRemove')}
      </ActionButton>
    </div>
  );
}

interface ActionButtonProps {
  onClick: () => void;
  disabled: boolean;
  variant: 'primary' | 'secondary' | 'danger';
  children: React.ReactNode;
}

function ActionButton({ onClick, disabled, variant, children }: ActionButtonProps) {
  const variants = {
    primary: 'text-white bg-gradient-brand hover:brightness-110',
    secondary: 'text-text-secondary bg-surface-soft hover:bg-surface-soft',
    danger: 'text-semantic-danger bg-red-50 hover:bg-red-100',
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${variants[variant]} disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}
