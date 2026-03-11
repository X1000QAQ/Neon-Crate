// ============================================================================
// Type Definitions - Extracted from api.ts for better organization
// ============================================================================

export interface Task {
  id: number;
  file_path: string;
  file_name?: string;
  media_type: 'movie' | 'tv';
  status: 'pending' | 'scraped' | 'failed' | 'archived' | 'ignored';
  tmdb_id?: number | string;
  imdb_id?: string;
  title?: string;
  year?: number | string;
  poster_path?: string;
  local_poster_path?: string;
  target_path?: string;
  sub_status?: 'pending' | 'scraped' | 'failed' | 'missing';
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

export interface SettingsConfig {
  settings: {
    ui_lang: string;
    min_size_mb: number;
    filename_clean_regex: string;
    cron_interval_min: number;
    cron_enabled: boolean;
    auto_process_enabled: boolean; // 前端 UI 专用：自动流水线总开关，后端忽略此字段
    auto_scrape: boolean;
    auto_subtitles: boolean;
    tmdb_api_key: string;
    os_api_key: string;
    sonarr_url: string;
    sonarr_api_key: string;
    radarr_url: string;
    radarr_api_key: string;
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
  };
  paths: Array<{
    id?: number;
    type: string;
    path: string;
    category: string;
    enabled?: boolean;
  }>;
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
