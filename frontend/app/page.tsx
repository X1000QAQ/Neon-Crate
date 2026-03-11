'use client';

import { useState } from 'react';
import { Film, LayoutDashboard, Settings as SettingsIcon, Activity } from 'lucide-react';
import StatsOverview from '@/components/media/StatsOverview';
import MiniLog from '@/components/media/MiniLog';
import MediaWall from '@/components/media/MediaWall';
import SystemMonitor from '@/components/media/SystemMonitor';
import SettingsHub from '@/components/settings/SettingsHub';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';

type View = 'dashboard' | 'media' | 'monitor' | 'settings';

export default function Home() {
  const [activeView, setActiveView] = useState<View>('dashboard');
  const { t } = useLanguage();

  const navItems = [
    { id: 'dashboard', label: t('nav_dashboard'), icon: LayoutDashboard },
    { id: 'media', label: t('nav_task_list'), icon: Film },
    { id: 'monitor', label: t('nav_monitor'), icon: Activity },
    { id: 'settings', label: t('nav_system_settings'), icon: SettingsIcon },
  ];

  return (
    <div className="min-h-screen relative">
      {/* 物理壁纸底层 (-z-20) */}
      <div 
        className="fixed inset-0 bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: 'url(/bg-main.jpg)', zIndex: -20 }}
      />
      
      {/* 量子全息暗场蒙版 (-z-10) */}
      <div 
        className="fixed inset-0 pointer-events-none" 
        style={{ 
          background: 'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.1) 0%, rgba(0, 0, 0, 0.85) 80%, rgba(0, 0, 0, 0.95) 100%)',
          backdropFilter: 'blur(3px)',
          zIndex: -10
        }} 
      />

      {/* 所有的实际内容都需要放在 z-10 上，防止被背景覆盖 */}
      <div className="relative z-10">
      {/* Header - Holographic Style */}
      <header className="relative z-50 border-b border-cyber-cyan/50" style={{ backdropFilter: 'blur(20px)', background: 'rgba(0, 0, 0, 0.4)' }}>
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-20 h-20 bg-transparent border-2 border-cyber-cyan flex items-center justify-center" style={{ boxShadow: '0 0 20px rgba(0, 230, 246, 0.5)' }}>
                <Film className="text-cyber-cyan" size={48} />
              </div>
              <div>
                <h1 className="text-5xl font-black text-cyber-cyan font-advent" style={{ textShadow: '0 0 20px rgba(0, 230, 246, 0.8)' }}>
                  Neon Crate
                </h1>
                <p className="text-cyber-cyan/70 text-lg">{t('app_subtitle')}</p>
              </div>
            </div>

            {/* Navigation - Holographic Buttons */}
            <nav className="flex gap-3">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActiveView(item.id as View)}
                  className={cn(
                    'flex items-center gap-2 px-5 py-2.5 transition-all border-2 font-semibold text-sm uppercase tracking-widest',
                    activeView === item.id
                      ? 'bg-cyber-cyan text-black border-cyber-cyan'
                      : 'bg-transparent text-cyber-cyan border-cyber-cyan/50 hover:border-cyber-cyan hover:bg-cyber-cyan/10'
                  )}
                  style={{
                    boxShadow: activeView === item.id 
                      ? '0 0 25px rgba(0, 230, 246, 0.6), inset 0 0 20px rgba(0, 230, 246, 0.2)' 
                      : '0 0 15px rgba(0, 230, 246, 0.3), inset 0 0 15px rgba(0, 230, 246, 0.05)',
                    backdropFilter: 'blur(10px)'
                  }}
                >
                  <item.icon size={18} />
                  <span>{item.label}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 container mx-auto max-w-[1800px] px-6 py-16">
        {activeView === 'dashboard' && (
          <div
            className="relative min-h-[800px] flex flex-col gap-12 p-8"
            style={{
              animation: 'fade-in 0.8s ease-out',
              background:
                'radial-gradient(circle at 50% 50%, rgba(0, 230, 246, 0.15) 0%, rgba(0, 0, 0, 0.95) 70%)',
            }}
          >
            {/* 上半区：统计卡片 + 指令舱 */}
            <div className="relative z-20 w-full">
              <StatsOverview />
            </div>

            {/* 下半区：全息日志流 (Holographic Stream) */}
            <div className="relative z-10 w-full flex-1">
              <MiniLog />
            </div>
          </div>
        )}

        {activeView === 'media' && (
          <div className="space-y-8" style={{ animation: 'fade-in 0.5s ease-out' }}>
            <div className="text-center mb-8">
              <h2 className="text-5xl font-black text-cyber-cyan uppercase tracking-widest mb-2 font-advent" style={{ textShadow: '0 0 30px rgba(0, 230, 246, 0.8)' }}>
                {t('nav_media')}
              </h2>
              <p className="text-cyber-cyan/70 text-lg tracking-wider">{t('dashboard_overview_desc')}</p>
            </div>
            <MediaWall />
          </div>
        )}

        {activeView === 'monitor' && (
          <div className="space-y-8" style={{ animation: 'fade-in 0.5s ease-out' }}>
            <div className="text-center mb-8">
              <h2 className="text-5xl font-black text-cyber-cyan uppercase tracking-widest mb-2 font-advent" style={{ textShadow: '0 0 30px rgba(0, 230, 246, 0.8)' }}>
                {t('monitor_title')}
              </h2>
              <p className="text-cyber-cyan/70 text-lg tracking-wider">{t('monitor_subtitle')}</p>
            </div>
            <SystemMonitor />
          </div>
        )}

        {activeView === 'settings' && (
          <div className="space-y-8" style={{ animation: 'fade-in 0.5s ease-out' }}>
            <SettingsHub />
          </div>
        )}
      </main>

      {/* Footer - Holographic */}
      <footer className="relative z-10 mt-16 py-6 border-t border-cyber-cyan/50" style={{ backdropFilter: 'blur(15px)' }}>
        <div className="container mx-auto px-6 text-center text-cyber-cyan/70 text-sm tracking-wider">
          <p>Neon Crate &copy; {new Date().getFullYear()} - {t('app_subtitle')}</p>
        </div>
      </footer>
      </div>

    </div>
  );
}
