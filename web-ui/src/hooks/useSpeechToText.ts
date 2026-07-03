import { useCallback, useRef, useState } from 'react';
import { useToastStore } from '../stores/toast';

/**
 * Speech-to-text, streaming-first with push-to-talk fallback.
 *
 * Streaming: `startStreaming(onPartial)` opens the mic, captures raw PCM via an
 * AudioWorklet, streams 16 kHz Int16 frames over `/ws/transcribe`, and invokes
 * `onPartial(text, isFinal)` as live transcripts arrive — words appear while
 * the user is still speaking. `stopStreaming()` ends the utterance and resolves
 * after the final transcript. Returns false from `startStreaming` if setup
 * fails so the caller can fall back to the batch path.
 *
 * Batch (fallback): `start()`/`stop()` — MediaRecorder → blob → POST
 * `/api/transcribe`, resolving one final string.
 *
 * Transcripts are only handed to the caller — never auto-sent — so the engineer
 * reviews before sending.
 */

const TARGET_SR = 16000;
const FRAME_MS = 250; // batch PCM into ~250ms frames

// Minimal worklet: forward each 128-sample Float32 block to the main thread.
const WORKLET_SOURCE = `
class PCMCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('pcm-capture', PCMCapture);
`;

function downsampleToInt16(input: Float32Array, fromRate: number): Int16Array {
  if (fromRate === TARGET_SR) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }
  const ratio = fromRate / TARGET_SR;
  const outLen = Math.floor(input.length / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = pos - i0;
    const s = Math.max(-1, Math.min(1, input[i0] * (1 - frac) + input[i1] * frac));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function wsUrl(): string {
  // Mirror api/websocket.ts: dev dials the backend directly (avoids Vite HMR
  // WS conflicts); prod is relative to the page origin.
  const isDev = import.meta.env.DEV;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return isDev
    ? 'ws://localhost:8080/ws/transcribe'
    : `${protocol}//${window.location.host}/ws/transcribe`;
}

export function useSpeechToText() {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  // Batch refs
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // Shared / streaming refs
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const finalResolveRef = useRef<((text: string) => void) | null>(null);

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* already closed */ }
      wsRef.current = null;
    }
  }, []);

  // ── Streaming path ──────────────────────────────────────────────────────────

  const startStreaming = useCallback(
    async (onPartial: (text: string, isFinal: boolean) => void): Promise<boolean> => {
      if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
        return false; // caller falls back to batch
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;

        // Open the socket first; bail to fallback if it can't connect.
        const ws = await new Promise<WebSocket>((resolve, reject) => {
          const sock = new WebSocket(wsUrl());
          sock.binaryType = 'arraybuffer';
          sock.onopen = () => resolve(sock);
          sock.onerror = () => reject(new Error('ws connect failed'));
          setTimeout(() => reject(new Error('ws connect timeout')), 5000);
        });
        wsRef.current = ws;

        ws.onmessage = (ev) => {
          try {
            const d = JSON.parse(ev.data);
            if (d.type === 'partial') onPartial(d.text ?? '', false);
            else if (d.type === 'final') {
              onPartial(d.text ?? '', true);
              finalResolveRef.current?.(d.text ?? '');
              finalResolveRef.current = null;
            } else if (d.type === 'error') {
              useToastStore.getState().addToast(`Transcription error: ${d.detail ?? 'unknown'}`, 'error');
              finalResolveRef.current?.('');
              finalResolveRef.current = null;
            }
          } catch { /* ignore malformed frames */ }
        };
        ws.onclose = () => {
          finalResolveRef.current?.('');
          finalResolveRef.current = null;
        };

        // Ask for 16 kHz directly; browsers that ignore it get resampled below.
        let ctx: AudioContext;
        try {
          ctx = new AudioContext({ sampleRate: TARGET_SR });
        } catch {
          ctx = new AudioContext();
        }
        audioCtxRef.current = ctx;
        const workletUrl = URL.createObjectURL(
          new Blob([WORKLET_SOURCE], { type: 'application/javascript' })
        );
        try {
          await ctx.audioWorklet.addModule(workletUrl);
        } finally {
          URL.revokeObjectURL(workletUrl);
        }
        const source = ctx.createMediaStreamSource(stream);
        const node = new AudioWorkletNode(ctx, 'pcm-capture');

        // Accumulate worklet blocks into ~FRAME_MS frames, then send as Int16.
        const frameSamples = Math.round((ctx.sampleRate * FRAME_MS) / 1000);
        let pending: Float32Array[] = [];
        let pendingLen = 0;
        node.port.onmessage = (e: MessageEvent<Float32Array>) => {
          pending.push(e.data);
          pendingLen += e.data.length;
          if (pendingLen >= frameSamples && ws.readyState === WebSocket.OPEN) {
            const merged = new Float32Array(pendingLen);
            let off = 0;
            for (const p of pending) { merged.set(p, off); off += p.length; }
            pending = []; pendingLen = 0;
            const pcm = downsampleToInt16(merged, ctx.sampleRate);
            ws.send(pcm.buffer);
          }
        };
        source.connect(node);
        // Keep the graph alive without audible output.
        node.connect(ctx.destination);

        setRecording(true);
        return true;
      } catch {
        cleanupStream();
        setRecording(false);
        return false;
      }
    },
    [cleanupStream],
  );

  const stopStreaming = useCallback(async (): Promise<void> => {
    setRecording(false);
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      cleanupStream();
      return;
    }
    setTranscribing(true);
    try {
      const finalArrived = new Promise<string>((resolve) => {
        finalResolveRef.current = resolve;
        setTimeout(() => {
          finalResolveRef.current = null;
          resolve('');
        }, 15000);
      });
      ws.send(JSON.stringify({ type: 'stop' }));
      await finalArrived;
    } finally {
      setTranscribing(false);
      cleanupStream();
    }
  }, [cleanupStream]);

  // ── Batch (push-to-talk) fallback ───────────────────────────────────────────

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      useToastStore.getState().addToast('Voice input needs a secure (https/localhost) context.', 'error');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mr = new MediaRecorder(stream);
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorderRef.current = mr;
      mr.start();
      setRecording(true);
    } catch {
      cleanupStream();
      setRecording(false);
      useToastStore.getState().addToast('Microphone unavailable — check browser permissions.', 'error');
    }
  }, [cleanupStream]);

  const stop = useCallback(async (): Promise<string> => {
    const mr = recorderRef.current;
    setRecording(false);
    if (!mr) return '';

    const mimeType = mr.mimeType || 'audio/webm';
    const stopped = new Promise<Blob>((resolve) => {
      mr.onstop = () => resolve(new Blob(chunksRef.current, { type: mimeType }));
    });
    mr.stop();
    const blob = await stopped;
    cleanupStream();
    if (blob.size === 0) return '';

    const ext = mimeType.includes('ogg') ? 'ogg' : mimeType.includes('mp4') ? 'mp4' : 'webm';
    const form = new FormData();
    form.append('file', blob, `speech.${ext}`);

    setTranscribing(true);
    try {
      const resp = await fetch('/api/transcribe', { method: 'POST', body: form });
      if (!resp.ok) throw new Error(`status ${resp.status}`);
      const data = await resp.json();
      return (data.text ?? '').trim();
    } catch {
      useToastStore.getState().addToast('Transcription failed. Please try again.', 'error');
      return '';
    } finally {
      setTranscribing(false);
    }
  }, [cleanupStream]);

  return { recording, transcribing, start, stop, startStreaming, stopStreaming };
}
