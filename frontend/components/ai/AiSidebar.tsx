'use client';

import { Send, Download, X } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { api } from '@/lib/api';
import type { ChatMessage, PendingActionPayload, CandidateItem } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';

// AiSidebar — Quantum Neural-Core

// ── 授权决策层：下载全屏确认模态框 ──────────────────────────────────────
function DownloadConfirmOverlay({
  pending,
  onConfirm,
  onDeny,
  confirmLoading,
}: {
  pending: PendingActionPayload;
  onConfirm: () => void;
  onDeny: () => void;
  confirmLoading: boolean;
}) {
  const CYAN = 'var(--cyber-cyan)';
  const FONT_A = '"Advent Pro", sans-serif';
  const FONT_H = 'Hacked, "Advent Pro", monospace';
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', animation: 'overlayIn 0.2s ease' }}
    >
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes overlayIn { from { opacity:0 } to { opacity:1 } }
        @keyframes cardUp { from { opacity:0; transform:translateY(20px) } to { opacity:1; transform:translateY(0) } }
        @keyframes scanline { 0%{top:0%} 100%{top:100%} }
      ` }} />
      <div className="relative mx-4 w-full max-w-2xl"
        style={{ border: '1px solid rgba(0,230,246,0.35)', boxShadow: '0 0 60px rgba(0,230,246,0.15), inset 0 0 40px rgba(0,230,246,0.02)', background: 'rgba(2,8,16,0.97)', animation: 'cardUp 0.25s ease' }}
      >
        {/* 扫描线 */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ opacity: 0.04 }}>
          <div style={{ position:'absolute', left:0, right:0, height:'2px', background:`linear-gradient(to right,transparent,${CYAN},transparent)`, animation:'scanline 4s linear infinite' }} />
        </div>
        {/* 顶栏 */}
        <div className="flex items-center justify-between px-6 py-3" style={{ borderBottom: '1px solid rgba(0,230,246,0.12)' }}>
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: CYAN, boxShadow:`0 0 8px ${CYAN}` }} />
            <span className="text-xs tracking-[0.25em] uppercase" style={{ color: CYAN, fontFamily: FONT_A }}>下载授权请求</span>
          </div>
          <button onClick={onDeny} className="opacity-40 hover:opacity-100 transition-opacity" style={{ color: CYAN }}><X size={16}/></button>
        </div>
        {/* 内容 */}
        <div className="flex" style={{ minHeight: '320px' }}>
          {/* 海报 */}
          <div className="flex-shrink-0 relative overflow-hidden" style={{ width:'200px', borderRight:'1px solid rgba(0,230,246,0.10)' }}>
            {pending.poster_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={pending.poster_url} alt={pending.title||'海报'} className="w-full h-full object-cover" style={{ minHeight:'300px', filter:'brightness(0.9) contrast(1.05)' }} />
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ minHeight:'300px', background:'rgba(0,230,246,0.03)', color:'rgba(0,230,246,0.18)', fontFamily:FONT_H, fontSize:'11px', letterSpacing:'0.1em' }}>NO POSTER</div>
            )}
            <div className="absolute inset-0 pointer-events-none" style={{ background:'linear-gradient(to right,transparent 70%,rgba(2,8,16,0.85) 100%)' }} />
          </div>
          {/* 右侧信息 */}
          <div className="flex-1 flex flex-col justify-between p-6">
            <div>
              {/* 查重预警横幅：资源已在库中时显示 */}
              {pending.is_duplicate && (
                <div className="flex items-center gap-2 px-3 py-2 mb-4 text-xs font-bold"
                  style={{ background:'rgba(255,160,0,0.10)', border:'1px solid rgba(255,160,0,0.45)', color:'rgba(255,185,0,0.9)', fontFamily:FONT_A, letterSpacing:'0.06em' }}>
                  <span style={{ fontSize:'14px' }}>⚠️</span>
                  <span>该资源已存在于您的媒体库中{pending.existing_status ? `（${pending.existing_status}）` : ''}</span>
                </div>
              )}
              {/* 类型标签 */}
              <div className="mb-3">
                <span className="text-[10px] tracking-[0.2em] uppercase px-2 py-0.5"
                  style={{ border:'1px solid rgba(0,230,246,0.25)', color:'rgba(0,230,246,0.5)', fontFamily:FONT_A }}>
                  {pending.media_type === 'tv' ? 'TV SERIES' : 'MOVIE'}
                </span>
              </div>
              <h2 className="text-2xl font-bold leading-tight mb-1"
                style={{ color:CYAN, fontFamily:FONT_H, textShadow:'0 0 20px rgba(0,230,246,0.5)', letterSpacing:'0.03em' }}>
                {pending.title || pending.clean_name || '未知片名'}
              </h2>
              {pending.year && <div className="text-sm mb-4" style={{ color:'rgba(0,230,246,0.4)', fontFamily:FONT_A }}>{pending.year}</div>}
              <div style={{ height:'1px', background:'rgba(0,230,246,0.07)', marginBottom:'14px' }} />
              {pending.overview
                ? <p className="text-xs leading-relaxed line-clamp-6" style={{ color:'rgba(0,230,246,0.48)', fontFamily:FONT_A, lineHeight:'1.75' }}>{pending.overview}</p>
                : <p className="text-xs" style={{ color:'rgba(0,230,246,0.18)', fontFamily:FONT_A }}>暂无简介</p>
              }
            </div>
            {/* 按钮组 */}
            <div className="flex gap-3 mt-6">
              <button onClick={onConfirm} disabled={confirmLoading}
                className="flex-1 flex items-center justify-center gap-2 py-3 text-sm font-bold tracking-wider transition-all duration-200 disabled:opacity-50"
                style={{
                  border: pending.is_duplicate ? '1px solid rgba(255,160,0,0.6)' : `1px solid ${CYAN}`,
                  background: pending.is_duplicate ? 'rgba(255,160,0,0.08)' : 'rgba(0,230,246,0.07)',
                  color: pending.is_duplicate ? 'rgba(255,185,0,0.9)' : CYAN,
                  fontFamily:FONT_A, letterSpacing:'0.12em',
                  boxShadow: pending.is_duplicate ? '0 0 20px rgba(255,160,0,0.10)' : '0 0 20px rgba(0,230,246,0.08)'
                }}
                onMouseEnter={e => { if(!confirmLoading){ const el=e.currentTarget as HTMLElement; el.style.background=pending.is_duplicate?'rgba(255,160,0,0.18)':'rgba(0,230,246,0.16)'; el.style.boxShadow=pending.is_duplicate?'0 0 30px rgba(255,160,0,0.35)':'0 0 30px rgba(0,230,246,0.3)'; }}}
                onMouseLeave={e => { const el=e.currentTarget as HTMLElement; el.style.background=pending.is_duplicate?'rgba(255,160,0,0.08)':'rgba(0,230,246,0.07)'; el.style.boxShadow=pending.is_duplicate?'0 0 20px rgba(255,160,0,0.10)':'0 0 20px rgba(0,230,246,0.08)'; }}
              >
                <Download size={14}/>
                {confirmLoading ? '执行中...' : (pending.is_duplicate ? '强制重新下载' : '授权下载')}
              </button>
              <button onClick={onDeny} disabled={confirmLoading}
                className="px-5 py-3 text-sm transition-all duration-200 disabled:opacity-50"
                style={{ border:'1px solid rgba(255,80,80,0.22)', background:'rgba(255,80,80,0.04)', color:'rgba(255,100,100,0.55)', fontFamily:FONT_A, letterSpacing:'0.08em' }}
                onMouseEnter={e => { if(!confirmLoading){ const el=e.currentTarget as HTMLElement; el.style.background='rgba(255,80,80,0.12)'; el.style.borderColor='rgba(255,80,80,0.5)'; el.style.color='rgba(255,120,120,0.9)'; }}}
                onMouseLeave={e => { const el=e.currentTarget as HTMLElement; el.style.background='rgba(255,80,80,0.04)'; el.style.borderColor='rgba(255,80,80,0.22)'; el.style.color='rgba(255,100,100,0.55)'; }}
              >取消</button>
            </div>
          </div>
        </div>
        {/* 底栏技术信息 */}
        <div className="px-6 py-2 flex gap-4" style={{ borderTop:'1px solid rgba(0,230,246,0.07)' }}>
          {pending.tmdb_id && <span className="text-[10px]" style={{ color:'rgba(0,230,246,0.18)', fontFamily:FONT_A }}>TMDB #{pending.tmdb_id}</span>}
          <span className="text-[10px]" style={{ color:'rgba(0,230,246,0.18)', fontFamily:FONT_A }}>via Radarr / Sonarr</span>
        </div>
      </div>
    </div>
  );
}

export default function AiSidebar() {
  const pathname = usePathname();
  const { t } = useLanguage();

  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [visibleIdx, setVisibleIdx] = useState<Set<number>>(new Set());
  const [selectedMsgIdx, setSelectedMsgIdx] = useState<Set<number>>(new Set());
  const [waveAmplitude, setWaveAmplitude] = useState(0);
  // 授权决策层：下载意图的全屏确认模态框状态
  const [downloadPending, setDownloadPending] = useState<PendingActionPayload | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // 🚀 异步链路治理：AbortController 全生命周期管理。
  // 1. 注入信号：每次发送消息时创建新的 AbortController，将其 signal 传入底层 fetch 请求。
  // 2. 物理掐断：当用户连续发送新消息时，先 abort() 上一个飞行中的请求，浏览器立即切断网络连接。
  // 3. 资源回收：后端同步捕获 asyncio.CancelledError，释放 LLM 推理资源，避免无效计算堆积。
  const abortControllerRef = useRef<AbortController | null>(null);

  // 组件卸载时中止飞行中的请求
  useEffect(() => {
    return () => { abortControllerRef.current?.abort(); };
  }, []);

  const quickCommands = [
    { label: '/scan',    hint: t('ai_quick_scan') },
    { label: '/analyze', hint: t('ai_quick_scrape') },
    { label: '/failed',  hint: t('ai_quick_failed') },
    { label: '/status',  hint: t('ai_quick_status') },
  ];

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Matrix-drop stagger
  useEffect(() => {
    const idx = messages.length - 1;
    if (idx >= 0 && !visibleIdx.has(idx)) {
      const timer = setTimeout(() => setVisibleIdx(p => new Set([...p, idx])), 60);
      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // 神经波形动画引擎
  useEffect(() => {
    let animationFrameId: number;
    const animate = () => {
      setWaveAmplitude((prev) => (prev + 0.1) % 100);
      animationFrameId = requestAnimationFrame(animate);
    };
    animate();
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  if (pathname === '/auth/login') return null;

  const handleSendText = async (text: string, displayText?: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMessage = { role: 'user', content: displayText ?? text };
    // 幽灵取消防护：发送新消息前立即清除 downloadPending，避免竞态触发 handleDownloadDeny
    setDownloadPending(null);
    // 发送任何消息时，封死当前所有候选消息（防止用户二次选择）
    setMessages(prev => {
      const deadIdxs = new Set(
        prev.map((m, i) => {
          const hasStructured = m.role === 'assistant' && m.candidates && m.candidates.length > 0;
          return hasStructured ? i : -1;
        }).filter(i => i >= 0)
      );
      if (deadIdxs.size > 0) setSelectedMsgIdx(p => new Set([...p, ...deadIdxs]));
      return [...prev, userMsg];
    });
    setInput('');
    setMenuOpen(false);
    setLoading(true);
    try {
      // 🚀 异步链路治理 — 步骤 1：中止上一次飞行中的请求，注入新 AbortController
      // 确保同一时刻只有最新一条请求的 signal 处于激活状态
      abortControllerRef.current?.abort();
      abortControllerRef.current = new AbortController();
      const res = await api.chat(text, abortControllerRef.current.signal);
      // 执行权由后端 BackgroundTasks 统一管理，前端仅负责渲染回复文本
      setMessages(p => [...p, { 
        role: 'assistant', 
        content: res.response,
        candidates: res.candidates && res.candidates.length > 0 ? res.candidates : undefined,
        engine_tag: res.engine_tag,  // V2.0 血缘溯源标签
      }]);
      // 授权决策层：DOWNLOAD 意图携带 pending_action 时弹出全屏确认界面
      if (res.action === 'DOWNLOAD' && res.pending_action) {
        setDownloadPending(res.pending_action);
      }
    } catch (e) {
      // 🚀 异步链路治理 — 步骤 2：物理掐断后的前端静默处理
      // AbortError 说明这是主动中止（用户连续发送新消息 或 组件卸载），
      // 属于正常的用户行为而非异常，不应向对话框追加错误气泡，直接 return 静默退出。
      if (e instanceof Error && e.name === 'AbortError') return;
      const msg = e instanceof Error ? e.message : 'NEURAL LINK ERROR';
      setMessages(p => [...p, { role: 'assistant', content: msg }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const sent = input;
    setInput('');
    await handleSendText(sent);
  };

  // 授权决策层：用户点击「授权下载」后调用 /confirm 端点执行真正下载
  const handleDownloadConfirm = async () => {
    if (!downloadPending || confirmLoading) return;
    setConfirmLoading(true);
    try {
      const payload = JSON.stringify(downloadPending);
      const res = await api.confirmAction(payload);
      setDownloadPending(null);
      setMessages(p => [...p, { role: 'assistant', content: res.response }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '授权执行失败';
      setDownloadPending(null);
      setMessages(p => [...p, { role: 'assistant', content: `⚠️ ${msg}` }]);
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleDownloadDeny = () => {
    setDownloadPending(null);
    setMessages(p => [...p, { role: 'assistant', content: '已取消下载。' }]);
  };

  const CYAN = 'var(--cyber-cyan)';
  const CYAN_DIM = 'rgba(0,230,246,0.22)';
  const CYAN_MID = 'rgba(0,230,246,0.55)';
  const FONT_H = 'Hacked, "Advent Pro", monospace';
  const FONT_A = '"Advent Pro", sans-serif';

  return (
    <>
      {/* 授权决策层：下载全屏确认模态框 */}
      {downloadPending && (
        <DownloadConfirmOverlay
          pending={downloadPending}
          onConfirm={handleDownloadConfirm}
          onDeny={handleDownloadDeny}
          confirmLoading={confirmLoading}
        />
      )}
      {/* === QUANTUM AXIS: wide hit-area + hover glow === */}
      {/* Outer hit zone — wide transparent strip, easy to click */}
      <div
        onClick={() => setIsOpen(o => !o)}
        className="fixed z-[110] top-[5vh] h-[90vh] cursor-pointer transition-all duration-500 group"
        style={{
          right: isOpen ? '384px' : '0',
          width: '32px',          /* 扩大至 32px，更易命中 */
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'transparent',
        }}
      >
        {/* Visual line — stays thin but glows wider on hover */}
        <div
          className="h-full transition-all duration-300 relative group-hover:w-[6px] group-hover:animate-pulse"
          style={{
            width: '3px',
            background: CYAN,
            opacity: 0.6,
            boxShadow: '0 0 12px rgba(0,230,246,0.5), 0 0 25px rgba(0,230,246,0.3)',
          }}
        >
          {/* Hover state: WHITE CORE + MASSIVE GLOW + DROP SHADOW */}
          <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
            style={{
              background: 'linear-gradient(to right, #00f3ff, #fff, #00f3ff)',
              boxShadow: `
                0 0 10px #00f3ff,
                0 0 30px #00f3ff,
                0 0 60px rgba(0,243,255,0.8),
                0 0 100px rgba(0,243,255,0.4),
                0 0 150px rgba(0,243,255,0.2)
              `,
              filter: 'drop-shadow(0 0 15px #00f3ff) drop-shadow(0 0 30px rgba(0,243,255,0.6))',
            }}
          />
          
          {/* Top energy node — WHITE CORE on hover */}
          <div 
            className="absolute top-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full opacity-60 group-hover:opacity-100 group-hover:w-4 group-hover:h-4 transition-all duration-300"
            style={{ 
              background: CYAN,
              boxShadow: `0 0 12px ${CYAN}, 0 0 25px rgba(0,243,255,0.5)`,
            }}
          >
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 rounded-full transition-opacity duration-300"
              style={{
                background: '#fff',
                boxShadow: `
                  0 0 10px #00f3ff,
                  0 0 25px #00f3ff,
                  0 0 50px rgba(0,243,255,0.7)
                `,
              }}
            />
          </div>
          
          {/* Bottom energy node — WHITE CORE on hover */}
          <div 
            className="absolute bottom-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full opacity-60 group-hover:opacity-100 group-hover:w-4 group-hover:h-4 transition-all duration-300"
            style={{ 
              background: CYAN,
              boxShadow: `0 0 12px ${CYAN}, 0 0 25px rgba(0,243,255,0.5)`,
            }}
          >
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 rounded-full transition-opacity duration-300"
              style={{
                background: '#fff',
                boxShadow: `
                  0 0 10px #00f3ff,
                  0 0 25px #00f3ff,
                  0 0 50px rgba(0,243,255,0.7)
                `,
              }}
            />
          </div>
        </div>
        
        {/* Vertical label — EXTREME GLOW on hover */}
        <div className="absolute top-1/2 left-1/2 select-none pointer-events-none opacity-50 group-hover:opacity-100 transition-all duration-300"
          style={{
            writingMode: 'vertical-rl', fontSize: '8px', letterSpacing: '4px',
            color: CYAN, fontFamily: FONT_A, textTransform: 'uppercase',
            transform: 'translateX(-50%) translateY(-50%) rotate(180deg)', whiteSpace: 'nowrap',
            textShadow: '0 0 8px rgba(0,243,255,0.6)',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.textShadow = '0 0 15px #00f3ff, 0 0 30px #00f3ff, 0 0 50px rgba(0,243,255,0.5)';
            (e.currentTarget as HTMLElement).style.color = '#fff';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.textShadow = '0 0 8px rgba(0,243,255,0.6)';
            (e.currentTarget as HTMLElement).style.color = CYAN;
          }}
        >NEURAL</div>
      </div>

      {/* === NEURAL CORE PANEL === */}
      <div
        className="fixed top-[5vh] z-[100] h-[90vh] transition-all duration-500" /* z-sidebar */
        style={{ right: isOpen ? '4px' : '-384px', width: '380px' }}
      >
        <div
          className="flex flex-col w-full h-full relative overflow-hidden"
          style={{
            background: 'rgba(0,0,0,0.20)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            borderLeft: `1px solid ${CYAN_DIM}`,
          }}
        >
          {/* Neural Waveform Background */}
          <div className="absolute inset-0 pointer-events-none" style={{ opacity: 0.18 }}>
            <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
              {/* 恢复 SVG 的动态路径 */}
              {(() => {
                const w = waveAmplitude;
                const wp1 = `M 0 ${200 + Math.sin(w * 0.1) * 30} Q 96 ${
                  180 + Math.sin(w * 0.15) * 40
                }, 192 ${200 + Math.sin(w * 0.2) * 30} T 384 ${
                  200 + Math.sin(w * 0.25) * 30
                }`;
                const wp2 = `M 0 ${420 + Math.sin(w * 0.12) * 25} Q 96 ${
                  440 + Math.sin(w * 0.18) * 35
                }, 192 ${420 + Math.sin(w * 0.22) * 25} T 384 ${
                  420 + Math.sin(w * 0.28) * 25
                }`;
                const wp3 = `M 0 ${640 + Math.sin(w * 0.09) * 20} Q 96 ${
                  620 + Math.sin(w * 0.14) * 28
                }, 192 ${640 + Math.sin(w * 0.19) * 20} T 384 ${
                  640 + Math.sin(w * 0.24) * 20
                }`;
                return (
                  <>
                    <path d={wp1} stroke={CYAN} strokeWidth="1" fill="none" />
                    <path
                      d={wp2}
                      stroke={CYAN}
                      strokeWidth="1"
                      fill="none"
                      opacity="0.6"
                    />
                    <path
                      d={wp3}
                      stroke={CYAN}
                      strokeWidth="1"
                      fill="none"
                      opacity="0.3"
                    />
                  </>
                );
              })()}
            </svg>
          </div>
          {/* Depth glow */}
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: 'radial-gradient(ellipse at 50% 35%, rgba(0,230,246,0.05) 0%, transparent 70%)' }} />

          {/* Header */}
          <div className="flex-shrink-0 p-6 relative z-10" style={{ borderBottom: `1px solid ${CYAN_DIM}` }}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl uppercase tracking-widest font-bold"
                style={{ fontFamily: FONT_A, color: CYAN, textShadow: '0 0 20px rgba(0,230,246,0.8)' }}>
                NEURAL CORE
              </h2>
              <div className="flex gap-2 items-center">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-2 h-2 rounded-full animate-pulse"
                    style={{ background: CYAN, boxShadow: `0 0 10px ${CYAN}`, animationDelay: `${i * 0.35}s` }} />
                ))}
              </div>
            </div>
            <div className="text-xs tracking-wider" style={{ color: CYAN_MID, fontFamily: FONT_A }}>
              quantum_state: stable | neural_link: active
            </div>
          </div>

          {/* Chat flow */}
          <div className="flex-1 overflow-y-auto p-6 space-y-5 relative z-10" style={{ scrollbarWidth: 'none' }}>
            {messages.length === 0 && (
              <div className="mt-16 text-center text-xs tracking-widest uppercase"
                style={{ color: 'rgba(0,230,246,0.3)', fontFamily: FONT_A }}>
                <div className="mb-4 text-4xl" style={{ textShadow: '0 0 30px rgba(0,230,246,0.5)' }}>&#x25C8;</div>
                {t('ai_hello')}
              </div>
            )}
            {(() => {
              // 找到最后一条含候选列表的消息 idx，只有它的按钮是激活的
              let lastCandidateIdx = -1;
              messages.forEach((m, i) => {
                if (m.role === 'assistant' && (
                  (m.candidates && m.candidates.length > 0)
                )) {
                  lastCandidateIdx = i;
                }
              });
            return messages.map((msg, idx) => {
                const visible = visibleIdx.has(idx);
                // 结构化候选数据
                const structuredCandidates: CandidateItem[] = msg.candidates || [];
                const isActiveCandidates = structuredCandidates.length > 0 && idx === lastCandidateIdx && !selectedMsgIdx.has(idx);
                return (
                  <div key={idx} style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    opacity: visible ? 1 : 0,
                    transform: visible ? 'translateY(0)' : 'translateY(8px)',
                    transition: 'opacity 0.35s ease, transform 0.35s ease',
                  }}>
                    {msg.role === 'assistant' && (
                      <div className="max-w-[85%] relative group">
                        <div className="text-sm leading-relaxed whitespace-pre-wrap break-all"
                          style={{ color: CYAN, fontFamily: FONT_H, textShadow: '0 0 15px rgba(0,230,246,0.6)' }}>
                          {msg.content}
                        </div>
                        {/* V2.0 血缘溯源：引擎标识角标 */}
                        {msg.engine_tag && (
                          <div
                            className="mt-1 flex items-center gap-1 opacity-30 hover:opacity-100 transition-opacity duration-300 cursor-default select-none"
                            title={
                              msg.engine_tag === 'local'         ? 'Edge Node (本地模型)' :
                              msg.engine_tag === 'cloud'         ? 'Cloud API (云端模型)' :
                              'Fallback: 本地 → 云端补位'
                            }
                          >
                            <span className="text-[10px] tracking-wider" style={{ fontFamily: FONT_A, color: CYAN }}>
                              {msg.engine_tag === 'local'         && '🧠'}
                              {msg.engine_tag === 'cloud'         && '☁️'}
                              {msg.engine_tag === 'local->cloud'  && '🧠 → ☁️'}
                            </span>
                          </div>
                        )}
                        {/* 结构化候选按钮（优先） */}
                        {structuredCandidates.length > 0 && (
                          <div className="mt-3 flex flex-col gap-1.5">
                            {structuredCandidates.map((item, oi) => {
                              const isUsed = !isActiveCandidates;
                              const label = item.year ? `${item.title} (${item.year})` : item.title;
                              return (
                                <button
                                  key={oi}
                                  disabled={isUsed}
                                  onClick={() => {
                                    if (isUsed) return;
                                    setSelectedMsgIdx(p => new Set([...p, idx]));
                                    setTimeout(() => handleSendText(label, label), 50);
                                  }}
                                  className="text-left px-3 py-1.5 text-xs transition-all duration-200 relative flex items-center gap-2"
                                  style={{
                                    border: `1px solid ${isUsed ? 'rgba(0,230,246,0.10)' : 'rgba(0,230,246,0.30)'}`,
                                    background: isUsed ? 'rgba(0,0,0,0.1)' : 'rgba(0,230,246,0.05)',
                                    color: isUsed ? 'rgba(0,230,246,0.25)' : CYAN,
                                    fontFamily: FONT_A,
                                    letterSpacing: '0.04em',
                                    cursor: isUsed ? 'not-allowed' : 'pointer',
                                  }}
                                  onMouseEnter={e => {
                                    if (isUsed) return;
                                    const el = e.currentTarget as HTMLElement;
                                    el.style.background = 'rgba(0,230,246,0.15)';
                                    el.style.borderColor = 'rgba(0,230,246,0.7)';
                                    el.style.boxShadow = '0 0 12px rgba(0,230,246,0.3)';
                                  }}
                                  onMouseLeave={e => {
                                    if (isUsed) return;
                                    const el = e.currentTarget as HTMLElement;
                                    el.style.background = 'rgba(0,230,246,0.05)';
                                    el.style.borderColor = 'rgba(0,230,246,0.30)';
                                    el.style.boxShadow = 'none';
                                  }}
                                >
                                  <span style={{ opacity: isUsed ? 0.2 : 0.45, marginRight: '4px' }}>{oi + 1}.</span>
                                  <span>{item.media_type === 'tv' ? '📺' : '🎬'}</span>
                                  <span>{item.title}</span>
                                  {item.year && <span style={{ opacity: 0.5 }}>({item.year}){item.media_type === 'tv' ? ' [剧集]' : ''}</span>}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                    {msg.role === 'user' && (
                      <div className="max-w-[85%]">
                        <div className="text-sm leading-relaxed"
                          style={{ color: 'rgba(255,255,255,0.72)', fontFamily: FONT_H }}>
                          {msg.content}
                        </div>
                      </div>
                    )}
                  </div>
                );
              });
            })()}
            {loading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div className="flex gap-2 items-center pl-1">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="w-1.5 h-1.5 rounded-full animate-pulse"
                      style={{ background: CYAN, boxShadow: `0 0 8px ${CYAN}`, animationDelay: `${i * 0.2}s` }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick command tiles */}
          {messages.length === 0 && (
            <div className="px-6 pb-3 flex-shrink-0 relative z-10">
              <div className="grid grid-cols-2 gap-2">
                {quickCommands.map((cmd, idx) => (
                  <button key={idx}
                    onClick={() => { setInput(cmd.hint); setMenuOpen(false); }}
                    className="text-left px-3 py-2 text-xs transition-all duration-200"
                    style={{ border: '1px solid rgba(0,230,246,0.20)', background: 'rgba(0,0,0,0.25)', color: 'rgba(0,230,246,0.65)', fontFamily: FONT_A, letterSpacing: '0.05em' }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,230,246,0.08)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,230,246,0.45)'; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.25)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,230,246,0.20)'; }}
                  >
                    <span style={{ color: CYAN, opacity: 0.9 }}>{cmd.label}</span><br />
                    <span style={{ opacity: 0.5, fontSize: '10px' }}>{cmd.hint}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Quantum input console */}
          <div className="flex-shrink-0 p-5 relative z-10" style={{ borderTop: `1px solid ${CYAN_DIM}` }}>
            {menuOpen && (
              <div className="absolute left-5 right-5 bottom-full mb-2"
                style={{ background: 'rgba(0,0,0,0.88)', border: `1px solid ${CYAN_DIM}`, boxShadow: '0 0 30px rgba(0,230,246,0.2)', backdropFilter: 'blur(20px)' }}>
                {quickCommands.map((cmd, idx) => (
                  <button key={idx}
                    onMouseDown={() => { setInput(cmd.hint); setMenuOpen(false); }}
                    className="block w-full text-left px-4 py-2 text-xs transition-colors"
                    style={{ color: CYAN, fontFamily: FONT_H }}
                    onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'rgba(0,230,246,0.10)'}
                    onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
                  >
                    {cmd.label} — {cmd.hint}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              {/* Input: only bottom cyan line, transparent body */}
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onFocus={() => setMenuOpen(true)}
                onBlur={() => setTimeout(() => setMenuOpen(false), 150)}
                onKeyDown={e => e.key === 'Enter' && handleSend()}
                placeholder={t('ai_enter_command')}
                disabled={loading}
                className="flex-1 bg-transparent text-sm focus:outline-none placeholder:opacity-30"
                style={{
                  borderBottom: `1px solid ${CYAN_DIM}`,
                  color: CYAN,
                  fontFamily: FONT_H,
                  textShadow: '0 0 10px rgba(0,230,246,0.5)',
                  padding: '8px 4px',
                  caretColor: CYAN,
                }}
              />
              {/* Blinking cyan block cursor indicator */}
              <div className="w-2 h-5 flex-shrink-0 animate-pulse" style={{ background: CYAN, boxShadow: `0 0 8px ${CYAN}` }} />
              {/* Send button */}
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="flex-shrink-0 p-2 transition-all duration-200 disabled:opacity-30"
                style={{ color: CYAN }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.textShadow = `0 0 15px ${CYAN}`}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.textShadow = 'none'}
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>

    </>
  );
}
