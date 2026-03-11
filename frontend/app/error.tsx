'use client';

import { useEffect } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { useLanguage } from '@/hooks/useLanguage';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useLanguage();

  useEffect(() => {
    console.error('UI Render Error:', error);
  }, [error]);

  return (
    <html>
      <body className="bg-black">
        <div className="min-h-screen bg-black flex items-center justify-center p-4 relative overflow-hidden">
          {/* Quantum holo background */}
          <div className="pointer-events-none absolute inset-0 opacity-40">
            <div className="absolute -inset-32 bg-[radial-gradient(circle_at_top,rgba(0,255,209,0.18),transparent_60%)]" />
            <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent,rgba(0,255,209,0.06),transparent)] mix-blend-screen" />
            <div className="absolute inset-0 [background-image:linear-gradient(rgba(0,255,209,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,209,0.06)_1px,transparent_1px)] [background-size:100%_3px,3px_100%] opacity-30" />
          </div>

          <div className="relative w-full max-w-2xl">
            {/* Cyber frame accents */}
            <div className="pointer-events-none absolute -top-3 left-8 h-6 w-24 border-t-2 border-l-2 border-cyber-red" />
            <div className="pointer-events-none absolute -bottom-3 right-8 h-6 w-24 border-b-2 border-r-2 border-cyber-red" />

            <div className="relative w-full bg-black/80 border-2 border-cyber-red p-8 shadow-[0_0_30px_rgba(255,1,60,0.3)] overflow-hidden">
              {/* Header strip */}
              <div className="mb-6 flex items-center justify-between text-xs font-mono text-cyber-red/70">
                <span className="font-hacked tracking-[0.35em] uppercase text-cyber-red">
                  {t('error_system_failure')}
                </span>
                <span className="text-cyber-red/60">ERROR CODE: UI-CRASH</span>
              </div>

              {/* Icon */}
              <div className="flex justify-center mb-6">
                <div className="relative">
                  <div className="absolute -inset-4 border border-cyber-red/30" />
                  <div className="relative flex h-16 w-16 items-center justify-center border border-cyber-red bg-black">
                    <AlertTriangle className="w-9 h-9 text-cyber-red" />
                  </div>
                </div>
              </div>

              {/* Title */}
              <h1 className="font-hacked text-cyber-red text-center text-2xl tracking-[0.45em] uppercase mb-3">
                CRITICAL ERROR
              </h1>

              <p className="text-center font-advent text-sm text-cyber-red/80 mb-6">
                系统在渲染界面时发生致命异常 · NEURAL UI RENDER FAILURE
              </p>

              {/* Error Details */}
              <div className="mb-6 border border-cyber-red/40 bg-black/60 p-4">
                <div className="flex items-start gap-3">
                  <div className="pt-1 text-cyber-red">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-xs text-cyber-red/80 break-words">
                      {error.message || '未知错误 (Unknown Error)'}
                    </p>
                    {error.digest && (
                      <p className="mt-2 font-mono text-[11px] text-cyber-red/60">
                        DIGEST: {error.digest}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={reset}
                  className="flex-1 flex items-center justify-center gap-3 bg-black border border-cyber-cyan text-cyber-cyan font-advent tracking-[0.35em] uppercase py-3 px-6 transition-colors duration-200 hover:bg-cyber-cyan hover:text-black"
                >
                  <RefreshCw className="w-4 h-4" />
                  <span>{t('error_try_recover')}</span>
                </button>

                <button
                  onClick={() => (window.location.href = '/')}
                  className="flex-1 flex items-center justify-center gap-3 bg-black border border-cyber-red text-cyber-red font-advent tracking-[0.35em] uppercase py-3 px-6 transition-colors duration-200 hover:bg-cyber-red hover:text-black"
                >
                  <Home className="w-4 h-4" />
                  <span>{t('error_return_home')}</span>
                </button>
              </div>

              {/* Footer Hint */}
              <div className="mt-6 pt-4 border-t border-cyber-red/30">
                <p className="text-[11px] font-advent text-cyber-red/60 text-center leading-relaxed">
                  如果错误持续出现，请截取此界面并发送给系统维护者
                  <br />
                  IF PERSISTENT, CONTACT SYSTEM ADMIN WITH ERROR LOGS.
                </p>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
