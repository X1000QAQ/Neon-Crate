'use client';

import { useState, useRef, useCallback } from 'react';
import { Settings, Save, FolderOpen, Key, Code, Brain, FlaskConical } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSettings } from '@/hooks/useSettings';
import { useLanguage } from '@/hooks/useLanguage';
import BasicSettings from './BasicSettings';
import PathsSettings from './PathsSettings';
import APISettings from './APISettings';
import InferenceSettings from './InferenceSettings';
import PersonaSettings from './PersonaSettings';
import RegexLab from './RegexLab';

export default function SettingsHub() {
  const { t, setLang } = useLanguage();
  const { isLoading, isSaving, saveSettings } = useSettings();
  const [activeTab, setActiveTab] = useState<'basic' | 'paths' | 'api' | 'regex' | 'inference' | 'persona'>('basic');

  // [C-04 修复] 用局部 Toast 替代 alert() + window.location.reload()，回归 SPA 体验
  const [toast, setToast] = useState<string | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((msg: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast(msg);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const handleSave = async () => {
    const success = await saveSettings(setLang);
    if (success) {
      showToast(t('alert_save_ok'));
    } else {
      showToast(t('alert_save_fail'));
    }
  };

  const tabs = [
    { id: 'basic', label: t('nav_basic'), icon: Settings },
    { id: 'paths', label: t('nav_paths'), icon: FolderOpen },
    { id: 'api', label: t('nav_api'), icon: Key },
    { id: 'inference', label: t('nav_inference'), icon: Brain },
    { id: 'persona', label: t('nav_persona'), icon: Code },
    { id: 'regex', label: t('nav_regex'), icon: FlaskConical },
  ];

  if (isLoading) {
    return (
      <div
        className="w-full"
        style={{
          background: 'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 1) 70%)',
        }}
      >
        <div
          className="relative border border-cyber-cyan/50 p-8"
          style={{ backdropFilter: 'blur(25px)', boxShadow: '0 0 40px rgba(0, 230, 246, 0.22), inset 0 0 40px rgba(0, 230, 246, 0.05)' }}
        >
          <div className="flex items-center justify-center min-h-[420px]">
            <div className="text-cyber-cyan/70 text-center tracking-widest">{t('loading_settings')}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="w-full"
      style={{ background: 'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 1) 70%)' }}
    >
      {/* 顶部全息导航 */}
      <div className="flex gap-6 mb-8">
        {tabs.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as typeof activeTab)}
              className={cn(
                'flex-1 py-6 px-8 font-bold text-xl uppercase tracking-widest transition-all relative',
                active ? 'bg-transparent text-cyber-cyan border-2 border-cyber-cyan' : 'bg-transparent text-cyber-cyan border border-cyber-cyan/20'
              )}
              style={{ backdropFilter: 'blur(15px)', boxShadow: active ? '0 0 30px rgba(0, 230, 246, 0.4), inset 0 0 30px rgba(0, 230, 246, 0.1)' : 'none' }}
            >
              <tab.icon className="w-6 h-6 mx-auto mb-2" />
              {tab.label}
              {active && (
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-cyber-cyan" style={{ boxShadow: '0 0 15px var(--cyber-cyan)', animation: 'light-pulse 2s ease-in-out infinite' }} />
              )}
            </button>
          );
        })}
      </div>

      {/* 配置面板 */}
      <div
        className="relative bg-transparent border border-cyber-cyan/50"
        style={{ backdropFilter: 'blur(25px)', boxShadow: '0 0 40px rgba(0, 230, 246, 0.3), inset 0 0 40px rgba(0, 230, 246, 0.05)' }}
      >
        <div className="p-8">
          <div className="mb-8 pb-4 border-b border-cyber-cyan/50 flex items-start justify-between gap-6">
            <div className="min-w-0">
              <h2 className="text-3xl font-bold text-cyber-cyan uppercase tracking-widest flex items-center gap-3" style={{ textShadow: '0 0 20px rgba(0, 230, 246, 0.8)' }}>
                <Settings className="w-8 h-8" />
                {t('title_system_settings')}
              </h2>
              <p className="text-cyber-cyan/70 text-sm mt-2">{t('app_subtitle')} · {String(activeTab).toUpperCase()} MODULE</p>
            </div>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className={cn('flex items-center gap-3 px-6 py-3 bg-transparent border-2 border-cyber-cyan text-cyber-cyan font-bold text-sm uppercase tracking-widest transition-all hover:bg-cyber-cyan hover:text-black disabled:opacity-50 disabled:cursor-not-allowed')}
              style={{ boxShadow: '0 0 20px rgba(0, 230, 246, 0.35), inset 0 0 20px rgba(0, 230, 246, 0.08)' }}
            >
              <Save size={18} />
              <span>{isSaving ? t('btn_saving') : t('btn_save')}</span>
            </button>
          </div>

          {/* 子组件不再接收 config/setConfig props */}
          <div>
            {activeTab === 'basic' && <BasicSettings t={t} />}
            {activeTab === 'paths' && <PathsSettings t={t} />}
            {activeTab === 'api' && <APISettings t={t} />}
            {activeTab === 'inference' && <InferenceSettings t={t} />}
            {activeTab === 'persona' && <PersonaSettings t={t} />}
            {activeTab === 'regex' && <RegexLab t={t} />}
          </div>
        </div>
      </div>

      {/* [C-04] 局部 Toast 通知：替代 alert() + reload() */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-cyber-cyan text-black font-medium shadow-lg animate-slide-up">
          {toast}
        </div>
      )}
    </div>
  );
}
