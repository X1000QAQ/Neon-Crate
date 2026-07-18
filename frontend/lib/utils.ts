/**
 * utils - 前端通用工具函数集合
 *
 * 当前包含两类基础能力：
 * - `cn()`：合并 Tailwind CSS 类名，并自动处理冲突类名。
 * - `formatDate()`：兼容后端不同时间格式，统一输出中文本地化日期。
 *
 * 新手提示：
 * - 写组件 className 时优先使用 `cn()`，不要手动拼接复杂字符串。
 * - 展示后端时间字段时优先使用 `formatDate()`，避免浏览器解析差异。
 */
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * CSS 类名合并工具函数
 * 
 * 功能：合并 Tailwind CSS 类名，智能解决样式冲突
 * - clsx：根据条件动态拼接类名字符串
 * - twMerge：检测 Tailwind 类名冲突，后续类名优先级更高
 * 
 * 示例：
 * cn('px-2 py-1', 'px-3')  // 输出：'py-1 px-3'（px-3 覆盖 px-2）
 * cn('text-red-500', isPrimary && 'text-blue-500')  // 条件性应用类名
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 日期格式化函数
 * 
 * 功能：将后端返回的各种格式时间字符串转换为中文本地化日期显示
 * 
 * 支持的后端时间格式：
 * 1. ISO 8601：`2024-03-09T14:30:00`
 * 2. 逗号分隔：`2024-03-09, 14:30:00`
 * 3. 空格分隔：`2024-03-09 14:30:00`
 * 4. SQLite 时间戳：`2024-03-09 14:30:00.123`
 * 
 * 返回值：中文本地化格式 `2024-03-09 14:30`
 * 如果解析失败则返回 `"格式错误"` 提示
 */
export function formatDate(dateString: string): string {
  if (!dateString) return '刚刚';
  
  try {
    let cleanStr = dateString;
    
    // 处理带逗号的格式（如 "2024-03-09, 14:30:00"）
    cleanStr = cleanStr.replace(/,\s*/g, ' ');
    
    // 处理空格分隔的日期时间，转换为 ISO 8601 格式
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/.test(cleanStr)) {
      cleanStr = cleanStr.replace(' ', 'T');
    }
    
    // 处理 SQLite CURRENT_TIMESTAMP 格式
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+/.test(cleanStr)) {
      cleanStr = cleanStr.replace(' ', 'T');
    }
    
    const date = new Date(cleanStr);
    
    // 验证日期有效性
    if (isNaN(date.getTime())) {
      console.warn(`[formatDate] 无法解析日期: ${dateString}`);
      return '格式错误';
    }
    
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (error) {
    console.error(`[formatDate] 日期解析异常: ${dateString}`, error);
    return '格式错误';
  }
}
