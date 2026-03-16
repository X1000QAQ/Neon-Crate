import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function formatDate(dateString: string): string {
  if (!dateString) return '刚刚';
  
  try {
    // 多重兼容策略：处理后端返回的各种时间格式
    let cleanStr = dateString;
    
    // 策略 1：处理带逗号的格式（如 "2024-03-09, 14:30:00"）
    cleanStr = cleanStr.replace(/,\s*/g, ' ');
    
    // 策略 2：处理空格分隔的日期时间（如 "2024-03-09 14:30:00"）
    // 转换为 ISO 8601 格式
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/.test(cleanStr)) {
      cleanStr = cleanStr.replace(' ', 'T');
    }
    
    // 策略 3：处理 SQLite CURRENT_TIMESTAMP 格式
    // 如 "2024-03-09 14:30:00.123"
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
