import { useEffect, useState } from 'react';
import { API_BASE } from '@/lib/config';

export type NeuralLink = 'probing' | 'active' | 'offline';
export type QuantumState = 'stable' | 'syncing' | 'processing' | 'degraded';

export interface NeuralLinkStatus {
  neural_link: NeuralLink;
  quantum_state: QuantumState;
  updated_at: number; // ms epoch
}

type Listener = (s: NeuralLinkStatus) => void;

const DEFAULT_STATE: NeuralLinkStatus = {
  neural_link: 'probing',
  quantum_state: 'stable',
  updated_at: 0,
};

let _state: NeuralLinkStatus = DEFAULT_STATE;
let _listeners = new Set<Listener>();
let _timer: number | null = null;
let _inflight = false;

function emit(next: NeuralLinkStatus) {
  _state = next;
  _listeners.forEach((fn) => fn(_state));
}

function getToken(): string | null {
  try {
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

async function fetchJson(url: string, signal: AbortSignal) {
  const token = getToken();
  const res = await fetch(url, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<any>;
}

async function sampleOnce(signal: AbortSignal, busy: boolean) {
  // 防止并发 tick 堆叠（慢网/卡顿时很常见）
  if (_inflight) return;
  _inflight = true;
  try {
    // 1) 轻量探活：/system/stats 可返回即可视作链路可用
    await fetchJson(`${API_BASE}/system/stats`, signal);
    const link: NeuralLink = 'active';

    // 2) 后台任务运行态：任一 is_running=true 即 syncing；若 UI 自身忙则 processing
    const [scan, scrape, sub] = await Promise.all([
      fetchJson(`${API_BASE}/tasks/scan/status`, signal),
      fetchJson(`${API_BASE}/tasks/scrape_all/status`, signal),
      fetchJson(`${API_BASE}/tasks/find_subtitles/status`, signal),
    ]);

    const anyRunning = Boolean(scan?.is_running || scrape?.is_running || sub?.is_running);
    const q: QuantumState = busy ? 'processing' : anyRunning ? 'syncing' : 'stable';

    emit({
      neural_link: link,
      quantum_state: q,
      updated_at: Date.now(),
    });
  } catch {
    const link: NeuralLink = 'offline';
    const q: QuantumState = 'degraded';
    emit({
      neural_link: link,
      quantum_state: q,
      updated_at: Date.now(),
    });
  } finally {
    _inflight = false;
  }
}

function ensurePolling(options?: { enabled?: boolean; intervalMs?: number; busy?: boolean }) {
  const enabled = options?.enabled ?? true;
  if (!enabled) return;
  if (_timer !== null) return;

  const intervalMs = options?.intervalMs ?? 2500;
  const controller = new AbortController();

  const tick = () => {
    void sampleOnce(controller.signal, Boolean(options?.busy));
  };

  tick();
  _timer = window.setInterval(tick, intervalMs);

  const onDown = () => {
    const link: NeuralLink = 'offline';
    const q: QuantumState = 'degraded';
    emit({
      neural_link: link,
      quantum_state: q,
      updated_at: Date.now(),
    });
  };
  const onUp = () => {
    // 只更新 link，量子态交给下一次 tick 决定（避免在网络抖动时误报 stable）
    emit({
      ..._state,
      neural_link: 'active',
      updated_at: Date.now(),
    });
    tick();
  };
  window.addEventListener('neon-network-down', onDown as EventListener);
  window.addEventListener('neon-network-up', onUp as EventListener);

  // 在最后一个订阅者移除时清理（见 stopPollingIfIdle）
  (ensurePolling as any)._cleanup = () => {
    controller.abort();
    if (_timer !== null) window.clearInterval(_timer);
    _timer = null;
    window.removeEventListener('neon-network-down', onDown as EventListener);
    window.removeEventListener('neon-network-up', onUp as EventListener);
  };
}

function stopPollingIfIdle() {
  if (_listeners.size > 0) return;
  const cleanup = (ensurePolling as any)._cleanup as undefined | (() => void);
  cleanup?.();
  (ensurePolling as any)._cleanup = undefined;
}

export function useNeuralLinkStatus(options?: {
  enabled?: boolean;
  intervalMs?: number;
  busy?: boolean;
}): NeuralLinkStatus {
  const [state, setState] = useState<NeuralLinkStatus>(_state);

  useEffect(() => {
    const listener: Listener = (s) => setState(s);
    _listeners.add(listener);
    ensurePolling(options);
    return () => {
      _listeners.delete(listener);
      stopPollingIfIdle();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options?.enabled, options?.intervalMs, options?.busy]);

  return state;
}

