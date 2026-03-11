'use client';

import { useState, useEffect } from 'react';
import { Settings, Save, FolderOpen, Key, Code, Brain, FlaskConical } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import type { SettingsConfig } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';
import BasicSettings from './BasicSettings';
import PathsSettings from './PathsSettings';
import APISettings from './APISettings';
import InferenceSettings from './InferenceSettings';
import PersonaSettings from './PersonaSettings';
import RegexLab from './RegexLab';

export default function SettingsHub() {
  const { t, setLang } = useLanguage();
  const [activeTab, setActiveTab] = useState<'basic' | 'paths' | 'api' | 'regex' | 'inference' | 'persona'>('basic');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<SettingsConfig | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await api.getSettings();
      setConfig(data);
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;

    // 1+1 路径约束验证
    const activeStorage = config.paths.filter(p => p.enabled && p.type === 'library');
    const movieCount = activeStorage.filter(p => (p.category || '').toLowerCase() === 'movie').length;
    const tvCount = activeStorage.filter(p => (p.category || '').toLowerCase() === 'tv').length;
    
    if (movieCount > 1 || tvCount > 1) {
      alert(t('settings_config_conflict'));
      return;
    }
    
    if (activeStorage.length > 0 && (movieCount === 0 || tvCount === 0)) {
      alert(t('settings_config_missing'));
      return;
    }

    setSaving(true);
    try {
      // 🔧 关键：先同步更新前端语言状态和 localStorage
      setLang(config.settings.ui_lang as 'zh' | 'en');
      
      // 然后再保存到后端
      await api.updateSettings(config);
      alert(t('alert_save_ok'));
      
      // 🔧 强制刷新，确保所有字典 Key 重新加载
      setTimeout(() => {
        window.location.reload();
      }, 100);
    } catch (error) {
      console.error('Failed to save settings:', error);
      alert(t('alert_save_fail'));
    } finally {
      setSaving(false);
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

  if (loading) {
    return (
      <div
        className="w-full"
        style={{
          background:
            'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 1) 70%)',
        }}
      >
        <div
          className="relative border border-cyber-cyan/50 p-8"
          style={{
            backdropFilter: 'blur(25px)',
            boxShadow:
              '0 0 40px rgba(0, 230, 246, 0.22), inset 0 0 40px rgba(0, 230, 246, 0.05)',
          }}
        >
          <div className="flex items-center justify-center min-h-[420px]">
            <div className="text-cyber-cyan/70 text-center tracking-widest">
              {t('loading_settings')}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div
        className="w-full"
        style={{
          background:
            'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 1) 70%)',
        }}
      >
        <div
          className="relative border border-cyber-cyan/50 p-8"
          style={{
            backdropFilter: 'blur(25px)',
            boxShadow:
              '0 0 40px rgba(0, 230, 246, 0.22), inset 0 0 40px rgba(0, 230, 246, 0.05)',
          }}
        >
          <div className="flex items-center justify-center min-h-[420px]">
            <div className="text-cyber-red text-center tracking-widest">
              {t('load_failed')}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="w-full"
      style={{
        background:
          'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.08) 0%, rgba(0, 0, 0, 1) 70%)',
      }}
    >
      {/* 顶部全息导航 (Top Tabs) */}
      <div className="flex gap-6 mb-8">
        {tabs.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={cn(
                'flex-1 py-6 px-8 font-bold text-xl uppercase tracking-widest transition-all relative',
                active
                  ? 'bg-transparent text-cyber-cyan border-2 border-cyber-cyan'
                  : 'bg-transparent text-cyber-cyan border border-cyber-cyan/20'
              )}
              style={{
                backdropFilter: 'blur(15px)',
                boxShadow: active
                  ? '0 0 30px rgba(0, 230, 246, 0.4), inset 0 0 30px rgba(0, 230, 246, 0.1)'
                  : 'none',
              }}
            >
              <tab.icon className="w-6 h-6 mx-auto mb-2" />
              {tab.label}
              {active && (
                <div
                  className="absolute bottom-0 left-0 right-0 h-1 bg-cyber-cyan"
                  style={{
                    boxShadow: '0 0 15px var(--cyber-cyan)',
                    animation: 'light-pulse 2s ease-in-out infinite',
                  }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* 深空背景毛玻璃配置面板 */}
      <div
        className="relative bg-transparent border border-cyber-cyan/50"
        style={{
          backdropFilter: 'blur(25px)',
          boxShadow: '0 0 40px rgba(0, 230, 246, 0.3), inset 0 0 40px rgba(0, 230, 246, 0.05)',
        }}
      >
        <div className="p-8">
          {/* Header */}
          <div className="mb-8 pb-4 border-b border-cyber-cyan/50 flex items-start justify-between gap-6">
            <div className="min-w-0">
              <h2
                className="text-3xl font-bold text-cyber-cyan uppercase tracking-widest flex items-center gap-3"
                style={{
                  textShadow: '0 0 20px rgba(0, 230, 246, 0.8)',
                }}
              >
                <Settings className="w-8 h-8" />
                {t('title_system_settings')}
              </h2>
              <p className="text-cyber-cyan/70 text-sm mt-2">
                {t('app_subtitle')} · {String(activeTab).toUpperCase()} MODULE
              </p>
            </div>

            <button
              onClick={handleSave}
              disabled={saving}
              className={cn(
                'flex items-center gap-3 px-6 py-3 bg-transparent border-2 border-cyber-cyan text-cyber-cyan',
                'font-bold text-sm uppercase tracking-widest transition-all',
                'hover:bg-cyber-cyan hover:text-black',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
              style={{
                boxShadow: '0 0 20px rgba(0, 230, 246, 0.35), inset 0 0 20px rgba(0, 230, 246, 0.08)',
              }}
            >
              <Save size={18} />
              <span>{saving ? t('btn_saving') : t('btn_save')}</span>
            </button>
          </div>

          {/* Content */}
          <div>
            {activeTab === 'basic' && <BasicSettings config={config} setConfig={setConfig} t={t} />}
            {activeTab === 'paths' && <PathsSettings config={config} setConfig={setConfig} t={t} />}
            {activeTab === 'api' && <APISettings config={config} setConfig={setConfig} t={t} />}
            {activeTab === 'inference' && <InferenceSettings config={config} setConfig={setConfig} t={t} />}
            {activeTab === 'persona' && <PersonaSettings config={config} setConfig={setConfig} t={t} />}
            {activeTab === 'regex' && <RegexLab t={t} config={config} setConfig={setConfig} />}
          </div>
        </div>
      </div>

    </div>
  );
}
