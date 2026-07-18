/**
 * useMediaGroups - 媒体任务分组 Hook
 *
 * 将后端返回的扁平任务列表整理成前端媒体墙需要的分组结构。
 * 电影和 mixed 任务会作为单条媒体项展示；剧集任务会按作品和季数分组，
 * 方便 MediaWall / MediaRow 渲染“剧集 → 季 → 单集”的树形列表。
 *
 * 新手提示：
 * - 输入是原始 `Task[]`，输出是适合 UI 渲染的 `MediaGroup[]`。
 * - `useMemo` 用于避免每次渲染都重新分组，只有 tasks 变化时才重新计算。
 * - 分组 key 由媒体类型和标题/清洗名/文件名组成，因此上游标题变化会影响分组结果。
 */
import { useMemo } from 'react';
import type { Task } from '@/types';

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

export function useMediaGroups(tasks: Task[]): MediaGroup[] {
  return useMemo((): MediaGroup[] => {
    const map = new Map<string, MediaGroup>();
    for (const task of tasks) {
      const mtype = task.media_type || 'movie';
      // TV 任务优先从文件路径提取剧集根目录作为 key，避免 title/clean_name 为空时
      // 退化为逐文件分组导致无法折叠的问题。
      // 路径结构示例：/storage/media/tv/咒术回战 (2020)/Season 1/xxx.mkv
      // 提取规则：取路径倒数第三段（剧集根目录名），作为跨季聚合的稳定 key。
      let groupName: string;
      if (mtype === 'tv') {
        const pathForKey = task.target_path || task.file_path || '';
        const parts = pathForKey.replace(/\\/g, '/').split('/').filter(Boolean);
        // 路径至少需要 3 段：.../{series}/{season}/{file}
        const seriesDir = parts.length >= 3 ? parts[parts.length - 3] : null;
        groupName = (task.title || task.clean_name || seriesDir || task.file_name || String(task.id)).trim();
      } else {
        groupName = (task.title || task.clean_name || task.file_name || String(task.id)).trim();
      }
      const key = `${mtype}::${groupName}`;
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
      if (!g.poster_path) g.poster_path = task.local_poster_path || task.poster_path;
      if (mtype === 'movie' || mtype === 'mixed') {
        g.task = task;
      } else if (mtype === 'tv') {
        const s = task.season ?? 1;
        if (!g.seasons.has(s)) g.seasons.set(s, []);
        g.seasons.get(s)!.push(task);
      }
    }
    return Array.from(map.values());
  }, [tasks]);
}
