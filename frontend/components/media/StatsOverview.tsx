/**
 * ============================================================================
 * StatsOverview - 仪表盘统计卡片与指令中心
 * ============================================================================
 * 
 * [组件职责]
 * 1. 展示媒体库统计数据（电影数、剧集数、待处理、已完成）
 * 2. 提供三大核心操作按钮（扫描、刮削、字幕）
 * 
 * [布局架构]
 * 
 * 1. 统计卡片区 (Grid 4列响应式布局)
 *    ┌──────────┬──────────┬──────────┬──────────┐
 *    │  电影数  │  剧集数  │ 待处理数 │ 已完成数 │
 *    │  Card 1  │  Card 2  │  Card 3  │  Card 4  │
 *    └──────────┴──────────┴──────────┴──────────┘
 *    - 移动端 (< md): 1列垂直堆叠
 *    - 平板端 (md ~ lg): 2列 2行
 *    - 桌面端 (≥ lg): 4列横向排列
 *    - 卡片间距: 32px (gap-8)
 * 
 * 2. 指令中心区 (Grid 3列响应式布局)
 *    ┌──────────┬──────────┬──────────┐
 *    │   扫描   │   刮削   │   字幕   │
 *    │  SCAN    │  SCRAPE  │  SUBS    │
 *    └──────────┴──────────┴──────────┘
 *    - 移动端 (< md): 1列垂直堆叠
 *    - 桌面端 (≥ md): 3列横向排列
 *    - 按钮间距: 24px (gap-6)
 * 
 * [赛博视觉元素]
 * 
 * 统计卡片发光效果：
 * - 外层光晕: 0 0 30px rgba(0,230,246,0.3) - 30px扩散，30%透明度
 * - 内层微光: inset 0 0 30px rgba(0,230,246,0.05) - 内部5%透明度
 * - 毛玻璃: backdropFilter blur(20px) - 20px模糊半径
 * - 悬浮动画: hologram-float 3~4.5s 无限循环
 * 
 * 指令按钮交互效果：
 * - 静态: border-cyber-cyan/60 (60%透明度边框)
 * - Hover: 边框全亮 + 背景10%填充 + 25px发光
 * - 禁用: 60%透明度 + 禁止点击
 * 
 * [性能优化]
 * - 扫描后30秒内每1.5秒刷新统计（高频更新期）
 * - 30秒后停止轮询，避免频繁读库
 * 
 * ============================================================================
 */
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

  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

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
      showToast('加载统计数据失败，请刷新重试');
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
      showToast('扫描触发失败，请重试');
    } finally {
      setScanning(false);
    }
  };

  const handleScrape = async () => {
    setScraping(true);
    try {
      await api.triggerScrapeAll();
      setTimeout(() => { loadStats().catch(() => showToast('刮削后刷新统计失败')); }, 1000);
    } catch (error) {
      showToast('刮削触发失败，请重试');
    } finally {
      setScraping(false);
    }
  };

  const handleFindSubtitles = async () => {
    setFindingSubs(true);
    try {
      await api.triggerFindSubtitles();
      setTimeout(() => { loadStats().catch(() => showToast('字幕任务后刷新统计失败')); }, 1000);
    } catch (error) {
      showToast('字幕任务触发失败，请重试');
    } finally {
      setFindingSubs(false);
    }
  };

  if (loading) {
    return (
      /* 
        加载骨架屏 Grid 布局 (4列响应式)
        - 移动端 (< md): 1列
        - 平板端 (md ~ lg): 2列
        - 桌面端 (≥ lg): 4列
        - 卡片间距: 32px (gap-8)
      */
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {[...Array(4)].map((_, i) => (
          <div 
            key={i} 
            className="relative bg-transparent border border-cyber-cyan/30 p-6 animate-pulse"
            style={{ 
              backdropFilter: 'blur(20px)', // 毛玻璃效果：20px模糊
              boxShadow: '0 0 30px rgba(0, 230, 246, 0.2), inset 0 0 30px rgba(0, 230, 246, 0.05)' 
              // 双层发光：外层30px/20%透明度 + 内层30px/5%透明度
            }}
          >
            {/* 图标占位 */}
            <div className="h-12 w-12 bg-cyber-cyan/20 mb-4"></div>
            {/* 标签占位 */}
            <div className="h-4 bg-cyber-cyan/20 w-3/4 mb-2"></div>
            {/* 数值占位 */}
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
      {/* 
        ═══════════════════════════════════════════════════════════════
        统计卡片区 Grid 布局 (4列响应式)
        ═══════════════════════════════════════════════════════════════
        响应式断点：
        - 移动端 (< md): grid-cols-1 单列垂直堆叠
        - 平板端 (md ~ lg): grid-cols-2 两列两行
        - 桌面端 (≥ lg): grid-cols-4 四列横向排列
        
        卡片间距: gap-8 (32px)
        
        视觉效果：
        - 毛玻璃: blur(20px)
        - 双层发光: 外层30px + 内层30px
        - 悬浮动画: hologram-float (每个卡片延迟0.5s)
        - Hover: 边框全亮 + 放大5%
        ═══════════════════════════════════════════════════════════════
      */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {statCards.map((card, index) => (
          <div
            key={index}
            className="relative bg-transparent border border-cyber-cyan/50 p-6 transition-all hover:border-cyber-cyan hover:scale-105"
            style={{ 
              backdropFilter: 'blur(20px)', // 毛玻璃：20px模糊半径
              boxShadow: '0 0 30px rgba(0, 230, 246, 0.3), inset 0 0 30px rgba(0, 230, 246, 0.05)',
              // 双层发光：
              // - 外层：30px扩散，30%透明度（环境光晕）
              // - 内层：30px扩散，5%透明度（内部微光）
              animation: `hologram-float ${3 + index * 0.5}s ease-in-out infinite`
              // 悬浮动画：3s/3.5s/4s/4.5s 交错循环
            }}
          >
            {/* 卡片头部：标签 + 图标 */}
            <div className="flex items-center justify-between mb-3">
              <span 
                className="text-xs font-semibold text-cyber-cyan/70 tracking-[0.25em] uppercase" 
              >
                {card.label}
              </span>
              <card.icon className="w-6 h-6 text-cyber-cyan" />
            </div>
            
            {/* 统计数值：5xl 超大字体 + 发光效果 */}
            <div
              className={cn("text-5xl font-black", card.color)}
              style={{
                textShadow: '0 0 20px rgba(0, 230, 246, 0.8)' // 文字发光：20px扩散，80%透明度
              }}
            >
              {card.value}
            </div>
            
            {/* 底部分隔线：渐变 + 发光 */}
            <div 
              className="h-px w-full mt-4 bg-gradient-to-r from-transparent via-cyber-cyan to-transparent" 
              style={{ boxShadow: '0 0 10px rgba(0, 230, 246, 0.6)' }} // 线条发光：10px扩散
            />
          </div>
        ))}
      </div>

      {/* 
        ═══════════════════════════════════════════════════════════════
        指令中心区 Grid 布局 (3列响应式)
        ═══════════════════════════════════════════════════════════════
        响应式断点：
        - 移动端 (< md): grid-cols-1 单列垂直堆叠
        - 桌面端 (≥ md): grid-cols-3 三列横向排列
        
        按钮间距: gap-6 (24px)
        
        容器样式：
        - 上边距: mt-12 (48px，与统计卡片拉开距离)
        - 边框: 2px 青色边框（比卡片更粗）
        - 内边距: p-8 (32px)
        - 毛玻璃: blur(30px，比卡片更模糊)
        
        按钮交互：
        - 静态: 60%透明度边框
        - Hover: 边框全亮 + 背景10%填充 + 25px发光
        - 禁用: 60%透明度 + 禁止点击
        ═══════════════════════════════════════════════════════════════
      */}
      <div
        className="mt-12 relative bg-black/20 border-2 border-cyber-cyan/60 p-8"
        style={{
          backdropFilter: 'blur(30px)', // 毛玻璃：30px模糊（比卡片更强）
          boxShadow:
            '0 0 30px rgba(0, 230, 246, 0.2), inset 0 0 20px rgba(0, 230, 246, 0.1)',
          // 双层发光：外层30px/20%透明度 + 内层20px/10%透明度
        }}
      >
        {/* 标题：指令中心 */}
        <h3
          className="text-2xl font-black text-cyber-cyan uppercase tracking-widest mb-6 text-center font-advent"
          style={{ textShadow: '0 0 20px rgba(0, 230, 246, 0.8)' }} // 标题发光：20px扩散
        >
          {t('ui_command_center')}
        </h3>
        
        {/* 三大操作按钮 Grid 布局 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* 按钮1: 扫描 (SCAN) */}
          <button
            onClick={handleScan}
            disabled={scanning}
            className={cn(
              'flex flex-col items-center justify-center gap-3 px-6 py-4 border border-cyber-cyan/60 text-cyber-cyan transition-all',
              'hover:border-cyber-cyan hover:bg-cyber-cyan/10 hover:shadow-[0_0_25px_rgba(0,230,246,0.6)]',
              // Hover效果：边框全亮 + 背景10%填充 + 25px发光/60%透明度
              'disabled:opacity-60 disabled:cursor-not-allowed' // 禁用状态：60%透明度
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

          {/* 按钮2: 刮削 (SCRAPE) */}
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

          {/* 按钮3: 字幕 (SUBTITLES) */}
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

      {/* Toast 通知：固定在底部中央 */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-cyber-cyan text-black font-medium shadow-lg animate-slide-up">
          {toast}
        </div>
      )}
    </>
  );
}
