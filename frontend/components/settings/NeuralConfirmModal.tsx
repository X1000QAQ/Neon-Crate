/**
 * NeuralConfirmModal - 通用确认弹窗组件
 * 
 * 核心职责：
 * 1. 显示重要操作的确认弹窗
 * 2. 支持"默认"和"警告"两种视觉风格
 * 3. 使用 createPortal 挂载到 document.body（避免层叠上下文问题）
 * 4. 支持 Escape 键快速关闭
 * 5. 管理页面滚动锁定（防止弹窗后面的页面滚动）
 * 
 * Props 说明：
 * - isOpen：弹窗是否打开
 * - title：弹窗标题
 * - message：确认提示文本
 * - confirmLabel：确认按钮文本（默认："Confirm"）
 * - cancelLabel：取消按钮文本（默认："Cancel"）
 * - variant：视觉风格（'default' 青色 | 'warning' 橙色）
 * - onConfirm：确认按钮回调
 * - onCancel：取消按钮回调
 * 
 * 视觉效果：
 * - variant='default'：青色边框 + 青色发光 + 青色确认按钮
 * - variant='warning'：橙色边框 + 橙色发光 + 橙色确认按钮
 * - 全屏半透明黑色背景 + 毛玻璃效果
 * - 中央居中显示的弹窗面板
 * 
 * 交互特性：
 * - 点击背景区域可关闭弹窗
 * - 按 Escape 键可快速关闭
 * - 两个按钮提供明确的选择
 * 
 * 使用场景：
 * - 格式重置确认
 * - 数据库清空确认
 * - 批量删除确认
 * - 其他重要操作确认
 * 
 * @component
 */

'use client';

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface NeuralConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'warning';
  onConfirm: () => void;
  onCancel: () => void;
}

export default function NeuralConfirmModal({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  onCancel,
}: NeuralConfirmModalProps) {
  const portalRef = useRef<Element | null>(null);

  useEffect(() => {
    portalRef.current = document.body;
  }, []);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onCancel]);

  if (!isOpen || typeof document === 'undefined') return null;

  const isWarning = variant === 'warning';

  const panelShadow = isWarning
    ? '0 0 60px rgba(245,158,11,0.15)'
    : '0 0 60px rgba(0,255,255,0.08)';
  const neonLine = isWarning
    ? 'bg-gradient-to-r from-transparent via-amber-500/60 to-transparent'
    : 'bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent';
  const titleColor = isWarning ? 'text-amber-400' : 'text-cyber-cyan';
  const confirmBtnClass = isWarning
    ? 'bg-amber-500 text-black shadow-[0_0_16px_rgba(245,158,11,0.4)] hover:shadow-[0_0_24px_rgba(245,158,11,0.6)] hover:brightness-110'
    : 'bg-cyber-cyan text-black shadow-[0_0_16px_rgba(0,255,255,0.3)] hover:shadow-[0_0_24px_rgba(0,255,255,0.5)] hover:brightness-110';

  const modal = (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center"
      onClick={onCancel}
      style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0 }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-xl" />

      {/* Panel */}
      <div
        className="relative w-full max-w-sm mx-4 rounded-xl border border-white/10 bg-black/90 animate-in fade-in zoom-in-95 duration-200"
        style={{ boxShadow: panelShadow }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Neon top line */}
        <div className={`absolute top-0 left-6 right-6 h-px rounded-full ${neonLine}`} />

        <div className="p-6">
          {/* Title */}
          <h3
            className={`font-bold text-sm uppercase tracking-[0.2em] mb-3 ${titleColor}`}
            style={{ fontFamily: 'var(--font-advent, inherit)' }}
          >
            {title}
          </h3>

          {/* Message */}
          <p className="text-white/60 text-sm leading-relaxed mb-6">
            {message}
          </p>

          {/* Actions */}
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white/50 border border-white/10 hover:border-white/20 hover:text-white/70 transition-all"
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${confirmBtnClass}`}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
