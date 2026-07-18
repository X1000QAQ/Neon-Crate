/**
 * NeuralPrimitives - 赛博朋克风格的 UI 原子组件库
 * 
 * 核心职责：
 * 提供一套可复用的基础 UI 组件，统一应用的视觉风格和交互体验。
 * 所有组件都遵循神经网络/赛博朋克的设计语言。
 * 
 * 组件清单：
 * 1. NeuralSection - 分区容器（左边框、悬浮效果）
 * 2. NeuralLabel - 标签文本（青色、大写、字间距）
 * 3. NeuralHint - 提示文本（更淡的青色、小号）
 * 4. NeuralInput - 输入框（左边框、focus 发光效果）
 * 5. NeuralTextarea - 多行文本框（同 NeuralInput 风格）
 * 6. NeuralSelect - 下拉选择器（同风格）
 * 7. NeuralToggle - 开关按钮（切换激活状态）
 * 8. NeuralCoreSwitch - 核心开关（用于语言切换、启用/禁用等）
 * 
 * 设计规范：
 * - 主色：青色（#06b6d4 / var(--cyber-cyan)）
 * - 背景：黑色半透明（bg-black/40）
 * - 边框：左侧竖线（border-l-2）
 * - Focus 效果：发光 + 背景加深
 * - 过渡：所有状态变化使用 transition-all
 * 
 * Props 模式：
 * - label：可选的标签文本
 * - hint：可选的提示文本
 * - wrapperClassName：容器的自定义类名
 * - 继承原生 HTML 属性（HTMLAttributes）
 * 
 * @component
 */

'use client';

import type React from 'react';
import { Power } from 'lucide-react';
import { cn } from '@/lib/utils';

type BaseProps = {
  label?: string;
  hint?: string;
};

type WrapperProps = {
  wrapperClassName?: string;
};

export function NeuralSection({
  title,
  children,
  className,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        'relative bg-black/20 border-l-2 border-cyber-cyan/30 p-6 transition-all',
        'hover:border-cyber-cyan/80',
        className
      )}
    >
      {title && (
        <div
          className="mb-4 text-cyber-cyan text-xs font-semibold uppercase tracking-[0.25em] font-advent"
          style={{ textShadow: '0 0 8px rgba(0, 230, 246, 0.6)' }}
        >
          {title}
        </div>
      )}
      {children}
    </section>
  );
}

export function NeuralLabel({ children }: { children: React.ReactNode }) {
  return (
    <label
      className="block text-cyber-cyan/70 text-xs font-semibold uppercase tracking-[0.25em] mb-3"
     
    >
      {children}
    </label>
  );
}

export function NeuralHint({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="mt-2 text-cyber-cyan/55 text-xs"
     
    >
      {children}
    </p>
  );
}

export function NeuralInput({
  label,
  hint,
  wrapperClassName,
  ...props
}: BaseProps & WrapperProps & React.InputHTMLAttributes<HTMLInputElement>) {
  const { className: inputClassName, style, onFocus, onBlur, ...rest } = props;
  return (
    <div className={wrapperClassName}>
      {label && <NeuralLabel>{label}</NeuralLabel>}
      <input
        {...rest}
        className={cn(
          'neural-input font-hacked',
          'w-full bg-black/40 text-cyber-cyan px-4 py-3 text-base font-normal',
          'border-0 border-l-2 border-cyber-cyan/40',
          'focus:outline-none focus:bg-black/60',
          'placeholder:text-cyber-cyan/40',
          'transition-all',
          inputClassName
        )}
        style={{
          boxShadow: 'inset 0 0 20px rgba(0, 0, 0, 0.6)',
          ...(style || {}),
        }}
        onFocus={(e) => {
          onFocus?.(e);
          e.currentTarget.style.boxShadow =
            '0 0 20px rgba(0, 230, 246, 0.4), inset 0 0 20px rgba(0, 230, 246, 0.1)';
        }}
        onBlur={(e) => {
          onBlur?.(e);
          e.currentTarget.style.boxShadow = 'inset 0 0 20px rgba(0, 0, 0, 0.6)';
        }}
      />
      {hint && <NeuralHint>{hint}</NeuralHint>}
    </div>
  );
}

export function NeuralTextarea({
  label,
  hint,
  wrapperClassName,
  ...props
}: BaseProps & WrapperProps & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className: textareaClassName, style, onFocus, onBlur, ...rest } = props;
  return (
    <div className={wrapperClassName}>
      {label && <NeuralLabel>{label}</NeuralLabel>}
      <textarea
        {...rest}
        className={cn(
          'neural-textarea font-hacked',
          'w-full bg-black/40 text-cyber-cyan px-4 py-3 text-base font-normal resize-none',
          'border-0 border-l-2 border-cyber-cyan/40',
          'focus:outline-none focus:bg-black/60',
          'transition-all',
          textareaClassName
        )}
        style={{
          boxShadow: 'inset 0 0 20px rgba(0, 0, 0, 0.6)',
          ...(style || {}),
        }}
        onFocus={(e) => {
          onFocus?.(e);
          e.currentTarget.style.boxShadow =
            '0 0 20px rgba(0, 230, 246, 0.4), inset 0 0 20px rgba(0, 230, 246, 0.1)';
        }}
        onBlur={(e) => {
          onBlur?.(e);
          e.currentTarget.style.boxShadow = 'inset 0 0 20px rgba(0, 0, 0, 0.6)';
        }}
      />
      {hint && <NeuralHint>{hint}</NeuralHint>}
    </div>
  );
}

export function NeuralSelect({
  label,
  hint,
  wrapperClassName,
  children,
  ...props
}: BaseProps &
  WrapperProps &
  React.SelectHTMLAttributes<HTMLSelectElement> & { children: React.ReactNode }) {
  const { className: selectClassName, style, onFocus, onBlur, ...rest } = props;
  return (
    <div className={wrapperClassName}>
      {label && <NeuralLabel>{label}</NeuralLabel>}
      <select
        {...rest}
        className={cn(
          'neural-select font-advent',
          'w-full bg-black/40 text-cyber-cyan px-4 py-3 text-base font-normal',
          'border-0 border-l-2 border-cyber-cyan/40',
          'focus:outline-none focus:bg-black/60',
          'transition-all',
          selectClassName
        )}
        style={{
          boxShadow: 'inset 0 0 20px rgba(0, 0, 0, 0.6)',
          ...(style || {}),
        }}
        onFocus={(e) => {
          onFocus?.(e);
          e.currentTarget.style.boxShadow =
            '0 0 20px rgba(0, 230, 246, 0.4), inset 0 0 20px rgba(0, 230, 246, 0.1)';
        }}
        onBlur={(e) => {
          onBlur?.(e);
          e.currentTarget.style.boxShadow = 'inset 0 0 20px rgba(0, 0, 0, 0.6)';
        }}
      >
        {children}
      </select>
      {hint && <NeuralHint>{hint}</NeuralHint>}
    </div>
  );
}

export function NeuralCoreSwitch({
  active,
  onToggle,
  size = 96,
  label,
  statusText,
  className,
}: {
  active: boolean;
  onToggle: () => void;
  size?: number;
  label?: string;
  statusText?: string;
  className?: string;
}) {
  const px = `${size}px`;
  const iconSize = Math.max(18, Math.round(size * 0.25));
  const innerSize = Math.max(34, Math.round(size * 0.5));

  return (
    <div className={cn('flex items-center gap-6', className)}>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          'relative rounded-full transition-all shrink-0',
          'hover:scale-110 focus:outline-none'
        )}
        style={{
          width: px,
          height: px,
          minWidth: px,
          minHeight: px,
          background: active
            ? 'radial-gradient(circle, rgba(0, 230, 246, 0.85) 0%, rgba(0, 230, 246, 0.28) 52%, rgba(0, 0, 0, 0) 100%)'
            : 'radial-gradient(circle, rgba(0, 230, 246, 0.18) 0%, rgba(0, 0, 0, 0) 70%)',
          boxShadow: active
            ? '0 0 17px rgba(0, 230, 246, 0.75), 0 0 7px rgba(0, 230, 246, 0.35), inset 0 0 11px rgba(0, 230, 246, 0.45)'
            : '0 0 12px rgba(0, 230, 246, 0.22), inset 0 0 10px rgba(0, 230, 246, 0.08)',
        }}
        aria-pressed={active}
      >
        <div
          className={cn(
            'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 transition-all',
            active
              ? 'border-white bg-cyber-cyan'
              : 'border-cyber-cyan/50 bg-black'
          )}
          style={{
            width: `${innerSize}px`,
            height: `${innerSize}px`,
            boxShadow: active ? '0 0 20px rgba(0, 230, 246, 1)' : 'none',
          }}
        >
          <Power
            className={cn(
              'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
              active ? 'text-black' : 'text-cyber-cyan'
            )}
            style={{ width: `${iconSize}px`, height: `${iconSize}px` }}
          />
        </div>
        {active && (
          <>
            <div
              className="absolute inset-0 rounded-full border-2 border-cyber-cyan animate-ping"
              style={{ animationDuration: '2s', transform: 'scale(0.5)', willChange: 'transform' }}
            />
            <div
              className="absolute inset-0 rounded-full border border-cyber-cyan animate-ping"
              style={{ animationDuration: '3s', animationDelay: '0.5s', transform: 'scale(0.5)', willChange: 'transform' }}
            />
          </>
        )}
      </button>

      {(label || statusText) && (
        <div className="min-w-0">
          {label && (
            <div
              className="text-cyber-cyan/80 text-sm font-semibold uppercase tracking-[0.2em]"
             
            >
              {label}
            </div>
          )}
          {statusText && (
            <div
              className="mt-2 text-cyber-cyan text-sm"
              style={{
                textShadow: '0 0 10px rgba(0, 230, 246, 0.6)',
              }}
            >
              {statusText}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

