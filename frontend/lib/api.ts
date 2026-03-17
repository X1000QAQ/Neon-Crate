import { API_BASE } from './config';
import { ApiError, notifyLinkDown, notifyLinkUp } from './apiError';
import type {
  Task,
  TasksResponse,
  StatsResponse,
  ScanResponse,
  ChatResponse,
  LogEntry,
  SettingsConfig,
  AuthStatusResponse,
  TokenResponse,
} from '@/types';

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

function getHeaders(includeAuth: boolean = true): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  
  if (includeAuth) {
    const token = getAuthToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }
  
  return headers;
}

async function safeJson<T>(res: Response): Promise<T> {
  const ct = res.headers.get('content-type') ?? '';
  if (!ct.includes('application/json')) {
    throw new ApiError('INVALID_CONTENT', res.status, `Expected JSON but got content-type: ${ct}`);
  }
  return res.json() as Promise<T>;
}

async function secureFetch(url: string, options?: RequestInit, timeoutMs: number = 15000): Promise<Response> {
  // 🚀 异步链路治理 — 步骤 1：注入超时 AbortSignal
  // secureFetch 内建超时熔断：timeoutMs 后自动 abort，防止请求无限挂起。
  // 若调用方（如 chat()）额外传入外部 signal，两个 signal 通过 options 合并，
  // 任意一个触发都能物理切断 fetch 连接。
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // [P-05 修复] 手动监听外部 signal，将其中止事件桥接到内部 controller，
  // 解决 { ...options, signal: controller.signal } 覆盖外部 signal 导致信号联动失效的问题。
  // 不使用 AbortSignal.any() 以保持兼容性。
  if (options?.signal) {
    options.signal.addEventListener('abort', () => controller.abort());
  }

  let res: Response;
  try {
    res = await fetch(url, { ...options, signal: controller.signal });
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err?.name === 'AbortError') {
      // 🚀 异步链路治理 — 步骤 2：超时物理掐断
      // AbortError 说明请求超时被熔断，而非用户主动取消；向上抛 REQUEST_TIMEOUT 区分语义。
      throw new ApiError('REQUEST_TIMEOUT', 408, `Request timed out after ${timeoutMs / 1000} seconds`);
    }
    notifyLinkDown();
    throw new ApiError('NETWORK_ERROR', 0, err?.message ?? 'Network error');
  }
  clearTimeout(timeoutId);

  // 🚀 复航信号：只要不是 5xx 或断网，判定链路通畅，自动解除全局红色网络警告横幅
  if (res.status < 500) {
    notifyLinkUp();
  }

  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('token');
      window.location.href = '/auth/login';
    }
    throw new ApiError('UNAUTHORIZED', 401, 'Unauthorized');
  }

  if (res.status === 403) throw new ApiError('FORBIDDEN', 403, '权限不足或被拒绝访问');
  if (res.status === 404) throw new ApiError('NOT_FOUND', 404, '请求的资源不存在');
  if (res.status === 429) throw new ApiError('RATE_LIMITED', 429, '请求过于频繁，请稍后重试');
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError('VALIDATION_ERROR', 422, typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || '参数错误'));
  }

  if (res.status >= 500) {
    notifyLinkDown();
    throw new ApiError('SERVER_ERROR', res.status, `Server error: ${res.status}`);
  }

  return res;
}

export const api = {
  async authStatus(): Promise<AuthStatusResponse> {
    const res = await fetch(`${API_BASE}/auth/status`);
    if (!res.ok) throw new Error('Failed to check auth status');
    return safeJson<AuthStatusResponse>(res);
  },

  async initAuth(username: string, password: string): Promise<{ success: boolean; message: string }> {
    const res = await fetch(`${API_BASE}/auth/init`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || '初始化失败');
    }
    return safeJson(res);
  },

  async login(username: string, password: string): Promise<TokenResponse> {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || '登录失败');
    }
    return safeJson<TokenResponse>(res);
  },

  async getTasks(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    media_type?: string;
    search?: string;
  }): Promise<TasksResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.append('page', params.page.toString());
    if (params?.page_size) query.append('page_size', params.page_size.toString());
    if (params?.status) query.append('status', params.status);
    if (params?.media_type) query.append('media_type', params.media_type);
    if (params?.search) query.append('search', params.search);

    const res = await secureFetch(`${API_BASE}/tasks?${query}`, {
      headers: getHeaders(),
    });
    
    if (!res.ok) throw new Error('Failed to fetch tasks');
    return safeJson<TasksResponse>(res);
  },

  async getStats(): Promise<StatsResponse> {
    const res = await secureFetch(`${API_BASE}/system/stats`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch stats');
    return safeJson<StatsResponse>(res);
  },

  async triggerScan(): Promise<ScanResponse> {
    const res = await secureFetch(`${API_BASE}/tasks/scan`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to trigger scan');
    return safeJson<ScanResponse>(res);
  },

  async getScanStatus(): Promise<any> {
    const res = await secureFetch(`${API_BASE}/tasks/scan/status`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch scan status');
    return safeJson(res);
  },

  async triggerScrapeAll(): Promise<ScanResponse> {
    const res = await secureFetch(`${API_BASE}/tasks/scrape_all`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to trigger scrape all');
    return safeJson<ScanResponse>(res);
  },

  async triggerFindSubtitles(): Promise<ScanResponse> {
    const res = await secureFetch(`${API_BASE}/tasks/find_subtitles`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to trigger find subtitles');
    return safeJson<ScanResponse>(res);
  },

  async getSystemLogs(tags?: string): Promise<LogEntry[]> {
    const url = tags
      ? `${API_BASE}/system/logs?tags=${encodeURIComponent(tags)}`
      : `${API_BASE}/system/logs`;
    const res = await secureFetch(url, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch system logs');
    const data = await safeJson<{ logs?: LogEntry[] }>(res);
    return data.logs || [];
  },

  async deleteTask(taskId: number): Promise<void> {
    const res = await secureFetch(`${API_BASE}/tasks/${taskId}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to delete task');
  },

  async deleteBatchTasks(ids: number[]): Promise<{ success: boolean; deleted: number }> {
    const res = await secureFetch(`${API_BASE}/tasks/delete_batch`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) throw new Error('Failed to delete batch');
    return safeJson(res);
  },

  async purgeAllTasks(): Promise<{ success: boolean; deleted: number; message: string }> {
    const res = await secureFetch(`${API_BASE}/tasks/purge`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ confirm: 'CONFIRM' }),
    });
    if (!res.ok) throw new Error('Failed to purge tasks');
    return safeJson(res);
  },

  async chat(message: string, signal?: AbortSignal): Promise<ChatResponse> {
    const res = await secureFetch(`${API_BASE}/agent/chat`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ message }),
      ...(signal ? { signal } : {}),
    }, 60000);  // AI 推理最长 60s（本地 14B 模型宽限）
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP Error ${res.status}`);
    }
    return safeJson<ChatResponse>(res);
  },

  // 授权决策层：下载意图的用户授权执行入口
  async confirmAction(actionCode: string): Promise<ChatResponse> {
    const res = await secureFetch(`${API_BASE}/agent/confirm`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ message: actionCode }),
    }, 60000);  // 下载授权执行同样需要等待 LLM + Servarr 响应
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP Error ${res.status}`);
    }
    return safeJson<ChatResponse>(res);
  },

  async getSettings(): Promise<SettingsConfig> {
    const res = await secureFetch(`${API_BASE}/tasks/settings`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch settings');
    return safeJson<SettingsConfig>(res);
  },

  async updateSettings(config: SettingsConfig): Promise<{ success: boolean; message: string }> {
    const res = await secureFetch(`${API_BASE}/tasks/settings`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error('Failed to update settings');
    return safeJson(res);
  },

  async resetSettings(target: 'ai' | 'regex' | 'formats'): Promise<{ success: boolean; message: string }> {
    const res = await secureFetch(`${API_BASE}/tasks/settings/reset`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ target }),
    });
    if (!res.ok) throw new Error('Failed to reset settings');
    return safeJson(res);
  },

  async verifyApiKey(keyType: string, keyValue: string, url?: string): Promise<boolean> {
    try {
      const res = await secureFetch(`${API_BASE}/tasks/settings/verify-key`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ 
          key_type: keyType, 
          key_value: keyValue,
          url: url || undefined
        })
      });
      const data = await safeJson<{ valid: boolean }>(res);
      return data.valid === true;
    } catch (error) {
      console.error('Failed to verify key:', error);
      return false;
    }
  },

  async retryTask(id: number): Promise<{ success: boolean; message: string }> {
    const res = await secureFetch(`${API_BASE}/tasks/${id}/retry`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to retry task');
    return safeJson(res);
  },

  async searchTmdb(keyword: string, mediaType: string): Promise<{
    tmdb_id: number;
    title: string;
    year: string;
    overview: string;
    poster_path: string | null;
    imdb_id: string | null;
  }[]> {
    const res = await secureFetch(
      `${API_BASE}/tasks/search_tmdb?keyword=${encodeURIComponent(keyword)}&media_type=${encodeURIComponent(mediaType)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail || 'TMDB 搜索失败');
    }
    return safeJson(res);
  },

  async rebuildTask(params: {
    task_id: number;
    is_archive?: boolean;
    tmdb_id?: number;
    keyword_hint?: string;
    media_type?: string;
    refix_nfo?: boolean;
    refix_poster?: boolean;
    refix_subtitle?: boolean;
    nuclear_reset?: boolean;
    season?: number;
    episode?: number;
  }): Promise<{
    success: boolean;
    task_id: number;
    title: string;
    tmdb_id: number | null;
    rebuilt: { nfo: boolean; poster: boolean; subtitle: string; nuclear: boolean };
    message: string;
  }> {
    // ── 补录任务请求业务链路 ──
    // 1. 合并默认参数与用户传入参数 -> 2. 构建请求体 -> 3. 发送 POST 请求到后端 -> 
    // 4. 校验响应状态 -> 5. 解析 JSON 响应 -> 6. 返回重建结果
    const res = await secureFetch(`${API_BASE}/tasks/manual_rebuild`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        // 1. 设置默认参数（若前端未传入则使用默认值）
        is_archive: true,
        media_type: 'movie',
        refix_nfo: true,
        refix_poster: true,
        refix_subtitle: true,
        nuclear_reset: false,
        // 2. 覆盖默认参数（前端传入的参数优先级更高）
        ...params,
      }),
    }, 60000);  // 60 秒超时（核级清理可能耗时较长）
    
    // 3. 校验响应状态
    if (!res.ok) {
      // 4. 尝试解析错误信息
      const errData = await res.json().catch(() => ({}));
      throw new Error((errData as { detail?: string }).detail || 'Failed to rebuild task');
    }
    
    // 5. 解析并返回成功响应
    return safeJson(res);
  },
};
