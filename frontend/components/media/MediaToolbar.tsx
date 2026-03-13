/**
 * MediaToolbar - 媒体库操作工具栏
 *
 * 职责：
 * - 搜索栏：关键词过滤任务列表
 * - 危险操作：批量删除（需选中）、重置数据库（需输入 CONFIRM）
 * - 任务触发：扫描 / 刮削 / 字幕三大后台任务的入口按钮
 * - 筛选器：按状态（4 项）和类型（电影/剧集）过滤列表
 *
 * 注意：statusFilter 有效值为 all/pending/archived/failed/ignored
 * success 已移除（tasks 表从不写入该状态，选择后永远返回空列表）
 */
'use client';

import { Search, RefreshCw, Trash2, Database, Filter, Radar, Wand2, Subtitles } from 'lucide-react';
import { useLanguage } from '@/hooks/useLanguage';
import { cn } from '@/lib/utils';

interface MediaToolbarProps {
  searchKeyword: string;          // 当前搜索关键词
  onSearchChange: (val: string) => void;  // 搜索词变更回调
  onRefresh: () => void;          // 刷新任务列表
  loading: boolean;               // 是否正在加载（刷新按钮 loading 态）
  selectedCount: number;          // 当前选中数量（0 时批量删除禁用）
  onBatchDelete: () => void;      // 批量删除选中记录（仅数据库，不删文件）
  onPurge: () => void;            // 核弹：清空全部数据库记录（需二次确认）
  onScan: () => void;             // 触发物理扫描任务
  scanning: boolean;              // 扫描任务是否进行中
  onScrapeAll: () => void;        // 触发全量元数据刮削
  scraping: boolean;              // 刮削任务是否进行中
  onFindSubtitles: () => void;    // 触发字幕查找任务
  findingSubs: boolean;           // 字幕查找是否进行中
  statusFilter: string;           // 当前状态筛选值（all/pending/archived/failed/ignored）
  onStatusChange: (val: string) => void;  // 状态筛选变更回调
  typeFilter: string;             // 当前类型筛选值（all/movie/tv）
  onTypeChange: (val: string) => void;    // 类型筛选变更回调
}

export default function MediaToolbar({
  searchKeyword,
  onSearchChange,
  onRefresh,
  loading,
  selectedCount,
  onBatchDelete,
  onPurge,
  onScan,
  scanning,
  onScrapeAll,
  scraping,
  onFindSubtitles,
  findingSubs,
  statusFilter,
  onStatusChange,
  typeFilter,
  onTypeChange,
}: MediaToolbarProps) {
  const { t } = useLanguage();

  return (
    <div className="space-y-6">
      {/* 搜索栏 - 非对称切角透明工具栏 */}
      <div className="relative bg-transparent border border-cyber-cyan/50 p-6 hover:border-cyber-cyan transition-all" style={{
        backdropFilter: 'blur(20px)',
        boxShadow: '0 0 40px rgba(6, 182, 212, 0.4), inset 0 0 40px rgba(6, 182, 212, 0.08)'
      }}>
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-cyber-cyan" size={20} />
            <input
              type="text"
              value={searchKeyword}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder={t('toolbar_search_placeholder')}
              className="cyan-input w-full pl-12 pr-6 py-3 placeholder-cyber-cyan/40 focus:outline-none transition-all font-semibold uppercase tracking-wider text-sm"
              style={{
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 20px rgba(6, 182, 212, 0.2), inset 0 0 20px rgba(6, 182, 212, 0.05)',
              }}
            />
          </div>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="bg-transparent border border-cyber-cyan text-cyber-cyan px-6 py-3 font-semibold text-sm uppercase tracking-wider hover:bg-cyber-cyan hover:text-black transition-all disabled:opacity-50"
            style={{
              backdropFilter: 'blur(10px)',
              boxShadow: '0 0 20px rgba(6, 182, 212, 0.3), inset 0 0 20px rgba(6, 182, 212, 0.05)',
            }}
          >
            <RefreshCw size={18} className={cn("inline-block mr-2", loading && 'animate-spin')} />
            {t('toolbar_refresh')}
          </button>
          <button
            onClick={onBatchDelete}
            disabled={selectedCount === 0}
            className="bg-transparent border border-cyber-red text-cyber-red px-6 py-3 font-semibold text-sm uppercase tracking-wider hover:bg-cyber-red hover:text-white transition-all disabled:opacity-50"
            style={{
              backdropFilter: 'blur(10px)',
              boxShadow: '0 0 20px rgba(255, 1, 60, 0.3)',
            }}
          >
            <Trash2 size={18} className="inline-block mr-2" />
            {t('toolbar_delete')}
            {selectedCount > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-white/20 rounded text-xs">{selectedCount}</span>
            )}
          </button>
          <button
            onClick={onPurge}
            className="bg-transparent border border-cyber-red text-cyber-red px-6 py-3 font-semibold text-sm uppercase tracking-wider hover:bg-cyber-red hover:text-white transition-all"
            style={{
              backdropFilter: 'blur(10px)',
              boxShadow: '0 0 20px rgba(255, 1, 60, 0.3)',
            }}
          >
            <Database size={18} className="inline-block mr-2" />
            {t('toolbar_reset')}
          </button>
        </div>
      </div>

      {/* 过滤器 + 操作按钮 */}
      <div className="relative bg-transparent border border-cyber-cyan/50 p-6 hover:border-cyber-cyan transition-all" style={{
        backdropFilter: 'blur(20px)',
        boxShadow: '0 0 40px rgba(6, 182, 212, 0.4), inset 0 0 40px rgba(6, 182, 212, 0.08)'
      }}>
        <div className="flex items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <Filter className="text-cyber-cyan" size={24} />
            <h3 className="text-xl font-bold text-cyber-cyan" style={{ 
              textShadow: '0 0 10px rgba(6, 182, 212, 0.6)'
            }}>
              {t('toolbar_filters')}
            </h3>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onScan}
              disabled={scanning}
              className="bg-transparent border border-cyber-cyan text-cyber-cyan px-6 py-3 font-semibold text-sm uppercase tracking-wider hover:bg-cyber-cyan hover:text-black transition-all disabled:opacity-50"
              style={{
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 20px rgba(6, 182, 212, 0.4)',
              }}
            >
              <Radar size={18} className={cn("inline-block mr-2", scanning && 'animate-spin')} />
              {scanning ? t('dashboard_btn_scanning') : t('toolbar_scan')}
            </button>
            <button
              onClick={onScrapeAll}
              disabled={scraping}
              className="bg-transparent border border-cyber-cyan text-cyber-cyan px-6 py-3 font-semibold text-sm uppercase tracking-wider hover:bg-cyber-cyan hover:text-black transition-all disabled:opacity-50"
              style={{
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 20px rgba(6, 182, 212, 0.3)',
              }}
            >
              <Wand2 size={18} className={cn("inline-block mr-2", scraping && 'animate-spin')} />
              {scraping ? t('dashboard_btn_scraping') : t('toolbar_scrape')}
            </button>
            <button
              onClick={onFindSubtitles}
              disabled={findingSubs}
              className="bg-transparent border border-cyber-cyan text-cyber-cyan px-6 py-3 font-semibold text-sm uppercase tracking-wider hover:bg-cyber-cyan hover:text-black transition-all disabled:opacity-50"
              style={{
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 20px rgba(6, 182, 212, 0.3)',
              }}
            >
              <Subtitles size={18} className={cn("inline-block mr-2", findingSubs && 'animate-pulse')} />
              {findingSubs ? t('dashboard_btn_finding') : t('toolbar_subtitles')}
            </button>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="text-cyber-cyan/70 text-xs uppercase tracking-wider mb-2 block font-semibold">
              {t('filter_status')}
            </label>
            <select
              value={statusFilter}
              onChange={(e) => onStatusChange(e.target.value)}
              className="cyan-input w-full px-4 py-3 focus:outline-none transition-all font-semibold text-sm"
              style={{
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 15px rgba(6, 182, 212, 0.2)',
              }}
            >
              <option value="all" className="bg-black">{t('filter_status_all')}</option>
              <option value="pending" className="bg-black">{t('filter_status_pending')}</option>
              <option value="archived" className="bg-black">{t('filter_status_archived')}</option>
              <option value="failed" className="bg-black">{t('filter_status_failed')}</option>
              <option value="ignored" className="bg-black">{t('filter_status_ignored')}</option>
            </select>
          </div>
          <div>
            <label className="text-cyber-cyan/70 text-xs uppercase tracking-wider mb-2 block font-semibold">
              {t('filter_type')}
            </label>
            <select
              value={typeFilter}
              onChange={(e) => onTypeChange(e.target.value)}
              className="cyan-input w-full px-4 py-3 focus:outline-none transition-all font-semibold text-sm"
              style={{
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 15px rgba(6, 182, 212, 0.2)',
              }}
            >
              <option value="all" className="bg-black">{t('filter_type_all')}</option>
              <option value="movie" className="bg-black">{t('filter_type_movie')}</option>
              <option value="tv" className="bg-black">{t('filter_type_tv')}</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
