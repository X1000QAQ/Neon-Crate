/**
 * 前端 API 客户端模块
 * 
 * 职责：
 * - 统一管理所有后端 API 调用
 * - 处理 HTTP 请求和响应
 * - 自动鉴权和错误处理
 * - 监控网络链路状态
 * 
 * 核心特性：
 * - 内建超时熔断机制（默认 15 秒）
 * - 支持外部 AbortSignal 取消请求
 * - 自动 Token 刷新和 401 重定向
 * - 网络故障自动通知（全屏横幅）
 * 
 * 架构模式：
 * secureFetch() ← 超时 + 错误处理基础
 * └─ api.{method}() ← 业务 API 方法
 */

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

/**
 * 从 localStorage 获取认证 Token
 * 
 * @returns Token 字符串，未登录时返回 null
 * @note 仅在浏览器环境可用（SSR 时返回 null）
 */
function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

/**
 * 构建 HTTP 请求头
 * 
 * 功能：
 * - 添加 Content-Type: application/json
 * - 自动附加 Authorization Bearer Token（若已登录）
 * 
 * @param includeAuth - 是否附加认证 Token（默认 true）
 * @returns 请求头对象，用于 fetch 配置
 * 
 * @example
 * const headers = getHeaders();  // 包含 token
 * const headers = getHeaders(false);  // 不包含 token（用于公开接口）
 */
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

/**
 * 安全的 JSON 响应解析
 * 
 * 功能：
 * - 验证响应的 Content-Type 为 JSON
 * - 若不是 JSON，抛出明确的错误
 * - 避免解析非 JSON 响应导致的错误
 * 
 * @param res - fetch Response 对象
 * @returns 解析后的 JSON 数据
 * @throws ApiError 若 Content-Type 不包含 application/json
 */
async function safeJson<T>(res: Response): Promise<T> {
  const ct = res.headers.get('content-type') ?? '';
  if (!ct.includes('application/json')) {
    throw new ApiError('INVALID_CONTENT', res.status, `Expected JSON but got content-type: ${ct}`);
  }
  return res.json() as Promise<T>;
}


/**
 * 安全的 HTTP 请求封装
 * 
 * 核心职责：
 * 1. 内建超时熔断（防止请求无限挂起）
 * 2. 统一错误处理（区分不同错误类型）
 * 3. 网络链路监控（故障时显示全屏警告）
 * 4. 支持外部中止信号（如 AI 对话中途取消）
 * 
 * 错误分类：
 * - REQUEST_TIMEOUT (408)：超时（内建或外部中止）
 * - NETWORK_ERROR (0)：网络故障
 * - UNAUTHORIZED (401)：Token 过期，自动重定向登录页
 * - FORBIDDEN (403)：权限不足
 * - NOT_FOUND (404)：资源不存在
 * - RATE_LIMITED (429)：请求过于频繁
 * - VALIDATION_ERROR (422)：参数校验失败
 * - SERVER_ERROR (5xx)：服务器错误
 * 
 * @param url - 请求 URL
 * @param options - fetch 配置（可包含 signal 用于外部取消）
 * @param timeoutMs - 超时时间（毫秒，默认 15000）
 * @returns Response 对象
 * @throws ApiError 若请求失败
 * 
 * 工作流程：
 * 1. 创建内部 AbortController 并设置超时
 * 2. 若外部传入 signal，监听其 abort 事件，联动内部控制器
 * 3. 发送 fetch 请求，捕获 AbortError 并转换为 REQUEST_TIMEOUT
 * 4. 检查 HTTP 状态码，针对不同错误采取对应处理
 * 5. 状态 < 500 时，通知网络恢复；状态 >= 500 时，通知网络故障
 */
async function secureFetch(url: string, options?: RequestInit, timeoutMs: number = 15000): Promise<Response> {
  // 步骤 1：创建内部 AbortController，并在 timeoutMs 后自动 abort
  // 这样做是为了防止后端未及时响应导致请求无限挂起
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // 步骤 2：桥接外部中止信号
  // 若调用方传入 signal（如 AiSidebar 中止 AI 对话），则监听其 abort 事件
  // 当外部 signal abort 时，同时 abort 内部控制器，实现双信号联动
  // （不使用 AbortSignal.any() 以保持浏览器兼容性）
  if (options?.signal) {
    options.signal.addEventListener('abort', () => controller.abort());
  }

  let res: Response;
  try {
    // 步骤 3：发送 fetch 请求，使用内部控制器的 signal
    res = await fetch(url, { ...options, signal: controller.signal });
  } catch (err: any) {
    clearTimeout(timeoutId);
    
    // 步骤 4：区分不同的中止原因
    if (err?.name === 'AbortError') {
      // AbortError 可能由超时或用户主动取消引起
      // 这里将其视为超时（REQUEST_TIMEOUT），便于前端统一处理
      throw new ApiError('REQUEST_TIMEOUT', 408, `Request timed out after ${timeoutMs / 1000} seconds`);
    }
    
    // 网络错误：发送全局"网络故障"通知
    notifyLinkDown();
    throw new ApiError('NETWORK_ERROR', 0, err?.message ?? 'Network error');
  }
  clearTimeout(timeoutId);

  // 步骤 5：根据 HTTP 状态码判定网络链路状态
  // 若状态码 < 500（即不是服务器错误），则判定链路通畅，解除故障警告
  if (res.status < 500) {
    notifyLinkUp();
  }

  // 步骤 6：处理特殊 HTTP 状态码

  // 401 Unauthorized：Token 过期或无效
  // 自动清除本地 Token，重定向到登录页，用户需重新登录
  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('token');
      window.location.href = '/auth/login';
    }
    throw new ApiError('UNAUTHORIZED', 401, 'Unauthorized');
  }

  // 403 Forbidden：无权访问此资源
  if (res.status === 403) throw new ApiError('FORBIDDEN', 403, '权限不足或被拒绝访问');
  
  // 404 Not Found：资源不存在
  if (res.status === 404) throw new ApiError('NOT_FOUND', 404, '请求的资源不存在');
  
  // 429 Too Many Requests：请求过于频繁，触发限流
  if (res.status === 429) throw new ApiError('RATE_LIMITED', 429, '请求过于频繁，请稍后重试');
  
  // 422 Unprocessable Entity：参数校验失败
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError('VALIDATION_ERROR', 422, typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || '参数错误'));
  }

  // 5xx Server Error：服务器错误
  // 发送全局"网络故障"通知（显示离线横幅）
  if (res.status >= 500) {
    notifyLinkDown();
    throw new ApiError('SERVER_ERROR', res.status, `Server error: ${res.status}`);
  }

  return res;
}

/**
 * 统一的 API 客户端对象
 * 
 * 包含所有与后端的交互方法。每个方法都：
 * - 使用 secureFetch 确保安全性和错误处理
 * - 自动附加认证 Token（getHeaders 函数）
 * - 返回 Promise 类型的响应数据
 * - 抛出 ApiError 异常便于调用方捕获
 */
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

  async resetSettings(target: 'ai' | 'formats'): Promise<{ success: boolean; message: string }> {
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
    scope?: 'series' | 'season' | 'episode';
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
