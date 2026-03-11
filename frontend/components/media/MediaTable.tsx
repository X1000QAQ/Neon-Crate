'use client';

import { Film, Tv, RefreshCw, Trash2, AlertCircle } from 'lucide-react';

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
import SecureImage from '@/components/common/SecureImage';
import type { Task } from '@/types';
import { cn, formatDate } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';

interface MediaTableProps {
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
}

export default function MediaTable({
  loading,
  tasks,
  selectedIds,
  onToggleSelect,
  onSelectAll,
  onInvertSelection,
  isAllSelected,
  isSomeSelected,
  onRetry,
  onDelete,
}: MediaTableProps) {
  const { t } = useLanguage();

  const getPosterUrl = (task: Task): string => {
    const posterPath = (task as any).local_poster_path || task.poster_path;
    if (!posterPath) return '/placeholder-poster.jpg';

    if (posterPath.startsWith('http://') || posterPath.startsWith('https://')) {
      return posterPath;
    }

    return `/api/v1/public/image?path=${encodeURIComponent(posterPath)}`;
  };

  const getStatusLabel = (status: string): string => {
    const s = (status || '').toLowerCase();
    if (s === 'archived') return t('status_archived');
    if (s === 'match failed' || s === 'failed') return t('status_failed');
    if (s === 'ignored') return t('status_ignored');
    return t('status_pending');
  };

  const getSubStatusLabel = (subStatus: string | undefined | null): string => {
    const s = (subStatus ?? '').toLowerCase();
    if (s === 'scraped' || s === 'success' || s === 'found') return t('status_sub_ready');
    if (s === 'failed' || s === 'match failed' || s === 'missing') return t('status_sub_missing');
    return t('status_sub_finding');
  };

  const getStatusColor = (status: string) => {
    const s = (status || '').toLowerCase();
    if (s === 'archived') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
    if (s === 'failed' || s === 'match failed') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
    if (s === 'ignored') return 'border-gray-400 text-gray-400 bg-gray-400/10';
    // pending/processing 属于常态流动信息，不使用黄色常亮
    return 'border-cyber-cyan/30 text-cyber-cyan/70 bg-cyber-cyan/5';
  };

  const getSubStatusColor = (subStatus: string | undefined | null) => {
    const s = (subStatus ?? '').toLowerCase();
    if (s === 'scraped' || s === 'success' || s === 'found') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
    if (s === 'failed' || s === 'match failed' || s === 'missing') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
    // finding 属于常态过程，不用黄色占据注意力
    return 'border-cyber-cyan/20 text-cyber-cyan/50 bg-cyber-cyan/5';
  };

  return (
    <>
      {loading ? (
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="relative bg-transparent border border-cyber-cyan/30 p-3 animate-pulse"
              style={{
                backdropFilter: 'blur(25px)',
                boxShadow: '0 0 40px rgba(6, 182, 212, 0.15)'
              }}
            >
              <div className="flex items-center gap-3">
                <div className="w-16 h-24 bg-cyber-cyan/10 border border-cyber-cyan/30" />
                <div className="flex-1 space-y-2">
                  <div className="h-5 bg-cyber-cyan/10 rounded w-2/3" />
                  <div className="h-4 bg-cyber-cyan/10 rounded w-1/2" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <div className="relative bg-transparent border border-cyber-cyan/50 p-12 text-center hover:border-cyber-cyan transition-all" style={{
          backdropFilter: 'blur(20px)',
          boxShadow: '0 0 40px rgba(6, 182, 212, 0.4), inset 0 0 40px rgba(6, 182, 212, 0.08)'
        }}>
          <AlertCircle className="mx-auto mb-4 text-cyber-cyan/60" size={48} />
          <p className="text-cyber-cyan text-lg font-semibold">{t('no_data')}</p>
          <p className="text-cyber-cyan/60 text-sm mt-2">{t('task_no_data_hint')}</p>
        </div>
      ) : (
        <>
          {/* 批量操作工具栏 */}
          <div className="relative bg-transparent border-b border-cyber-cyan/50 p-2 mb-1" style={{
            backdropFilter: 'blur(15px)',
            boxShadow: '0 0 30px rgba(6, 182, 212, 0.2)'
          }}>
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={isAllSelected}
                onChange={() => (isAllSelected ? onInvertSelection() : onSelectAll())}
                ref={(el) => {
                  if (el) el.indeterminate = isSomeSelected && !isAllSelected;
                }}
                className="rounded border-cyber-cyan/40 bg-transparent text-cyber-cyan focus:ring-cyber-cyan"
              />
              <button
                type="button"
                onClick={onSelectAll}
                className="text-xs text-cyber-cyan/70 hover:text-cyber-cyan transition-colors font-semibold"
               
              >
                {t('select_all_page')}
              </button>
              <span className="text-cyber-cyan/30">|</span>
              <button
                type="button"
                onClick={onInvertSelection}
                className="text-xs text-cyber-cyan/70 hover:text-cyber-cyan transition-colors font-semibold"
               
              >
                {t('invert_page')}
              </button>
            </div>
          </div>

          {/* 量子浮动面板列表 - 适中尺寸 */}
          <div className="space-y-4">
            {tasks.map((task, idx) => {
              const anyTask = task as any;
              const rawFallbackName =
                (anyTask.name as string | undefined) ||
                task.file_name ||
                task.file_path?.split(/[/\\]/).pop() ||
                '-';
              const originalName = task.file_path ? task.file_path.split(/[/\\]/).pop() || rawFallbackName : rawFallbackName;
              const normalizedTitle = (task.title ?? '').trim();
              const noisePattern = /\b(4k|2160p|1080p|720p|480p|360p)\b/i;
              const hasRealTitle =
                !!normalizedTitle &&
                normalizedTitle !== rawFallbackName &&
                normalizedTitle !== originalName &&
                !noisePattern.test(normalizedTitle);

              // 构建上方展示标题：刮削名 + 年份 + 剧集季集信息
              let displayTitle: string;
              if (hasRealTitle) {
                let titleParts = normalizedTitle;
                if (task.year) titleParts += ` (${task.year})`;
                // 剧集追加季集信息
                if (task.media_type === 'tv') {
                  const season = (task as any).season;
                  const episode = (task as any).episode;
                  if (season != null && episode != null) {
                    titleParts += ` S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`;
                  } else if (season != null) {
                    titleParts += ` Season ${season}`;
                  }
                }
                displayTitle = titleParts;
              } else {
                displayTitle = rawFallbackName;
              }

              return (
                <div
                  key={task.id}
                  className={cn(
                    "relative bg-transparent border border-cyber-cyan/30 p-3 hover:border-cyber-cyan hover:bg-cyber-cyan/5transition-all group",
                    "relative bg-transparent border border-cyber-cyan/30 p-3 hover:border-cyber-cyan hover:bg-cyber-cyan/5transition-all group"
                  )}
                  style={{
                    backdropFilter: 'blur(25px)',
                    boxShadow: '0 0 40px rgba(6, 182, 212, 0.2)',
                    animationDelay: `${idx * 0.1}s`
                  }}
                >
                  <div className="flex items-center gap-3">
                    {/* 选择框 */}
                    <div className="flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(task.id)}
                        onChange={() => onToggleSelect(task.id)}
                        className="rounded border-cyber-cyan/40 bg-transparent text-cyber-cyan focus:ring-cyber-cyan"
                      />
                    </div>

                    {/* 全息海报 - 适中尺寸 (1.5x) */}
                    <div className="relative w-16 h-24 flex-shrink-0 group/poster">
                      <div className="absolute inset-0 bg-cyber-cyan/10 border border-cyber-cyan/50 overflow-hidden transition-all group-hover/poster:border-cyber-cyan group-hover/poster:shadow-[0_0_15px_rgba(6,182,212,0.4)]">
                        {task.poster_path || task.local_poster_path ? (
                          <SecureImage
                            src={getPosterUrl(task)}
                            alt={task.title || t('task_unknown')}
                            width={64}
                            height={96}
                            className="object-cover w-full h-full opacity-80 group-hover/poster:opacity-100 group-hover/poster:scale-110 transition-all duration-300"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            {task.media_type === 'movie' ? (
                              <Film className="text-cyber-cyan/40" size={20} />
                            ) : (
                              <Tv className="text-cyber-cyan/40" size={20} />
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 任务信息区 - 适中布局 */}
                    <div className="flex-1 min-w-0 flex items-center gap-4">
                      {/* 标题与文件名 */}
                      <div className="flex-1 min-w-0">
                        <h3 
                          className="text-cyber-yellow font-semibold text-base truncate"
                          style={{ 
                            textShadow: '0 0 8px rgba(249, 240, 2, 0.4)'
                          }}
                          title={displayTitle}
                        >
                          {displayTitle}
                        </h3>
                        <p 
                          className="text-cyber-cyan/50 text-xs truncate mt-0.5"
                         
                          title={originalName}
                        >
                          {originalName}
                        </p>
                        {/* 路径信息：入库地址 + 原始地址 */}
                        <div className="mt-1 space-y-0.5">
                          {task.target_path && (
                            <p className="text-cyber-cyan/30 text-xs truncate" title={task.target_path}>
                              <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_dst')}:</span>
                              {task.target_path}
                            </p>
                          )}
                          <p className="text-cyber-cyan/30 text-xs truncate" title={task.file_path || ''}>
                            <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_src')}:</span>
                            {task.file_path || '-'}
                          </p>
                        </div>
                      </div>

                      {/* 状态标签 - 横向排列 */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span 
                          className={cn(
                            "px-2.5 py-1 text-xs font-semibold border transition-all",
                            getStatusColor(task.status)
                          )}
                          style={{ 
                            backdropFilter: 'blur(10px)',
                          }}
                        >
                          {getStatusLabel(task.status)}
                        </span>
                        <span 
                          className={cn(
                            "px-2.5 py-1 text-xs font-semibold border transition-all",
                            getSubStatusColor(task.sub_status)
                          )}
                          style={{ 
                            backdropFilter: 'blur(10px)',
                          }}
                        >
                          {getSubStatusLabel(task.sub_status)}
                        </span>
                      </div>

                      {/* 外部链接 */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {task.tmdb_id != null && String(task.tmdb_id).trim() !== '' && (
                          <a
                            href={
                              task.media_type === 'tv'
                                ? `https://www.themoviedb.org/tv/${task.tmdb_id}`
                                : `https://www.themoviedb.org/movie/${task.tmdb_id}`
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 text-xs font-semibold bg-transparent border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all"
                            style={{ 
                              backdropFilter: 'blur(10px)',
                            }}
                          >
                            TMDB
                          </a>
                        )}
                        {task.imdb_id != null && String(task.imdb_id).trim() !== '' && String(task.imdb_id).toUpperCase() !== 'N/A' && (
                          <a
                            href={`https://www.imdb.com/title/${String(task.imdb_id).startsWith('tt') ? task.imdb_id : 'tt' + task.imdb_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 text-xs font-semibold bg-transparent border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all"
                            style={{ 
                              backdropFilter: 'blur(10px)',
                            }}
                          >
                            IMDb
                          </a>
                        )}
                      </div>

                      {/* 时间戳 */}
                      <span className="text-cyber-cyan/50 text-xs flex-shrink-0">
                        {task.created_at ? formatDate(task.created_at) : t('task_just_now')}
                      </span>

                      {/* 操作按钮 */}
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        {(task.status === 'failed' || (task.status || '').toLowerCase() === 'match failed') && (
                          <button
                            onClick={() => onRetry(task.id)}
                            className="p-2 bg-transparent border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all group/btn"
                            style={{ backdropFilter: 'blur(10px)' }}
                            title={t('task_retry')}
                          >
                            <RefreshCw size={16} className="group-hover/btn:rotate-180 transition-transform duration-500" />
                          </button>
                        )}

                        <button
                          onClick={() => onDelete(task.id)}
                          className="p-2 bg-transparent border border-cyber-red text-cyber-red hover:bg-cyber-red hover:text-white transition-all"
                          style={{ backdropFilter: 'blur(10px)' }}
                          title={t('task_delete_record')}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* 流水线进度条：扫描30% → 刮削60% → 字幕100% */}
                  {(() => {
                    const progress = getProgress(task.status, task.sub_status);
                    if (progress === 0) return null;
                    const color = progress === 100
                      ? 'from-cyber-cyan to-green-400'
                      : 'from-cyber-cyan to-[rgba(0,230,246,0.5)]';
                    return (
                      <div className="relative h-1 bg-cyber-cyan/10 border-t border-cyber-cyan/20 mt-2 overflow-hidden">
                        <div
                          className={`absolute inset-y-0 left-0 bg-gradient-to-r ${color} transition-all duration-700`}
                          style={{
                            width: `${progress}%`,
                            boxShadow: '0 0 8px rgba(0, 230, 246, 0.8)',
                          }}
                        />
                      </div>
                    );
                  })()}


                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
