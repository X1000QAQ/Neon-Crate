'use client';

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { api } from '@/lib/api';
import type { Task } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';
import MediaPagination from './MediaPagination';
import MediaTable from './MediaTable';
import MediaToolbar from './MediaToolbar';
const PAGE_SIZE = 20;

export default function MediaWall() {
  const { t } = useLanguage();
  // React Hooks 死循环止血点：useLanguage 每次渲染都会返回新引用的 `t` 函数，
  // 若把 `t` 放入 loadTasks 的依赖数组，会导致 loadTasks 身份每渲染变化 -> useEffect 重复发包。
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  }, [t]);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [scraping, setScraping] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [findingSubs, setFindingSubs] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [purgeModalOpen, setPurgeModalOpen] = useState(false);
  const [purgeConfirmText, setPurgeConfirmText] = useState('');
  const [purging, setPurging] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [batchDeleteModalOpen, setBatchDeleteModalOpen] = useState(false);
  const [batchDeleting, setBatchDeleting] = useState(false);

  // 交互契约：Toast 采用单次计时器串行复位，避免并发提示导致可见时长坍缩
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 并发控制：列表拉取使用 AbortController，新请求签发时废止前一飞行实例，保证状态与最新筛选一致
  const loadAbortRef = useRef<AbortController | null>(null);

  // 生命周期：卸载时释放计时器与中止未决请求，杜绝悬挂异步回写
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      loadAbortRef.current?.abort();
    };
  }, []);

  // 依赖次序：showToast 先于 loadTasks 声明，闭包内引用稳定
  const showToast = useCallback((msg: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast(msg);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  }, []);

  // 语义路由：后端 message 已为 i18n 键或直出句；键命中则翻译，否则原样透出（兼容过渡期混排）
  const resolveMessageKey = useCallback((raw?: string | null) => {
    if (!raw) return t('msg_rebuild_complete_default');
    const translated = (t as (key: string) => string)(raw);
    return translated !== raw ? translated : raw;
  }, [t]);

  const loadTasks = useCallback(async () => {
    // 1. [请求废止] -> 2. [签发新 Controller] -> 3. [后续分支以 signal 判定是否丢弃过期回包]
    loadAbortRef.current?.abort();
    loadAbortRef.current = new AbortController();
    const signal = loadAbortRef.current.signal;

    setLoading(true);
    try {
      const params: { page?: number; page_size?: number; status?: string; media_type?: string; search?: string } = {
        page: 1,
        page_size: 99999,
      };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (typeFilter !== 'all') params.media_type = typeFilter;
      if (debouncedKeyword.trim()) params.search = debouncedKeyword.trim();

      const data = await api.getTasks(params);
      if (signal.aborted) return;
      setTasks(data.tasks);
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') return;
      const err = error as Error & { status?: number; body?: unknown };
      showToast(
        tRef.current('error_load_tasks').replace(
          '{detail}',
          err?.message?.trim() ? err.message : tRef.current('error_network_generic'),
        ),
      );
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [statusFilter, typeFilter, debouncedKeyword, showToast]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedKeyword(searchKeyword), 500);
    return () => clearTimeout(timer);
  }, [searchKeyword]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // 1. [筛选语义变更] -> 2. [作品聚合集合重置] -> 3. [页码强制归一，消除「新条件下仍停留在旧页码」的索引空洞]
  useEffect(() => {
    setPage(1);
  }, [statusFilter, typeFilter, debouncedKeyword]);

  // 物理视图：页码递增后滚动复位，保证列表首屏可见
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [page]);

  // 智能排序：最新 created_at 排在最上面；前端再按状态类型过滤
  const filteredTasks = useMemo(() => {
    let list = [...tasks];
    if (statusFilter !== 'all') {
      if (statusFilter === 'failed') {
        list = list.filter((x) => (x.status || '').toLowerCase() === 'failed');
      } else {
        list = list.filter((x) => (x.status || '').toLowerCase() === statusFilter.toLowerCase());
      }
    }
    if (typeFilter !== 'all') list = list.filter((x) => x.media_type === typeFilter);
    list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return list;
  }, [tasks, statusFilter, typeFilter]);

  // 将任务按「作品（电影/剧集根）」进行前置聚合，解决剧集被分页截断的问题
  const groupedWorks = useMemo(() => {
    const map = new Map<string, Task[]>();
    for (const task of filteredTasks) {
      const mtype = task.media_type || 'movie';
      const key = `${mtype}::${(task.title || task.clean_name || task.file_name || String(task.id)).trim()}`;
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key)!.push(task);
    }
    // map 会自然保持首次插入的顺序（即组内最新 created_at 的任务顺序）
    return Array.from(map.values());
  }, [filteredTasks]);

  const totalWorks = groupedWorks.length;

  const paginatedTasks = useMemo(() => {
    // 对「作品实体」进行分页，每页严格显示 PAGE_SIZE 个电影或剧集
    const pageGroups = groupedWorks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    // 展平为 Task[] 传给底层的 MediaTable，确保单个剧集的所有分集被完整传入
    return pageGroups.flat();
  }, [groupedWorks, page]);

  const handleRetry = useCallback(async (taskId: number) => {
    try {
      await api.retryTask(taskId);
      showToast(t('msg_task_unlocked_rescan'));
      loadTasks();
    } catch (error) {
      console.error('Failed to unlock task:', error);
      showToast(t('msg_unlock_failed'));
    }
  }, [loadTasks, showToast, t]);

  const handleDelete = useCallback(async (taskId: number) => {
    if (!confirm(t('confirm_delete_task'))) return;
    try {
      await api.deleteTask(taskId);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
      await loadTasks();
      showToast(t('delete_record_success'));
    } catch (error) {
      console.error('Failed to delete task:', error);
      showToast(t('task_delete') + t('op_failed'));
    }
  }, [loadTasks, showToast, t]);

  const handleDeleteBatch = useCallback(async (ids: number[]) => {
    if (ids.length === 0) return;
    if (!confirm(t('confirm_delete_batch_with_episodes').replace('{count}', String(ids.length)))) return;
    try {
      await api.deleteBatchTasks(ids);
      await loadTasks();
      showToast(t('delete_batch_records_success').replace('{count}', String(ids.length)));
    } catch (error) {
      console.error('Batch delete failed:', error);
      showToast(t('msg_batch_delete_failed'));
    }
  }, [loadTasks, showToast, t]);

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAllCurrentPage = useCallback(() => {
    const ids = new Set(paginatedTasks.map((x) => x.id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  }, [paginatedTasks]);

  const invertSelectionCurrentPage = useCallback(() => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      paginatedTasks.forEach((task) => {
        if (next.has(task.id)) next.delete(task.id);
        else next.add(task.id);
      });
      return next;
    });
  }, [paginatedTasks]);

  const isAllCurrentPageSelected = paginatedTasks.length > 0 && paginatedTasks.every((t) => selectedIds.has(t.id));
  const isSomeCurrentPageSelected = paginatedTasks.some((t) => selectedIds.has(t.id));

  const handleBatchDelete = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setBatchDeleting(true);
    try {
      await api.deleteBatchTasks(ids);
      setSelectedIds(new Set());
      setBatchDeleteModalOpen(false);
      await loadTasks();
      showToast(t('delete_record_success') + ` (${ids.length})`);
    } catch (error) {
      console.error('Batch delete failed:', error);
      showToast(t('task_delete') + t('op_failed'));
    } finally {
      setBatchDeleting(false);
    }
  }, [selectedIds, loadTasks, showToast, t]);

  const openBatchDeleteConfirm = () => {
    if (selectedIds.size === 0) return;
    setBatchDeleteModalOpen(true);
  };

  const handlePurge = async () => {
    if (purgeConfirmText.trim().toUpperCase() !== 'CONFIRM') return;
    setPurging(true);
    try {
      const res = await api.purgeAllTasks();
      setPurgeModalOpen(false);
      setPurgeConfirmText('');
      setSelectedIds(new Set());
      await loadTasks();
      showToast(t('purge_success') + ` (${res.deleted})`);
    } catch (error) {
      console.error('Failed to purge:', error);
      showToast(t('op_reset_failed'));
    } finally {
      setPurging(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      await api.triggerScan();
      showToast(t('ai_scan_triggered'));
      setTimeout(() => {
        loadTasks();
        setScanning(false);
      }, 2000);
    } catch (error) {
      showToast(t('scan_trigger_failed'));
      setScanning(false);
    }
  };

  const handleScrapeAll = async () => {
    setScraping(true);
    try {
      await api.triggerScrapeAll();
      setTimeout(() => { loadTasks().catch(() => showToast(t('msg_refresh_list_after_scrape_failed'))); }, 1000);
    } catch (error) {
      showToast(t('msg_scrape_trigger_failed'));
    } finally {
      setScraping(false);
    }
  };

  const handleFindSubtitles = async () => {
    setFindingSubs(true);
    try {
      await api.triggerFindSubtitles();
      setTimeout(() => { loadTasks().catch(() => showToast(t('msg_refresh_list_after_subtitle_failed'))); }, 1000);
    } catch (error) {
      showToast(t('msg_subtitle_task_trigger_failed'));
    } finally {
      setFindingSubs(false);
    }
  };

  const handleRebuild = useCallback(async (params: {
    task_id: number;
    is_archive: boolean;
    media_type: string;
    refix_nfo: boolean;
    refix_poster: boolean;
    refix_subtitle: boolean;
    keyword_hint?: string;
    tmdb_id?: number;
    nuclear_reset?: boolean;
    season?: number;
    episode?: number;
    scope?: 'series' | 'season' | 'episode';
  }) => {
    try {
      const res = await api.rebuildTask(params);
      showToast(resolveMessageKey(res.message));
      // 立即刷新一次，同步后端同步写入的字段（nfo/poster）
      await loadTasks();
      // 字幕任务走后台异步链路（OpenSubtitles API 约 4-6 秒），指数退避轮询
      // 轮询计划：3s → 再等 3s → 再等 4s，最多 3 次，检测到终态即停止
      if (params.refix_subtitle) {
        const terminalStates = new Set(['scraped', 'success', 'failed', 'missing']);
        // 时序策略：三档间隔累计覆盖异步字幕链路典型耗时窗口
        const intervals = [3000, 3000, 4000];
        // 类型契约：task_id 规范为 number，与快照列表中的 id 严格相等匹配
        const taskId = Number(params.task_id);
        for (const ms of intervals) {
          await new Promise<void>(resolve => setTimeout(resolve, ms));
          await loadTasks();
          try {
            // 观测：全量拉取任务快照以读取目标 sub_status；与列表刷新解耦，专用于终态判定
            const snapshot = await api.getTasks({ page: 1, page_size: 99999 });
            const target = snapshot.tasks.find((tk: import('@/types').Task) => Number(tk.id) === taskId);
            if (target && terminalStates.has((target.sub_status || '').toLowerCase())) break;
          } catch { /* 轮询观测失败不阻断主流程：终态可能延后由后续扫描呈现 */ }
        }
      }
    } catch (error) {
      showToast(t('msg_rebuild_failed_generic'));
    }
  }, [loadTasks, resolveMessageKey, showToast, t]);

  return (
    <div className="w-full h-full flex flex-col">
      <div className="space-y-6 flex-1">
          <MediaToolbar 
            searchKeyword={searchKeyword}
            onSearchChange={setSearchKeyword}
            onRefresh={loadTasks}
            loading={loading}
            selectedCount={selectedIds.size}
            onBatchDelete={openBatchDeleteConfirm}
            onPurge={() => setPurgeModalOpen(true)}

            onScan={handleScan}
            scanning={scanning}
            onScrapeAll={handleScrapeAll}
            scraping={scraping}
            onFindSubtitles={handleFindSubtitles}
            findingSubs={findingSubs}

            statusFilter={statusFilter}
            onStatusChange={setStatusFilter}
            typeFilter={typeFilter}
            onTypeChange={setTypeFilter}
          />

          {/* 工业级高密度 Table */}
          <MediaTable 
            loading={loading}
            tasks={paginatedTasks}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelect}
            onSelectAll={selectAllCurrentPage}
            onInvertSelection={invertSelectionCurrentPage}
            isAllSelected={isAllCurrentPageSelected}
            isSomeSelected={isSomeCurrentPageSelected}
            onRetry={handleRetry}
            onDelete={handleDelete}
            onDeleteBatch={handleDeleteBatch}
            onRebuild={handleRebuild}
          />

          {/* 批量删除二次确认弹窗 */}
          {batchDeleteModalOpen && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60"
              onClick={() => !batchDeleting && setBatchDeleteModalOpen(false)}
            >
              <div className="bg-black border-2 border-cyber-cyan/40 p-6 max-w-md w-full shadow-xl" onClick={(e) => e.stopPropagation()}>
                <h3 className="text-lg font-bold text-white mb-2">{t('batch_delete_btn')}</h3>
                <p className="text-white/60 text-sm mb-4">
                  {t('confirm_batch_delete').replace('{count}', String(selectedIds.size))}
                </p>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setBatchDeleteModalOpen(false)}
                    disabled={batchDeleting}
                    className="px-4 py-2 rounded-lg bg-black border border-cyber-cyan text-white hover:bg-cyber-cyan/10 transition-colors disabled:opacity-50"
                  >
                    {t('btn_cancel')}
                  </button>
                  <button
                    onClick={handleBatchDelete}
                    disabled={batchDeleting}
                    className="px-4 py-2 rounded-lg bg-cyber-red text-white hover:brightness-110 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {batchDeleting ? t('op_deleting') : t('task_delete_record')}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 重置数据库双重确认弹窗 */}
          {purgeModalOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" onClick={() => !purging && setPurgeModalOpen(false)}>
              <div className="bg-black border-2 border-cyber-red/60 p-6 max-w-md w-full shadow-xl" onClick={(e) => e.stopPropagation()}>
                <h3 className="text-lg font-bold text-white mb-2">{t('confirm_purge_all')}</h3>
                <p className="text-white/60 text-sm mb-4">{t('confirm_purge_type_confirm')}</p>
                <input
                  type="text"
                  value={purgeConfirmText}
                  onChange={(e) => setPurgeConfirmText(e.target.value)}
                  placeholder="CONFIRM"
                  className="w-full px-4 py-2 bg-black border border-cyber-red rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyber-red mb-4"
                />
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => { setPurgeModalOpen(false); setPurgeConfirmText(''); }}
                    disabled={purging}
                    className="px-4 py-2 rounded-lg bg-black border border-cyber-cyan text-white hover:bg-cyber-cyan/10 transition-colors disabled:opacity-50"
                  >
                    {t('btn_cancel')}
                  </button>
                  <button
                    onClick={handlePurge}
                    disabled={purging || purgeConfirmText.trim().toUpperCase() !== 'CONFIRM'}
                    className="px-4 py-2 rounded-lg bg-cyber-red text-white hover:brightness-110 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {purging ? t('btn_purging') : t('btn_confirm_purge')}
                  </button>
                </div>
              </div>
            </div>
          )}

          {toast && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-cyber-cyan text-black font-medium shadow-lg animate-slide-up">
              {toast}
            </div>
          )}

          {/* 分页：按作品实体（Works）分页，每页严格显示 PAGE_SIZE 个电影或剧集 */}
          <MediaPagination
            currentPage={page}
            totalPages={Math.ceil(totalWorks / PAGE_SIZE)}
            totalItems={totalWorks}
            onPageChange={setPage}
          />
        </div>
    </div>
  );
}
