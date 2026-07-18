/** @type {import('next').NextConfig} */
const nextConfig = {
  // 🚀 双模式支持：本地开发 + AIO 部署
  // - 本地开发（npm run dev）：output: 'standalone'，启用代理
  // - AIO 部署（docker build）：output: 'export'，静态导出
  output: process.env.NEXT_PUBLIC_BUILD_MODE === 'aio' ? 'export' : 'standalone',

  // 🔧 SPA 路由回退修复：启用尾部斜杠
  // 本地开发和 AIO 都需要这个
  trailingSlash: true,

  // 🌐 本地开发模式：API 代理配置
  // AIO 模式下 rewrites 不生效（因为 output: 'export'），但没关系
  // 因为 AIO 时前后端同端口，相对路径会自动指向本地后端
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: '/api/v1/:path*',
          destination: `${process.env.NEXT_PUBLIC_API_BACKEND || 'http://127.0.0.1:8000'}/api/v1/:path*`,
        },
      ],
    };
  },
};

module.exports = nextConfig;
