/**
 * LanguageSelector - 语言双按钮切换组件
 * 
 * 核心职责：
 * - 显示中文/英文两个切换按钮
 * - 实时反馈当前选中的语言
 * - 通过 onChange 回调通知父组件
 * 
 * Props 说明：
 * - label：显示在上方的标签文本
 * - description：标签下方的描述文字
 * - value：当前选中的语言（'zh' 或 'en'）
 * - onChange：语言切换时的回调函数
 * - t：翻译函数（用于获取本地化的语言名称）
 * 
 * 视觉效果：
 * - 已选中：青色发光边框 + 背景填充 + 阴影
 * - 未选中：灰色边框 + 透明背景 + hover 效果
 * 
 * 使用场景：
 * - BasicSettings Tab 中的 UI 语言切换
 * - 多语言偏好设置（字幕语言、海报语言等）
 * 
 * @component
 */

'use client';
import { cn } from '@/lib/utils';

interface Props {
  label: string;
  description: string;
  value: string;
  onChange: (val: string) => void;
  t: (key: string) => string;
}

export function LanguageSelector({ label, description, value, onChange, t }: Props) {
  return (
    <div className="flex flex-col space-y-2">
      <div>
        <label className="text-sm font-medium text-cyber-cyan">{label}</label>
        <p className="text-xs text-gray-400 mt-1">{description}</p>
      </div>
      <div className="flex gap-2">
        {['zh', 'en'].map((lang) => (
          <button
            key={lang}
            onClick={() => onChange(lang)}
            className={cn(
              "px-4 py-2 rounded text-sm font-mono transition-all border",
              value === lang
                ? "bg-cyber-cyan/20 border-cyber-cyan text-cyber-cyan shadow-[0_0_10px_rgba(0,230,246,0.3)]"
                : "bg-transparent border-gray-700 text-gray-400 hover:border-gray-500"
            )}
          >
            {t(`lang_${lang}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
