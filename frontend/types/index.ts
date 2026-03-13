// ============================================================================
// Type Definitions - Extracted from api.ts for better organization
// ============================================================================

export interface Task {
  id: number;
  file_path: string;
  file_name?: string;
  media_type: 'movie' | 'tv';
  status: 'pending' | 'archived' | 'failed' | 'ignored';
  tmdb_id?: number;
  imdb_id?: string;
  title?: string;
  year?: number;
  poster_path?: string;
  local_poster_path?: string;
  target_path?: string;
  sub_status?: 'pending' | 'success' | 'failed' | 'missing';
  season?: number | null;
  episode?: number | null;
  created_at: string;
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

export interface ChatResponse {
  response: string;
  action?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
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
  llm_provider: string;
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
