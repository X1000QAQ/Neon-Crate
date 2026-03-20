'use client';

import { Download, X } from 'lucide-react';
import { useLanguage } from '@/hooks/useLanguage';
import type { PendingActionPayload } from '@/types';

const CYAN = 'var(--cyber-cyan)';
const FONT_A = '"Advent Pro", sans-serif';
const FONT_H = 'Hacked, "Advent Pro", monospace';

interface DownloadConfirmOverlayProps {
  pending: PendingActionPayload;
  onConfirm: () => void;
  /** 并发门控：confirmLoading 为 true 时调用方应忽略否认；组件内对 onDeny 二次守卫 */
  onDeny: () => void;
  confirmLoading: boolean;
}

/**
 * DownloadConfirmOverlay — 下载授权全屏确认模态框
 *
 * 组件边界：从 AiSidebar 拆出，专责下载授权模态。
 * 契约：文案经 t() 下发；确认进行中屏蔽否认回调，与上层 finally 语义互斥。
 */
export default function DownloadConfirmOverlay({
  pending,
  onConfirm,
  onDeny,
  confirmLoading,
}: DownloadConfirmOverlayProps) {
  const { t } = useLanguage();

  // 交互互斥：确认请求在途时拒绝否认，与父级确认流程的 finally 阶段对齐
  const handleDeny = () => {
    if (confirmLoading) return;
    onDeny();
  };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{
        background: 'rgba(0,0,0,0.85)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        animation: 'overlayIn 0.2s ease',
      }}
    >
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes overlayIn { from { opacity:0 } to { opacity:1 } }
        @keyframes cardUp { from { opacity:0; transform:translateY(20px) } to { opacity:1; transform:translateY(0) } }
        @keyframes scanline { 0%{top:0%} 100%{top:100%} }
      ` }} />
      <div
        className="relative mx-4 w-full max-w-2xl"
        style={{
          border: '1px solid rgba(0,230,246,0.35)',
          boxShadow: '0 0 60px rgba(0,230,246,0.15), inset 0 0 40px rgba(0,230,246,0.02)',
          background: 'rgba(2,8,16,0.97)',
          animation: 'cardUp 0.25s ease',
        }}
      >
        {/* 扫描线 */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ opacity: 0.04 }}>
          <div style={{ position: 'absolute', left: 0, right: 0, height: '2px', background: `linear-gradient(to right,transparent,${CYAN},transparent)`, animation: 'scanline 4s linear infinite' }} />
        </div>

        {/* 顶栏 */}
        <div className="flex items-center justify-between px-6 py-3" style={{ borderBottom: '1px solid rgba(0,230,246,0.12)' }}>
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: CYAN, boxShadow: `0 0 8px ${CYAN}` }} />
            {/* 标题：下载授权 → i18n */}
            <span className="text-xs tracking-[0.25em] uppercase" style={{ color: CYAN, fontFamily: FONT_A }}>
              {t('overlay_download_auth_title')}
            </span>
          </div>
          <button onClick={handleDeny} className="opacity-40 hover:opacity-100 transition-opacity" style={{ color: CYAN }}>
            <X size={16} />
          </button>
        </div>

        {/* 内容 */}
        <div className="flex" style={{ minHeight: '320px' }}>
          {/* 海报 */}
          <div className="flex-shrink-0 relative overflow-hidden" style={{ width: '200px', borderRight: '1px solid rgba(0,230,246,0.10)' }}>
            {pending.poster_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={pending.poster_url}
                alt={pending.title || t('overlay_poster_alt')}
                className="w-full h-full object-cover"
                style={{ minHeight: '300px', filter: 'brightness(0.9) contrast(1.05)' }}
              />
            ) : (
              <div
                className="w-full h-full flex items-center justify-center"
                style={{ minHeight: '300px', background: 'rgba(0,230,246,0.03)', color: 'rgba(0,230,246,0.18)', fontFamily: FONT_H, fontSize: '11px', letterSpacing: '0.1em' }}
              >
                NO POSTER
              </div>
            )}
            <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(to right,transparent 70%,rgba(2,8,16,0.85) 100%)' }} />
          </div>

          {/* 右侧信息 */}
          <div className="flex-1 flex flex-col justify-between p-6">
            <div>
              {/* 查重预警横幅 */}
              {pending.is_duplicate && (
                <div
                  className="flex items-center gap-2 px-3 py-2 mb-4 text-xs font-bold"
                  style={{ background: 'rgba(255,160,0,0.10)', border: '1px solid rgba(255,160,0,0.45)', color: 'rgba(255,185,0,0.9)', fontFamily: FONT_A, letterSpacing: '0.06em' }}
                >
                  <span style={{ fontSize: '14px' }}>⚠️</span>
                  {/* 已存在资源提示 → i18n */}
                  <span>
                    {t('overlay_duplicate_warning')}
                    {pending.existing_status ? `（${pending.existing_status}）` : ''}
                  </span>
                </div>
              )}

              {/* 类型标签 */}
              <div className="mb-3">
                <span
                  className="text-[10px] tracking-[0.2em] uppercase px-2 py-0.5"
                  style={{ border: '1px solid rgba(0,230,246,0.25)', color: 'rgba(0,230,246,0.5)', fontFamily: FONT_A }}
                >
                  {pending.media_type === 'tv' ? 'TV SERIES' : 'MOVIE'}
                </span>
              </div>

              <h2
                className="text-2xl font-bold leading-tight mb-1"
                style={{ color: CYAN, fontFamily: FONT_H, textShadow: '0 0 20px rgba(0,230,246,0.5)', letterSpacing: '0.03em' }}
              >
                {/* 片名占位 → i18n */}
                {pending.title || pending.clean_name || t('overlay_unknown_title')}
              </h2>
              {pending.year && (
                <div className="text-sm mb-4" style={{ color: 'rgba(0,230,246,0.4)', fontFamily: FONT_A }}>
                  {pending.year}
                </div>
              )}
              <div style={{ height: '1px', background: 'rgba(0,230,246,0.07)', marginBottom: '14px' }} />
              {pending.overview ? (
                <p className="text-xs leading-relaxed line-clamp-6" style={{ color: 'rgba(0,230,246,0.48)', fontFamily: FONT_A, lineHeight: '1.75' }}>
                  {pending.overview}
                </p>
              ) : (
                <p className="text-xs" style={{ color: 'rgba(0,230,246,0.18)', fontFamily: FONT_A }}>
                  {/* 简介缺省 → i18n（text_no_overview） */}
                  {t('text_no_overview')}
                </p>
              )}
            </div>

            {/* 按钮组 */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={onConfirm}
                disabled={confirmLoading}
                className="flex-1 flex items-center justify-center gap-2 py-3 text-sm font-bold tracking-wider transition-all duration-200 disabled:opacity-50"
                style={{
                  border: pending.is_duplicate ? '1px solid rgba(255,160,0,0.6)' : `1px solid ${CYAN}`,
                  background: pending.is_duplicate ? 'rgba(255,160,0,0.08)' : 'rgba(0,230,246,0.07)',
                  color: pending.is_duplicate ? 'rgba(255,185,0,0.9)' : CYAN,
                  fontFamily: FONT_A, letterSpacing: '0.12em',
                  boxShadow: pending.is_duplicate ? '0 0 20px rgba(255,160,0,0.10)' : '0 0 20px rgba(0,230,246,0.08)',
                }}
                onMouseEnter={e => {
                  if (!confirmLoading) {
                    const el = e.currentTarget as HTMLElement;
                    el.style.background = pending.is_duplicate ? 'rgba(255,160,0,0.18)' : 'rgba(0,230,246,0.16)';
                    el.style.boxShadow = pending.is_duplicate ? '0 0 30px rgba(255,160,0,0.35)' : '0 0 30px rgba(0,230,246,0.3)';
                  }
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLElement;
                  el.style.background = pending.is_duplicate ? 'rgba(255,160,0,0.08)' : 'rgba(0,230,246,0.07)';
                  el.style.boxShadow = pending.is_duplicate ? '0 0 20px rgba(255,160,0,0.10)' : '0 0 20px rgba(0,230,246,0.08)';
                }}
              >
                <Download size={14} />
                {/* 主按钮文案：进行中 / 授权 / 强制 → i18n */}
                {confirmLoading
                  ? t('overlay_btn_executing')
                  : pending.is_duplicate
                    ? t('overlay_btn_force_download')
                    : t('overlay_btn_authorize')}
              </button>
              <button
                onClick={handleDeny}
                disabled={confirmLoading}
                className="px-5 py-3 text-sm transition-all duration-200 disabled:opacity-50"
                style={{ border: '1px solid rgba(255,80,80,0.22)', background: 'rgba(255,80,80,0.04)', color: 'rgba(255,100,100,0.55)', fontFamily: FONT_A, letterSpacing: '0.08em' }}
                onMouseEnter={e => {
                  if (!confirmLoading) {
                    const el = e.currentTarget as HTMLElement;
                    el.style.background = 'rgba(255,80,80,0.12)';
                    el.style.borderColor = 'rgba(255,80,80,0.5)';
                    el.style.color = 'rgba(255,120,120,0.9)';
                  }
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLElement;
                  el.style.background = 'rgba(255,80,80,0.04)';
                  el.style.borderColor = 'rgba(255,80,80,0.22)';
                  el.style.color = 'rgba(255,100,100,0.55)';
                }}
              >
                {/* 次要操作：取消 → i18n */}
                {t('btn_cancel')}
              </button>
            </div>
          </div>
        </div>

        {/* 底栏技术信息 */}
        <div className="px-6 py-2 flex gap-4" style={{ borderTop: '1px solid rgba(0,230,246,0.07)' }}>
          {pending.tmdb_id && (
            <span className="text-[10px]" style={{ color: 'rgba(0,230,246,0.18)', fontFamily: FONT_A }}>
              TMDB #{pending.tmdb_id}
            </span>
          )}
          <span className="text-[10px]" style={{ color: 'rgba(0,230,246,0.18)', fontFamily: FONT_A }}>
            via Radarr / Sonarr
          </span>
        </div>
      </div>
    </div>
  );
}
