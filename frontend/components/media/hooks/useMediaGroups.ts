/**
 * useMediaGroups - 媒体任务分组 Hook
 *
 * 将后端返回的扁平任务列表整理成前端媒体墙需要的分组结构。
 * 电影和 mixed 任务会作为单条媒体项展示；剧集任务会按作品和季数分组，
 * 方便 MediaWall / MediaRow 渲染"剧集 → 季 → 单集"的树形列表。
 */
import { useMemo } from 'react';
import type { Task } from '@/types';
import type { PathConfig } from '@/types';

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

/**
 * 根据用户配置的路径列表，提取任务的剧集根目录名和季号。
 *
 * 策略：
 * 1. 遍历所有已启用的路径配置，找到匹配的前缀
 * 2. 去掉前缀后，取第一段作为剧集根目录名
 * 3. 再在剩余路径中寻找 Season X 目录确定季号
 *
 * 示例（download 路径 /storage/ready_for_ai_tv）：
 *   /storage/ready_for_ai_tv/Futurama/Futurama.S07E11.mkv
 *   → seriesName = "Futurama", season = 7 (从文件名 SxxExx 提取)
 *
 * 示例（library 路径 /storage/media/tv）：
 *   /storage/media/tv/葬送的芙莉莲 (2023)/Season 1/xxx.mkv
 *   → seriesName = "葬送的芙莉莲 (2023)", season = 1
 */
function extractSeriesInfo(
  path: string,
  configPaths: PathConfig[],
): { seriesName: string | null; season: number | null } {
  const normalized = path.replace(/\\/g, '/');

  // 按路径长度降序排列，优先匹配最长前缀
  const sorted = [...configPaths]
    .filter((p) => p.enabled && (p.category === 'tv' || p.category === 'mixed'))
    .sort((a, b) => b.path.length - a.path.length);

  for (const cp of sorted) {
    const prefix = cp.path.replace(/\\/g, '/').replace(/\/$/, '');
    if (!normalized.startsWith(prefix + '/')) continue;

    const relative = normalized.slice(prefix.length + 1);
    const parts = relative.split('/').filter(Boolean);
    if (parts.length === 0) continue;

    // 第一段是剧集根目录名
    const seriesName = parts[0];

    // 在剩余段中寻找 Season X 确定季号
    let season: number | null = null;
    for (let i = 1; i < parts.length; i++) {
      const m = parts[i].match(/^season\s*(\d+)$/i);
      if (m) { season = Number(m[1]); break; }
    }

    return { seriesName, season };
  }

  // 没有匹配的配置路径，fallback：在路径中找 Season X 目录
  const parts = normalized.split('/').filter(Boolean);
  for (let i = 0; i < parts.length; i++) {
    const m = parts[i].match(/^season\s*(\d+)$/i);
    if (m) {
      return {
        seriesName: i > 0 ? parts[i - 1] : null,
        season: Number(m[1]),
      };
    }
  }
  return {
    seriesName: parts.length >= 3 ? parts[parts.length - 3] : null,
    season: null,
  };
}

export function useMediaGroups(tasks: Task[], configPaths: PathConfig[] = []): MediaGroup[] {
  return useMemo((): MediaGroup[] => {
    const map = new Map<string, MediaGroup>();

    for (const task of tasks) {
      const mtype = task.media_type || 'movie';

      let groupName: string;
      let seasonNum: number | null = task.season ?? null;

      if (mtype === 'tv') {
        const path = task.target_path || task.file_path || '';
        const { seriesName, season } = extractSeriesInfo(path, configPaths);

        // 季号优先级：task.season > 路径 Season X 目录 > SxxExx 正则 > 1
        if (seasonNum == null && season != null) seasonNum = season;
        if (seasonNum == null) {
          const source = [task.target_path, task.file_path, task.file_name].filter(Boolean).join(' ');
          const m = source.match(/S(\d{1,2})E\d{1,3}/i);
          if (m) seasonNum = Number(m[1]);
        }
        if (seasonNum == null) seasonNum = 1;

        // 剧集名优先级：task.title > task.clean_name > 路径提取 > fallback id
        groupName = (task.title || task.clean_name || seriesName || String(task.id)).trim();
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
      if (!g.title && task.title) g.title = task.title;
      if (!g.clean_name && task.clean_name) g.clean_name = task.clean_name;

      if (mtype === 'movie' || mtype === 'mixed') {
        g.task = task;
      } else if (mtype === 'tv') {
        const s = seasonNum as number;
        if (!g.seasons.has(s)) g.seasons.set(s, []);
        g.seasons.get(s)!.push(task);
      }
    }

    return Array.from(map.values());
  }, [tasks, configPaths]);
}
