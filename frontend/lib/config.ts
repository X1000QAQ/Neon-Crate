// API 基础配置
// 使用相对路径，通过 Next.js rewrites 代理到后端
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';

// 🔍 调试锚点：确认环境变量是否被正确注入
console.log('[Config-Debug] Current API_BASE:', API_BASE);
