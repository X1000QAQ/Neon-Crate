/**
 * MediaTable - 媒体任务三重折叠列表
 * Level 1: 作品根节点 (电影/剧集)
 * Level 2: 季节点 (仅剧集)
 * Level 3: 单集节点 (仅剧集)
 * 补录三剑客: 📄 NFO / 🖼️ 海报 / ⌨️ 字幕 — 放在"创建时间"时间戳正下方
 */
'use client';

import { useState, memo, useMemo, useCallback } from 'react';
import {
  Film, Tv, RefreshCw, Trash2, AlertCircle,
  ChevronDown, ChevronRight, FileText, Image, Subtitles,
} from 'lucide-react';
import SecureImage from '@/components/common/SecureImage';
import RebuildDialog, { type RebuildMode } from './RebuildDialog';
import type { Task } from '@/types';
import { cn, formatDate } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';

// ── 进度计算 ──────────────────────────────────────────────────────────
function getProgress(status: string, subStatus?: string | null): number {
  const s = (status || '').toLowerCase();
  const ss = (subStatus || '').toLowerCase();
  if (s === 'pending') return 30;
  if (s === 'archived' || s === 'scraped') {
    if (ss === 'scraped' || ss === 'found' || ss === 'success') return 100;
    return 60;
  }
  return 0;
}

// ── 分组数据结构 ──────────────────────────────────────────────────────
interface MediaGroup {
  key: string;
  media_type: 'movie' | 'tv';
  task?: Task;                       // 电影：直接存单条
  seasons: Map<number, Task[]>;      // 剧集：season → episodes
  total_count: number;
  archived_count: number;
  poster_path?: string;
  tmdb_id?: number;
  title?: string;
  clean_name?: string;
}

// ── Props ─────────────────────────────────────────────────────────────
export interface MediaTableProps {
  loading: boolean;
  tasks: Task[];
  selectedIds: Set<number>;
  onToggleSelect: (id: number) => void;
  onSelectAll: () => void;
  onInvertSelection: () => void;
  isAllSelected: boolean;
  isSomeSelected: boolean;
  onRetry: (taskId: number) => void;
  onDelete: (taskId: number) => void;
  onRebuild: (params: {
    task_id: number;
    is_archive: boolean;
    media_type: string;
    refix_nfo: boolean;
    refix_poster: boolean;
    refix_subtitle: boolean;
    keyword_hint?: string;
    tmdb_id?: number;
    nuclear_reset?: boolean;
    season?: number;
    episode?: number;
  }) => Promise<void>;
}

// ── 状态色 ───────────────────────────────────────────────────────────
function getStatusColor(status: string) {
  const s = (status || '').toLowerCase();
  if (s === 'archived') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
  if (s === 'failed') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
  if (s === 'ignored') return 'border-orange-400 text-orange-400 bg-orange-400/10 font-mono';
  return 'border-cyber-cyan/30 text-cyber-cyan/70 bg-cyber-cyan/5';
}
function getSubStatusColor(sub?: string | null) {
  const s = (sub ?? '').toLowerCase();
  if (s === 'scraped' || s === 'success' || s === 'found') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
  if (s === 'failed' || s === 'missing') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
  return 'border-cyber-cyan/20 text-cyber-cyan/50 bg-cyber-cyan/5';
}

// ── 补录按钮是否可用 ─────────────────────────────────────────────────
function canRebuild(status: string) {
  const s = (status || '').toLowerCase();
  return s === 'archived' || s === 'failed';
}

// ── 单集行（Level 3 / 电影叶节点）────────────────────────────────────
interface TaskRowProps {
  task: Task;
  indent?: number;
  onRetry: (id: number) => void;
  onDelete: (id: number) => void;
  onRebuildClick: (task: Task, mode: RebuildMode) => void;
  rebuildingId: number | null;
  processingId: number | null;
  setProcessingId: (id: number | null) => void;
}

const TaskRow = memo(function TaskRow({
  task, indent = 0, onRetry, onDelete, onRebuildClick,
  rebuildingId, processingId, setProcessingId,
}: TaskRowProps) {
  const { t } = useLanguage();

  const getPosterUrl = (t: Task) => t.local_poster_path || t.poster_path || '/placeholder-poster.jpg';

  const rawName = task.file_name || task.file_path?.split(/[/\\]/).pop() || '-';
  const noiseRe = /\b(4k|2160p|1080p|720p|480p|360p)\b/i;
  const _bestName = task.title || task.clean_name;
  const hasTitle = !!_bestName && _bestName !== rawName && !noiseRe.test(_bestName);
  let displayTitle = hasTitle ? _bestName : rawName;
  if (hasTitle) {
    if (task.year) displayTitle += ` (${task.year})`;
    if (task.media_type === 'tv') {
      const s = task.season, e = task.episode;
      if (s != null && e != null) displayTitle += ` S${String(s).padStart(2,'0')}E${String(e).padStart(2,'0')}`;
      else if (s != null) displayTitle += ` Season ${s}`;
    }
  }

  const isArchived = (task.status || '').toLowerCase() === 'archived';
  const rebuildable = canRebuild(task.status);
  const isRebuilding = rebuildingId === task.id;

  const progress = getProgress(task.status, task.sub_status);
  const progressColor = progress === 100
    ? 'from-cyber-cyan to-green-400'
    : 'from-cyber-cyan to-[rgba(0,230,246,0.5)]';

  return (
    <div
      className="relative border border-cyber-cyan/30 p-3 hover:border-cyber-cyan hover:bg-cyber-cyan/5 transition-all"
      style={{
        marginLeft: indent,
        backdropFilter: 'blur(25px)',
        boxShadow: '0 0 30px rgba(6,182,212,0.15)',
      }}
    >
      <div className="flex items-center gap-3">
        {/* 海报 */}
        <div className="relative w-14 h-20 flex-shrink-0 overflow-hidden border border-cyber-cyan/40">
          <SecureImage
            src={getPosterUrl(task)}
            alt={task.title || task.clean_name || rawName}
            width={56} height={80}
            className="object-cover w-full h-full opacity-80"
            fallback={
              <div className="w-full h-full flex items-center justify-center bg-black/40">
                {task.media_type === 'movie' ? <Film className="text-cyber-cyan/30" size={18}/> : <Tv className="text-cyber-cyan/30" size={18}/>}
              </div>
            }
          />
        </div>

        {/* 信息区 */}
        <div className="flex-1 min-w-0 flex items-center gap-3">
          {/* 标题+路径 */}
          <div className="flex-1 min-w-0">
            {/* ── 标题行：TMDB 确认片名 + 年份 + 季集号 ──
                业务链路：1. 判断是否有 TMDB 标题 -> 2. 若有则拼接年份和季集号 -> 3. 否则使用原始文件名
            */}
            <h4 className="font-semibold text-sm truncate text-cyber-yellow" style={{textShadow:'0 0 8px rgba(249,240,2,0.4)'}} title={displayTitle}>
              {displayTitle}
            </h4>
            
            {/* ── 原始文件名行：下载源中的原始文件名 ──
                业务链路：1. 从 task.file_name 读取 -> 2. 若无则从 task.file_path 提取文件名 -> 3. 显示为灰色副标题
            */}
            <p className="text-xs truncate mt-0.5 text-cyber-cyan/50" title={rawName}>{rawName}</p>
            
            {/* 🚀 今生：目标入库路径 (置于上方)
                业务链路：1. 检查 task.target_path 是否存在 -> 2. 若存在则显示为"入库路径" -> 3. 使用 t('path_dst') 获取多语言标签
            */}
            {task.target_path && (
              <p className="text-cyber-cyan/30 text-xs truncate mt-1" title={task.target_path}>
                <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_dst')}:</span>{task.target_path}
              </p>
            )}
            
            {/* 前世：原始绝对路径 (置于下方)
                业务链路：1. 显示 task.file_path（下载源中的原始路径）-> 2. 使用 t('path_src') 获取多语言标签 -> 3. 用于追溯文件来源
            */}
            <p className="text-cyber-cyan/40 text-xs truncate mt-0.5" title={task.file_path}>
              <span className="text-cyber-cyan/60 font-mono mr-1">{t('path_src')}:</span>{task.file_path}
            </p>
          </div>

          {/* 状态标签 */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className={cn('px-2 py-0.5 text-xs font-semibold border', getStatusColor(task.status))}>
              {t(('status_' + task.status.toLowerCase()) as Parameters<typeof t>[0]) || task.status}
            </span>
            <span className={cn('px-2 py-0.5 text-xs font-semibold border', getSubStatusColor(task.sub_status))}>
              {t(('sub_status_' + (task.sub_status || 'pending').toLowerCase()) as Parameters<typeof t>[0]) || task.sub_status || 'pending'}
            </span>
          </div>

          {/* 外链 */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {task.tmdb_id && (
              <a href={`https://www.themoviedb.org/${task.media_type === 'tv' ? 'tv' : 'movie'}/${task.tmdb_id}`}
                target="_blank" rel="noopener noreferrer"
                className="px-2 py-0.5 text-xs border border-cyber-cyan/60 text-cyber-cyan/70 hover:bg-cyber-cyan hover:text-black transition-all">TMDB</a>
            )}
            {task.imdb_id && (
              <a href={`https://www.imdb.com/title/${task.imdb_id}`}
                target="_blank" rel="noopener noreferrer"
                className="px-2 py-0.5 text-xs border border-yellow-400/60 text-yellow-400/70 hover:bg-yellow-400 hover:text-black transition-all">IMDb</a>
            )}
          </div>

          {/* 时间戳 + 补录三剑客 — 绝对约束：三剑客在时间戳正下方 */}
          <div className="flex-shrink-0 flex flex-col items-end gap-1">
            <span className="text-cyber-cyan/50 text-xs whitespace-nowrap">
              {task.created_at ? formatDate(task.created_at) : t('task_just_now')}
            </span>
            {/* 补录三剑客 */}
            {rebuildable && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => onRebuildClick(task, 'nfo')}
                  disabled={isRebuilding}
                  title={t('tooltip_rebuild_nfo')}
                  className={cn(
                    'p-1 border text-xs transition-all',
                    isRebuilding ? 'border-cyber-cyan/20 text-cyber-cyan/20 cursor-wait'
                      : 'border-cyber-cyan/50 text-cyber-cyan/70 hover:border-cyber-cyan hover:bg-cyber-cyan/10'
                  )}
                >
                  <FileText size={12}/>
                </button>
                <button
                  onClick={() => onRebuildClick(task, 'poster')}
                  disabled={isRebuilding}
                  title={t('tooltip_rebuild_poster')}
                  className={cn(
                    'p-1 border text-xs transition-all',
                    isRebuilding ? 'border-purple-400/20 text-purple-400/20 cursor-wait'
                      : 'border-purple-400/50 text-purple-400/70 hover:border-purple-400 hover:bg-purple-400/10'
                  )}
                >
                  <Image size={12}/>
                </button>
                <button
                  onClick={() => onRebuildClick(task, 'subtitle')}
                  disabled={isRebuilding}
                  title={t('tooltip_trigger_subtitle')}
                  className={cn(
                    'p-1 border text-xs transition-all',
                    isRebuilding ? 'border-green-400/20 text-green-400/20 cursor-wait'
                      : 'border-green-400/50 text-green-400/70 hover:border-green-400 hover:bg-green-400/10'
                  )}
                >
                  <Subtitles size={12}/>
                </button>
              </div>
            )}
          </div>

          {/* 操作按钮 */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {task.status === 'failed' && (
              <button
                onClick={async () => { if (processingId !== null) return; setProcessingId(task.id); try { await Promise.resolve(onRetry(task.id)); } finally { setProcessingId(null); } }}
                disabled={processingId === task.id}
                className={cn('p-1.5 border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all', processingId === task.id && 'opacity-50 cursor-not-allowed')}
                title={t('btn_retry')}
              >
                <RefreshCw size={14} className={cn(processingId === task.id && 'animate-spin')}/>
              </button>
            )}
            <button
              onClick={async () => { if (processingId !== null) return; setProcessingId(task.id); try { await Promise.resolve(onDelete(task.id)); } finally { setProcessingId(null); } }}
              disabled={processingId === task.id}
              className={cn('p-1.5 border border-cyber-red text-cyber-red hover:bg-cyber-red hover:text-white transition-all', processingId === task.id && 'opacity-50 cursor-not-allowed')}
              title={t('task_delete_record')}
            >
              <Trash2 size={14} className={cn(processingId === task.id && 'animate-pulse')}/>
            </button>
          </div>
        </div>
      </div>

      {/* 进度条 */}
      {progress > 0 && (
        <div className="relative h-1 bg-cyber-cyan/10 border-t border-cyber-cyan/20 mt-2 overflow-hidden">
          <div
            className={`absolute inset-y-0 left-0 bg-gradient-to-r ${progressColor} transition-all duration-700`}
            style={{ width: `${progress}%`, boxShadow: '0 0 8px rgba(0,230,246,0.8)' }}
          />
        </div>
      )}
    </div>
  );
});

// ── 主组件 ───────────────────────────────────────────────────────────
function MediaTable({
  loading, tasks, selectedIds,
  onToggleSelect, onSelectAll, onInvertSelection,
  isAllSelected, isSomeSelected,
  onRetry, onDelete, onRebuild,
}: MediaTableProps) {
  const { t } = useLanguage();
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [rebuildingId, setRebuildingId] = useState<number | null>(null);

  // RebuildDialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogTask, setDialogTask] = useState<Task | null>(null);
  const [dialogMode, setDialogMode] = useState<RebuildMode>('nfo');

  // Accordion open state: Set of group keys (L1) and season keys "key:season" (L2)
  const [openL1, setOpenL1] = useState<Set<string>>(new Set());
  const [openL2, setOpenL2] = useState<Set<string>>(new Set());

  // useMemo grouping — O(n) single pass
  const groups = useMemo((): MediaGroup[] => {
    const map = new Map<string, MediaGroup>();
    for (const task of tasks) {
      // 分组键加入 media_type 命名空间，防止同名电影与剧集被错误合并
      const mtype = task.media_type || 'movie';
      const key = `${mtype}::${(task.title || task.clean_name || task.file_name || String(task.id)).trim()}`;
      if (!map.has(key)) {
        map.set(key, {
          key,
          media_type: mtype as 'movie' | 'tv',
          seasons: new Map(),
          total_count: 0,
          archived_count: 0,
          poster_path: task.local_poster_path || task.poster_path,
          tmdb_id: task.tmdb_id,
          title: task.title,
          clean_name: task.clean_name,
        });
      }
      const g = map.get(key)!;
      g.total_count++;
      if ((task.status || '').toLowerCase() === 'archived') g.archived_count++;
      if (!g.poster_path) g.poster_path = task.local_poster_path || task.poster_path;
      if (mtype === 'movie') {
        g.task = task;
      } else {
        const s = task.season ?? 1;
        if (!g.seasons.has(s)) g.seasons.set(s, []);
        g.seasons.get(s)!.push(task);
      }
    }
    return Array.from(map.values());
  }, [tasks]);

  const toggleL1 = useCallback((key: string) => {
    setOpenL1(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }, []);
  const toggleL2 = useCallback((key: string) => {
    setOpenL2(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }, []);

  const handleRebuildClick = useCallback((task: Task, mode: RebuildMode) => {
    setDialogTask(task);
    setDialogMode(mode);
    setDialogOpen(true);
  }, []);

  const handleRebuildConfirm = useCallback(async (params: { tmdb_id?: number; media_type: string; nuclear_reset: boolean; season?: number; episode?: number }) => {
    if (!dialogTask) return;
    setRebuildingId(dialogTask.id);
    try {
      await onRebuild({
        task_id: dialogTask.id,
        is_archive: (dialogTask.status || '').toLowerCase() === 'archived',
        media_type: params.media_type,
        refix_nfo: dialogMode === 'nfo',
        refix_poster: dialogMode === 'poster',
        refix_subtitle: dialogMode === 'subtitle',
        tmdb_id: params.tmdb_id,
        nuclear_reset: params.nuclear_reset,
        season: params.season,
        episode: params.episode,
      });
    } finally {
      setRebuildingId(null);
    }
  }, [dialogTask, dialogMode, onRebuild]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="border border-cyber-cyan/30 p-3 animate-pulse" style={{ backdropFilter: 'blur(25px)' }}>
            <div className="flex gap-3">
              <div className="w-14 h-20 bg-cyber-cyan/10 border border-cyber-cyan/30" />
              <div className="flex-1 space-y-2 py-1">
                <div className="h-4 bg-cyber-cyan/10 rounded w-2/3" />
                <div className="h-3 bg-cyber-cyan/10 rounded w-1/2" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="border border-cyber-cyan/50 p-12 text-center" style={{ backdropFilter: 'blur(20px)', boxShadow: '0 0 40px rgba(6,182,212,0.4)' }}>
        <AlertCircle className="mx-auto mb-4 text-cyber-cyan/60" size={48} />
        <p className="text-cyber-cyan text-lg font-semibold">{t('no_data')}</p>
        <p className="text-cyber-cyan/60 text-sm mt-2">{t('task_no_data_hint')}</p>
      </div>
    );
  }

  return (
    <>
      {/* Batch toolbar */}
      <div className="border-b border-cyber-cyan/50 p-2 mb-1" style={{ backdropFilter: 'blur(15px)' }}>
        <div className="flex items-center gap-3">
          <input type="checkbox" checked={isAllSelected}
            onChange={() => isAllSelected ? onInvertSelection() : onSelectAll()}
            ref={el => { if (el) el.indeterminate = isSomeSelected && !isAllSelected; }}
            className="rounded border-cyber-cyan/40 bg-transparent text-cyber-cyan focus:ring-cyber-cyan"
          />
          <button onClick={onSelectAll} className="text-xs text-cyber-cyan/70 hover:text-cyber-cyan font-semibold">{t('select_all_page')}</button>
          <span className="text-cyber-cyan/30">|</span>
          <button onClick={onInvertSelection} className="text-xs text-cyber-cyan/70 hover:text-cyber-cyan font-semibold">{t('invert_page')}</button>
        </div>
      </div>

      {/* Groups */}
      <div className="space-y-2">
        {groups.map(group => {
          const l1Open = openL1.has(group.key);
          const posterSrc = group.poster_path || '/placeholder-poster.jpg';

          return (
            <div key={group.key} className="border border-cyber-cyan/40" style={{ backdropFilter: 'blur(20px)' }}>
              {/* ── Level 1: 作品根节点 ── */}

              {/* 电影：直接平铺，无折叠箭头，无手风琴 */}
              {group.media_type === 'movie' && group.task && (
                <TaskRow
                  task={group.task}
                  indent={0}
                  onRetry={onRetry}
                  onDelete={onDelete}
                  onRebuildClick={handleRebuildClick}
                  rebuildingId={rebuildingId}
                  processingId={processingId}
                  setProcessingId={setProcessingId}
                />
              )}

              {/* 剧集：折叠按钮 + Level 2/3 嵌套手风琴 */}
              {group.media_type === 'tv' && (
                <>
                  <button
                    onClick={() => toggleL1(group.key)}
                    className="w-full flex items-center gap-3 p-3 hover:bg-cyber-cyan/5 transition-all text-left"
                  >
                    {l1Open ? <ChevronDown size={16} className="text-cyber-cyan/60 flex-shrink-0" /> : <ChevronRight size={16} className="text-cyber-cyan/60 flex-shrink-0" />}
                    {/* 缩略海报 */}
                    <div className="w-10 h-14 flex-shrink-0 border border-cyber-cyan/40 overflow-hidden">
                      <SecureImage src={posterSrc} alt={group.title || group.key}
                        width={40} height={56} className="object-cover w-full h-full opacity-80"
                        fallback={<div className="w-full h-full flex items-center justify-center bg-black/40"><Tv size={14} className="text-cyber-cyan/40"/></div>}
                      />
                    </div>
                    {/* 作品信息 */}
                    <div className="flex-1 min-w-0">
                      <p className="font-bold text-cyber-cyan truncate" style={{ textShadow: '0 0 8px rgba(0,230,246,0.5)' }}>
                        {group.title || group.clean_name || group.key.split('::')[1]}
                      </p>
                      <p className="text-xs text-cyber-cyan/50 mt-0.5">
                        {t('text_tv_episodes_count').replace('{count}', String(group.total_count))}
                        {' · '}
                        <span className="text-cyber-cyan/70">{group.archived_count}/{group.total_count} {t('text_archived')}</span>
                      </p>
                    </div>
                    {/* 总进度条 */}
                    <div className="flex-shrink-0 w-24">
                      <div className="h-1.5 bg-cyber-cyan/10 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-cyber-cyan to-green-400 transition-all duration-700"
                          style={{ width: `${group.total_count ? Math.round(group.archived_count / group.total_count * 100) : 0}%` }}
                        />
                      </div>
                    </div>
                  </button>

                  {/* Level 2/3 展开内容 */}
                  <div
                    className="overflow-hidden transition-all duration-300 ease-in-out"
                    style={{ maxHeight: l1Open ? '9999px' : '0px' }}
                  >
                    <div className="border-t border-cyber-cyan/20">
                      {Array.from(group.seasons.entries()).sort(([a],[b]) => a-b).map(([season, episodes]) => {
                        const l2Key = `${group.key}:${season}`;
                        const l2Open = openL2.has(l2Key);
                        return (
                          <div key={season} className="border-b border-cyber-cyan/10 last:border-0">
                            {/* ── Level 2: 季节点 ── */}
                            <button
                              onClick={() => toggleL2(l2Key)}
                              className="w-full flex items-center gap-2 px-4 py-2 hover:bg-cyber-cyan/5 transition-all text-left"
                            >
                              {l2Open ? <ChevronDown size={14} className="text-cyber-cyan/50 flex-shrink-0" /> : <ChevronRight size={14} className="text-cyber-cyan/50 flex-shrink-0" />}
                              <span className="text-sm font-semibold text-cyber-cyan/80 uppercase tracking-wider">{`Season ${season}`}</span>
                              <span className="text-xs text-cyber-cyan/40 ml-2">{episodes.length} {t('text_episodes_count').replace('{count}', String(episodes.length))}</span>
                            </button>
                            {/* ── Level 3: 单集 ── */}
                            <div
                              className="overflow-hidden transition-all duration-300 ease-in-out"
                              style={{ maxHeight: l2Open ? '9999px' : '0px' }}
                            >
                              <div className="space-y-1 p-1 border-t border-cyber-cyan/10">
                                {episodes.sort((a,b) => (a.episode??0)-(b.episode??0)).map(ep => (
                                  <TaskRow
                                    key={ep.id}
                                    task={ep}
                                    indent={8}
                                    onRetry={onRetry}
                                    onDelete={onDelete}
                                    onRebuildClick={handleRebuildClick}
                                    rebuildingId={rebuildingId}
                                    processingId={processingId}
                                    setProcessingId={setProcessingId}
                                  />
                                ))}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* RebuildDialog */}
      {dialogTask && (
        <RebuildDialog
          open={dialogOpen}
          task={dialogTask}
          mode={dialogMode}
          onConfirm={handleRebuildConfirm}
          onClose={() => setDialogOpen(false)}
        />
      )}
    </>
  );
}

export default memo(MediaTable);
