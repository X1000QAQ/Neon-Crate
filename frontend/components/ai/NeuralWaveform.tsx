'use client';

import { useEffect, useRef } from 'react';

const CYAN = 'var(--cyber-cyan)';

/**
 * NeuralWaveform — 神经波形背景动画
 *
 * 动画隔离：振幅与路径动画状态内聚于本组件，不上升触发 AiSidebar 重渲染。
 * SVG 路径经 ref 直驱 DOM，动画帧在 React commit 之外更新。
 */
export default function NeuralWaveform() {
  const path1Ref = useRef<SVGPathElement>(null);
  const path2Ref = useRef<SVGPathElement>(null);
  const path3Ref = useRef<SVGPathElement>(null);

  useEffect(() => {
    let w = 0;
    let animationFrameId: number;

    const animate = () => {
      w = (w + 0.1) % 100;

      // 直接操作 DOM attribute，完全绕过 React setState → re-render 管线
      if (path1Ref.current) {
        path1Ref.current.setAttribute(
          'd',
          `M 0 ${200 + Math.sin(w * 0.1) * 30} Q 96 ${
            180 + Math.sin(w * 0.15) * 40
          }, 192 ${200 + Math.sin(w * 0.2) * 30} T 384 ${
            200 + Math.sin(w * 0.25) * 30
          }`
        );
      }
      if (path2Ref.current) {
        path2Ref.current.setAttribute(
          'd',
          `M 0 ${420 + Math.sin(w * 0.12) * 25} Q 96 ${
            440 + Math.sin(w * 0.18) * 35
          }, 192 ${420 + Math.sin(w * 0.22) * 25} T 384 ${
            420 + Math.sin(w * 0.28) * 25
          }`
        );
      }
      if (path3Ref.current) {
        path3Ref.current.setAttribute(
          'd',
          `M 0 ${640 + Math.sin(w * 0.09) * 20} Q 96 ${
            620 + Math.sin(w * 0.14) * 28
          }, 192 ${640 + Math.sin(w * 0.19) * 20} T 384 ${
            640 + Math.sin(w * 0.24) * 20
          }`
        );
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  return (
    <div className="absolute inset-0 pointer-events-none" style={{ opacity: 0.18 }}>
      <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <path ref={path1Ref} stroke={CYAN} strokeWidth="1" fill="none" />
        <path ref={path2Ref} stroke={CYAN} strokeWidth="1" fill="none" opacity="0.6" />
        <path ref={path3Ref} stroke={CYAN} strokeWidth="1" fill="none" opacity="0.3" />
      </svg>
    </div>
  );
}
