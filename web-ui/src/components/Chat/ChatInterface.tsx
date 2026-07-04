import { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload } from 'lucide-react';
import { useChatStore } from '../../stores/chat';
import { useArtifactsStore } from '../../stores/artifacts';
import { useToastStore } from '../../stores/toast';
import { useArtifactUpload } from '../../hooks/useArtifactUpload';
import { apiClient } from '../../api/client';
import { MessageList } from './MessageList';
import { QueueBar } from './QueueBar';
import { InputBox } from './InputBox';
import { LandingPage } from './LandingPage';

export function ChatInterface() {
  const error = useChatStore(state => {
    const sid = state.currentSessionId;
    return sid ? state.sessionStates[sid]?.error ?? null : null;
  });
  const currentSessionId = useChatStore(state => state.currentSessionId);
  const loadSession = useChatStore(state => state.loadSession);
  const [bridgeChecked, setBridgeChecked] = useState(false);
  const addToast = useToastStore(state => state.addToast);

  const { upload, uploading } = useArtifactUpload();
  const scanArtifacts = useArtifactsStore(state => state.scanArtifacts);

  // Auto-join TUI session in bridge mode
  useEffect(() => {
    let cancelled = false;
    apiClient.getBridgeInfo().then(info => {
      if (cancelled) return;
      if (info.bridge_mode && info.session_id) {
        loadSession(info.session_id);
      }
      setBridgeChecked(true);
    }).catch(() => {
      if (!cancelled) setBridgeChecked(true);
    });
    return () => { cancelled = true; };
  }, [loadSession]);

  const { getRootProps, isDragActive } = useDropzone({
    onDrop: useCallback(async (acceptedFiles: File[]) => {
      if (!currentSessionId || acceptedFiles.length === 0) return;
      const convId = parseInt(currentSessionId, 10);
      if (isNaN(convId)) return;
      let uploaded = 0;
      for (const file of acceptedFiles) {
        const result = await upload(file, 'conversation', convId);
        if (result) uploaded++;
      }
      if (uploaded > 0) {
        scanArtifacts(currentSessionId).catch(() => {});
        addToast(
          uploaded === 1
            ? `"${acceptedFiles[0].name}" uploaded`
            : `${uploaded} files uploaded`,
          'success',
          3000,
        );
      }
    }, [currentSessionId, upload, scanArtifacts, addToast]),
    noClick: true,
    noKeyboard: true,
    disabled: !currentSessionId,
  });

  // Brief null render while checking bridge info (imperceptible)
  if (!bridgeChecked && !currentSessionId) {
    return null;
  }

  if (!currentSessionId) {
    return <LandingPage />;
  }

  return (
    <div
      {...getRootProps()}
      className="flex flex-col h-full relative animate-fade-in"
    >
      {error && (
        <div className="mx-6 mt-4 flex items-start gap-3 rounded-md border border-semantic-danger/25 bg-semantic-danger/10 px-4 py-3 text-semantic-danger">
          <span aria-hidden className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-[50%] bg-semantic-danger" />
          <p className="text-body-sm leading-[1.5]">
            <strong className="font-[600]">Something went wrong.</strong> {error}
          </p>
        </div>
      )}

      <MessageList />
      <QueueBar />
      <InputBox />

      {/* Drag-and-drop overlay */}
      {isDragActive && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-2 rounded-lg border-2 border-dashed border-accent-magenta bg-accent-magenta/[0.06]" />
          <div className="animate-scale-in relative flex items-center gap-3 rounded-md border border-hairline-soft bg-canvas px-6 py-4 shadow-modal">
            <Upload className="h-5 w-5 text-accent-magenta" strokeWidth={1.75} />
            <span className="text-body-sm font-[540] text-ink">Drop files to add them as artifacts</span>
          </div>
        </div>
      )}

      {/* Upload progress indicator */}
      {uploading && (
        <div className="animate-slide-up absolute bottom-24 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-pill border border-hairline-soft bg-canvas px-4 py-2 text-body-sm text-ink shadow-hover">
          <div className="h-3 w-3 animate-spin rounded-[50%] border-2 border-accent-magenta border-t-transparent" />
          Uploading…
        </div>
      )}

    </div>
  );
}
