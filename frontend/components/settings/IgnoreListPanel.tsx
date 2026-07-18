'use client';

import { useState, useEffect, useCallback } from 'react';
import { Trash2, RefreshCw, EyeOff, AlertTriangle } from 'lucide-react';
import type { I18nKey } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

interface IgnoreListPanelProps {
  t: (key: I18nKey) => string;
}

export default function IgnoreListPanel({ t }: IgnoreListPanelProps) {
  const [paths, setPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [removingPath, setRemovingPath] = useState<string | null>(null);
  const [clearConfirm, setClearConfirm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getIgnoreList();
      setPaths(res.paths);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRemove = async (path: string) => {
    setRemovingPath(path);
    try {
      await api.unignorePath(path);
      setPaths((prev) => prev.filter((p) => p !== path));
    } finally {
      setRemovingPath(null);
    }
  };

  const handleClearAll = async () => {
    if (!clearConfirm) {
      setClearConfirm(true);
      setTimeout(() => setClearConfirm(false), 3000);
      return;
    }
    setClearConfirm(false);
    setLoading(true);
    try {
      await Promise.all(paths.map((p) => api.unignorePath(p)));
      setPaths([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 标题区 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <EyeOff className="w-5 h-5 text-orange-400" />
          <div>
            <h3
              className="text-lg font-bold text-orange-400 uppercase tracking-widest"
              style={{ textShadow: '0 0 12px rgba(251,146,60,0.5)' }}
            >
              {(t as (k: string) => string)('ignore_list_title')}
            </h3>
            <p className="text-xs text-cyber-cyan/50 mt-0.5">
              {(t as (k: string) => string)('ignore_list_desc')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="p-2 border border-cyber-cyan/40 text-cyber-cyan/60 hover:border-cyber-cyan hover:text-cyber-cyan transition-all"
            title={(t as (k: string) => string)('btn_refresh')}
          >
            <RefreshCw size={14} className={cn(loading && 'animate-spin')} />
          </button>
          {paths.length > 0 && (
            <button
              onClick={handleClearAll}
              disabled={loading}
              className={cn(
                'flex items-center gap-2 px-3 py-2 text-xs font-bold uppercase tracking-widest border transition-all',
                clearConfirm
                  ? 'border-cyber-red text-cyber-red bg-cyber-red/10 animate-pulse'
                  : 'border-cyber-red/50 text-cyber-red/70 hover:border-cyber-red hover:text-cyber-red hover:bg-cyber-red/5'
              )}
            >
              <AlertTriangle size={12} />
              {clearConfirm
                ? (t as (k: string) => string)('ignore_clear_confirm')
                : (t as (k: string) => string)('ignore_clear_all')}
            </button>
          )}
        </div>
      </div>

      {/* 统计行 */}
      <div
        className="border border-orange-400/30 bg-orange-400/5 px-4 py-2 flex items-center justify-between text-xs"
      >
        <span className="text-orange-400/70 font-mono uppercase tracking-widest">
          {(t as (k: string) => string)('ignore_list_count').replace('{count}', String(paths.length))}
        </span>
        <span className="text-cyber-cyan/30 font-mono">data/ignore_paths.txt</span>
      </div>

      {/* 清单列表 */}
      {loading && paths.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-cyber-cyan/30 text-sm tracking-widest">
          {(t as (k: string) => string)('loading')}
        </div>
      ) : paths.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 border border-cyber-cyan/10">
          <EyeOff size={32} className="text-cyber-cyan/20" />
          <p className="text-cyber-cyan/30 text-sm tracking-widest">
            {(t as (k: string) => string)('ignore_list_empty')}
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {paths.map((path) => (
            <div
              key={path}
              className="flex items-center gap-3 border border-orange-400/20 bg-orange-400/5 px-4 py-2.5 hover:border-orange-400/50 hover:bg-orange-400/10 transition-all group"
            >
              <EyeOff size={12} className="text-orange-400/50 flex-shrink-0" />
              <span
                className="flex-1 font-mono text-xs text-cyber-cyan/60 truncate group-hover:text-cyber-cyan/80"
                title={path}
              >
                {path}
              </span>
              <button
                onClick={() => handleRemove(path)}
                disabled={removingPath === path}
                className={cn(
                  'flex-shrink-0 p-1.5 border border-cyber-cyan/30 text-cyber-cyan/40 hover:border-cyber-cyan hover:text-cyber-cyan transition-all',
                  removingPath === path && 'opacity-50 cursor-not-allowed'
                )}
                title={(t as (k: string) => string)('btn_unignore')}
              >
                {removingPath === path ? (
                  <RefreshCw size={12} className="animate-spin" />
                ) : (
                  <Trash2 size={12} />
                )}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 说明脚注 */}
      <p className="text-cyber-cyan/25 text-xs font-mono leading-relaxed border-t border-cyber-cyan/10 pt-4">
        {(t as (k: string) => string)('ignore_list_note')}
      </p>
    </div>
  );
}
