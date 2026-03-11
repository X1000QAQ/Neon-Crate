'use client';

import { useEffect, useRef, useState } from 'react';
import { Film, Tv, Clock, CheckCircle, Radar, Wand2, Subtitles } from 'lucide-react';
import { api } from '@/lib/api';
import type { StatsResponse } from '@/types';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';

export default function StatsOverview() {
  const { t } = useLanguage();
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [findingSubs, setFindingSubs] = useState(false);
  const scanBoostTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    loadStats();
    // 不再轮询，避免频繁读库。数据在扫描/刮削完成后由按钮回调主动刷新。
    return () => {
      if (scanBoostTimerRef.current) clearInterval(scanBoostTimerRef.current);
    };
  }, []);

  const loadStats = async () => {
    try {
      const data = await api.getStats();
      setStats(data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      await api.triggerScan();
      await loadStats();
      if (scanBoostTimerRef.current) {
        clearInterval(scanBoostTimerRef.current);
      }
      const startedAt = Date.now();
      scanBoostTimerRef.current = setInterval(() => {
        void loadStats();
        if (Date.now() - startedAt > 30000) {
          clearInterval(scanBoostTimerRef.current!);
          scanBoostTimerRef.current = null;
        }
      }, 1500);
    } catch (error) {
      console.error('Failed to trigger scan:', error);
    } finally {
      setScanning(false);
    }
  };

  const handleScrape = async () => {
    setScraping(true);
    try {
      await api.triggerScrapeAll();
      setTimeout(() => { loadStats().catch(console.error); }, 1000);
    } catch (error) {
      console.error('Failed to trigger scrape all:', error);
    } finally {
      setScraping(false);
    }
  };

  const handleFindSubtitles = async () => {
    setFindingSubs(true);
    try {
      await api.triggerFindSubtitles();
      setTimeout(() => { loadStats().catch(console.error); }, 1000);
    } catch (error) {
      console.error('Failed to trigger find subtitles:', error);
    } finally {
      setFindingSubs(false);
    }
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {[...Array(4)].map((_, i) => (
          <div 
            key={i} 
            className="relative bg-transparent border border-cyber-cyan/30 p-6 animate-pulse"
            style={{ 
              backdropFilter: 'blur(20px)', 
              boxShadow: '0 0 30px rgba(0, 230, 246, 0.2), inset 0 0 30px rgba(0, 230, 246, 0.05)' 
            }}
          >
            <div className="h-12 w-12 bg-cyber-cyan/20 mb-4"></div>
            <div className="h-4 bg-cyber-cyan/20 w-3/4 mb-2"></div>
            <div className="h-8 bg-cyber-cyan/20 w-1/2"></div>
          </div>
        ))}
      </div>
    );
  }

  const statCards = [
    {
      icon: Film,
      label: t('stat_total_movies'),
      value: stats?.movies || 0,
      color: 'text-cyber-cyan',
    },
    {
      icon: Tv,
      label: t('stat_total_tv'),
      value: stats?.tv_shows || 0,
      color: 'text-cyber-cyan',
    },
    { icon: Clock, label: t('stat_pending'), value: stats?.pending || 0, color: 'text-cyber-cyan' },
    { icon: CheckCircle, label: t('stat_completed'), value: stats?.completed || 0, color: 'text-cyber-cyan' },
  ];

  return (
    <>
      {/* Floating Stats Cards - Compact Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {statCards.map((card, index) => (
          <div
            key={index}
            className="relative bg-transparent border border-cyber-cyan/50 p-6 transition-all hover:border-cyber-cyan hover:scale-105"
            style={{ 
              backdropFilter: 'blur(20px)', 
              boxShadow: '0 0 30px rgba(0, 230, 246, 0.3), inset 0 0 30px rgba(0, 230, 246, 0.05)',
              animation: `hologram-float ${3 + index * 0.5}s ease-in-out infinite`
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <span 
                className="text-xs font-semibold text-cyber-cyan/70 tracking-[0.25em] uppercase" 
               
              >
                {card.label}
              </span>
              <card.icon className="w-6 h-6 text-cyber-cyan" />
            </div>
            <div
              className={cn("text-5xl font-black", card.color)}
              style={{
                textShadow: '0 0 20px rgba(0, 230, 246, 0.8)'
              }}
            >
              {card.value}
            </div>
            <div 
              className="h-px w-full mt-4 bg-gradient-to-r from-transparent via-cyber-cyan to-transparent" 
              style={{ boxShadow: '0 0 10px rgba(0, 230, 246, 0.6)' }} 
            />
          </div>
        ))}
      </div>

      {/* COMMAND CENTER 悬浮控制台 */}
      <div
        className="mt-12 relative bg-black/20 border-2 border-cyber-cyan/60 p-8"
        style={{
          backdropFilter: 'blur(30px)',
          boxShadow:
            '0 0 30px rgba(0, 230, 246, 0.2), inset 0 0 20px rgba(0, 230, 246, 0.1)',
        }}
      >
        <h3
          className="text-2xl font-black text-cyber-cyan uppercase tracking-widest mb-6 text-center font-advent"
          style={{ textShadow: '0 0 20px rgba(0, 230, 246, 0.8)' }}
        >
          {t('ui_command_center')}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Scan */}
          <button
            onClick={handleScan}
            disabled={scanning}
            className={cn(
              'flex flex-col items-center justify-center gap-3 px-6 py-4 border border-cyber-cyan/60 text-cyber-cyan transition-all',
              'hover:border-cyber-cyan hover:bg-cyber-cyan/10 hover:shadow-[0_0_25px_rgba(0,230,246,0.6)]',
              'disabled:opacity-60 disabled:cursor-not-allowed'
            )}
          >
            <div className="flex items-center gap-2">
              <Radar className="w-5 h-5" />
              <span className="text-sm font-semibold tracking-[0.25em] uppercase">
                {t('dashboard_btn_scan')}
              </span>
            </div>
            <span className="text-xs text-cyber-cyan/70">
              {scanning ? t('stat_scanning_active') : t('stat_scanning_idle')}
            </span>
          </button>

          {/* Scrape */}
          <button
            onClick={handleScrape}
            disabled={scraping}
            className={cn(
              'flex flex-col items-center justify-center gap-3 px-6 py-4 border border-cyber-cyan/60 text-cyber-cyan transition-all',
              'hover:border-cyber-cyan hover:bg-cyber-cyan/10 hover:shadow-[0_0_25px_rgba(0,230,246,0.6)]',
              'disabled:opacity-60 disabled:cursor-not-allowed'
            )}
          >
            <div className="flex items-center gap-2">
              <Wand2 className="w-5 h-5" />
              <span className="text-sm font-semibold tracking-[0.25em] uppercase">
                {t('dashboard_btn_scrape')}
              </span>
            </div>
            <span className="text-xs text-cyber-cyan/70">
              {scraping ? t('stat_scraping_active') : t('stat_scraping_idle')}
            </span>
          </button>

          {/* Find Subtitles */}
          <button
            onClick={handleFindSubtitles}
            disabled={findingSubs}
            className={cn(
              'flex flex-col items-center justify-center gap-3 px-6 py-4 border border-cyber-cyan/60 text-cyber-cyan transition-all',
              'hover:border-cyber-cyan hover:bg-cyber-cyan/10 hover:shadow-[0_0_25px_rgba(0,230,246,0.6)]',
              'disabled:opacity-60 disabled:cursor-not-allowed'
            )}
          >
            <div className="flex items-center gap-2">
              <Subtitles className="w-5 h-5" />
              <span className="text-sm font-semibold tracking-[0.25em] uppercase text-nowrap">
                {t('dashboard_btn_find_subtitles')}
              </span>
            </div>
            <span className="text-xs text-cyber-cyan/70">
              {findingSubs ? t('stat_finding_subtitles_active') : t('stat_finding_subtitles_idle')}
            </span>
          </button>
        </div>
      </div>
    </>
  );
}
