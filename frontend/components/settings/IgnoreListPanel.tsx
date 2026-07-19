'use client';

import { useCallback, useEffect, useState } from 'react';
import { EyeOff, File, FolderTree, RefreshCw, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { IgnoreRule } from '@/types';
import type { I18nKey } from '@/lib/i18n';

interface Props { t: (key: I18nKey) => string; }

export default function IgnoreListPanel({ t }: Props) {
  const [rules, setRules] = useState<IgnoreRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRules((await api.getIgnoreRules()).rules); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const remove = async (id: string) => {
    setRemoving(id);
    try { await api.deleteIgnoreRule(id); await load(); }
    finally { setRemoving(null); }
  };

  const clear = async () => {
    if (!armed) { setArmed(true); window.setTimeout(() => setArmed(false), 3000); return; }
    setArmed(false);
    setLoading(true);
    try { await api.clearIgnoreRules(); setRules([]); }
    finally { setLoading(false); }
  };

  return <div className="space-y-6">
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <EyeOff className="text-orange-400" size={22} />
        <div><h3 className="text-lg font-bold text-orange-400">{(t as (k: string) => string)('ignore_list_title')}</h3><p className="text-xs text-cyber-cyan/50">{(t as (k: string) => string)('ignore_list_desc')}</p></div>
      </div>
      <div className="flex gap-2">
        <button onClick={() => void load()} disabled={loading} className="p-2 border border-cyber-cyan/40 text-cyber-cyan"><RefreshCw size={14} className={cn(loading && 'animate-spin')} /></button>
        {rules.length > 0 && <button onClick={() => void clear()} className={cn('px-3 py-2 text-xs border', armed ? 'border-cyber-red text-cyber-red animate-pulse' : 'border-cyber-red/50 text-cyber-red/70')}><Trash2 size={13} className="inline mr-1" />{armed ? (t as (k: string) => string)('ignore_clear_confirm') : (t as (k: string) => string)('ignore_clear_all')}</button>}
      </div>
    </div>
    <div className="border border-orange-400/30 bg-orange-400/5 px-4 py-2 text-xs text-orange-400/70">{(t as (k: string) => string)('ignore_list_count').replace('{count}', String(rules.length))}</div>
    {rules.length === 0 && !loading ? <div className="py-16 text-center text-cyber-cyan/30">{(t as (k: string) => string)('ignore_list_empty')}</div> : <div className="space-y-2">{rules.map((rule) => {
      const Icon = rule.scope === 'directory' ? FolderTree : File;
      return <div key={rule.id} className="flex items-center gap-3 border border-orange-400/20 bg-orange-400/5 px-4 py-3"><Icon size={16} className="text-orange-400/70 shrink-0" /><div className="min-w-0 flex-1"><div className="text-xs text-orange-400 uppercase">{rule.scope === 'directory' ? (t as (k: string) => string)('ignore_scope_directory') : (t as (k: string) => string)('ignore_scope_file')} · {(t as (k: string) => string)('ignore_list_count').replace('{count}', String(rule.matched_task_count ?? 0))}</div><div className="font-mono text-xs text-cyber-cyan/70 truncate" title={rule.path}>{rule.path}</div></div><button onClick={() => void remove(rule.id)} disabled={removing === rule.id} className="p-1.5 border border-cyber-cyan/30 text-cyber-cyan/60"><Trash2 size={13} /></button></div>;
    })}</div>}
  </div>;
}
