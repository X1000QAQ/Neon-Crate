'use client';

import { useEffect, useState } from 'react';
import { Terminal } from 'lucide-react';
import { api } from '@/lib/api';
import type { LogEntry } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';

const MINI_LOG_LINES = 50;
const POLL_INTERVAL_MS = 3000;
const MIN_DISPLAY_LINES = 8;

export default function MiniLog() {
  const { t } = useLanguage();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const list = await api.getSystemLogs();
        setLogs((list || []).slice(-MINI_LOG_LINES));
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    fetchLogs();
    const interval = setInterval(fetchLogs, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const filteredLogs = logs.filter((log) => {
    const msg = (log.message || '').toString();

    // 过滤掉高频心跳/状态请求日志
    const isNoise =
      msg.includes('成功获取系统配置') ||
      msg.includes('GET /api/v1/tasks') ||
      msg.includes('GET /api/v1/system/stats') ||
      msg.includes('搜索关键词') ||
      (msg.includes('[API]') && msg.includes('返回任务数'));
    if (isNoise) return false;

    // 仅保留带关键业务标签的日志
    const whitelistKeywords = [
      '[SCAN]',
      '[TMDB]',
      '[SUBTITLE]',
      '[ORG]',
      '[ORGANIZER]',
      '[CLEAN]',
      '[LLM]',
      '[AI]',
      '[AI-EXEC]',
      '[META]',
      '[DB]',
      '[SECURITY]',
      '[API]',
      '[ERROR]',
      '[WARNING]',
    ];

    return whitelistKeywords.some((tag) => msg.includes(tag));
  });

  // 如果过滤后日志不足，补充占位日志以保证视觉高度
  const displayLogs = [...filteredLogs];
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

  return (
    <div 
      className="relative bg-transparent border border-cyber-cyan/50 p-6" 
      style={{ 
        backdropFilter: 'blur(25px)', 
        boxShadow: '0 0 40px rgba(0, 230, 246, 0.4), inset 0 0 40px rgba(0, 230, 246, 0.08)' 
      }}
    >
      <div className="mb-4 flex items-center gap-3">
        <Terminal className="w-6 h-6 text-cyber-cyan" />
        <h3 
          className="text-xl font-bold text-cyber-cyan uppercase tracking-widest" 
         
        >
          {t('ui_holographic_stream')}
        </h3>
      </div>
      <div 
        className="space-y-2 font-mono text-sm h-[300px] overflow-y-auto" 
       
      >
        {error && (
          <div className="text-cyber-red py-2 px-3 bg-black/20 border-l-2 border-cyber-red">
            {error}
          </div>
        )}
        {displayLogs.map((log, idx) => (
          <div 
            key={idx} 
            className="text-cyber-cyan py-2 px-3 bg-black/20 border-l-2 border-cyber-cyan/30 hover:border-cyber-cyan hover:bg-black/40 transition-all" 
            style={{ 
              animation: `fade-in 0.3s ease-out ${idx * 0.15}s both`, 
              opacity: 0 
            }}
          >
            <span className="text-cyber-cyan/50 mr-3">
              [{String(idx + 1).padStart(2, '0')}]
            </span>
            <span className={levelColor(log.level)}>[{log.level}]</span>
            <span className="text-cyber-cyan/90 ml-2">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
