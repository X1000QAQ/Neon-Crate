'use client';

import { Send } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { api } from '@/lib/api';
import type { ChatMessage } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';

// 解析候选列表消息，返回 { text, candidates }
function parseCandidates(content: string): { text: string; candidates: string[] } {
  const marker = '__CANDIDATES__';
  const idx = content.indexOf(marker);
  if (idx === -1) return { text: content, candidates: [] };
  const text = content.slice(0, idx).trimEnd();
  try {
    const candidates = JSON.parse(content.slice(idx + marker.length));
    return { text, candidates: Array.isArray(candidates) ? candidates : [] };
  } catch {
    return { text, candidates: [] };
  }
}

// AiSidebar — Quantum Neural-Core

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
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  // 恢复：神经波形动画引擎
  useEffect(() => {
    let animationFrameId: number;
    const animate = () => {
      // 放慢量子神经波形速度
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
    // 发送任何消息时，封死当前所有候选消息（防止用户二次选择）
    setMessages(prev => {
      const deadIdxs = new Set(
        prev.map((m, i) => (m.role === 'assistant' && parseCandidates(m.content).candidates.length > 0 ? i : -1))
            .filter(i => i >= 0)
      );
      if (deadIdxs.size > 0) setSelectedMsgIdx(p => new Set([...p, ...deadIdxs]));
      return [...prev, userMsg];
    });
    setInput('');
    setMenuOpen(false);
    setLoading(true);
    try {
      const res = await api.chat(text);
      setMessages(p => [...p, { role: 'assistant', content: res.response }]);
      if (res.action === 'ACTION_SCAN') {
        api.triggerScan().catch((e) => setMessages(p => [...p, { role: 'assistant', content: `扫描触发失败: ${e instanceof Error ? e.message : '未知错误'}` }]));
        setMessages(p => [...p, { role: 'assistant', content: t('ai_scan_triggered') }]);
      }
      if (res.action === 'ACTION_SCRAPE') {
        api.triggerScrapeAll().catch((e) => setMessages(p => [...p, { role: 'assistant', content: `刮削触发失败: ${e instanceof Error ? e.message : '未知错误'}` }]));
        setMessages(p => [...p, { role: 'assistant', content: t('ai_scrape_triggered') }]);
      }
      if (res.action === 'ACTION_SUBTITLE') {
        api.triggerFindSubtitles().catch((e) => setMessages(p => [...p, { role: 'assistant', content: `字幕任务触发失败: ${e instanceof Error ? e.message : '未知错误'}` }]));
        setMessages(p => [...p, { role: 'assistant', content: t('ai_subtitle_triggered') }]);
      }
    } catch (e) {
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

  const CYAN = 'var(--cyber-cyan)';
  const CYAN_DIM = 'rgba(0,230,246,0.22)';
  const CYAN_MID = 'rgba(0,230,246,0.55)';
  const FONT_H = 'Hacked, "Advent Pro", monospace';
  const FONT_A = '"Advent Pro", sans-serif';

  return (
    <>
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
                if (m.role === 'assistant' && parseCandidates(m.content).candidates.length > 0) {
                  lastCandidateIdx = i;
                }
              });
              return messages.map((msg, idx) => {
                const visible = visibleIdx.has(idx);
                const parsed = msg.role === 'assistant' ? parseCandidates(msg.content) : { text: msg.content, candidates: [] };
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
                        <div className="text-sm leading-relaxed whitespace-pre-wrap"
                          style={{ color: CYAN, fontFamily: FONT_H, textShadow: '0 0 15px rgba(0,230,246,0.6)' }}>
                          {parsed.text}
                        </div>
                        {/* 候选快捷按钮 */}
                        {parsed.candidates.length > 0 && (
                          <div className="mt-3 flex flex-col gap-1.5">
                            {parsed.candidates.map((opt, oi) => {
                              // 只有最后一条候选消息且未被选中时激活，其余全部变灰
                              const isUsed = selectedMsgIdx.has(idx) || idx !== lastCandidateIdx;
                              return (
                                <button
                                  key={oi}
                                  disabled={isUsed}
                                  onClick={() => {
                                    if (isUsed) return;
                                    setSelectedMsgIdx(p => new Set([...p, idx]));
                                    setTimeout(() => handleSendText(opt, opt), 50);
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
                                    const dot = el.querySelector('.candidate-dot') as HTMLElement;
                                    if (dot) { dot.style.opacity = '1'; dot.style.boxShadow = `0 0 8px ${CYAN}`; }
                                  }}
                                  onMouseLeave={e => {
                                    if (isUsed) return;
                                    const el = e.currentTarget as HTMLElement;
                                    el.style.background = 'rgba(0,230,246,0.05)';
                                    el.style.borderColor = 'rgba(0,230,246,0.30)';
                                    el.style.boxShadow = 'none';
                                    const dot = el.querySelector('.candidate-dot') as HTMLElement;
                                    if (dot) { dot.style.opacity = '0'; dot.style.boxShadow = 'none'; }
                                  }}
                                >
                                  <span
                                    className="candidate-dot"
                                    style={{
                                      position: 'absolute',
                                      left: '-14px',
                                      top: '50%',
                                      transform: 'translateY(-50%)',
                                      width: '6px',
                                      height: '6px',
                                      borderRadius: '50%',
                                      background: CYAN,
                                      opacity: 0,
                                      transition: 'opacity 0.2s, box-shadow 0.2s',
                                      flexShrink: 0,
                                    }}
                                  />
                                  <span style={{ opacity: isUsed ? 0.2 : 0.45, marginRight: '4px' }}>{oi + 1}.</span>
                                  {opt}
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
