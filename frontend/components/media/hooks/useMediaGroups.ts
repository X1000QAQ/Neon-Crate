/**
 * useMediaGroups - 媒体任务分组 Hook
 *
 * 将后端返回的扁平任务列表整理成前端媒体墙需要的分组结构。
 * 所有分组 key 生成逻辑来自 groupingUtils，与 MediaWall 完全共享，
 * 保证分页边界和渲染边界严格一致。
 */
import { useMemo } from 'react';
import type { Task, PathConfig } from '@/types';
import { buildGroupKey, resolveSeasonNum } from '../utils/groupingUtils';

export interface MediaGroup {
  key: string;
  media_type: 'movie' | 'tv' | 'mixed';
  task?: Task;
  seasons: Map<number, Task[]>;
  total_count: number;
  archived_count: number;
  ignored_count: number;
  poster_path?: string;
  tmdb_id?: number;
  title?: string;
  clean_name?: string;
}

export function useMediaGroups(tasks: Task[], configPaths: PathConfig[] = []): MediaGroup[] {
  return useMemo((): MediaGroup[] => {
    const map = new Map<string, MediaGroup>();

    for (const task of tasks) {
      const mtype = task.media_type || 'movie';
      const key = buildGroupKey(task, configPaths);

      if (!map.has(key)) {
        map.set(key, {
          key,
          media_type: mtype as 'movie' | 'tv' | 'mixed',
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
      // 元数据：有 TMDB 刮削结果的任务数据质量更高，优先覆盖路径 fallback 填入的值
      if (task.title) g.title = task.title;
      if (task.clean_name && !g.title) g.clean_name = task.clean_name;
      if (task.tmdb_id && !g.tmdb_id) g.tmdb_id = task.tmdb_id;
      if (!g.poster_path) g.poster_path = task.local_poster_path || task.poster_path;
      if (task.local_poster_path) g.poster_path = task.local_poster_path;

      if (mtype === 'movie' || mtype === 'mixed') {
        g.task = task;
      } else if (mtype === 'tv') {
        const s = resolveSeasonNum(task, configPaths);
        if (!g.seasons.has(s)) g.seasons.set(s, []);
        g.seasons.get(s)!.push(task);
      }
    }

    return Array.from(map.values());
  }, [tasks, configPaths]);
}
