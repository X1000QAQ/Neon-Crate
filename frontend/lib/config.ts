/**
 * API 基础配置
 * 
 * 说明：
 * - 使用相对路径 `/api/v1`，通过 Next.js 的 rewrites 代理机制转发到后端
 * - 在开发环境下，Next.js 会将 `/api/v1/*` 的请求转发到 `http://localhost:8000/api/v1/*`
 * - 在生产 AIO 模式下，前后端共用一个端口（8000），相对路径会自动指向本地后端
 * 
 * 工作流程：
 * 1. 前端发起请求到 `/api/v1/tasks`
 * 2. 浏览器携带 Authorization Token
 * 3. Next.js 代理服务器转发请求到后端实际地址
 * 4. 响应原路返回前端
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';
