/**
 * MiniLog - 仪表盘全息数据流日志面板
 *
 * 职责：
 * - 实时拉取后端日志（由 useLogs hook 提供）
 * - 过滤噪音日志（心跳请求、配置获取等高频无意义日志）
 * - 白名单过滤：只显示带业务标签的日志（[SCAN]/[TMDB]/[SUBTITLE] 等）
 * - 日志不足 8 条时用占位文本填充，保证视觉高度
 * - 有新日志时自动平滑滚动到底部
 *
 * v1.0.0 美学口径：
 * - 视觉域为 **Holographic Void**（霓虹青为主），此组件仅承载“数据流”语义，不引入废土装甲/黄色主视觉。
 *
 * 性能红线：
 * - 过滤/补全逻辑必须保持纯函数 + `useMemo`，禁止在 render 期执行高昂计算。
 * - 行渲染使用 `React.memo`，避免父组件刷新导致日志全量重绘。
 */
'use client';

import { useEffect, useRef, memo, useMemo } from 'react';
import { Terminal } from 'lucide-react';
import type { LogEntry } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';
import { useLogs } from '@/hooks/useLogs';
import { useNeuralLinkStatus } from '@/hooks/useNeuralLinkStatus';

// ── 纯函数提升到组件外：避免每次渲染重新创建，确保 React.memo 有效 ──
function levelColor(level: string): string {
  switch ((level || '').toUpperCase()) {
    case 'ERROR': return 'text-cyber-red';
    case 'WARNING': return 'text-cyber-yellow';
    case 'DEBUG': return 'text-cyber-cyan/40';
    default: return 'text-cyber-cyan';
  }
}

function levelBorderColor(level: string): string {
  switch ((level || '').toUpperCase()) {
    case 'ERROR': return 'border-cyber-red shadow-[0_0_8px_rgba(255,0,60,0.6)]';
    case 'WARNING': return 'border-cyber-yellow shadow-[0_0_6px_rgba(255,215,0,0.4)]';
    case 'DEBUG': return 'border-cyber-cyan/20';
    default: return 'border-cyber-cyan/30';
  }
}

function safeMessage(msg: unknown): string {
  if (typeof msg === 'object' && msg !== null) return JSON.stringify(msg);
  return String(msg || '');
}

// ── React.memo 记忆化日志行：key 由时间戳保证唯一，避免全量重绘 ──
const LogRow = memo(function LogRow({ log, idx }: { log: LogEntry; idx: number }) {
  return (
    <div
      className={`terminal-row text-cyber-cyan py-2 px-3 bg-black/20 border-l-2 ${levelBorderColor(log.level)} hover:border-cyber-cyan hover:bg-black/40 hover:shadow-[0_0_12px_rgba(0,230,246,0.3)] transition-all duration-200`}
    >
      <span className="text-cyber-cyan/50 mr-3">[{String(idx + 1).padStart(2, '0')}]</span>
      <span className={levelColor(log.level)}>[{log.level}]</span>
      <span className="text-cyber-cyan/90 ml-2">{safeMessage(log.message)}</span>
    </div>
  );
});

/** 最多展示最新 50 条过滤后日志，防止 DOM 节点过多影响性能 */
const MINI_LOG_LINES = 50;
/** 最少展示行数，不足时用占位文本补全以保证视觉高度 */
const MIN_DISPLAY_LINES = 8;

export default function MiniLog() {
  const { t } = useLanguage();
  const { logs, error } = useLogs();
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
  const containerRef = useRef<HTMLDivElement>(null);

  // 防御性数据处理：确保 logs 始终是数组
  const safeLogs = Array.isArray(logs) ? logs : [];

  // [Action 3 修复] filteredLogs 和 displayLogs 包裹进 useMemo，
  // 避免每次父组件渲染都重新执行高昂的 filter + slice + 补全逻辑。
  const { filteredLogs, displayLogs } = useMemo(() => {
    const placeholderMessages = [
      'Holographic matrix stabilized',
      'Scanning deep space coordinates',
      'Signal detected at quantum layer',
      'Decrypting transmission stream',
      'Data stream integrity verified',
      'Void navigation systems online',
      'All holographic nodes synchronized',
      'System monitoring active',
    ];

    const filtered = safeLogs
      .filter((log) => {
        const msg = (log.message || '').toString();
        const isNoise =
          msg.includes('成功获取系统配置') ||
          msg.includes('GET /api/v1/tasks') ||
          msg.includes('GET /api/v1/system/stats') ||
          msg.includes('搜索关键词') ||
          (msg.includes('[API]') && msg.includes('返回任务数'));
        if (isNoise) return false;
        const whitelistKeywords = [
          '[SCAN]', '[TMDB]', '[SUBTITLE]', '[ORG]', '[ORGANIZER]',
          '[CLEAN]', '[LLM]', '[AI]', '[AI-EXEC]', '[META]',
          '[DB]', '[SECURITY]', '[API]', '[ERROR]', '[DEBUG]',
        ];
        return whitelistKeywords.some((tag) => msg.includes(tag));
      })
      .slice(-MINI_LOG_LINES);

    const display: LogEntry[] = [...filtered];
    while (display.length < MIN_DISPLAY_LINES) {
      display.push({
        level: 'INFO',
        message: placeholderMessages[display.length % placeholderMessages.length],
        timestamp: new Date().toISOString(),
      } as LogEntry);
    }

    return { filteredLogs: filtered, displayLogs: display };
  }, [safeLogs]);

  // 自动滚动优化：安全检查 Ref 是否已绑定
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredLogs.length]);

  return (
    <div
      className="relative bg-transparent border border-cyber-cyan/50 p-6 overflow-hidden"
      style={{ backdropFilter: 'blur(25px)', boxShadow: '0 0 40px rgba(0, 230, 246, 0.4), inset 0 0 40px rgba(0, 230, 246, 0.08)' }}
    >
      {/* CRT 扫描线装饰 */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 230, 246, 0.02) 2px, rgba(0, 230, 246, 0.02) 4px)',
          zIndex: 1
        }}
      />
      
      <div className="mb-4 flex items-start justify-between gap-4 relative z-10">
        <div className="flex items-center gap-3">
        <Terminal className="w-6 h-6 text-cyber-cyan" />
        <h3 className="text-xl font-bold text-cyber-cyan uppercase tracking-widest">
          {t('ui_holographic_stream')}
        </h3>
        </div>
        <div className="text-[11px] font-mono tracking-wider text-cyber-cyan/50 whitespace-nowrap pt-1">
          {neuralStatusText}
        </div>
      </div>
      <div ref={containerRef} className="space-y-2 font-mono text-sm h-[300px] overflow-y-auto relative z-10" style={{ contain: 'content' }}>
        {error && (
          <div className="text-cyber-red py-2 px-3 bg-black/20 border-l-2 border-cyber-red shadow-[0_0_8px_rgba(255,0,60,0.6)]">
            {error}
          </div>
        )}
        {displayLogs.map((log, idx) => (
          <LogRow
            key={log.timestamp ? `${log.timestamp}-${idx}` : `placeholder-${idx}`}
            log={log}
            idx={idx}
          />
        ))}
      </div>
      
      <style jsx>{`
        @keyframes terminal-entry {
          from { 
            opacity: 0; 
            transform: translateX(-10px); 
            filter: brightness(1.8);
          }
          to { 
            opacity: 1; 
            transform: translateX(0); 
            filter: brightness(1);
          }
        }
        
        .terminal-row {
          animation: terminal-entry 0.2s ease-out forwards;
        }
      `}</style>
    </div>
  );
}
