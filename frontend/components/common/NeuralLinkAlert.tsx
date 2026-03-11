'use client';

import { useNetwork } from '@/context/NetworkContext';

export default function NeuralLinkAlert() {
  const { isLinkDown, setLinkDown } = useNetwork();

  if (!isLinkDown) return null;

  function handleReconnect() {
    setLinkDown(false);
    window.location.reload();
  }

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.75)' }}
    >
      <div
        className="animate-pulse border-2 border-red-500 rounded-lg p-8 max-w-md w-full mx-4 text-center"
        style={{
          backgroundColor: 'rgba(10, 0, 0, 0.92)',
          boxShadow: '0 0 32px 8px rgba(239,68,68,0.6), 0 0 64px 16px rgba(239,68,68,0.25)',
        }}
      >
        <div className="text-red-500 text-4xl mb-4 font-mono font-bold tracking-widest">
          ⚠ NEURAL LINK SEVERED
        </div>
        <div className="text-red-300 text-sm mb-8 font-mono tracking-wide">
          警告：神经链路连接中断
        </div>
        <button
          onClick={handleReconnect}
          className="px-6 py-2 border border-red-500 text-red-400 font-mono text-sm tracking-widest uppercase hover:bg-red-500 hover:text-black transition-colors duration-200"
          style={{
            boxShadow: '0 0 12px 2px rgba(239,68,68,0.4)',
          }}
        >
          尝试重连 RECONNECT
        </button>
      </div>
    </div>
  );
}
