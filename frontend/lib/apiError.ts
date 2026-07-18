/**
 * API 错误处理模块
 * 
 * 核心职责：
 * 1. 统一管理 HTTP 请求的错误信息
 * 2. 通过 CustomEvent 全局通知网络状态变化（用于显示/隐藏离线提示横幅）
 */

/**
 * ApiError 自定义错误类
 * 
 * 属性说明：
 * - code: 错误代码（用于前端区分不同错误类型，如 REQUEST_TIMEOUT / UNAUTHORIZED 等）
 * - status: HTTP 状态码（如 401 / 404 / 500）
 * - message: 用户可读的错误描述
 * 
 * 使用示例：
 * throw new ApiError('REQUEST_TIMEOUT', 408, '请求超时，请检查网络连接');
 */
export class ApiError extends Error {
  code: string;      // 错误分类代码（REQUEST_TIMEOUT / NETWORK_ERROR / UNAUTHORIZED 等）
  status: number;    // HTTP 状态码

  constructor(code: string, status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

/**
 * 通知全局网络链路断开
 * 
 * 工作原理：
 * 1. 发送 CustomEvent 事件到 window
 * 2. NetworkContext 监听此事件
 * 3. 触发全屏红色"网络故障"提示横幅
 * 
 * 触发场景：
 * - 请求超时（5xx 错误）
 * - 网络不可达（NETWORK_ERROR）
 */
export function notifyLinkDown(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('neon-network-down'));
  }
}

/**
 * 通知全局网络链路恢复
 * 
 * 触发场景：
 * - 任何成功的 HTTP 响应（状态码 < 500）
 */
export function notifyLinkUp(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('neon-network-up'));
  }
}
