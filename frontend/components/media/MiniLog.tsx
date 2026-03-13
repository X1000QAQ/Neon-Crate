/**
 * MiniLog - 仪表盘全息数据流日志面板
 *
 * 职责：
 * - 实时拉取后端日志（由 useLogs hook 提供）
 * - 过滤噪音日志（心跳请求、配置获取等高频无意义日志）
 * - 白名单过滤：只显示带业务标签的日志（[SCAN]/[TMDB]/[SUBTITLE] 等）
 * - 日志不足 8 条时用占位文本填充，保证视觉高度
 * - 有新日志时自动平滑滚动到底部
 */
'use client';

import { useEffect, useRef } from 'react';
import { Terminal } from 'lucide-react';
import type { LogEntry } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';
import { useLogs } from '@/hooks/useLogs';

/** 最多展示最新 50 条过滤后日志，防止 DOM 节点过多影响性能 */
const MINI_LOG_LINES = 50;
/** 最少展示行数，不足时用占位文本补全以保证视觉高度 */
const MIN_DISPLAY_LINES = 8;

export default function MiniLog() {
  const { t } = useLanguage();
  const { logs, error } = useLogs();
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 防御性数据处理：确保 logs 始终是数组
  const safeLogs = Array.isArray(logs) ? logs : [];

  const filteredLogs = safeLogs
    .filter((log) => {
      const msg = (log.message || '').toString();

      // 噪音日志定义：前端每 3 秒轮询一次后端，会产生大量心跳日志
      // 这些日志对用户无意义，过滤后才能清晰看到业务流转
      const isNoise =
        msg.includes('成功获取系统配置') ||
        msg.includes('GET /api/v1/tasks') ||
        msg.includes('GET /api/v1/system/stats') ||
        msg.includes('搜索关键词') ||
        (msg.includes('[API]') && msg.includes('返回任务数'));
      if (isNoise) return false;

      // 仅保留带关键业务标签的日志（与后端 VALID_TAGS 对齐）
      const whitelistKeywords = [
        '[SCAN]', '[TMDB]', '[SUBTITLE]', '[ORG]', '[ORGANIZER]',
        '[CLEAN]', '[LLM]', '[AI]', '[AI-EXEC]', '[META]',
        '[DB]', '[SECURITY]', '[API]', '[ERROR]', '[DEBUG]',
      ];
      return whitelistKeywords.some((tag) => msg.includes(tag));
    })
    .slice(-MINI_LOG_LINES);

  // 自动滚动优化：安全检查 Ref 是否已绑定
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredLogs.length]);

  // 如果过滤后日志不足，补充占位日志以保证视觉高度
  const displayLogs: LogEntry[] = [...filteredLogs];
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
  while (displayLogs.length < MIN_DISPLAY_LINES) {
    displayLogs.push({
      level: 'INFO',
      message: placeholderMessages[displayLogs.length % placeholderMessages.length],
      timestamp: new Date().toISOString(),
    } as LogEntry);
  }

  const levelColor = (level: string) => {
    switch ((level || '').toUpperCase()) {
      case 'ERROR': return 'text-cyber-red';
      case 'WARNING': return 'text-cyber-yellow';
      case 'DEBUG': return 'text-cyber-cyan/40';
      default: return 'text-cyber-cyan';
    }
  };

  const levelBorderColor = (level: string) => {
    switch ((level || '').toUpperCase()) {
      case 'ERROR': return 'border-cyber-red shadow-[0_0_8px_rgba(255,0,60,0.6)]';
      case 'WARNING': return 'border-cyber-yellow shadow-[0_0_6px_rgba(255,215,0,0.4)]';
      case 'DEBUG': return 'border-cyber-cyan/20';
      default: return 'border-cyber-cyan/30';
    }
  };

  // 渲染安全检查：确保 message 始终是字符串
  const safeMessage = (msg: any): string => {
    if (typeof msg === 'object' && msg !== null) {
      return JSON.stringify(msg);
    }
    return String(msg || '');
  };

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
      
      <div className="mb-4 flex items-center gap-3 relative z-10">
        <Terminal className="w-6 h-6 text-cyber-cyan" />
        <h3 className="text-xl font-bold text-cyber-cyan uppercase tracking-widest">
          {t('ui_holographic_stream')}
        </h3>
      </div>
      <div ref={containerRef} className="space-y-2 font-mono text-sm h-[300px] overflow-y-auto relative z-10">
        {error && (
          <div className="text-cyber-red py-2 px-3 bg-black/20 border-l-2 border-cyber-red shadow-[0_0_8px_rgba(255,0,60,0.6)]">
            {error}
          </div>
        )}
        {displayLogs.map((log, idx) => (
          <div
            key={log.id || log.timestamp || `log-${idx}`}
            className={`terminal-row text-cyber-cyan py-2 px-3 bg-black/20 border-l-2 ${levelBorderColor(log.level)} hover:border-cyber-cyan hover:bg-black/40 hover:shadow-[0_0_12px_rgba(0,230,246,0.3)] transition-all duration-200`}
          >
            <span className="text-cyber-cyan/50 mr-3">[{String(idx + 1).padStart(2, '0')}]</span>
            <span className={levelColor(log.level)}>[{log.level}]</span>
            <span className="text-cyber-cyan/90 ml-2">{safeMessage(log.message)}</span>
          </div>
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
