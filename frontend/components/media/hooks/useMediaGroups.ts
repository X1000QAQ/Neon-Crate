/**
 * useMediaGroups - 媒体任务分组 Hook
 *
 * 将后端返回的扁平任务列表整理成前端媒体墙需要的分组结构。
 * 电影和 mixed 任务会作为单条媒体项展示；剧集任务会按作品和季数分组，
 * 方便 MediaWall / MediaRow 渲染"剧集 → 季 → 单集"的树形列表。
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

/**
 * 从路径中提取剧集根目录名和季号。
 *
 * 策略：在路径段中找到 "Season X" 目录，取其上一级作为剧集根目录名。
 * 这样无论路径深度如何，都能稳定提取到正确的剧集名。
 *
 * 示例：
 *   /storage/media/tv/葬送的芙莉莲 (2023)/Season 1/xxx.mkv
 *   → seriesName = "葬送的芙莉莲 (2023)", season = 1
 */
function extractSeriesInfo(path: string): { seriesName: string | null; season: number | null } {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  for (let i = 0; i < parts.length; i++) {
    const m = parts[i].match(/^season\s*(\d+)$/i);
    if (m) {
      return {
        seriesName: i > 0 ? parts[i - 1] : null,
        season: Number(m[1]),
      };
    }
  }
  // 没有找到 Season X 目录，倒数第三段作为剧集名
  return {
    seriesName: parts.length >= 3 ? parts[parts.length - 3] : null,
    season: null,
  };
}

export function useMediaGroups(tasks: Task[]): MediaGroup[] {
  return useMemo((): MediaGroup[] => {
    const map = new Map<string, MediaGroup>();

    for (const task of tasks) {
      const mtype = task.media_type || 'movie';

      let groupName: string;
      let seasonNum: number | null = task.season ?? null;

      if (mtype === 'tv') {
        const path = task.target_path || task.file_path || '';
        const { seriesName, season } = extractSeriesInfo(path);

        // 季号优先级：task.season > 路径 Season X 目录 > SxxExx 正则 > 1
        if (seasonNum == null && season != null) {
          seasonNum = season;
        }
        if (seasonNum == null) {
          const source = [task.target_path, task.file_path, task.file_name].filter(Boolean).join(' ');
          const m = source.match(/S(\d{1,2})E\d{1,3}/i);
          if (m) seasonNum = Number(m[1]);
        }
        if (seasonNum == null) seasonNum = 1;

        // 剧集名优先级：task.title > task.clean_name > 路径 Season X 上一级目录 > fallback id
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
      // 优先用有 title 的任务补全组级别的元数据
      if (!g.title && task.title) g.title = task.title;
      if (!g.clean_name && task.clean_name) g.clean_name = task.clean_name;

      if (mtype === 'movie' || mtype === 'mixed') {
        g.task = task;
      } else if (mtype === 'tv') {
        if (!g.seasons.has(seasonNum)) g.seasons.set(seasonNum, []);
        g.seasons.get(seasonNum)!.push(task);
      }
    }

    return Array.from(map.values());
  }, [tasks]);
}
