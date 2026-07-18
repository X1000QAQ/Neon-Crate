/**
 * groupingUtils - 媒体分组共享工具函数
 *
 * 所有与"如何识别一部剧/电影是同一个作品"相关的逻辑集中在此文件。
 * MediaWall（分页预聚合）和 useMediaGroups（渲染聚合）都使用同一套函数，
 * 确保两处的分组边界完全一致，消除分页单位与渲染单位不对齐的问题。
 */

import type { Task, PathConfig } from '@/types';

/**
 * 去掉标题末尾的年份标注，用于跨来源聚合时的 key 规范化。
 *
 * 示例：
 *   "葬送的芙莉莲 (2023)" → "葬送的芙莉莲"
 *   "Futurama (2022)"     → "Futurama"
 *   "葬送的芙莉莲"        → "葬送的芙莉莲"（无变化）
 */
export function stripYear(name: string): string {
  return name.replace(/\s*\(\d{4}\)\s*$/, '').trim();
}

/**
 * 根据用户配置的路径列表，从文件路径中提取剧集根目录名和季号。
 *
 * 匹配策略（按优先级）：
 * 1. 找到匹配的用户配置前缀，剥离后取第一段作为剧集名
 *    /storage/ready_for_ai_tv/Futurama/xxx.mkv  → "Futurama"
 *    /storage/media/tv/葬送的芙莉莲 (2023)/Season 1/xxx.mkv → "葬送的芙莉莲 (2023)"
 * 2. 没有配置路径匹配时，在路径段中找 Season X 目录，取其上一级
 * 3. 最终 fallback：倒数第三段
 *
 * 季号来源（按优先级）：
 * 1. 用户配置路径匹配后，在剩余路径段中找 Season X 目录
 * 2. fallback：在完整路径中找 Season X 目录
 */
export function extractSeriesInfo(
  path: string,
  configPaths: PathConfig[],
): { seriesName: string | null; season: number | null } {
  const normalized = path.replace(/\\/g, '/');

  const sorted = [...configPaths]
    .filter((p) => p.enabled && (p.category === 'tv' || p.category === 'mixed'))
    .sort((a, b) => b.path.length - a.path.length);

  for (const cp of sorted) {
    const prefix = cp.path.replace(/\\/g, '/').replace(/\/$/, '');
    if (!normalized.startsWith(prefix + '/')) continue;

    const relative = normalized.slice(prefix.length + 1);
    const parts = relative.split('/').filter(Boolean);
    if (parts.length === 0) continue;

    const seriesName = parts[0];

    let season: number | null = null;
    for (let i = 1; i < parts.length; i++) {
      const m = parts[i].match(/^season\s*(\d+)$/i);
      if (m) { season = Number(m[1]); break; }
    }

    return { seriesName, season };
  }

  // fallback：在完整路径中找 Season X 目录
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

/**
 * 从路径和 SxxExx 文件名中提取季号。
 *
 * 优先级：task.season > Season X 目录 > SxxExx 正则 > 1
 */
export function resolveSeasonNum(task: Task, configPaths: PathConfig[]): number {
  if (task.season != null) return task.season;

  const path = task.target_path || task.file_path || '';
  const { season } = extractSeriesInfo(path, configPaths);
  if (season != null) return season;

  const source = [task.target_path, task.file_path, task.file_name].filter(Boolean).join(' ');
  const m = source.match(/S(\d{1,2})E\d{1,3}/i);
  if (m) return Number(m[1]);

  return 1;
}

/**
 * 生成任务的分组 key — MediaWall 和 useMediaGroups 必须使用同一个函数。
 *
 * 对于 TV 任务：
 *   key = `tv::{规范化剧集名}`
 *   规范化 = stripYear(title || clean_name || 路径提取的剧集名)
 *
 * 对于电影/混合任务：
 *   key = `{mtype}::{title || clean_name || file_name || id}`
 */
export function buildGroupKey(task: Task, configPaths: PathConfig[]): string {
  const mtype = task.media_type || 'movie';

  if (mtype === 'tv') {
    const path = task.target_path || task.file_path || '';
    const { seriesName } = extractSeriesInfo(path, configPaths);
    const rawName = task.title || task.clean_name || seriesName || String(task.id);
    return `tv::${stripYear(rawName.trim())}`;
  }

  return `${mtype}::${(task.title || task.clean_name || task.file_name || String(task.id)).trim()}`;
}

/**
 * 提取用于 UI 显示的剧集标题。
 *
 * 优先级：task.title > task.clean_name > configPaths 前缀剥离的目录名 > Season X 上一级目录 > file_name > id
 */
export function resolveDisplayTitle(task: Task, configPaths: PathConfig[]): string {
  if (task.title) return task.title;
  if (task.clean_name) return task.clean_name;

  if (task.media_type === 'tv') {
    const path = task.target_path || task.file_path || '';
    if (path) {
      const { seriesName } = extractSeriesInfo(path, configPaths);
      if (seriesName) return seriesName;
    }
  }

  return task.file_name || `#${task.id}`;
}
