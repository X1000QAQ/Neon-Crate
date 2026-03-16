'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { X, Search, FileText, Image, Subtitles, Check, Loader2, Zap } from 'lucide-react';
import { api } from '@/lib/api';
import type { Task } from '@/types';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';

export type RebuildMode = 'nfo' | 'poster' | 'subtitle';

interface TmdbResult {
  tmdb_id: number;
  title: string;
  year: string;
  overview: string;
  poster_path: string | null;
  imdb_id: string | null;
}

interface RebuildDialogProps {
  open: boolean;
  task: Task;
  mode: RebuildMode;
  onConfirm: (params: {
    tmdb_id?: number;
    media_type: string;
    nuclear_reset: boolean;
    season?: number;
    episode?: number;
  }) => void;
  onClose: () => void;
}

const MODE_META: Record<RebuildMode, { icon: React.ReactNode; label: string; i18nKey: string; color: string }> = {
  nfo:      { icon: <FileText size={16} />,  label: 'NFO 深度纠偏',  i18nKey: 'rebuild_mode_nfo',      color: 'text-cyber-cyan'  },
  poster:   { icon: <Image size={16} />,     label: '海报强制覆盖',  i18nKey: 'rebuild_mode_poster',    color: 'text-purple-400'  },
  subtitle: { icon: <Subtitles size={16} />, label: '字幕即时触发',  i18nKey: 'rebuild_mode_subtitle',  color: 'text-green-400'   },
};

const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w92';

export default function RebuildDialog({ open, task, mode, onConfirm, onClose }: RebuildDialogProps) {
  const { t } = useLanguage();
  const [mediaType, setMediaType] = useState<string>(task.media_type || 'movie');
  const [keyword, setKeyword]     = useState<string>(task.title || '');
  const [results, setResults]     = useState<TmdbResult[]>([]);
  const [selected, setSelected]   = useState<TmdbResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [season, setSeason]   = useState<number | ''>(task.season ?? 1);
  const [episode, setEpisode] = useState<number | ''>(task.episode ?? '');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── 开门重置器：当弹窗打开且任务变化时，重置所有本地状态 ──
  // 业务链路：1. 监听 open 状态与 task.id 变化 -> 2. 触发弹窗展示 -> 
  // 3. 彻底清空上一轮的幽灵记忆 (keyword, results, selected) -> 4. 重新灌入当前 task 的基础参数
  // 防止 Dialog 幽灵记忆陷阱：if (!open) return null 只隐藏不卸载，
  // 导致状态被永久冻结。此 useEffect 确保每次打开新任务时，状态都被重置。
  useEffect(() => {
    if (open) {
      // 1. 重置媒体类型（从 task 读取或默认为 movie）
      setMediaType(task.media_type || 'movie');
      // 2. 重置搜索关键词（从 task.title 读取或清空）
      setKeyword(task.title || '');
      // 3. 清空上一轮的搜索结果列表
      setResults([]);
      // 4. 清空上一轮的选中项
      setSelected(null);
      // 5. 清空上一轮的搜索错误信息
      setSearchErr(null);
      // 6. 重置季数（TV 专用，从 task 读取或默认为 1）
      setSeason(task.season ?? 1);
      // 7. 重置集数（TV 专用，从 task 读取或清空）
      setEpisode(task.episode ?? '');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, task.id]);

  const handleSearch = useCallback(async (kw: string, mt: string) => {
    // ── TMDB 搜索业务链路 ──
    // 1. 校验关键词非空 -> 2. 设置加载状态 -> 3. 调用 API 搜索 -> 4. 更新结果列表 -> 5. 清空选中项 -> 6. 异常处理
    if (!kw.trim()) { setResults([]); return; }
    setSearching(true);
    setSearchErr(null);
    try {
      // 1. 调用后端 TMDB 搜索接口
      const res = await api.searchTmdb(kw.trim(), mt);
      // 2. 更新搜索结果列表
      setResults(res);
      // 3. 清空上一轮的选中项（新搜索结果需重新选择）
      setSelected(null);
    } catch (e) {
      // 4. 捕获异常并显示错误信息
      setSearchErr((e as Error).message || 'TMDB 搜索失败');
    } finally {
      // 5. 关闭加载状态
      setSearching(false);
    }
  }, []);

  // ── 关键词变化处理（防抖） ──
  // 业务链路：1. 更新关键词状态 -> 2. 清除上一轮的防抖定时器 -> 3. 设置新的防抖定时器（400ms 延迟）-> 4. 触发搜索
  const onKeywordChange = (v: string) => {
    setKeyword(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => handleSearch(v, mediaType), 400);
  };

  // ── 媒体类型变化处理 ──
  // 业务链路：1. 更新媒体类型 -> 2. 若关键词非空，立即重新搜索（切换类型时需更新结果）
  const onMediaTypeChange = (mt: string) => {
    setMediaType(mt);
    if (keyword.trim()) handleSearch(keyword, mt);
  };

  // ── 核级重构执行器 ──
  // 业务链路：1. 防止重复点击（检查 executing 状态）-> 2. 设置执行中标志 -> 
  // 3. 构建请求参数（tmdb_id、media_type、nuclear_reset=true、季集号）-> 4. 调用父组件回调 -> 5. 关闭弹窗
  // 注意：NFO 模式下强制 nuclear_reset=true，确保核级清理必被执行
  const handleNuclearExecute = () => {
    if (executing) return;
    setExecuting(true);
    onConfirm({
      tmdb_id: selected?.tmdb_id,
      media_type: mediaType,
      nuclear_reset: true,
      season: mediaType === 'tv' && season !== '' ? Number(season) : undefined,
      episode: mediaType === 'tv' && episode !== '' ? Number(episode) : undefined,
    });
    onClose();
  };

  if (!open) return null;

  const meta = MODE_META[mode];
  const isNfo = mode === 'nfo';

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.78)', backdropFilter: 'blur(8px)' }}
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg mx-4 border border-cyber-cyan/40 flex flex-col"
        style={{
          background: 'rgba(0,8,18,0.97)',
          boxShadow: '0 0 50px rgba(0,230,246,0.18)',
          maxHeight: '90vh',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-cyber-cyan/20">
          <div className={cn('flex items-center gap-2 font-bold text-sm uppercase tracking-widest', meta.color)}>
            {meta.icon}
            <span>{t(meta.i18nKey as Parameters<typeof t>[0])}</span>
          </div>
          <button onClick={onClose} className="text-cyber-cyan/40 hover:text-cyber-cyan transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* ── Task info strip ── */}
        <div className="px-5 py-2 border-b border-cyber-cyan/10 text-xs font-mono text-cyber-cyan/50 truncate">
          ID: <span className="text-cyber-cyan/70">{task.id}</span>
          {' · '}
          <span className="text-cyber-cyan/60">{task.file_name || task.file_path}</span>
        </div>

        {/* ── Body (scrollable) ── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

          {/* Non-NFO: simple confirm */}
          {!isNfo && (
            <p className="text-cyber-cyan/60 text-sm">
              {mode === 'poster'
                ? '将强制删除旧 poster.jpg 并从 TMDB 重新下载。'
                : '将立即触发字幕搜索，结果通常在 30 秒内返回。'}
            </p>
          )}

          {/* NFO: nuclear-only flow */}
          {isNfo && (
            <>
              {/* Mission briefing */}
              <div className="border border-red-500/30 bg-red-500/5 px-4 py-3">
                <p className="text-red-400/80 text-xs leading-relaxed">
                  ☢️ <strong className="text-red-400">核级重构模式</strong>：执行此操作将立即清理目录杂质、
                  重写 NFO 并重新触发云端识别。<strong className="text-red-400/70">不可撤销。</strong>
                </p>
              </div>

              {/* Media type selector */}
              <div>
                <label className="block text-xs text-cyber-cyan/50 uppercase tracking-wider mb-1.5">{t('label_media_type')}</label>
                <div className="flex gap-2">
                  {(['movie', 'tv'] as const).map(t_type => (
                    <button
                      key={t_type}
                      onClick={() => onMediaTypeChange(t_type)}
                      className={cn(
                        'px-4 py-1.5 border text-xs uppercase tracking-wider transition-all',
                        mediaType === t_type
                          ? 'border-cyber-cyan bg-cyber-cyan text-black font-bold'
                          : 'border-cyber-cyan/30 text-cyber-cyan/60 hover:border-cyber-cyan/60'
                      )}
                    >
                      {t_type === 'movie' ? t('media_type_movie') : t('media_type_tv')}
                    </button>
                  ))}
                </div>
              </div>

              {/* Search bar */}
              <div>
                <label className="block text-xs text-cyber-cyan/50 uppercase tracking-wider mb-1.5">{t('label_search_title')}</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={keyword}
                    onChange={e => onKeywordChange(e.target.value)}
                    placeholder={mediaType === 'tv' ? t('placeholder_tv_example') : t('placeholder_movie_example')}
                    className="flex-1 bg-transparent border border-cyber-cyan/40 px-3 py-2 text-cyber-cyan text-sm
                               outline-none focus:border-cyber-cyan placeholder:text-cyber-cyan/25"
                    onKeyDown={e => e.key === 'Enter' && handleSearch(keyword, mediaType)}
                  />
                  <button
                    onClick={() => handleSearch(keyword, mediaType)}
                    disabled={searching || !keyword.trim()}
                    className={cn(
                      'px-3 py-2 border text-sm transition-all flex items-center gap-1',
                      searching || !keyword.trim()
                        ? 'border-cyber-cyan/20 text-cyber-cyan/30 cursor-not-allowed'
                        : 'border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black'
                    )}
                  >
                    {searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                    {t('btn_search')}
                  </button>
                </div>
              </div>

              {/* Search error */}
              {searchErr && (
                <p className="text-cyber-red text-xs border border-cyber-red/30 px-3 py-2">{searchErr}</p>
              )}

              {/* Results list */}
              {results.length > 0 && (
                <div className="border border-cyber-cyan/20 divide-y divide-cyber-cyan/10 max-h-64 overflow-y-auto">
                  {results.map(r => (
                    <button
                      key={r.tmdb_id}
                      onClick={() => setSelected(r)}
                      className={cn(
                        'w-full flex items-start gap-3 px-3 py-2.5 text-left transition-all',
                        selected?.tmdb_id === r.tmdb_id
                          ? 'bg-cyber-cyan/15 border-l-2 border-cyber-cyan'
                          : 'hover:bg-cyber-cyan/5 border-l-2 border-transparent'
                      )}
                    >
                      <div className="w-8 h-12 flex-shrink-0 border border-cyber-cyan/30 overflow-hidden bg-black/40">
                        {r.poster_path ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={`${TMDB_IMAGE_BASE}${r.poster_path}`}
                            alt={r.title}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-cyber-cyan/20 text-xs">?</div>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-cyber-cyan truncate">{r.title}</span>
                          {r.year && <span className="text-xs text-cyber-cyan/50 flex-shrink-0">({r.year})</span>}
                          {selected?.tmdb_id === r.tmdb_id && (
                            <Check size={12} className="text-cyber-cyan flex-shrink-0" />
                          )}
                        </div>
                        <p className="text-xs text-cyber-cyan/40 mt-0.5 line-clamp-2 leading-snug">
                          {r.overview || t('text_no_overview')}
                        </p>
                        <span className="text-xs text-cyber-cyan/30 font-mono">
                          {r.imdb_id ? `IMDb ${r.imdb_id}` : `TMDB #${r.tmdb_id}`}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Selected summary */}
              {selected && (
                <div className="flex items-center gap-2 px-3 py-2 border border-red-500/40 bg-red-500/5 text-xs">
                  <Check size={12} className="text-red-400 flex-shrink-0" />
                  <span className="text-cyber-cyan/70">{t('text_target_locked')}</span>
                  <span className="text-cyber-cyan font-semibold">{selected.title}</span>
                  {selected.year && <span className="text-cyber-cyan/50">({selected.year})</span>}
                  <span className="text-cyber-cyan/30 font-mono ml-auto">
                    {selected.imdb_id ? `IMDb ${selected.imdb_id}` : `TMDB #${selected.tmdb_id}`}
                  </span>
                </div>
              )}

              {/* TV-only: Season / Episode override inputs */}
              {mediaType === 'tv' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-cyber-cyan/50 uppercase tracking-wider mb-1.5">
                      {t('label_season')}
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={season}
                      onChange={e => setSeason(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
                      className="w-full bg-transparent border border-cyber-cyan/40 px-3 py-2 text-cyber-cyan text-sm
                                 outline-none focus:border-cyber-cyan placeholder:text-cyber-cyan/25"
                      placeholder="1"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cyber-cyan/50 uppercase tracking-wider mb-1.5">
                      {t('label_episode')} <span className="text-cyber-cyan/30">{t('text_optional')}</span>
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={episode}
                      onChange={e => setEpisode(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
                      className="w-full bg-transparent border border-cyber-cyan/40 px-3 py-2 text-cyber-cyan text-sm
                                 outline-none focus:border-cyber-cyan placeholder:text-cyber-cyan/25"
                      placeholder={t('text_optional')}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="px-5 py-4 border-t border-cyber-cyan/20 flex justify-center">
          {isNfo ? (
            <button
              onClick={handleNuclearExecute}
              disabled={!selected || executing}
              className={cn(
                'w-full py-3 font-bold text-sm uppercase tracking-widest transition-all flex items-center justify-center gap-2 border',
                selected && !executing
                  ? 'bg-red-500 text-white border-red-400 hover:bg-red-400'
                  : 'bg-red-500/20 text-red-400/40 border-red-500/20 cursor-not-allowed'
              )}
              style={selected && !executing ? { boxShadow: '0 0 24px rgba(239,68,68,0.45)' } : {}}
            >
              {executing
                ? <><Loader2 size={15} className="animate-spin" /> {t('text_executing')}</>
                : <><Zap size={15} /> {selected ? t('btn_nuclear_rebuild') : t('text_select_target_first')}</>
              }
            </button>
          ) : (
            <div className="flex gap-3 w-full">
              <button
                onClick={onClose}
                className="flex-1 py-2 border border-cyber-cyan/30 text-cyber-cyan/60
                           hover:border-cyber-cyan/60 text-sm uppercase tracking-wider transition-all"
              >
                {t('btn_cancel')}
              </button>
              <button
                onClick={() => { onConfirm({ media_type: mediaType, nuclear_reset: false }); onClose(); }}
                className="flex-1 py-2 font-bold text-sm uppercase tracking-wider
                           bg-cyber-cyan text-black hover:bg-cyber-cyan/80 border border-cyber-cyan transition-all"
                style={{ boxShadow: '0 0 20px rgba(0,230,246,0.35)' }}
              >
                {t('btn_confirm_execute')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
