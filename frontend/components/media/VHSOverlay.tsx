/**
 * VHSOverlay - 忽略任务的 VHS 故障视觉层
 *
 * 用于给被忽略或异常的媒体卡片叠加“录像带损坏”风格的视觉反馈，
 * 包括噪声层、扫描线、追踪条、RGB 偏移和 TAPE ERROR 标签。
 *
 * 新手提示：
 * - 这是纯视觉组件，不接收业务 Props，也不修改任务状态。
 * - `pointer-events-none` 确保遮罩不会挡住上层按钮或行点击事件。
 * - 具体动画样式依赖全局 CSS 中的 `vhs-*` 类。
 */
'use client';

import { AlertOctagon } from 'lucide-react';

export function VHSOverlay() {
  return (
    <div className="absolute inset-0 pointer-events-none vhs-ignored">
      <div className="absolute inset-0 z-10 opacity-30 vhs-noise" />
      <div className="absolute inset-0 z-20 opacity-40 vhs-scanlines" />
      <div className="absolute left-0 right-0 h-6 z-20 opacity-60 vhs-tracking-bar" style={{ top: '30%' }} />
      <div
        className="absolute left-0 right-0 h-5 z-20 opacity-40"
        style={{
          top: '60%',
          background:
            'linear-gradient(90deg, transparent 0%, rgba(0,0,0,0.3) 30%, rgba(0,0,0,0.5) 50%, rgba(0,0,0,0.3) 70%, transparent 100%)',
        }}
      />
      <div className="absolute inset-0 z-25 mix-blend-screen opacity-20 vhs-rgb-red" />
      <div className="absolute inset-0 z-25 mix-blend-screen opacity-20 vhs-rgb-blue" />
      <div className="absolute top-0.5 left-0.5 right-0.5 z-30">
        <div className="px-1 py-[1px] bg-black/70 backdrop-blur-sm text-orange-400 text-[7px] font-mono leading-none">
          ▶ REC 00:00:00:00 [CORRUPTED]
        </div>
      </div>
      <div className="absolute inset-0 flex items-center justify-center z-30">
        <div
          className="px-1.5 py-1 bg-orange-600/80 border border-orange-400 text-white font-mono text-[8px] backdrop-blur-sm"
          style={{
            textShadow: '0 0 8px rgba(251, 146, 60, 0.8)',
            boxShadow: '0 0 12px rgba(251, 146, 60, 0.55)',
            transform: 'rotate(-8deg)',
          }}
        >
          <div className="flex flex-col items-center gap-0.5">
            <AlertOctagon size={10} />
            <span className="leading-none">TAPE ERROR</span>
            <span className="text-[7px] opacity-70 leading-none">00:00:00:00</span>
          </div>
        </div>
      </div>
    </div>
  );
}
