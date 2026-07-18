/**
 * useNeuralLinkStatus - 神经链接状态监控 Hook
 * 
 * 核心职责：
 * - 实时监控后端网络连接状态
 * - 追踪后台任务的运行状态（扫描、刮削、字幕）
 * - 向 UI 提供网络和任务状态信息
 * - 支持全局单例轮询（多个组件共享一个轮询定时器）
 * 
 * 状态类型：
 * - neural_link: 'probing' | 'active' | 'offline'
 *   - probing: 正在探活（初始状态）
 *   - active: 连接正常
 *   - offline: 连接断开
 * 
 * - quantum_state: 'stable' | 'syncing' | 'processing' | 'degraded'
 *   - stable: 系统稳定，无后台任务
 *   - syncing: 后台有任务正在运行
 *   - processing: 前端繁忙状态
 *   - degraded: 系统故障或降级
 * 
 * 实现特点：
 * - 全局单例模式：所有 Hook 实例共享一个轮询定时器
 * - 自动清理：当最后一个订阅者卸载时，自动停止轮询
 * - 错误恢复：与 NetworkContext 联动，网络故障时主动更新状态
 * - 防并发：内置防护机制避免轮询重叠堆叠
 * 
 * 使用场景：
 * - NeuralLinkAlert 组件显示网络状态指示器
 * - 系统监控面板展示后台任务状态
 * - 任何需要实时监听系统健康度的组件
 * 
 * @example
 * const status = useNeuralLinkStatus({ enabled: true, intervalMs: 5000 });
 * return <div>链接: {status.neural_link}, 状态: {status.quantum_state}</div>;
 */

import { useEffect, useState } from 'react';
import { API_BASE } from '@/lib/config';

export type NeuralLink = 'probing' | 'active' | 'offline';
export type QuantumState = 'stable' | 'syncing' | 'processing' | 'degraded';

export interface NeuralLinkStatus {
  neural_link: NeuralLink;
  quantum_state: QuantumState;
  updated_at: number;
}

type Listener = (s: NeuralLinkStatus) => void;

const DEFAULT_STATE: NeuralLinkStatus = {
  neural_link: 'probing',
  quantum_state: 'stable',
  updated_at: 0,
};

// 全局状态容器（所有 Hook 实例共享）
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

/**
 * 单次探活采样
 * 检测 API 可用性和后台任务运行状态
 */
async function sampleOnce(signal: AbortSignal, busy: boolean) {
  if (_inflight) return;
  _inflight = true;
  try {
    // 步骤 1: 轻量探活，检测 API 是否可用
    await fetchJson(`${API_BASE}/system/stats`, signal);
    const link: NeuralLink = 'active';

    // 步骤 2: 查询后台任务运行状态
    const [scan, scrape, sub] = await Promise.all([
      fetchJson(`${API_BASE}/tasks/scan/status`, signal),
      fetchJson(`${API_BASE}/tasks/scrape_all/status`, signal),
      fetchJson(`${API_BASE}/tasks/find_subtitles/status`, signal),
    ]);

    // 步骤 3: 决定量子态
    // - 若前端繁忙则返回 processing
    // - 若任何后台任务在运行则返回 syncing
    // - 否则返回 stable
    const anyRunning = Boolean(scan?.is_running || scrape?.is_running || sub?.is_running);
    const q: QuantumState = busy ? 'processing' : anyRunning ? 'syncing' : 'stable';

    emit({
      neural_link: link,
      quantum_state: q,
      updated_at: Date.now(),
    });
  } catch {
    // 采样失败时标记离线和降级状态
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

/**
 * 启动全局轮询（如果尚未启动）
 * 支持自动清理：当最后一个订阅者卸载时停止轮询
 */
function ensurePolling(options?: { enabled?: boolean; intervalMs?: number; busy?: boolean }) {
  const enabled = options?.enabled ?? true;
  if (!enabled) return;
  if (_timer !== null) return;

  const intervalMs = options?.intervalMs ?? 5000;
  const controller = new AbortController();

  const tick = () => {
    void sampleOnce(controller.signal, Boolean(options?.busy));
  };

  tick();
  _timer = window.setInterval(tick, intervalMs);

  // 监听网络事件，与 NetworkContext 联动
  const onDown = () => {
    emit({
      neural_link: 'offline',
      quantum_state: 'degraded',
      updated_at: Date.now(),
    });
  };
  
  const onUp = () => {
    // 网络恢复时主动更新链接状态，但量子态由下次轮询决定
    emit({
      ..._state,
      neural_link: 'active',
      updated_at: Date.now(),
    });
    tick();
  };

  window.addEventListener('neon-network-down', onDown as EventListener);
  window.addEventListener('neon-network-up', onUp as EventListener);

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

