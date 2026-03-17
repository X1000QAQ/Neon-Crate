'use client';

/**
 * SystemMonitor — 全息虚空系统监控台（v1.0.0）
 *
 * 业务定位：
 * - 只做“展示与筛选”：从 `useLogs()` 获取全量日志，前端按 tag 过滤与渲染。
 * - 不做轮询、不做请求编排，避免监控面板反向制造系统压力。
 *
 * 性能约束：
 * - 大量日志渲染使用 `useMemo` 进行派生与哈希地址（`__addr`）生成，降低重渲染抖动。
 * - 自动滚动只在 `autoScroll=true` 时启用，避免用户回看时被强制拉回底部。
 */

import { useEffect, useRef, useMemo, useState } from 'react';
import { Terminal, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { LogEntry } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';
import { useLogs } from '@/hooks/useLogs';
import { useNeuralLinkStatus } from '@/hooks/useNeuralLinkStatus';

const LOG_TAGS = [
  { key: 'SCAN', labelKey: 'monitor_tag_scan' },
  { key: 'TMDB', labelKey: 'monitor_tag_scrape' },
  { key: 'SUBTITLE', labelKey: 'monitor_tag_subtitle' },
  { key: 'ORG', labelKey: 'monitor_tag_organizer' },
  { key: 'CLEAN', labelKey: 'monitor_tag_clean' },
  { key: 'LLM', labelKey: 'monitor_tag_llm' },
  { key: 'AI', labelKey: 'monitor_tag_ai' },
  { key: 'META', labelKey: 'monitor_tag_meta' },
  { key: 'DB', labelKey: 'monitor_tag_db' },
  { key: 'SECURITY', labelKey: 'monitor_tag_security' },
  { key: 'API', labelKey: 'monitor_tag_api' },
  { key: 'ERROR', labelKey: 'monitor_tag_error' },
] as const;

type RenderedLogEntry = LogEntry & { __addr: string };

function hashToHex(input: string) {
  let h = 2166136261; // FNV-1a like
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const hex = (h >>> 0).toString(16).toUpperCase().padStart(4, '0');
  return `0x${hex.slice(-4)}`;
}

function levelToColor(level: string) {
  switch (level) {
    case 'INFO':
      return 'text-cyber-cyan';
    case 'WARNING':
      return 'text-cyber-yellow';
    case 'ERROR':
      return 'text-cyber-red';
    default:
      return 'text-cyber-cyan/60';
  }
}

function levelToDot(level: string) {
  switch (level) {
    case 'INFO':
      return 'bg-cyber-cyan shadow-[0_0_10px_var(--cyber-cyan)]';
    case 'WARNING':
      return 'bg-cyber-yellow shadow-[0_0_10px_var(--cyber-yellow)]';
    case 'ERROR':
      return 'bg-cyber-red shadow-[0_0_10px_var(--cyber-red)]';
    default:
      return 'bg-white/20 shadow-[0_0_10px_rgba(255,255,255,0.15)]';
  }
}

export default function SystemMonitor() {
  const { t } = useLanguage();
  // ✅ 从 LogContext 获取全量日志，不再自行轮询
  const { logs: allLogs } = useLogs();
  const neural = useNeuralLinkStatus({ intervalMs: 2500 });
  const tr = (key: string, fallback: string) => {
    const out = (t as unknown as (k: string) => string)(key);
    return out === key ? fallback : out;
  };
  const neuralStatusText =
    `${tr('ui_quantum_state', '量子态')}: ` +
    `${tr(`status_${neural.quantum_state}`, neural.quantum_state === 'stable' ? '稳定' : neural.quantum_state === 'syncing' ? '同步中' : neural.quantum_state === 'processing' ? '演算中' : '降级')}` +
    ` | ` +
    `${tr('ui_neural_link', '神经链路')}: ` +
    `${tr(`status_${neural.neural_link}`, neural.neural_link === 'active' ? '在线' : neural.neural_link === 'offline' ? '离线' : '探活中')}`;

  const [tagFilters, setTagFilters] = useState<Record<string, boolean>>({
    SCAN: true, TMDB: true, SUBTITLE: true, ORG: true, CLEAN: true,
    LLM: true, AI: true, META: true, DB: true, SECURITY: true, API: true, ERROR: true,
  });
  const [autoScroll, setAutoScroll] = useState(true);
  // 本地清空时间戳（只显示清空后的新日志，不影响 Context 全局数据）
  const [clearedAt, setClearedAt] = useState<string | null>(null);
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // ✅ tags 改为前端过滤，不再依赖 tagsParam 触发后端请求
  const logs = useMemo(() => {
    const base = clearedAt
      ? allLogs.filter(log => log.timestamp > clearedAt)
      : allLogs;
    const activeTags = Object.entries(tagFilters).filter(([, v]) => v).map(([k]) => k);
    if (activeTags.length === 0) return base;
    return base.filter(log =>
      activeTags.some(tag =>
        (log.message || '').includes(`[${tag}]`) || log.tag === tag
      )
    );
  }, [allLogs, tagFilters, clearedAt]);

  useEffect(() => {
    if (autoScroll) {
      const el = logsContainerRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const renderedLogs: RenderedLogEntry[] = useMemo(() => {
    return logs.map<RenderedLogEntry>((log, index) => {
      const stamp = typeof log.timestamp === 'string' ? log.timestamp : String(log.timestamp);
      const addr = hashToHex(`${stamp}|${log.level}|${log.message}|${index}`);
      return { ...log, __addr: addr } satisfies RenderedLogEntry;
    });
  }, [logs]);

  const infoCount = useMemo(() => logs.filter((l) => l.level === 'INFO').length, [logs]);
  const warningCount = useMemo(() => logs.filter((l) => l.level === 'WARNING').length, [logs]);
  const errorCount = useMemo(() => logs.filter((l) => l.level === 'ERROR').length, [logs]);

  return (
    <div
      className="w-full h-full max-h-screen overflow-hidden bg-black p-6 flex flex-col min-h-0"
      style={{
        backgroundImage:
          'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 1) 70%)',
      }}
    >
      <div className="grid grid-cols-1 gap-6 flex-1 min-h-0">
        {/* Quantum Stream Panel */}
        <div
          className="flex flex-col bg-transparent border border-cyber-cyan/20 min-h-0 overflow-hidden"
          style={{
            backdropFilter: 'blur(16px)',
            boxShadow: 'inset 0 0 20px rgba(0, 230, 246, 0.05)',
          }}
        >
          {/* Header */}
          <div className="p-4 border-b border-cyber-cyan/20 flex items-start justify-between gap-6">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <Terminal className="text-cyber-cyan" size={20} />
                <div
                  className="text-cyber-cyan font-bold tracking-widest"
                  style={{ textShadow: '0 0 20px rgba(0, 230, 246, 0.8)' }}
                >
                  {t('monitor_quantum_stream')}
                </div>
                <div className="flex gap-2 ml-2">
                  <div
                    className="w-2.5 h-2.5 rounded-full bg-cyber-cyan animate-pulse"
                    style={{ boxShadow: '0 0 15px var(--cyber-cyan)' }}
                  />
                  <div
                    className="w-2.5 h-2.5 rounded-full bg-cyber-cyan animate-pulse"
                    style={{ boxShadow: '0 0 15px var(--cyber-cyan)', animationDelay: '0.5s' }}
                  />
                </div>
              </div>
              <div className="text-cyber-cyan/40 text-xs font-mono mt-1 tracking-wider">
                {t('monitor_memory_readout')}
              </div>
              <div className="text-cyber-cyan/50 text-[11px] font-mono mt-1 tracking-wider">
                {neuralStatusText}
              </div>
            </div>

            {/* Filters (aligned right, usable checkboxes) */}
            <div className="shrink-0">
              <div className="flex items-center justify-end gap-4 mb-2">
                <label className="flex items-center gap-2 text-xs font-mono text-cyber-cyan/60 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={autoScroll}
                    onChange={(e) => setAutoScroll(e.target.checked)}
                    className="w-3.5 h-3.5 accent-cyber-cyan"
                  />
                  <span className="whitespace-nowrap">{t('monitor_auto_scroll')}</span>
                </label>
                <button
                  onClick={() => setClearedAt(new Date().toISOString())}
                  className="px-2.5 py-1 bg-transparent text-cyber-cyan/70 text-xs font-mono tracking-widest border border-cyber-cyan/20 hover:border-cyber-cyan/50 hover:text-cyber-cyan transition-colors"
                  style={{ boxShadow: 'inset 0 0 20px rgba(0, 230, 246, 0.05)' }}
                >
                  {t('monitor_clear_logs')}
                </button>
              </div>
              <div className="text-cyber-cyan/50 text-xs font-mono tracking-widest mb-2">
                {t('monitor_filters')}
              </div>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
                {LOG_TAGS.map(({ key, labelKey }) => (
                  <label
                    key={key}
                    className="flex items-center gap-2 text-xs font-mono text-cyber-cyan/60 cursor-pointer select-none"
                  >
                    <input
                      type="checkbox"
                      checked={tagFilters[key] ?? true}
                      onChange={(e) => setTagFilters((prev) => ({ ...prev, [key]: e.target.checked }))}
                      className="w-3.5 h-3.5 accent-cyber-cyan"
                    />
                    <span className="whitespace-nowrap">{t(labelKey)}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* Logs */}
          <div
            ref={logsContainerRef}
            className="flex-1 overflow-y-auto p-4 font-mono text-sm bg-transparent"
          >
            {renderedLogs.length === 0 ? (
              <div className="text-center text-cyber-cyan/40 mt-8">
                <Activity className="mx-auto mb-2" size={28} />
                <p className="font-mono tracking-wider">{t('monitor_waiting_logs')}</p>
              </div>
            ) : (
              <div className="space-y-2">
                {renderedLogs.map((log, index) => (
                  <div
                    key={`${log.timestamp}-${index}`}
                    className="group px-3 py-2 border-l-2 border-cyber-cyan/10 hover:border-cyber-cyan/40 transition-all"
                    style={{
                      animation: `matrix-drop 0.45s ease-out ${Math.min(index * 0.02, 0.4)}s both`,
                      background: 'rgba(0, 0, 0, 0.15)',
                    }}
                  >
                    <div className="flex items-start gap-3">
                      {/* Dot-matrix indicator (no background labels) */}
                      <div className="mt-1 flex flex-col gap-1.5">
                        <div className={cn('w-2 h-2 rounded-full', levelToDot(log.level))} />
                        <div className="w-1.5 h-1.5 rounded-full bg-cyber-cyan/10" />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3 text-xs">
                          <span className="opacity-40">{log.__addr}</span>
                          <span className="text-cyber-cyan/60 whitespace-nowrap">
                            {new Date(log.timestamp).toLocaleTimeString('zh-CN')}
                          </span>
                          <span className={cn('font-bold tracking-widest', levelToColor(log.level))}>
                            [{log.level}]
                          </span>
                        </div>
                        <div
                          className="text-cyber-cyan font-mono tracking-tight break-words"
                          style={{
                            textShadow: '0 0 10px rgba(0, 230, 246, 0.5)',
                            animation: 'quantum-flicker 0.2s ease-out',
                          }}
                        >
                          {log.message}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            )}
          </div>

          {/* Stats Bar */}
          <div className="grid grid-cols-3 gap-4 p-4 border-t border-cyber-cyan/20 bg-transparent">
            <div className="text-center">
              <div className="text-cyber-cyan text-2xl font-bold" style={{ textShadow: '0 0 16px rgba(0, 230, 246, 0.35)' }}>
                {infoCount}
              </div>
              <div className="text-cyber-cyan/40 text-xs font-mono tracking-widest">{t('monitor_level_info')}</div>
            </div>
            <div className="text-center">
              <div
                className={cn(
                  'text-2xl font-bold',
                  warningCount > 0 ? 'text-cyber-yellow' : 'text-cyber-cyan/35'
                )}
                style={{
                  textShadow:
                    warningCount > 0
                      ? '0 0 16px rgba(249, 240, 2, 0.22)'
                      : '0 0 12px rgba(0, 230, 246, 0.18)',
                }}
              >
                {warningCount}
              </div>
              <div className="text-cyber-cyan/40 text-xs font-mono tracking-widest">{t('monitor_level_warning')}</div>
            </div>
            <div className="text-center">
              <div className="text-cyber-red text-2xl font-bold" style={{ textShadow: '0 0 16px rgba(255, 1, 60, 0.25)' }}>
                {errorCount}
              </div>
              <div className="text-cyber-cyan/40 text-xs font-mono tracking-widest">{t('monitor_level_error')}</div>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes matrix-drop {
          0% {
            opacity: 0;
            transform: translateY(-18px);
          }
          100% {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes quantum-flicker {
          0% {
            opacity: 0.6;
            filter: blur(0.6px);
          }
          40% {
            opacity: 1;
            filter: blur(0);
          }
          70% {
            opacity: 0.85;
          }
          100% {
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
