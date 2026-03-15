/** @type {import('next').NextConfig} */
const nextConfig = {
  // 🚀 AIO 模式：静态导出，由 FastAPI 后端统一托管
  // 1. 生成纯静态产物（out/ 目录）
  // -> 2. Dockerfile 多阶段构建将 out/ 注入 backend/static/
  // -> 3. FastAPI main.py 挂载 /static 目录，单端口（8000）托管前后端
  output: 'export',

  // AIO 模式下前端与后端同域，使用相对路径，彻底消灭跨域问题
  // API 请求走 /api/v1/... 相对路径，由同一个 8000 端口响应
  // ⚠️ 注意：output: 'export' 与 rewrites() 不兼容，已移除代理规则
};

module.exports = nextConfig;
