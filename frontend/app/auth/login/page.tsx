'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff, Cpu, Wifi, Database, Shield } from 'lucide-react';
import { api } from '@/lib/api';
import { useLanguage } from '@/hooks/useLanguage';

const CHECKS = [
  { label: 'CPU', status: 'NOMINAL', icon: Cpu },
  { label: 'NETWORK', status: 'SECURE', icon: Wifi },
  { label: 'DATABASE', status: 'ONLINE', icon: Database },
  { label: 'AUTH', status: 'READY', icon: Shield },
];

export default function LoginPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [isInit, setIsInit] = useState<boolean | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootPct, setBootPct] = useState(0);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [uFocus, setUFocus] = useState(false);
  const [pFocus, setPFocus] = useState(false);
  const [cFocus, setCFocus] = useState(false);
  const [glitch, setGlitch] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.authStatus().then(s => setIsInit(s.initialized)).catch(() => setIsInit(true));
  }, []);

  useEffect(() => {
    const t = setInterval(() => setBootPct(p => { if (p >= 100) { clearInterval(t); return 100; } return p + 5; }), 120);
    const d = setTimeout(() => setBooting(false), 2600);
    return () => { clearInterval(t); clearTimeout(d); };
  }, []);

  useEffect(() => {
    if (booting) return;
    const id = setInterval(() => { setGlitch(true); setTimeout(() => setGlitch(false), 150); }, 4500);
    return () => clearInterval(id);
  }, [booting]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setLoading(true);
    try {
      if (isInit) {
        const r = await api.login(username, password);
        localStorage.setItem('token', r.access_token);
        localStorage.setItem('username', r.username);
        router.push('/');
      } else {
        if (password !== confirmPw) { setError('PASSWORD_MISMATCH'); setLoading(false); return; }
        if (password.length < 6) { setError('KEY_TOO_SHORT: min 6 chars'); setLoading(false); return; }
        await api.initAuth(username, password);
        const r = await api.login(username, password);
        localStorage.setItem('token', r.access_token);
        localStorage.setItem('username', r.username);
        router.push('/');
      }
    } catch (err: any) { setError(err.message || 'ACCESS_DENIED'); }
    finally { setLoading(false); }
  };


  return (
    <div
      className="min-h-screen relative flex items-center justify-center overflow-hidden"
    >
      {/* 物理壁纸底层 (-z-20) */}
      <div 
        className="fixed inset-0 bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: 'url(/bg-login.jpg)', zIndex: -20 }}
      />
      {/* 量子全息暗场蒙版 (-z-10) */}
      <div 
        className="fixed inset-0 pointer-events-none"
        style={{ 
          background: 'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 0.9) 70%, rgba(0, 0, 0, 0.98) 100%)',
          backdropFilter: 'blur(3px)',
          zIndex: -10
        }}
      />
      {/* Holographic rings */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ opacity: 0.22 }}>
        <div className="absolute rounded-full border-dashed" style={{ width: 860, height: 860, borderWidth: 2, borderColor: 'var(--cyber-cyan)', animation: 'spin 28s linear infinite', boxShadow: '0 0 50px rgba(0,230,246,0.2)' }} />
        <div className="absolute rounded-full" style={{ width: 620, height: 620, borderWidth: 1, borderStyle: 'solid', borderColor: 'rgba(0,230,246,0.6)', animation: 'spin 18s linear infinite reverse' }} />
        <div className="absolute rounded-full border-dashed" style={{ width: 400, height: 400, borderWidth: 1, borderColor: 'rgba(0,230,246,0.4)', animation: 'spin 10s linear infinite' }} />
      </div>
      <div className="absolute top-6 left-6 w-10 h-10 border-t-2 border-l-2 pointer-events-none" style={{ borderColor: 'rgba(0,230,246,0.4)' }} />
      <div className="absolute top-6 right-6 w-10 h-10 border-t-2 border-r-2 pointer-events-none" style={{ borderColor: 'rgba(0,230,246,0.4)' }} />
      <div className="absolute bottom-6 left-6 w-10 h-10 border-b-2 border-l-2 pointer-events-none" style={{ borderColor: 'rgba(0,230,246,0.4)' }} />
      <div className="absolute bottom-6 right-6 w-10 h-10 border-b-2 border-r-2 pointer-events-none" style={{ borderColor: 'rgba(0,230,246,0.4)' }} />
      <div className="relative z-10 w-full max-w-md mx-4" style={{ background: 'transparent', border: '1px solid rgba(0,230,246,0.28)', backdropFilter: 'blur(24px)', boxShadow: '0 0 80px rgba(0,230,246,0.12), inset 0 0 80px rgba(0,230,246,0.03)' }}>
        <div className="absolute top-0 left-0 right-0 h-px" style={{ background: 'linear-gradient(90deg,transparent,var(--cyber-cyan),transparent)', boxShadow: '0 0 20px var(--cyber-cyan)' }} />
        <div className="absolute bottom-0 left-0 right-0 h-px" style={{ background: 'linear-gradient(90deg,transparent,rgba(0,230,246,0.4),transparent)' }} />
        <div className="p-10">
          <div className="mb-8 pb-6" style={{ borderBottom: '1px solid rgba(0,230,246,0.18)' }}>
            <div className="flex items-center gap-3 mb-2">
              <Shield className="w-8 h-8 flex-shrink-0" style={{ color: 'var(--cyber-cyan)', filter: 'drop-shadow(0 0 8px var(--cyber-cyan))' }} />
              <h1 className="text-3xl font-black uppercase tracking-widest" style={{ color: 'var(--cyber-cyan)', textShadow: '0 0 20px rgba(0,230,246,0.9), 0 0 60px rgba(0,230,246,0.35)' }}>SYSTEM ACCESS</h1>
            </div>
            <p className="text-xs tracking-[0.28em] uppercase pl-11" style={{ color: 'rgba(0,230,246,0.42)' }}>
              {isInit === false ? 'ROOT NODE BOOTSTRAP PROTOCOL' : 'HOLOGRAPHIC TERMINAL INTERFACE v2.1'}
            </p>
          </div>
          {booting ? (
            <div className="space-y-5">
              <p className="text-lg uppercase tracking-widest animate-pulse" style={{ color: 'var(--cyber-cyan)', textShadow: '0 0 15px rgba(0,230,246,0.8)' }}>SYSTEM CHECK...</p>
              <div className="space-y-2">
                {CHECKS.map((c, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2" style={{ borderLeft: '2px solid rgba(0,230,246,0.38)', background: 'rgba(0,230,246,0.04)', opacity: bootPct > i * 25 ? 1 : 0.18, transition: 'opacity 0.5s ease', boxShadow: bootPct > i * 25 ? '0 0 20px rgba(0,230,246,0.12)' : 'none' }}>
                    <div className="flex items-center gap-2">
                      <c.icon className="w-4 h-4" style={{ color: 'var(--cyber-cyan)' }} />
                      <span className="text-sm tracking-widest" style={{ color: 'var(--cyber-cyan)' }}>{c.label}</span>
                    </div>
                    <span className="text-xs" style={{ color: bootPct > i * 25 ? '#10B981' : 'rgba(0,230,246,0.3)', textShadow: bootPct > i * 25 ? '0 0 10px rgba(16,185,129,0.7)' : 'none', transition: 'all 0.4s' }}>{bootPct > i * 25 ? c.status : '...'}</span>
                  </div>
                ))}
              </div>
              <div className="w-full relative overflow-hidden" style={{ background: 'rgba(0,230,246,0.08)', height: 4 }}>
                <div className="absolute top-0 left-0 h-full transition-all duration-300" style={{ width: bootPct + '%', background: 'var(--cyber-cyan)', boxShadow: '0 0 18px var(--cyber-cyan)' }} />
                <div className="absolute inset-0" style={{ background: 'linear-gradient(90deg,transparent,rgba(0,230,246,0.5),transparent)', animation: 'login-scan 2s linear infinite' }} />
              </div>
              <p className="text-right text-xs tracking-widest" style={{ color: 'rgba(0,230,246,0.42)' }}>{bootPct}%</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-7">
              <div className="relative">
                <label className="block text-xs uppercase tracking-[0.28em] mb-3" style={{ color: uFocus ? 'var(--cyber-cyan)' : 'rgba(0,230,246,0.48)', transition: 'color 0.3s' }}>NEURAL_ID</label>
                <div className="relative">
                  <input type="text" value={username} onChange={e => setUsername(e.target.value)} onFocus={() => setUFocus(true)} onBlur={() => setUFocus(false)} placeholder="Enter Neural ID" autoComplete="username" required minLength={3} className="w-full bg-transparent px-0 py-3 text-lg focus:outline-none" style={{ color: 'var(--cyber-cyan)', borderBottom: '1px solid rgba(0,230,246,0.28)', textShadow: uFocus ? '0 0 12px rgba(0,230,246,0.5)' : 'none', transition: 'text-shadow 0.3s' }} />
                  <div className="absolute bottom-0 left-0 h-px transition-all duration-500" style={{ width: uFocus ? '100%' : '0%', background: 'var(--cyber-cyan)', boxShadow: '0 0 12px var(--cyber-cyan)' }} />
                </div>
              </div>
              <div className="relative">
                <label className="block text-xs uppercase tracking-[0.28em] mb-3" style={{ color: pFocus ? 'var(--cyber-cyan)' : 'rgba(0,230,246,0.48)', letterSpacing: '0.25em', transition: 'color 0.3s' }}>QUANTUM_KEY</label>
                <div className="relative">
                  <input type={showPw ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} onFocus={() => setPFocus(true)} onBlur={() => setPFocus(false)} placeholder="Enter Quantum Key" autoComplete="current-password" required minLength={6} className="w-full bg-transparent px-0 py-3 pr-10 text-lg focus:outline-none" style={{ color: 'var(--cyber-cyan)', borderBottom: '1px solid rgba(0,230,246,0.28)', textShadow: pFocus ? '0 0 12px rgba(0,230,246,0.5)' : 'none', transition: 'text-shadow 0.3s' }} />
                  <div className="absolute bottom-0 left-0 h-px transition-all duration-500" style={{ width: pFocus ? '100%' : '0%', background: 'var(--cyber-cyan)', boxShadow: '0 0 12px var(--cyber-cyan)' }} />
                  <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-0 top-1/2 -translate-y-1/2" style={{ color: 'rgba(0,230,246,0.5)' }} onMouseEnter={e => (e.currentTarget.style.color = 'var(--cyber-cyan)')} onMouseLeave={e => (e.currentTarget.style.color = 'rgba(0,230,246,0.5)')}>
                    {showPw ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>
              {isInit === false && (
                <div className="relative">
                  <label className="block text-xs uppercase tracking-[0.28em] mb-3" style={{ color: cFocus ? 'var(--cyber-cyan)' : 'rgba(0,230,246,0.48)', letterSpacing: '0.25em', transition: 'color 0.3s' }}>CONFIRM_KEY</label>
                  <div className="relative">
                    <input type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} onFocus={() => setCFocus(true)} onBlur={() => setCFocus(false)} placeholder="Confirm Quantum Key" required minLength={6} className="w-full bg-transparent px-0 py-3 text-lg focus:outline-none" style={{ color: 'var(--cyber-cyan)', borderBottom: '1px solid rgba(0,230,246,0.28)', textShadow: cFocus ? '0 0 12px rgba(0,230,246,0.5)' : 'none', transition: 'text-shadow 0.3s' }} />
                    <div className="absolute bottom-0 left-0 h-px transition-all duration-500" style={{ width: cFocus ? '100%' : '0%', background: 'var(--cyber-cyan)', boxShadow: '0 0 12px var(--cyber-cyan)' }} />
                  </div>
                </div>
              )}
              {error && (
                <div className="px-4 py-3 text-xs tracking-widest" style={{ color: 'var(--cyber-red)', background: 'rgba(255,1,60,0.08)', border: '1px solid rgba(255,1,60,0.30)', textShadow: '0 0 10px rgba(255,1,60,0.6)' }}>⚠ {error}</div>
              )}
              <div className="relative pt-2">
                <div className="absolute -inset-1 pointer-events-none" style={{ background: 'linear-gradient(90deg,transparent,rgba(0,230,246,0.25),transparent)', animation: 'login-pulse 2.5s ease-in-out infinite' }} />
                <button type="submit" disabled={loading} className="relative w-full py-4 text-lg font-black uppercase tracking-widest transition-all" style={{ color: 'var(--cyber-cyan)', border: '1px solid rgba(0,230,246,0.55)', background: 'transparent', boxShadow: '0 0 30px rgba(0,230,246,0.2)', animation: glitch ? 'glitch-x 0.15s linear' : 'none' }} onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,230,246,0.08)'; e.currentTarget.style.boxShadow = '0 0 50px rgba(0,230,246,0.4)'; }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.boxShadow = '0 0 30px rgba(0,230,246,0.2)'; }}>
                  {loading ? 'AUTHENTICATING...' : isInit === false ? 'INITIALIZE LINK' : 'INITIATE LINK'}
                </button>
              </div>
              <p className="text-center text-xs tracking-[0.2em] pt-2 font-advent" style={{ color: 'rgba(0,230,246,0.30)' }}>
                {t('ui_terminal_id')}
              </p>
            </form>
          )}
        </div>
      </div>
      <style>{`
        @keyframes login-scan {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
        @keyframes login-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.9; }
        }
        @keyframes glitch-x {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-3px); }
          75% { transform: translateX(3px); }
        }
      `}</style>
    </div>
  );
}

