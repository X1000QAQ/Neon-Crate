/**
 * MediaTable — 等高扁平折叠列表（Flat Hierarchical List, v1.0.0）
 *
 * 业务定位：
 * - 将“电影单体任务 + 电视剧（剧 → 季 → 集）”统一压平到同一种 Row 渲染模型，层级仅由缩进表达。
 * - 为 `/tasks/manual_rebuild` 提供“补录三剑客”入口：📄 NFO / 🖼️ 海报 / ⌨️ 字幕（位于创建时间下方）。
 *
 * v1.0.0 架构语义对齐：
 * - **ignored = VHS 故障态**：当 `status === 'ignored'` 时，UI 叠加 VHS 噪点/扫描线/RGB 分离/印章层，
 *   并依赖后端在重复媒体拦截时继承 `local_poster_path`（否则会出现白板破图）。
 * - **分组状态传播**：TV 组/季状态根据子集聚合（如全 ignored 则父级也为 ignored，以维持语义一致）。
 *
 * 稳定性红线（DO NOT BREAK）：
 * - 复杂派生（分组、计数、聚合）必须由 `useMemo` 输出，避免父组件刷新造成全量重算与 UI 抖动。
 * - 任何与“ignored VHS 叠层”的结构改动，都必须保持 `pointer-events: none`，禁止阻断交互。
 */
'use client';

import { useState, memo, useMemo, useCallback, Fragment } from 'react';
import {
  Film, Tv, RefreshCw, Trash2, AlertCircle, AlertOctagon,
  ChevronDown, ChevronRight, FileText, Image, Subtitles,
} from 'lucide-react';
import SecureImage from '@/components/common/SecureImage';
import RebuildDialog, { type RebuildMode } from './RebuildDialog';
import type { Task } from '@/types';
import { cn, formatDate } from '@/lib/utils';
import type { I18nKey } from '@/lib/i18n';
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
  ignored_count: number;
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
  onDeleteBatch: (ids: number[]) => void;
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

// ── sub_status 复合字符串解析器 ──────────────────────────────────────
// 后端 rebuild 操作写入复合结构：rebuild_complete:nfo:ok;subtitle:triggered
// 此函数拦截该格式，转换为本地化标签；普通枚举值走原有 sub_status_ 路径
function formatSubStatus(raw: string | null | undefined, t: (k: I18nKey) => string): string {
  if (!raw) return t('sub_status_pending');
  // 1. 复合重构状态：rebuild_complete:nfo:ok;subtitle:triggered
  if (raw.startsWith('rebuild_complete:')) {
    const payload = raw.slice('rebuild_complete:'.length);
    const labels: string[] = [];
    for (const part of payload.split(';')) {
      if (part.startsWith('nfo:')) {
        const st = part.slice(4);
        labels.push(t('msg_nfo_rebuild').replace('{status}', st === 'ok' ? '✅' : '❌'));
      } else if (part.startsWith('poster:')) {
        const st = part.slice(7);
        labels.push(t('msg_poster_rebuild').replace('{status}', st === 'ok' ? '✅' : '❌'));
      } else if (part.startsWith('subtitle:')) {
        const st = part.slice(9);
        labels.push(st === 'triggered' ? t('msg_subtitle_triggered') : t('msg_nfo_rebuild').replace('{status}', st));
      }
    }
    return labels.length
      ? t('msg_rebuild_complete') + labels.join(' | ')
      : t('msg_rebuild_complete');
  }
  // 2. 标准枚举映射：直接查 sub_status_{raw}
  //    找不到时严禁显示 key 名，直接返回原始值（不带前缀）
  const key = ('sub_status_' + raw.toLowerCase()) as I18nKey;
  const trans = (t as (k: string) => string)(key);
  return trans !== key ? trans : raw;
}

// ── 补录按钮是否可用 ─────────────────────────────────────────────────
function canRebuild(status: string) {
  const s = (status || '').toLowerCase();
  return s === 'archived' || s === 'failed';
}

// ── UniversalMediaRow Props ─────────────────────────────────────────
interface UniversalMediaRowProps {
  level: 0 | 1 | 2;
  isExpandable?: boolean;
  isExpanded?: boolean;
  onToggle?: () => void;
  posterSrc?: string;
  title: string;
  subtitle: string;
  status?: string;
  progress?: number;
  onDelete: () => void;
  task?: Task;
  onRebuildClick?: (task: Task, mode: RebuildMode) => void;
  rebuildingId?: number | null;
  processingId?: number | null;
  setProcessingId?: (id: number | null) => void;
  onRetry?: (id: number) => void;
}

// ── UniversalMediaRow — 等高行组件（所有层级共用）────────────────────
const UniversalMediaRow = memo(function UniversalMediaRow({
  level, isExpandable, isExpanded, onToggle,
  posterSrc, title, subtitle, status = 'pending', progress,
  onDelete, task, onRebuildClick, rebuildingId, processingId,
  setProcessingId, onRetry,
}: UniversalMediaRowProps) {
  const { t } = useLanguage();

  const effectiveStatus = (task?.status ?? status ?? 'pending').toLowerCase();
  const isIgnored = effectiveStatus === 'ignored';

  const resolvedProgress = progress !== undefined
    ? progress
    : getProgress(task?.status ?? '', task?.sub_status);

  const progressColor = resolvedProgress === 100
    ? 'from-cyber-cyan to-green-400'
    : 'from-cyber-cyan to-[rgba(0,230,246,0.5)]';

  return (
    <div
      className={cn(
        "relative border border-cyber-cyan/30 p-3 hover:border-cyber-cyan hover:bg-cyber-cyan/5 transition-all",
        isIgnored && "border-orange-400/70 bg-orange-400/5 hover:border-orange-400 hover:bg-orange-400/10"
      )}
      style={{
        marginLeft: level * 32,
        backdropFilter: 'blur(25px)',
        boxShadow: '0 0 30px rgba(6,182,212,0.15)',
      }}
    >
      <div className="flex items-center gap-3">
        {/* 折叠箭头占位 */}
        <div className="flex-shrink-0 w-5 flex items-center justify-center">
          {isExpandable ? (
            <button onClick={onToggle} className="text-cyber-cyan/60 hover:text-cyber-cyan transition-colors">
              {isExpanded ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}
            </button>
          ) : null}
        </div>

        {/* 海报：严格 w-14 h-20，全层级一致 */}
        <div
          className={cn(
            "relative w-14 h-20 flex-shrink-0 overflow-hidden border border-cyber-cyan/40",
            isIgnored && "border-orange-400/70"
          )}
        >
          <SecureImage
            src={posterSrc || task?.local_poster_path || task?.poster_path || '/placeholder-poster.jpg'}
            alt={title}
            width={56} height={80}
            className={cn(
              "object-cover w-full h-full opacity-80",
              isIgnored && "vhs-filter"
            )}
            fallback={
              <div className="w-full h-full flex items-center justify-center bg-black/40">
                {task?.media_type === 'tv'
                  ? <Tv className="text-cyber-cyan/30" size={18}/>
                  : <Film className="text-cyber-cyan/30" size={18}/>}
              </div>
            }
          />

          {/* VHS Glitch — 仅 ignored 状态激活 */}
          {isIgnored && (
            <div className="absolute inset-0 pointer-events-none vhs-ignored">
              {/* VHS 噪点纹理（Demo：SVG turbulence） */}
              <div className="absolute inset-0 z-10 opacity-30 vhs-noise" />

              {/* VHS 扫描线（Demo：粗糙 5px 间距） */}
              <div className="absolute inset-0 z-20 opacity-40 vhs-scanlines" />

              {/* 磁带拉伸条（Demo：横向 tracking bar） */}
              <div className="absolute left-0 right-0 h-6 z-20 opacity-60 vhs-tracking-bar" style={{ top: '30%' }} />
              <div
                className="absolute left-0 right-0 h-5 z-20 opacity-40"
                style={{
                  top: '60%',
                  background:
                    'linear-gradient(90deg, transparent 0%, rgba(0,0,0,0.3) 30%, rgba(0,0,0,0.5) 50%, rgba(0,0,0,0.3) 70%, transparent 100%)',
                }}
              />

              {/* VHS 色彩分离（Demo：红/蓝偏移） */}
              <div className="absolute inset-0 z-25 mix-blend-screen opacity-20 vhs-rgb-red" />
              <div className="absolute inset-0 z-25 mix-blend-screen opacity-20 vhs-rgb-blue" />

              {/* 顶部时间码（Demo：REC bar） */}
              <div className="absolute top-0.5 left-0.5 right-0.5 z-30">
                <div className="px-1 py-[1px] bg-black/70 backdrop-blur-sm text-orange-400 text-[7px] font-mono leading-none">
                  ▶ REC 00:00:00:00 [CORRUPTED]
                </div>
              </div>

              {/* VHS 时间码错误印章（Demo：橙色 TAPE ERROR） */}
              <div className="absolute inset-0 flex items-center justify-center z-30">
                <div
                  className="px-1.5 py-1 bg-orange-600/80 border border-orange-400 text-white font-mono text-[8px] backdrop-blur-sm"
                  style={{
                    textShadow: '0 0 8px rgba(251, 146, 60, 0.8)',
                    boxShadow: '0 0 12px rgba(251, 146, 60, 0.55)',
                    transform: 'rotate(-8deg)',
                  }}
                >
                  <div className="flex flex-col items-center gap-0.5">
                    <AlertOctagon size={10} />
                    <span className="leading-none">TAPE ERROR</span>
                    <span className="text-[7px] opacity-70 leading-none">00:00:00:00</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 信息区 */}
        <div className="flex-1 min-w-0 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <h4 className="font-semibold text-sm truncate text-cyber-yellow"
              style={{ textShadow: '0 0 8px rgba(249,240,2,0.4)' }} title={title}>
              {title}
            </h4>
            <p className="text-xs truncate mt-0.5 text-cyber-cyan/50" title={subtitle}>{subtitle}</p>
            {task?.target_path && (
              <p className="text-cyber-cyan/30 text-xs truncate mt-1" title={task.target_path}>
                <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_dst')}:</span>{task.target_path}
              </p>
            )}
            {task?.file_path && (
              <p className="text-cyber-cyan/40 text-xs truncate mt-0.5" title={task.file_path}>
                <span className="text-cyber-cyan/60 font-mono mr-1">{t('path_src')}:</span>{task.file_path}
              </p>
            )}
          </div>

          {/* 状态标签 */}
          {task ? (
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span className={cn('px-2 py-0.5 text-xs font-semibold border', getStatusColor(task.status))}>
                {t(('status_' + task.status.toLowerCase()) as Parameters<typeof t>[0]) || task.status}
              </span>
              <span className={cn('px-2 py-0.5 text-xs font-semibold border', getSubStatusColor(task.sub_status))}>
                {formatSubStatus(task.sub_status, t)}
              </span>
            </div>
          ) : (
            <span className={cn('px-2 py-0.5 text-xs font-semibold border flex-shrink-0', getStatusColor(status))}>
              {t(('status_' + status.toLowerCase()) as Parameters<typeof t>[0]) || status}
            </span>
          )}

          {/* 外链 */}
          {task && (
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
          )}

          {/* 时间戳 + 补录三剑客（仅 task 节点）*/}
          {task && onRebuildClick && (
            <div className="flex-shrink-0 flex flex-col items-end gap-1">
              <span className="text-cyber-cyan/50 text-xs whitespace-nowrap">
                {task.created_at ? formatDate(task.created_at) : t('task_just_now')}
              </span>
              {canRebuild(task.status) && (
                <div className="flex items-center gap-1">
                  <button onClick={(e) => { e.stopPropagation(); onRebuildClick(task, 'nfo'); }} disabled={rebuildingId === task.id}
                    title={t('tooltip_rebuild_nfo')}
                    className={cn('p-1 border text-xs transition-all',
                      rebuildingId === task.id ? 'border-cyber-cyan/20 text-cyber-cyan/20 cursor-wait'
                        : 'border-cyber-cyan/50 text-cyber-cyan/70 hover:border-cyber-cyan hover:bg-cyber-cyan/10')}>
                    <FileText size={12}/>
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); onRebuildClick(task, 'poster'); }} disabled={rebuildingId === task.id}
                    title={t('tooltip_rebuild_poster')}
                    className={cn('p-1 border text-xs transition-all',
                      rebuildingId === task.id ? 'border-purple-400/20 text-purple-400/20 cursor-wait'
                        : 'border-purple-400/50 text-purple-400/70 hover:border-purple-400 hover:bg-purple-400/10')}>
                    <Image size={12}/>
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); onRebuildClick(task, 'subtitle'); }} disabled={rebuildingId === task.id}
                    title={t('tooltip_trigger_subtitle')}
                    className={cn('p-1 border text-xs transition-all',
                      rebuildingId === task.id ? 'border-green-400/20 text-green-400/20 cursor-wait'
                        : 'border-green-400/50 text-green-400/70 hover:border-green-400 hover:bg-green-400/10')}>
                    <Subtitles size={12}/>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* 操作按钮：重试（仅 failed task）+ 常驻红色删除 */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {task?.status === 'failed' && onRetry && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (processingId !== null) return;
                  setProcessingId?.(task.id);
                  try { await Promise.resolve(onRetry(task.id)); }
                  finally { setProcessingId?.(null); }
                }}
                disabled={processingId === task.id}
                className={cn('p-1.5 border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all',
                  processingId === task.id && 'opacity-50 cursor-not-allowed')}
                title={t('btn_retry')}
              >
                <RefreshCw size={14} className={cn(processingId === task.id && 'animate-spin')}/>
              </button>
            )}
            {/* ★ 常驻红色删除按钮 — 所有层级必显示 */}
            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (task && processingId !== null) return;
                if (task) setProcessingId?.(task.id);
                try { await Promise.resolve(onDelete()); }
                finally { if (task) setProcessingId?.(null); }
              }}
              disabled={task ? processingId === task.id : false}
              className={cn('p-1.5 border border-cyber-red text-cyber-red hover:bg-cyber-red hover:text-white transition-all',
                task && processingId === task.id && 'opacity-50 cursor-not-allowed')}
              title={t('task_delete_record')}
            >
              <Trash2 size={14}/>
            </button>
          </div>
        </div>
      </div>

      {/* 进度条 */}
      {resolvedProgress > 0 && (
        <div className="relative h-1 bg-cyber-cyan/10 border-t border-cyber-cyan/20 mt-2 overflow-hidden">
          <div
            className={`absolute inset-y-0 left-0 bg-gradient-to-r ${progressColor} transition-all duration-700`}
            style={{ width: `${resolvedProgress}%`, boxShadow: '0 0 8px rgba(0,230,246,0.8)' }}
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
  onRetry, onDelete, onDeleteBatch, onRebuild,
}: MediaTableProps) {
  const { t } = useLanguage();
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [rebuildingId, setRebuildingId] = useState<number | null>(null);

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
          ignored_count: 0,
          poster_path: task.local_poster_path || task.poster_path,
          tmdb_id: task.tmdb_id,
          title: task.title,
          clean_name: task.clean_name,
        });
      }
      const g = map.get(key)!;
      g.total_count++;
      if ((task.status || '').toLowerCase() === 'archived') g.archived_count++;
      if ((task.status || '').toLowerCase() === 'ignored') g.ignored_count++;
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

      {/* Groups — 扁平化渲染，仅通过 marginLeft 体现层级 */}
      <div className="space-y-2">
        {groups.map(group => {
          const l1Open = openL1.has(group.key);

          // ── 电影：level=0 直接渲染 ──
          if (group.media_type === 'movie' && group.task) {
            return (
              <UniversalMediaRow
                key={group.key}
                level={0}
                task={group.task}
                title={group.title || group.clean_name || ''}
                subtitle={group.task.file_name || ''}
                onDelete={() => onDelete(group.task!.id)}
                onRetry={onRetry}
                onRebuildClick={handleRebuildClick}
                rebuildingId={rebuildingId}
                processingId={processingId}
                setProcessingId={setProcessingId}
              />
            );
          }

          // ── 剧集：Fragment 拍扁，消除 wrapper border ──
          if (group.media_type === 'tv') {
            const allEpisodeIds = Array.from(group.seasons.values()).flat().map(e => e.id);
            const tvProgress = group.total_count
              ? Math.round(group.archived_count / group.total_count * 100)
              : 0;
            const tvAllIgnored = group.ignored_count > 0 && group.ignored_count === group.total_count;
            const tvRootStatus = tvAllIgnored
              ? 'ignored'
              : (group.archived_count === group.total_count ? 'archived' : 'pending');

            const tvRoot = (
              <UniversalMediaRow
                level={0}
                isExpandable={true}
                isExpanded={l1Open}
                onToggle={() => toggleL1(group.key)}
                posterSrc={group.poster_path}
                title={group.title || group.clean_name || ''}
                subtitle={`共 ${group.total_count} 集`}
                status={tvRootStatus}
                progress={tvProgress}
                onDelete={() => onDeleteBatch(allEpisodeIds)}
              />
            );

            if (!l1Open) return tvRoot;

            return (
              <Fragment key={group.key}>
                {tvRoot}
                {Array.from(group.seasons.entries()).sort(([a],[b]) => a - b).map(([season, episodes]) => {
                  const l2Key = `${group.key}:${season}`;
                  const l2Open = openL2.has(l2Key);
                  const seasonIds = episodes.map(e => e.id);
                  const seasonArchived = episodes.filter(e =>
                    (e.status || '').toLowerCase() === 'archived'
                  ).length;
                  const seasonIgnored = episodes.filter(e =>
                    (e.status || '').toLowerCase() === 'ignored'
                  ).length;
                  const seasonProgress = episodes.length
                    ? Math.round(seasonArchived / episodes.length * 100)
                    : 0;
                  const seasonAllIgnored = seasonIgnored > 0 && seasonIgnored === episodes.length;
                  const seasonStatus = seasonAllIgnored
                    ? 'ignored'
                    : (seasonArchived === episodes.length ? 'archived' : 'pending');

                  const seasonRow = (
                    <UniversalMediaRow
                      level={1}
                      isExpandable={true}
                      isExpanded={l2Open}
                      onToggle={() => toggleL2(l2Key)}
                      posterSrc={group.poster_path}
                      title={`Season ${season}`}
                      subtitle={`${episodes.length} 集`}
                      status={seasonStatus}
                      progress={seasonProgress}
                      onDelete={() => onDeleteBatch(seasonIds)}
                    />
                  );

                  if (!l2Open) return seasonRow;

                  return (
                    <Fragment key={l2Key}>
                      {seasonRow}
                      {episodes
                        .sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0))
                        .map(ep => (
                          <UniversalMediaRow
                            key={ep.id}
                            level={2}
                            task={ep}
                            title={`E${String(ep.episode ?? 0).padStart(2, '0')} ${ep.title || ''}`}
                            subtitle={ep.file_name || ''}
                            onDelete={() => onDelete(ep.id)}
                            onRetry={onRetry}
                            onRebuildClick={handleRebuildClick}
                            rebuildingId={rebuildingId}
                            processingId={processingId}
                            setProcessingId={setProcessingId}
                          />
                        ))}
                    </Fragment>
                  );
                })}
              </Fragment>
            );
          }

          return null;
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
