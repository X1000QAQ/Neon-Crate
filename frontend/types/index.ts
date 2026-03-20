// ============================================================================
// Type Definitions - Extracted from api.ts for better organization
// ============================================================================

export interface Task {
  id: number;
  file_path: string;
  file_name?: string;
  clean_name?: string;
  media_type: 'movie' | 'tv';
  status: 'pending' | 'archived' | 'failed' | 'ignored' | 'scraped';
  tmdb_id?: number;
  imdb_id?: string;
  title?: string;
  year?: number | string;  // DB 存储为 TEXT，后端未做类型转换，前端兼容两种类型
  poster_path?: string;
  local_poster_path?: string;
  target_path?: string;
  sub_status?: 'pending' | 'failed' | 'missing' | 'scraped' | 'found' | 'success';
  season?: number | null;
  episode?: number | null;
  created_at: string;
  is_archive?: boolean;
}

export interface TasksResponse {
  tasks: Task[];
  total: number;
  page: number;
  page_size: number;
}

export interface StatsResponse {
  movies: number;
  tv_shows: number;
  pending: number;
  completed: number;
}

export interface ScanResponse {
  message: string;
  task_id?: string | null;
}

// 授权决策层：下载意图的视觉确认载荷，携带元数据供前端渲染全屏确认界面
export interface PendingActionPayload {
  action: string;       // 意图代码（如 DOWNLOAD）
  label: string;        // 操作名称（如「下载」）
  description: string;  // 操作摘要
  // 下载意图专属元数据
  title?: string;       // TMDB 确认片名
  year?: string;        // 上映年份
  poster_url?: string;  // TMDB 海报完整 URL
  overview?: string;    // 剧情简介
  media_type?: string;  // movie | tv
  tmdb_id?: number;     // TMDB ID（用于精确下载）
  clean_name?: string;  // 原始中文片名（fallback 用）
  en_name?: string;     // 英文片名
  // 查重审计结果
  is_duplicate?: boolean;       // 是否已在库中
  existing_status?: string;     // 存在状态描述（如「已在库中」「正在监控」）
}

// 结构化候选列表单项
export interface CandidateItem {
  title: string;
  year: string;
  media_type: string;
  tmdb_id?: number;
}

export interface ChatResponse {
  response: string;
  action?: string;
  pending_action?: PendingActionPayload;
  candidates?: CandidateItem[];
  engine_tag?: string;  // v1.0.0 血缘溯源："cloud" | "local" | "local->cloud"
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  engine_tag?: string;  // v1.0.0 气泡标识用
  candidates?: import('./index').CandidateItem[];
}

export interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
  message: string;
  tag?: string;
}

export interface SystemSettings {
  ui_lang: string;
  min_size_mb: number;
  filename_clean_regex: string;
  cron_enabled: boolean;
  cron_interval_min: number;
  auto_process_enabled: boolean;
  auto_scrape: boolean;
  auto_subtitles: boolean;
  tmdb_api_key: string;
  os_api_key: string;
  radarr_url: string;
  radarr_api_key: string;
  sonarr_url: string;
  sonarr_api_key: string;
  llm_cloud_enabled: boolean;
  llm_local_enabled: boolean;
  llm_cloud_url: string;
  llm_cloud_key: string;
  llm_cloud_model: string;
  llm_local_url: string;
  llm_local_key: string;
  llm_local_model: string;
  ai_name: string;
  ai_persona: string;
  expert_archive_rules: string;
  master_router_rules: string;
  // 多语言偏好
  subtitle_lang: string;
  poster_lang: string;
  rename_lang: string;
  // 文件格式过滤
  supported_video_exts?: string;
  supported_subtitle_exts?: string;
}

export interface PathConfig {
  id?: number;
  type: string;
  path: string;
  category: string;
  enabled: boolean;
}

export interface SettingsConfig {
  settings: SystemSettings;
  paths: PathConfig[];
}

export interface AuthStatusResponse {
  initialized: boolean;
  message: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  username: string;
}

// ============================================================================
// Task Status Interfaces - 三大后台任务状态接口
// ============================================================================

export interface ScanStatus {
  is_running: boolean;
  last_scan_time: number | null;
  last_scan_count: number;
  error: string | null;
}

export interface ScrapeStatus {
  is_running: boolean;
  last_run_time: number | null;
  processed_count: number;
  error: string | null;
}

export interface SubtitleStatus {
  is_running: boolean;
  last_run_time: number | null;
  processed_count: number;
  error: string | null;
}
