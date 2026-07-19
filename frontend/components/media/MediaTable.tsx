/**
 * MediaTable - 媒体任务列表组件
 * 
 * 职责：
 * - 以三级层次结构展示媒体任务：剧集（Series）→ 季（Season）→ 单集（Episode）
 * - 支持批量选择、删除、重试和重构操作
 * - 处理电影（Movie）和剧集（TV）两种媒体类型的不同展示逻辑
 * 
 * 层级结构：
 * - Level 0: 电影单文件 / 剧集根（可展开）
 * - Level 1: 季（Season，可展开）
 * - Level 2: 单集（Episode）
 * 
 * 状态管理：
 * - expandedGroups: 已展开的剧集根
 * - expandedSeasons: 已展开的季
 * - selectedIds: 批量操作的选中任务 ID
 */
'use client';

import { useState } from 'react';
import { CheckSquare, MinusSquare, Square } from 'lucide-react';
import type { Task, PathConfig } from '@/types';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';
import { MediaRow } from './MediaRow';
import RebuildDialog, { type RebuildMode } from './RebuildDialog';
import { useMediaGroups, type MediaGroup } from './hooks/useMediaGroups';
import { resolveDisplayTitle } from './utils/groupingUtils';

type Scope = 'series' | 'season' | 'episode';

interface MediaTableProps {
  loading: boolean;
  tasks: Task[];
  configPaths?: PathConfig[];
  selectedIds: Set<number>;
  onToggleSelect: (id: number) => void;
  onSelectAll: () => void;
  onInvertSelection: () => void;
  isAllSelected: boolean;
  isSomeSelected: boolean;
  onRetry: (taskId: number) => Promise<void> | void;
  onDelete: (taskId: number) => Promise<void> | void;
  onDeleteBatch: (ids: number[]) => Promise<void> | void;
  onIgnore: (scope: 'file' | 'directory', paths: string[]) => Promise<void> | void;
  onUnignore: (ruleId: string) => Promise<void> | void;
  onRebuild: (params: {
    task_id: number;
    is_archive: boolean;
    media_type: string;
    refix_nfo: boolean;
    refix_poster: boolean;
    refix_subtitle: boolean;
    tmdb_id?: number;
    nuclear_reset?: boolean;
    season?: number;
    episode?: number;
    scope?: Scope;
  }) => Promise<void> | void;
}

/**
 * 解析季集坐标（Season/Episode）
 * 
 * 策略：
 * 1. 优先使用结构化字段（task.season / task.episode）
 * 2. 降级从路径中正则提取 SxxExx 格式
 * 3. 兼容 S1E1 到 S99E999 的范围
 */
function parseSeasonEpisode(task: Task) {
  const source = [task.target_path, task.file_path, task.file_name].filter(Boolean).join(' ');
  const match = source.match(/S(\d{1,2})E(\d{1,3})/i);

  let season = task.season ?? (match ? Number(match[1]) : null);
  // 当结构化字段和 SxxExx 都取不到季号时，从路径的 Season X 目录名提取
  if (season == null) {
    const pathForSeason = task.target_path || task.file_path || '';
    const parts = pathForSeason.replace(/\\/g, '/').split('/').filter(Boolean);
    const seasonDir = parts.length >= 2 ? parts[parts.length - 2] : '';
    const seasonMatch = seasonDir.match(/season\s*(\d+)/i);
    if (seasonMatch) season = Number(seasonMatch[1]);
  }

  return {
    season,
    episode: task.episode ?? (match ? Number(match[2]) : null),
  };
}

/**
 * 剧集集数显示的位数宽度（补零到两位，如 S01E05）
 */
const EPISODE_NUMBER_WIDTH = 2;

/**
 * 格式化数字为两位补零格式，缺失时显示 `?`
 * 
 * @example
 * formatNumberOrUnknown(5)  // "05"
 * formatNumberOrUnknown(null)  // "?"
 */
function formatNumberOrUnknown(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? String(value).padStart(EPISODE_NUMBER_WIDTH, '0') : '?';
}

/**
 * 生成任务副标题
 * - 电影：显示年份或文件名
 * - 剧集：显示 SxxExx 格式的季集坐标
 */
function subtitleOf(task: Task) {
  if (task.media_type !== 'tv') return task.year || task.file_name || task.file_path;
  const { season, episode } = parseSeasonEpisode(task);
  return `S${formatNumberOrUnknown(season ?? 1)}E${formatNumberOrUnknown(episode)}`;
}

/**
 * 提取媒体组内的所有任务
 * - 电影组：返回单个任务
 * - 剧集组：返回所有季的所有集
 */
function tasksOf(group: MediaGroup) {
  return group.task ? [group.task] : Array.from(group.seasons.values()).flat();
}

/**
 * 聚合状态（优先显示失败 > 忽略 > 已归档 > 待处理）
 */
function statusOf(tasks: Task[]): Task['status'] {
  if (tasks.some((task) => task.status === 'failed')) return 'failed';
  if (tasks.every((task) => task.status === 'ignored')) return 'ignored';
  if (tasks.every((task) => task.status === 'archived' || task.status === 'scraped')) return 'archived';
  return 'pending';
}

export default function MediaTable({
  loading,
  tasks,
  configPaths = [],
  selectedIds,
  onToggleSelect,
  onSelectAll,
  onInvertSelection,
  isAllSelected,
  isSomeSelected,
  onRetry,
  onDelete,
  onDeleteBatch,
  onIgnore,
  onUnignore,
  onRebuild,
}: MediaTableProps) {
  const { t } = useLanguage();
  const groups = useMediaGroups(tasks, configPaths);
  
  // 展开状态：记录哪些剧集根和季已被用户展开
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [expandedSeasons, setExpandedSeasons] = useState<Set<string>>(new Set());
  
  // 处理中状态：标记正在执行异步操作的任务 ID（防止重复点击）
  const [processingId, setProcessingId] = useState<number | null>(null);
  
  // 重构对话框状态
  const [rebuild, setRebuild] = useState<{ task: Task; mode: RebuildMode; scope: Scope } | null>(null);

  /**
   * 切换 Set 中某个 key 的存在状态（已存在则删除，不存在则添加）
   */
  const flip = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, key: string) => {
    setter((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  /**
   * 批量删除：单任务走 onDelete，多任务走 onDeleteBatch
   */
  const deleteIds = async (ids: number[]) => {
    if (ids.length === 1) await onDelete(ids[0]);
    else await onDeleteBatch(ids);
  };

  /**
   * 批量选中：逐个调用 onToggleSelect
   */
  const selectIds = (ids: number[]) => ids.forEach((id) => onToggleSelect(id));

  /**
   * 打开重构对话框
   */
  const openRebuild = (task: Task, mode: RebuildMode, scope: Scope = 'episode') => setRebuild({ task, mode, scope });

  // 加载状态
  if (loading) {
    return <div className="border border-cyber-cyan/30 bg-black/30 p-8 text-center text-cyber-cyan/70">{t('loading_settings')}</div>;
  }

  // 空状态
  if (tasks.length === 0) {
    return <div className="border border-cyber-cyan/30 bg-black/30 p-8 text-center text-cyber-cyan/60">{t('task_no_data_hint')}</div>;
  }

  /**
   * 渲染复选框（单个或批量）
   */
  const renderSelect = (ids: number[]) => {
    const checked = ids.length > 0 && ids.every((id) => selectedIds.has(id));
    return (
      <button
        onClick={() => selectIds(ids)}
        className={cn(
          'w-8 border border-cyber-cyan/20 text-cyber-cyan/60 hover:text-cyber-cyan hover:border-cyber-cyan transition-colors flex items-center justify-center',
          checked && 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10',
        )}
      >
        {checked ? <CheckSquare size={15} /> : <Square size={15} />}
      </button>
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between border border-cyber-cyan/30 bg-black/30 px-3 py-2 text-xs text-cyber-cyan/70">
        <div className="flex items-center gap-3">
          <button onClick={onSelectAll} className="flex items-center gap-1 hover:text-cyber-cyan transition-colors">
            {isAllSelected ? <CheckSquare size={14} /> : isSomeSelected ? <MinusSquare size={14} /> : <Square size={14} />}
            <span>{t('select_all_page')}</span>
          </button>
          <button onClick={onInvertSelection} className="hover:text-cyber-cyan transition-colors">{t('invert_page')}</button>
        </div>
        <div>{selectedIds.size > 0 ? `${selectedIds.size} / ${tasks.length}` : tasks.length}</div>
      </div>

      {groups.map((group) => {
        const groupTasks = tasksOf(group);
        const groupIds = groupTasks.map((task) => task.id);
        const rep = group.task ?? groupTasks[0];
        if (!rep) return null;

        if (group.media_type !== 'tv') {
          return (
            <div key={group.key} className="flex items-stretch gap-2">
              {renderSelect([rep.id])}
              <div className="flex-1 min-w-0">
                <MediaRow level={0} title={resolveDisplayTitle(rep, configPaths)} subtitle={subtitleOf(rep)} status={rep.status} task={rep} onDelete={() => deleteIds([rep.id])} onIgnore={rep.file_path ? () => onIgnore('file', [rep.file_path]) : undefined} onUnignore={rep.ignore_rule ? () => onUnignore(rep.ignore_rule!.id) : undefined} onRetry={onRetry} onRebuildClick={openRebuild} processingId={processingId} setProcessingId={setProcessingId} />
              </div>
            </div>
          );
        }

        const groupExpanded = expandedGroups.has(group.key);
        return (
          <div key={group.key} className="space-y-2">
            <div className="flex items-stretch gap-2">
              {renderSelect(groupIds)}
              <div className="flex-1 min-w-0">
                <MediaRow level={0} isExpandable isExpanded={groupExpanded} onToggle={() => flip(setExpandedGroups, group.key)} posterSrc={group.poster_path} title={group.title || group.clean_name || resolveDisplayTitle(rep, configPaths)} subtitle={t('media_table_tv_summary').replace('{seasons}', String(group.seasons.size)).replace('{episodes}', String(group.total_count))} status={statusOf(groupTasks)} task={rep} onDelete={() => deleteIds(groupIds)} onIgnore={() => onIgnore('directory', groupTasks.map(t => t.file_path).filter(Boolean))} onUnignore={rep.ignore_rule ? () => onUnignore(rep.ignore_rule!.id) : undefined} onRetry={onRetry} onRebuildClick={openRebuild} processingId={processingId} setProcessingId={setProcessingId} scopeOverride="series" />
              </div>
            </div>

            {groupExpanded && Array.from(group.seasons.entries()).sort(([a], [b]) => a - b).map(([season, seasonTasks]) => {
              const sorted = [...seasonTasks].sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0));
              const seasonIds = sorted.map((task) => task.id);
              const seasonKey = `${group.key}:${season}`;
              const seasonExpanded = expandedSeasons.has(seasonKey);
              const seasonRep = sorted[0];
              return (
                <div key={seasonKey} className="space-y-2">
                  <div className="flex items-stretch gap-2">
                    {renderSelect(seasonIds)}
                    <div className="flex-1 min-w-0">
                      <MediaRow level={1} isExpandable isExpanded={seasonExpanded} onToggle={() => flip(setExpandedSeasons, seasonKey)} posterSrc={group.poster_path} title={t('media_table_season_label').replace('{season}', String(season))} subtitle={t('media_table_tv_season_episodes').replace('{count}', String(sorted.length))} status={statusOf(sorted)} task={seasonRep} onDelete={() => deleteIds(seasonIds)} onIgnore={() => onIgnore('directory', sorted.map(t => t.file_path).filter(Boolean))} onUnignore={seasonRep.ignore_rule ? () => onUnignore(seasonRep.ignore_rule!.id) : undefined} onRetry={onRetry} onRebuildClick={openRebuild} processingId={processingId} setProcessingId={setProcessingId} hidePoster scopeOverride="season" />
                    </div>
                  </div>
                  {seasonExpanded && sorted.map((task) => (
                    <div key={task.id} className="flex items-stretch gap-2">
                      {renderSelect([task.id])}
                      <div className="flex-1 min-w-0">
                        <MediaRow level={2} title={resolveDisplayTitle(task, configPaths)} subtitle={subtitleOf(task)} status={task.status} task={task} onDelete={() => deleteIds([task.id])} onIgnore={task.file_path ? () => onIgnore('file', [task.file_path]) : undefined} onUnignore={task.ignore_rule ? () => onUnignore(task.ignore_rule!.id) : undefined} onRetry={onRetry} onRebuildClick={openRebuild} processingId={processingId} setProcessingId={setProcessingId} hidePoster scopeOverride="episode" />
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        );
      })}

      {rebuild && (
        <RebuildDialog
          open
          task={rebuild.task}
          mode={rebuild.mode}
          scope={rebuild.scope}
          onClose={() => setRebuild(null)}
          onConfirm={async (params) => {
            await onRebuild({
              task_id: rebuild.task.id,
              is_archive: Boolean(rebuild.task.is_archive),
              media_type: params.media_type,
              refix_nfo: rebuild.mode === 'nfo',
              refix_poster: rebuild.mode === 'poster',
              refix_subtitle: rebuild.mode === 'subtitle',
              tmdb_id: params.tmdb_id,
              nuclear_reset: params.nuclear_reset,
              season: params.season ?? rebuild.task.season ?? undefined,
              episode: params.episode ?? rebuild.task.episode ?? undefined,
              scope: params.scope ?? rebuild.scope,
            });
          }}
        />
      )}
    </div>
  );
}
