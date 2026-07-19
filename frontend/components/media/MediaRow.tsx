/**
 * MediaRow - 媒体任务行组件（扁平树形结构的通用行组件）
 * 
 * 核心职责：
 * 1. 显示单个任务的信息行（支持三级嵌套：电影/剧集根/季/集）
 * 2. 展示海报、标题、状态、进度条等信息
 * 3. 提供折叠/展开按钮（用于树形列表）
 * 4. 提供删除、重构等操作按钮
 * 5. 支持选中状态（批量删除）
 * 
 * 设计特点：
 * - 扁平结构：所有行都是 MediaTable 直接子元素，通过 marginLeft 体现嵌套层级
 * - memo 优化：避免不必要的重渲染
 * - 三级显示：
 *   * level=0：电影或剧集根节点（marginLeft: 0）
 *   * level=1：季节点（marginLeft: 32px）
 *   * level=2：单集节点（marginLeft: 64px）
 * 
 * Props 说明：
 * - level：嵌套层级（0 / 1 / 2）
 * - isExpandable：是否可以折叠/展开
 * - isExpanded：当前是否已展开
 * - onToggle：点击展开/折叠时的回调
 * - posterSrc：海报图片路径
 * - title：任务标题
 * - subtitle：副标题（如季数、集数信息）
 * - status：任务状态（pending / archived / failed / ignored / scraped）
 * - progress：进度条百分比（0-100）
 * - onDelete：删除按钮回调
 * - task：完整的 Task 对象（用于重构操作）
 * - onRebuildClick：重构弹窗打开回调
 * - rebuildingId：当前重构中的任务 ID
 * - processingId：当前处理中的任务 ID
 * - scopeOverride：重构范围覆盖（series / season / episode）
 * 
 * 进度条计算规则：
 * - pending：30%（待处理）
 * - archived/scraped + 无字幕：60%（已刮削但缺字幕）
 * - archived/scraped + 已获字幕：100%（完全完成）
 * - 其他状态：0%（不显示进度条）
 * 
 * @component
 */

'use client';

import { memo } from 'react';
import {
  Film,
  Tv,
  RefreshCw,
  Trash2,
  ChevronDown,
  ChevronRight,
  Wand2,
  EyeOff,
  Eye,
} from 'lucide-react';
import SecureImage from '@/components/common/SecureImage';
import { VHSOverlay } from './VHSOverlay';
import { RebuildActions } from './RebuildActions';
import { cn, formatDate } from '@/lib/utils';
import type { Task } from '@/types';
import type { RebuildMode } from './RebuildDialog';
import type { I18nKey } from '@/lib/i18n';
import { useLanguage } from '@/hooks/useLanguage';

interface MediaRowProps {
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
  onIgnore?: () => void;
  onUnignore?: () => void;
  task?: Task;
  onRebuildClick?: (task: Task, mode: RebuildMode, scope?: 'series' | 'season' | 'episode') => void;
  rebuildingId?: number | null;
  processingId?: number | null;
  setProcessingId?: (id: number | null) => void;
  onRetry?: (id: number) => void;
  hidePoster?: boolean;
  scopeOverride?: 'series' | 'season' | 'episode';
}

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

function getStatusColor(status: string) {
  const s = (status || '').toLowerCase();
  if (s === 'archived') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
  if (s === 'failed') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
  if (s === 'ignored') return 'border-orange-400 text-orange-400 bg-orange-400/10 font-mono';
  if (s === 'duplicate') return 'border-cyber-red text-cyber-red bg-cyber-red/10 font-mono';
  return 'border-cyber-cyan/30 text-cyber-cyan/70 bg-cyber-cyan/5';
}

function getSubStatusColor(sub?: string | null) {
  const s = (sub ?? '').toLowerCase();
  if (s === 'scraped' || s === 'success' || s === 'found')
    return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
  if (s === 'failed' || s === 'missing') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
  return 'border-cyber-cyan/20 text-cyber-cyan/50 bg-cyber-cyan/5';
}

function getStatusLabel(status: string | null | undefined, t: (k: I18nKey) => string): string {
  const raw = (status || 'pending').toLowerCase();
  const key = (`status_${raw}`) as I18nKey;
  const translated = (t as (k: string) => string)(key);
  if (translated !== key) return translated;
  return (t as (k: string) => string)('status_unknown');
}

function formatSubStatus(raw: string | null | undefined, t: (k: I18nKey) => string): string {
  if (!raw) return t('sub_status_pending');
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
        labels.push(
          st === 'triggered' ? t('msg_subtitle_triggered') : t('msg_nfo_rebuild').replace('{status}', st)
        );
      }
    }
    return labels.length ? t('msg_rebuild_complete') + labels.join(' | ') : t('msg_rebuild_complete');
  }
  const key = ('sub_status_' + raw.toLowerCase()) as I18nKey;
  const trans = (t as (k: string) => string)(key);
  if (trans !== key) return trans;
  return (t as (k: string) => string)('sub_status_unknown');
}

export const MediaRow = memo(function MediaRow({
  level,
  isExpandable,
  isExpanded,
  onToggle,
  posterSrc,
  title,
  subtitle,
  status = 'pending',
  progress,
  onDelete,
  onIgnore,
  onUnignore,
  task,
  onRebuildClick,
  rebuildingId,
  processingId,
  setProcessingId,
  onRetry,
  hidePoster = false,
  scopeOverride,
}: MediaRowProps) {
  const { t } = useLanguage();
  const resolvedScope: 'series' | 'season' | 'episode' =
    scopeOverride ?? (level === 1 ? 'season' : level === 2 ? 'episode' : 'series');

  const effectiveStatus = (task?.status ?? status ?? 'pending').toLowerCase();
  const effectiveMediaType = task?.media_type ?? 'movie';
  const isIgnored = effectiveStatus === 'ignored';
  const isMixed = effectiveMediaType === 'mixed';

  const resolvedProgress = progress !== undefined ? progress : getProgress(task?.status ?? '', task?.sub_status);

  const progressColor =
    resolvedProgress === 100 ? 'from-cyber-cyan to-green-400' : 'from-cyber-cyan to-[rgba(0,230,246,0.5)]';

  return (
    <div
      className={cn(
        'relative border border-cyber-cyan/30 p-3 hover:border-cyber-cyan hover:bg-cyber-cyan/5 transition-all',
        isIgnored && 'border-orange-400/70 bg-orange-400/5 hover:border-orange-400 hover:bg-orange-400/10'
      )}
      style={{
        marginLeft: level * 32,
        backdropFilter: 'blur(25px)',
        boxShadow: '0 0 30px rgba(6,182,212,0.15)',
      }}
    >
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0 w-5 flex items-center justify-center">
          {isExpandable ? (
            <button onClick={onToggle} className="text-cyber-cyan/60 hover:text-cyber-cyan transition-colors">
              {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
          ) : null}
        </div>

        <div
          className={cn(
            'relative w-14 h-20 flex-shrink-0 overflow-hidden border border-cyber-cyan/40',
            isIgnored && 'border-orange-400/70'
          )}
        >
          <SecureImage
            src={posterSrc || task?.local_poster_path || task?.poster_path || '/placeholder-poster.jpg'}
            alt={title}
            width={56}
            height={80}
            className={cn('object-cover w-full h-full opacity-80', isIgnored && 'vhs-filter')}
            fallback={
              <div className="w-full h-full flex items-center justify-center bg-black/40">
                {task?.media_type === 'tv' ? (
                  <Tv className="text-cyber-cyan/30" size={18} />
                ) : task?.media_type === 'mixed' ? (
                  <Wand2 className="text-cyber-yellow/40" size={18} />
                ) : (
                  <Film className="text-cyber-cyan/30" size={18} />
                )}
              </div>
            }
          />

          {isIgnored && <VHSOverlay />}
        </div>

        <div className="flex-1 min-w-0 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <h4
              className="font-semibold text-sm truncate text-cyber-yellow"
              style={{ textShadow: '0 0 8px rgba(249,240,2,0.4)' }}
              title={title}
            >
              {title}
            </h4>
            <p className="text-xs truncate mt-0.5 text-cyber-cyan/50" title={subtitle}>
              {subtitle}
            </p>
            {task?.target_path && (
              <p className="text-cyber-cyan/30 text-xs truncate mt-1" title={task.target_path}>
                <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_dst')}:</span>
                {task.target_path}
              </p>
            )}
            {task?.file_path && (
              <p className="text-cyber-cyan/40 text-xs truncate mt-0.5" title={task.file_path}>
                <span className="text-cyber-cyan/60 font-mono mr-1">{t('path_src')}:</span>
                {task.file_path}
              </p>
            )}
          </div>

          {task ? (
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span className={cn('px-2 py-0.5 text-xs font-semibold border', getStatusColor(task.status))}>
                {getStatusLabel(task.status, t)}
              </span>
              <span className={cn('px-2 py-0.5 text-xs font-semibold border', getSubStatusColor(task.sub_status))}>
                {formatSubStatus(task.sub_status, t)}
              </span>
              {isMixed && (
                <span className="px-2 py-0.5 text-xs font-semibold border border-cyber-yellow text-cyber-yellow bg-cyber-yellow/10">
                  {t('badge_ai_pending')}
                </span>
              )}
            </div>
          ) : (
            <span className={cn('px-2 py-0.5 text-xs font-semibold border flex-shrink-0', getStatusColor(status))}>
              {getStatusLabel(status, t)}
            </span>
          )}

          {task && (
            <div className="flex items-center gap-1 flex-shrink-0">
              {task.tmdb_id && task.media_type !== 'mixed' && (
                <a
                  href={`https://www.themoviedb.org/${task.media_type === 'tv' ? 'tv' : 'movie'}/${task.tmdb_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-2 py-0.5 text-xs border border-cyber-cyan/60 text-cyber-cyan/70 hover:bg-cyber-cyan hover:text-black transition-all"
                >
                  TMDB
                </a>
              )}
              {task.imdb_id && (
                <a
                  href={`https://www.imdb.com/title/${task.imdb_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-2 py-0.5 text-xs border border-yellow-400/60 text-yellow-400/70 hover:bg-yellow-400 hover:text-black transition-all"
                >
                  IMDb
                </a>
              )}
            </div>
          )}

          {task && onRebuildClick && (
            <div className="flex-shrink-0 flex flex-col items-end gap-1">
              <span className="text-cyber-cyan/50 text-xs whitespace-nowrap">
                {task.created_at ? formatDate(task.created_at) : t('task_just_now')}
              </span>
              <RebuildActions
                task={task}
                rebuildingId={rebuildingId}
                onRebuildClick={onRebuildClick}
                scopeOverride={resolvedScope}
                hidePoster={hidePoster}
              />
            </div>
          )}

          <div className="flex items-center gap-1 flex-shrink-0">
            {task?.status === 'failed' && onRetry && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (processingId !== null) return;
                  setProcessingId?.(task.id);
                  try {
                    await Promise.resolve(onRetry(task.id));
                  } finally {
                    setProcessingId?.(null);
                  }
                }}
                disabled={processingId === task.id}
                className={cn(
                  'p-1.5 border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all',
                  processingId === task.id && 'opacity-50 cursor-not-allowed'
                )}
                title={t('btn_retry')}
              >
                <RefreshCw size={14} className={cn(processingId === task.id && 'animate-spin')} />
              </button>
            )}
            {onIgnore && task && !isIgnored && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (processingId !== null) return;
                  setProcessingId?.(task.id);
                  try {
                    await Promise.resolve(onIgnore());
                  } finally {
                    setProcessingId?.(null);
                  }
                }}
                disabled={processingId === task.id}
                className={cn(
                  'p-1.5 border border-orange-400/70 text-orange-400/70 hover:bg-orange-400 hover:text-black transition-all',
                  processingId === task.id && 'opacity-50 cursor-not-allowed'
                )}
                title={t('btn_ignore')}
              >
                <EyeOff size={14} />
              </button>
            )}
            {onUnignore && task && isIgnored && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (processingId !== null) return;
                  setProcessingId?.(task.id);
                  try {
                    await Promise.resolve(onUnignore());
                  } finally {
                    setProcessingId?.(null);
                  }
                }}
                disabled={processingId === task.id}
                className={cn(
                  'p-1.5 border border-cyber-cyan/70 text-cyber-cyan/70 hover:bg-cyber-cyan hover:text-black transition-all',
                  processingId === task.id && 'opacity-50 cursor-not-allowed'
                )}
                title={t('btn_unignore')}
              >
                <Eye size={14} />
              </button>
            )}
            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (task && processingId !== null) return;
                if (task) setProcessingId?.(task.id);
                try {
                  await Promise.resolve(onDelete());
                } finally {
                  if (task) setProcessingId?.(null);
                }
              }}
              disabled={task ? processingId === task.id : false}
              className={cn(
                'p-1.5 border border-cyber-red text-cyber-red hover:bg-cyber-red hover:text-white transition-all',
                task && processingId === task.id && 'opacity-50 cursor-not-allowed'
              )}
              title={t('task_delete_record')}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      </div>

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
