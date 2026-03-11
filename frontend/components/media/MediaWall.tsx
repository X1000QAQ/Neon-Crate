'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
import type { Task } from '@/types';
import { useLanguage } from '@/hooks/useLanguage';
import MediaPagination from './MediaPagination';
import MediaTable from './MediaTable';
import MediaToolbar from './MediaToolbar';
const PAGE_SIZE = 20;

export default function MediaWall() {
  const { t } = useLanguage();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
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

  const loadTasks = useCallback(async () => {
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
      
      // 前端数据解析双保险：强制修复后端可能的键名不一致
      const normalizedTasks = data.tasks.map(t => ({
        ...t,
        // 无论后端传的是 type 还是 media_type，都强行统一为 media_type
        media_type: t.media_type || (t as any).type || 'movie'
      }));
      
      setTasks(normalizedTasks);
      setTotal(data.total);
    } catch (error) {
      const err = error as Error & { status?: number; body?: unknown };
      console.error('[MediaWall] loadTasks 失败:', err?.message, 'status:', err?.status, 'body:', err?.body ?? error);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter, debouncedKeyword]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedKeyword(searchKeyword), 500);
    return () => clearTimeout(timer);
  }, [searchKeyword]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // 分页变更时自动回到顶部，避免页面停留在底部影响浏览体验
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [page]);

  // 智能排序：最新 created_at 排在最上面；前端再按状态类型过滤
  const filteredTasks = useMemo(() => {
    let list = [...tasks];
    if (statusFilter !== 'all') {
      if (statusFilter === 'failed') {
        list = list.filter((x) => {
          const s = (x.status || '').toLowerCase();
          return s === 'failed' || s === 'match failed';
        });
      } else {
        list = list.filter((x) => (x.status || '').toLowerCase() === statusFilter.toLowerCase());
      }
    }
    if (typeFilter !== 'all') list = list.filter((x) => x.media_type === typeFilter);
    list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return list;
  }, [tasks, statusFilter, typeFilter]);

  const totalFiltered = filteredTasks.length;
  const paginatedTasks = useMemo(
    () => filteredTasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredTasks, page]
  );

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleRetry = async (taskId: number) => {
    try {
      await api.retryTask(taskId);
      loadTasks();
    } catch (error) {
      console.error('Failed to retry task:', error);
    }
  };

  const handleDelete = async (taskId: number) => {
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
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllCurrentPage = () => {
    const ids = new Set(paginatedTasks.map((x) => x.id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  };

  const invertSelectionCurrentPage = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      paginatedTasks.forEach((t) => {
        if (next.has(t.id)) next.delete(t.id);
        else next.add(t.id);
      });
      return next;
    });
  };

  const isAllCurrentPageSelected = paginatedTasks.length > 0 && paginatedTasks.every((t) => selectedIds.has(t.id));
  const isSomeCurrentPageSelected = paginatedTasks.some((t) => selectedIds.has(t.id));

  const handleBatchDelete = async () => {
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
  };

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
      console.error('Failed to trigger scan:', error);
      setScanning(false);
    }
  };

  const handleScrapeAll = async () => {
    setScraping(true);
    try {
      await api.triggerScrapeAll();
      setTimeout(() => { loadTasks().catch(console.error); }, 1000);
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
      setTimeout(() => { loadTasks().catch(console.error); }, 1000);
    } catch (error) {
      console.error('Failed to trigger find subtitles:', error);
    } finally {
      setFindingSubs(false);
    }
  };

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

          {/* 分页：按过滤后总数分页 */}
          <MediaPagination
            currentPage={page}
            totalPages={Math.ceil(totalFiltered / PAGE_SIZE)}
            totalItems={totalFiltered}
            onPageChange={setPage}
          />
        </div>
    </div>
  );
}
