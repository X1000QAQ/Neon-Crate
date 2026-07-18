/**
 * RebuildActions - 媒体行内重构操作按钮组
 *
 * 在媒体任务行内展示 NFO、海报、字幕三个快捷重构入口。
 * 组件只负责展示按钮和派发点击事件，真正的重构参数选择和执行逻辑由上层
 * `RebuildDialog` 与 `MediaWall` 处理。
 *
 * 新手提示：
 * - 只有 archived / failed 状态的任务才允许显示重构按钮。
 * - 点击按钮时会 `stopPropagation()`，避免触发行展开/折叠等父级点击逻辑。
 * - `scopeOverride` 用于区分剧集级、季级、单集级的重构范围。
 */
'use client';

import { FileText, Image, Subtitles } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Task } from '@/types';
import type { RebuildMode } from './RebuildDialog';
import { useLanguage } from '@/hooks/useLanguage';

interface RebuildActionsProps {
  task: Task;
  rebuildingId?: number | null;
  onRebuildClick: (task: Task, mode: RebuildMode, scope?: 'series' | 'season' | 'episode') => void;
  scopeOverride?: 'series' | 'season' | 'episode';
  hidePoster?: boolean;
}

function canRebuild(status: string) {
  const s = (status || '').toLowerCase();
  return s === 'archived' || s === 'failed';
}

export function RebuildActions({
  task,
  rebuildingId,
  onRebuildClick,
  scopeOverride = 'episode',
  hidePoster = false,
}: RebuildActionsProps) {
  const { t } = useLanguage();

  if (!canRebuild(task.status)) return null;

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRebuildClick(task, 'nfo', scopeOverride);
        }}
        disabled={rebuildingId === task.id}
        title={t('tooltip_rebuild_nfo')}
        className={cn(
          'p-1 border text-xs transition-all',
          rebuildingId === task.id
            ? 'border-cyber-cyan/20 text-cyber-cyan/20 cursor-wait'
            : 'border-cyber-cyan/50 text-cyber-cyan/70 hover:border-cyber-cyan hover:bg-cyber-cyan/10'
        )}
      >
        <FileText size={12} />
      </button>
      {!hidePoster && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRebuildClick(task, 'poster', scopeOverride);
          }}
          disabled={rebuildingId === task.id}
          title={t('tooltip_rebuild_poster')}
          className={cn(
            'p-1 border text-xs transition-all',
            rebuildingId === task.id
              ? 'border-purple-400/20 text-purple-400/20 cursor-wait'
              : 'border-purple-400/50 text-purple-400/70 hover:border-purple-400 hover:bg-purple-400/10'
          )}
        >
          <Image size={12} />
        </button>
      )}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRebuildClick(task, 'subtitle', scopeOverride);
        }}
        disabled={rebuildingId === task.id}
        title={t('tooltip_trigger_subtitle')}
        className={cn(
          'p-1 border text-xs transition-all',
          rebuildingId === task.id
            ? 'border-green-400/20 text-green-400/20 cursor-wait'
            : 'border-green-400/50 text-green-400/70 hover:border-green-400 hover:bg-green-400/10'
        )}
      >
        <Subtitles size={12} />
      </button>
    </div>
  );
}
