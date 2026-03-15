/**
 * ============================================================================
 * MediaTable - 媒体任务卡片列表组件
 * ============================================================================
 * 
 * [组件职责]
 * - 以卡片形式渲染任务列表（含海报、标题、状态、路径、操作按钮）
 * - 支持批量选择（全选 / 反选）及单条选择
 * - 对 ignored 状态任务渲染 VHS 磁带损坏特效（7 层叠加）
 * - 渲染流水线进度条（pending 30% → archived 60% → 字幕完成 100%）
 *
 * [布局架构]
 * 
 * 1. 批量操作工具栏
 *    ┌────────────────────────────────────────────────┐
 *    │ [✓] 全选本页 | 反选本页                        │
 *    └────────────────────────────────────────────────┘
 *    - 固定在列表顶部
 *    - 毛玻璃效果: blur(15px)
 *    - 底部边框: border-cyber-cyan/50
 * 
 * 2. 任务卡片 (Flex 横向布局)
 *    ┌──┬────────┬──────────────────────────────────────┬────────┬────────┐
 *    │☐ │ 海报区 │         任务信息区                   │ 时间戳 │ 操作区 │
 *    │  │ 64x96  │ 标题+文件名+路径+状态标签+外部链接   │        │ 按钮组 │
 *    └──┴────────┴──────────────────────────────────────┴────────┴────────┘
 *    
 *    海报区 (64x96px):
 *    - 固定宽度: w-16 h-24
 *    - VHS 特效层级 (仅 ignored 状态):
 *      1. 灰度滤镜 (CSS filter)
 *      2. 噪点纹理 (SVG, z-10)
 *      3. 扫描线 (z-15)
 *      4. 磁带拉伸 (z-20)
 *      5. 色彩分离 (z-25)
 *      6. 错误印章 (z-30)
 *      7. 时间码 (z-35)
 *    
 *    任务信息区 (flex-1):
 *    - 标题: text-base font-semibold (黄色发光)
 *    - 文件名: text-xs (青色半透明)
 *    - 路径: text-xs (原始路径 + 入库路径)
 *    - 状态标签: 横向排列 (主状态 + 字幕状态)
 *    - 外部链接: TMDB + IMDb 按钮
 *    
 *    操作区 (flex-shrink-0):
 *    - 重试按钮 (仅失败任务显示)
 *    - 删除按钮 (红色警示风格)
 * 
 * 3. 流水线进度条
 *    ┌────────────────────────────────────────────────┐
 *    │ ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
 *    └────────────────────────────────────────────────┘
 *    - 高度: h-1
 *    - 位置: 卡片底部 (mt-2)
 *    - 进度: 30% (pending) → 60% (archived) → 100% (字幕完成)
 *    - 颜色: 青色渐变 (未完成) / 青绿渐变 (已完成)
 * 
 * [赛博视觉元素]
 * 
 * 卡片发光效果:
 * - 毛玻璃: blur(25px)
 * - 外层光晕: 0 0 40px rgba(6,182,212,0.2)
 * - Hover: 边框全亮 + 背景5%填充
 * 
 * VHS 磁带损坏特效 (ignored 状态):
 * - 7层叠加效果，z-index 从 10 到 35
 * - 灰度 + 对比度 + 棕褐色滤镜
 * - 噪点 + 扫描线 + 色彩分离
 * - TAPE ERROR 印章 + REC 时间码
 * 
 * [性能优化]
 * - 卡片入场动画延迟: idx * 0.1s (交错显示)
 * - 海报懒加载: SecureImage 组件处理
 * 
 * [架构说明]
 * 纯展示层组件，无内部状态，所有数据和回调由父组件 page.tsx 注入
 * 
 * ============================================================================
 */
'use client';

import { useState, memo } from 'react';
import { Film, Tv, RefreshCw, Trash2, AlertCircle } from 'lucide-react';

/**
 * 根据任务主状态和字幕子状态计算流水线进度百分比
 *
 * 进度三段式定义：
 * - 30%  → pending：文件已扫描入库，等待刮削
 * - 60%  → archived（无字幕）：元数据已刮削，等待字幕
 * - 100% → archived + sub_status 完成：全流程完成
 * - 0%   → failed / ignored：不展示进度条
 *
 * 注意：scraped 是历史遗留状态值，等同于 archived，兼容保留
 */
function getProgress(status: string, subStatus?: string | null): number {
  const s = (status || '').toLowerCase();
  const ss = (subStatus || '').toLowerCase();
  if (s === 'pending') return 30;
  if (s === 'archived' || s === 'scraped') {
    if (ss === 'scraped' || ss === 'found') return 100;
    return 60;
  }
  return 0;
}
import SecureImage from '@/components/common/SecureImage';
import type { Task } from '@/types';
import { cn, formatDate } from '@/lib/utils';
import { useLanguage } from '@/hooks/useLanguage';

interface MediaTableProps {
  loading: boolean;           // 是否正在加载数据（显示骨架屏）
  tasks: Task[];              // 任务列表数据
  selectedIds: Set<number>;   // 已选中的任务 ID 集合
  onToggleSelect: (id: number) => void;   // 切换单条选中状态
  onSelectAll: () => void;               // 全选当前页
  onInvertSelection: () => void;          // 反选当前页
  isAllSelected: boolean;    // 当前页是否全部选中
  isSomeSelected: boolean;   // 当前页是否有部分选中（用于 indeterminate 状态）
  onRetry: (taskId: number) => void;   // 重试失败任务（重置为 pending，等待下次扫描处理）
  onDelete: (taskId: number) => void;  // 删除单条任务记录（仅数据库，不删物理文件）
}

function MediaTable({
  loading,
  tasks,
  selectedIds,
  onToggleSelect,
  onSelectAll,
  onInvertSelection,
  isAllSelected,
  isSomeSelected,
  onRetry,
  onDelete,
}: MediaTableProps) {
  const { t } = useLanguage();
  // 🚀 飞行期防护：记录正在处理中的任务 ID，防止连点重复请求
  const [processingId, setProcessingId] = useState<number | null>(null);

  /**
   * 构建海报图片 URL
   *
   * 优先级：local_poster_path（本地缓存）> poster_path（远程/相对路径）
   * - 在线 URL（http/https）：直接返回，由 SecureImage 处理跨域
   * - 本地路径：转换为后端代理地址 /api/v1/public/image?path=...
   * - 无海报：返回占位图 /placeholder-poster.jpg
   */
  const getPosterUrl = (task: Task): string => {
    const posterPath = task.local_poster_path || task.poster_path;
    if (!posterPath) return '/placeholder-poster.jpg';
    // ✅ 直接返回原始路径，由 SecureImage 统一处理 URL 构建与鉴权
    // 不在此处拼接，避免相对路径绕过 SecureImage 的绝对地址锁定逻辑
    return posterPath;
  };

  const getStatusLabel = (status: string): string => {
    const s = (status || '').toLowerCase();
    if (s === 'archived') return t('status_archived');
    if (s === 'match failed' || s === 'failed') return t('status_failed');
    if (s === 'ignored') return 'TAPE CORRUPTED';  // 📼 VHS 风格标签
    return t('status_pending');
  };

  const getSubStatusLabel = (subStatus: string | undefined | null): string => {
    const s = (subStatus ?? '').toLowerCase();
    if (s === 'scraped' || s === 'success' || s === 'found') return t('status_sub_ready');
    if (s === 'failed' || s === 'match failed' || s === 'missing') return t('status_sub_missing');
    return t('status_sub_finding');
  };

  const getStatusColor = (status: string) => {
    const s = (status || '').toLowerCase();
    if (s === 'archived') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
    if (s === 'failed' || s === 'match failed') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
    if (s === 'ignored') return 'border-orange-400 text-orange-400 bg-orange-400/10 font-mono';  // 📼 VHS 风格
    // pending/processing 属于常态流动信息，不使用黄色常亮
    return 'border-cyber-cyan/30 text-cyber-cyan/70 bg-cyber-cyan/5';
  };

  const getSubStatusColor = (subStatus: string | undefined | null) => {
    const s = (subStatus ?? '').toLowerCase();
    if (s === 'scraped' || s === 'success' || s === 'found') return 'border-cyber-cyan text-cyber-cyan bg-cyber-cyan/10';
    if (s === 'failed' || s === 'match failed' || s === 'missing') return 'border-cyber-red text-cyber-red bg-cyber-red/10';
    // finding 属于常态过程，不用黄色占据注意力
    return 'border-cyber-cyan/20 text-cyber-cyan/50 bg-cyber-cyan/5';
  };

  return (
    <>
      {loading ? (
        /* 
          加载骨架屏 (5个占位卡片)
          - 垂直间距: space-y-4 (16px)
          - 毛玻璃: blur(25px)
          - 发光: 0 0 40px rgba(6,182,212,0.15)
        */
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="relative bg-transparent border border-cyber-cyan/30 p-3 animate-pulse"
              style={{
                backdropFilter: 'blur(25px)',
                boxShadow: '0 0 40px rgba(6, 182, 212, 0.15)'
              }}
            >
              <div className="flex items-center gap-3">
                {/* 海报占位 */}
                <div className="w-16 h-24 bg-cyber-cyan/10 border border-cyber-cyan/30" />
                <div className="flex-1 space-y-2">
                  {/* 标题占位 */}
                  <div className="h-5 bg-cyber-cyan/10 rounded w-2/3" />
                  {/* 文件名占位 */}
                  <div className="h-4 bg-cyber-cyan/10 rounded w-1/2" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : tasks.length === 0 ? (
        /* 
          空状态提示卡片
          - 居中布局: text-center
          - 毛玻璃: blur(20px)
          - 双层发光: 外层40px + 内层40px
        */
        <div className="relative bg-transparent border border-cyber-cyan/50 p-12 text-center hover:border-cyber-cyan transition-all" style={{
          backdropFilter: 'blur(20px)',
          boxShadow: '0 0 40px rgba(6, 182, 212, 0.4), inset 0 0 40px rgba(6, 182, 212, 0.08)'
        }}>
          <AlertCircle className="mx-auto mb-4 text-cyber-cyan/60" size={48} />
          <p className="text-cyber-cyan text-lg font-semibold">{t('no_data')}</p>
          <p className="text-cyber-cyan/60 text-sm mt-2">{t('task_no_data_hint')}</p>
        </div>
      ) : (
        <>
          {/* 
            ═══════════════════════════════════════════════════════════════
            批量操作工具栏
            ═══════════════════════════════════════════════════════════════
            布局: Flex 横向
            - Checkbox: 全选/半选状态（indeterminate）
            - 按钮: 全选本页 | 反选本页
            
            样式:
            - 毛玻璃: blur(15px)
            - 底部边框: border-cyber-cyan/50
            - 发光: 0 0 30px rgba(6,182,212,0.2)
            - 内边距: p-2
            - 底部间距: mb-1
            ═══════════════════════════════════════════════════════════════
          */}
          <div className="relative bg-transparent border-b border-cyber-cyan/50 p-2 mb-1" style={{
            backdropFilter: 'blur(15px)',
            boxShadow: '0 0 30px rgba(6, 182, 212, 0.2)'
          }}>
            <div className="flex items-center gap-3">
              {/* 全选 Checkbox（支持 indeterminate 半选状态）*/}
              <input
                type="checkbox"
                checked={isAllSelected}
                onChange={() => (isAllSelected ? onInvertSelection() : onSelectAll())}
                ref={(el) => {
                  if (el) el.indeterminate = isSomeSelected && !isAllSelected;
                }}
                className="rounded border-cyber-cyan/40 bg-transparent text-cyber-cyan focus:ring-cyber-cyan"
              />
              <button
                type="button"
                onClick={onSelectAll}
                className="text-xs text-cyber-cyan/70 hover:text-cyber-cyan transition-colors font-semibold"
              >
                {t('select_all_page')}
              </button>
              <span className="text-cyber-cyan/30">|</span> {/* 分隔符 */}
              <button
                type="button"
                onClick={onInvertSelection}
                className="text-xs text-cyber-cyan/70 hover:text-cyber-cyan transition-colors font-semibold"
              >
                {t('invert_page')}
              </button>
            </div>
          </div>

          {/* 
            ═══════════════════════════════════════════════════════════════
            任务卡片列表
            ═══════════════════════════════════════════════════════════════
            布局: 垂直堆叠
            - 卡片间距: space-y-4 (16px)
            - 入场动画: 交错延迟 idx * 0.1s
            ═══════════════════════════════════════════════════════════════
          */}
          <div className="space-y-4">
            {tasks.map((task, idx) => {
              const rawFallbackName =
                task.file_name ||
                task.file_path?.split(/[/\\]/).pop() ||
                '-';
              const originalName = task.file_path ? task.file_path.split(/[/\\]/).pop() || rawFallbackName : rawFallbackName;
              const normalizedTitle = (task.title ?? '').trim();
              const noisePattern = /\b(4k|2160p|1080p|720p|480p|360p)\b/i;
              const hasRealTitle =
                !!normalizedTitle &&
                normalizedTitle !== rawFallbackName &&
                normalizedTitle !== originalName &&
                !noisePattern.test(normalizedTitle);

              // 构建上方展示标题：刮削名 + 年份 + 剧集季集信息
              // 构建展示标题：优先使用刮削后的 title，降级使用原始文件名
              // 有效 title 条件：非空 + 不等于文件名 + 不含分辨率噪音词（如 1080p/4K）
              // 剧集追加：S01E01 格式（season + episode 均有值）或 Season N（仅 season）
              let displayTitle: string;
              if (hasRealTitle) {
                let titleParts = normalizedTitle;
                if (task.year) titleParts += ` (${task.year})`;
                // 剧集追加季集信息
                if (task.media_type === 'tv') {
                  const season = task.season;
                  const episode = task.episode;
                  if (season != null && episode != null) {
                    titleParts += ` S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`;
                  } else if (season != null) {
                    titleParts += ` Season ${season}`;
                  }
                }
                displayTitle = titleParts;
              } else {
                displayTitle = rawFallbackName;
              }

              return (
                /* 
                  ═══════════════════════════════════════════════════════════════
                  任务卡片 Flex 布局
                  ═══════════════════════════════════════════════════════════════
                  主容器: flex items-center gap-3
                  - 列1: Checkbox (flex-shrink-0)
                  - 列2: 海报区 (w-16 h-24, 固定尺寸)
                  - 列3: 任务信息区 (flex-1, 占用剩余空间)
                  
                  任务信息区内部 Flex 布局:
                  - 标题+文件名+路径 (flex-1 min-w-0, 允许截断)
                  - 状态标签 (flex-shrink-0, 横向排列)
                  - 外部链接 (flex-shrink-0, TMDB + IMDb)
                  - 时间戳 (flex-shrink-0)
                  - 操作按钮 (flex-shrink-0, 重试 + 删除)
                  
                  视觉效果:
                  - 毛玻璃: blur(25px)
                  - 发光: 0 0 40px rgba(6,182,212,0.2)
                  - Hover: 边框全亮 + 背景5%填充
                  - 入场动画延迟: idx * 0.1s
                  ═══════════════════════════════════════════════════════════════
                */
                <div
                  key={task.id}
                  className="relative bg-transparent border border-cyber-cyan/30 p-3 hover:border-cyber-cyan hover:bg-cyber-cyan/5 transition-all group"
                  style={{
                    backdropFilter: 'blur(25px)', // 毛玻璃: 25px模糊半径
                    boxShadow: '0 0 40px rgba(6, 182, 212, 0.2)', // 外层发光: 40px扩散
                    animationDelay: `${idx * 0.1}s` // 入场动画交错延迟
                  }}
                >
                  {/* 主 Flex 容器: 横向布局，间距12px */}
                  <div className="flex items-center gap-3">
                    {/* 列1: 选择框 (固定宽度) */}
                    <div className="flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(task.id)}
                        onChange={() => onToggleSelect(task.id)}
                        className="rounded border-cyber-cyan/40 bg-transparent text-cyber-cyan focus:ring-cyber-cyan"
                      />
                    </div>

                    {/* 列2: 全息海报区 (64x96px 固定尺寸) */}
                    <div className="relative w-16 h-24 flex-shrink-0 group/poster">
                      <div className="absolute inset-0 bg-cyber-cyan/10 border border-cyber-cyan/50 overflow-hidden transition-all group-hover/poster:border-cyber-cyan group-hover/poster:shadow-[0_0_15px_rgba(6,182,212,0.4)]">
                        {task.poster_path || task.local_poster_path ? (
                          <>
                        {/*
                          📼 VHS 磁带损坏特效系统（仅 ignored 状态触发）
                          特效层级（z-index 从低到高）：
                            1. 灰度/对比度滤镜（CSS filter，基础层）
                            2. 噪点纹理（SVG feTurbulence，z-10）
                            3. 扫描线（repeating-linear-gradient，z-15）
                            4. 磁带拉伸条纹（两条 div，z-20）
                            5. 色彩分离（红蓝 mix-blend-screen，z-25）
                            6. 错误印章（TAPE ERROR 标签，z-30）
                            7. 顶部时间码（REC 00:00:00:00，z-35）
                        */}
                        {/* 📼 VHS 滤镜包装层 */}
                            <div
                              className={cn(
                                "w-full h-full",
                                task.status === 'ignored' && 'grayscale-[0.7] contrast-110 brightness-80 sepia-[.4] saturate-150 opacity-70'
                              )}
                            >
                              <SecureImage
                                src={getPosterUrl(task)}
                                alt={task.title || t('task_unknown')}
                                width={64}
                                height={96}
                                className="object-cover w-full h-full opacity-80 group-hover/poster:opacity-100 group-hover/poster:scale-110 transition-all duration-300"
                                fallback={
                                  <div className="w-full h-full flex flex-col items-center justify-center bg-black/40">
                                    {task.media_type === 'movie' ? (
                                      <Film className="text-cyber-cyan/30" size={20} />
                                    ) : (
                                      <Tv className="text-cyber-cyan/30" size={20} />
                                    )}
                                    {task.status === 'ignored' && (
                                      <span className="text-[8px] mt-1 font-mono text-cyber-cyan/40 tracking-wider">DUPLICATE</span>
                                    )}
                                  </div>
                                }
                              />
                            </div>

                            {/* 📼 VHS 噪点纹理 - 只在 ignored 状态显示 */}
                            {task.status === 'ignored' && (
                              <div
                                className="absolute inset-0 pointer-events-none z-10 opacity-30"
                                style={{
                                  backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
                                  backgroundSize: '100px 100px',
                                }}
                              />
                            )}

                            {/* 📼 VHS 扫描线（粗糙） - 只在 ignored 状态显示 */}
                            {task.status === 'ignored' && (
                              <div
                                className="absolute inset-0 pointer-events-none z-15 opacity-40"
                                style={{
                                  background:
                                    'repeating-linear-gradient(0deg, rgba(0,0,0,0.5), rgba(0,0,0,0.5) 2px, transparent 2px, transparent 5px)',
                                  backgroundSize: '100% 5px',
                                }}
                              />
                            )}

                            {/* 📼 磁带拉伸效果（横向条纹） - 只在 ignored 状态显示 */}
                            {task.status === 'ignored' && (
                              <>
                                <div
                                  className="absolute left-0 right-0 h-8 pointer-events-none z-20 opacity-60"
                                  style={{
                                    top: '30%',
                                    background:
                                      'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.1) 20%, rgba(255,255,255,0.2) 50%, rgba(255,255,255,0.1) 80%, transparent 100%)',
                                    transform: 'scaleX(1.1)',
                                  }}
                                />
                                <div
                                  className="absolute left-0 right-0 h-6 pointer-events-none z-20 opacity-40"
                                  style={{
                                    top: '60%',
                                    background:
                                      'linear-gradient(90deg, transparent 0%, rgba(0,0,0,0.3) 30%, rgba(0,0,0,0.5) 50%, rgba(0,0,0,0.3) 70%, transparent 100%)',
                                  }}
                                />
                              </>
                            )}

                            {/* 📼 VHS 色彩分离（红蓝偏移） - 只在 ignored 状态显示 */}
                            {task.status === 'ignored' && (
                              <>
                                <div
                                  className="absolute inset-0 pointer-events-none z-25 mix-blend-screen opacity-20"
                                  style={{
                                    background: 'linear-gradient(90deg, #ff0000 0%, transparent 100%)',
                                    transform: 'translateX(-2px)',
                                  }}
                                />
                                <div
                                  className="absolute inset-0 pointer-events-none z-25 mix-blend-screen opacity-20"
                                  style={{
                                    background: 'linear-gradient(90deg, transparent 0%, #0000ff 100%)',
                                    transform: 'translateX(2px)',
                                  }}
                                />
                              </>
                            )}

                            {/* 📼 VHS 时间码错误印章 - 只在 ignored 状态显示 */}
                            {task.status === 'ignored' && (
                              <div className="absolute inset-0 flex items-center justify-center z-30">
                                <div
                                  className="px-2 py-1.5 bg-orange-600/80 border-2 border-orange-400 text-white font-mono text-[10px] backdrop-blur-sm"
                                  style={{
                                    textShadow: '0 0 8px rgba(251, 146, 60, 0.8)',
                                    boxShadow: '0 0 15px rgba(251, 146, 60, 0.6)',
                                    transform: 'rotate(-8deg)',
                                  }}
                                >
                                  <div className="flex flex-col items-center gap-0.5">
                                    <span className="font-bold">TAPE ERROR</span>
                                    <span className="opacity-70">00:00:00:00</span>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* 📼 VHS 顶部时间码 - 只在 ignored 状态显示 */}
                            {task.status === 'ignored' && (
                              <div className="absolute top-0.5 left-0.5 right-0.5 z-35">
                                <div className="px-1.5 py-0.5 bg-black/70 backdrop-blur-sm text-orange-400 text-[8px] font-mono">
                                  ▶ REC 00:00:00:00 [CORRUPTED]
                                </div>
                              </div>
                            )}
                          </>
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            {task.media_type === 'movie' ? (
                              <Film className="text-cyber-cyan/40" size={20} />
                            ) : (
                              <Tv className="text-cyber-cyan/40" size={20} />
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 列3: 任务信息区 (flex-1 弹性布局，占用剩余空间) */}
                    {/* min-w-0: 允许子元素截断 */}
                    <div className="flex-1 min-w-0 flex items-center gap-4">
                      {/* 子区域1: 标题与文件名 (flex-1, 允许截断) */}
                      <div className="flex-1 min-w-0">
                        {/* 主标题: 刮削后的标题 + 年份 + 季集信息 */}
                        <h3 
                          className={cn(
                            "font-semibold text-base truncate", // truncate: 超长截断显示省略号
                            task.status === 'ignored' ? 'text-orange-400/60' : 'text-cyber-yellow'
                          )}
                          style={
                            task.status === 'ignored'
                              ? {}
                              : { textShadow: '0 0 8px rgba(249, 240, 2, 0.4)' } // 黄色发光: 8px扩散
                          }
                          title={displayTitle} // Hover 显示完整标题
                        >
                          {displayTitle}
                        </h3>
                        {/* 副标题: 原始文件名 */}
                        <p 
                          className={cn(
                            "text-xs truncate mt-0.5",
                            task.status === 'ignored' ? 'text-orange-300/40 font-mono' : 'text-cyber-cyan/50'
                          )}
                          title={originalName}
                        >
                          {originalName}
                        </p>
                        {/* 路径信息: 入库地址 + 原始地址 */}
                        {/* 垂直间距: 2px */}
                        <div className="mt-1 space-y-0.5">
                          {task.target_path && (
                            <p className="text-cyber-cyan/30 text-xs truncate" title={task.target_path}>
                              <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_dst')}:</span>
                              {task.target_path}
                            </p>
                          )}
                          <p className="text-cyber-cyan/30 text-xs truncate" title={task.file_path || ''}>
                            <span className="text-cyber-cyan/50 font-mono mr-1">{t('path_src')}:</span>
                            {task.file_path || '-'}
                          </p>
                        </div>
                      </div>

                      {/* 子区域2: 状态标签 (flex-shrink-0, 横向排列) */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {/* 主状态标签 (archived/pending/failed/ignored) */}
                        <span 
                          className={cn(
                            "px-2.5 py-1 text-xs font-semibold border transition-all",
                            getStatusColor(task.status)
                          )}
                          style={{ 
                            backdropFilter: 'blur(10px)', // 标签毛玻璃: 10px模糊
                          }}
                        >
                          {getStatusLabel(task.status)}
                        </span>
                        {/* 字幕状态标签 (ready/missing/finding) */}
                        <span 
                          className={cn(
                            "px-2.5 py-1 text-xs font-semibold border transition-all",
                            getSubStatusColor(task.sub_status)
                          )}
                          style={{ 
                            backdropFilter: 'blur(10px)',
                          }}
                        >
                          {getSubStatusLabel(task.sub_status)}
                        </span>
                      </div>

                      {/* 子区域3: 外部链接 (flex-shrink-0) */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {/* TMDB 链接按钮 */}
                        {task.tmdb_id != null && String(task.tmdb_id).trim() !== '' && (
                          <a
                            href={
                              task.media_type === 'tv'
                                ? `https://www.themoviedb.org/tv/${task.tmdb_id}`
                                : `https://www.themoviedb.org/movie/${task.tmdb_id}`
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 text-xs font-semibold bg-transparent border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all"
                            style={{ 
                              backdropFilter: 'blur(10px)',
                            }}
                          >
                            TMDB
                          </a>
                        )}
                        {/* IMDb 链接按钮 */}
                        {task.imdb_id != null && String(task.imdb_id).trim() !== '' && String(task.imdb_id).toUpperCase() !== 'N/A' && (
                          <a
                            href={`https://www.imdb.com/title/${String(task.imdb_id).startsWith('tt') ? task.imdb_id : 'tt' + task.imdb_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 text-xs font-semibold bg-transparent border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all"
                            style={{ 
                              backdropFilter: 'blur(10px)',
                            }}
                          >
                            IMDb
                          </a>
                        )}
                      </div>

                      {/* 子区域4: 时间戳 (flex-shrink-0) */}
                      <span className="text-cyber-cyan/50 text-xs flex-shrink-0">
                        {task.created_at ? formatDate(task.created_at) : t('task_just_now')}
                      </span>

                      {/* 子区域5: 操作按钮组 (flex-shrink-0) */}
                      {/* 按钮间距: 6px */}
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        {/* 重试按钮 (仅失败任务显示) */}
                        {(task.status === 'failed' || (task.status || '').toLowerCase() === 'match failed') && (
                          <button
                            onClick={async () => {
                              if (processingId !== null) return;
                              setProcessingId(task.id);
                              try { await Promise.resolve(onRetry(task.id)); }
                              finally { setProcessingId(null); }
                            }}
                            disabled={processingId === task.id}
                            className={cn(
                              "p-2 bg-transparent border border-cyber-cyan text-cyber-cyan hover:bg-cyber-cyan hover:text-black transition-all group/btn",
                              processingId === task.id && "opacity-50 cursor-not-allowed"
                            )}
                            style={{ backdropFilter: 'blur(10px)' }}
                            title="将任务状态重置为待处理，下次扫描时会重新处理"
                          >
                            <RefreshCw size={16} className={cn("transition-transform duration-500", processingId === task.id ? "animate-spin" : "group-hover/btn:rotate-180")} />
                          </button>
                        )}

                        {/* 删除按钮 (红色警示风格) */}
                        <button
                          onClick={async () => {
                            if (processingId !== null) return;
                            setProcessingId(task.id);
                            try { await Promise.resolve(onDelete(task.id)); }
                            finally { setProcessingId(null); }
                          }}
                          disabled={processingId === task.id}
                          className={cn(
                            "p-2 bg-transparent border border-cyber-red text-cyber-red hover:bg-cyber-red hover:text-white transition-all",
                            processingId === task.id && "opacity-50 cursor-not-allowed"
                          )}
                          style={{ backdropFilter: 'blur(10px)' }}
                          title={t('task_delete_record')}
                        >
                          <Trash2 size={16} className={cn(processingId === task.id && "animate-pulse")} />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* 
                    流水线进度条
                    - 位置: 卡片底部 (mt-2)
                    - 高度: h-1 (4px)
                    - 背景: cyber-cyan/10
                    - 进度条: 渐变填充 + 发光效果
                    - 进度: 30% (pending) → 60% (archived) → 100% (字幕完成)
                    - 颜色: 青色渐变 (未完成) / 青绿渐变 (已完成)
                  */}
                  {(() => {
                    const progress = getProgress(task.status, task.sub_status);
                    if (progress === 0) return null; // 失败/忽略状态不显示进度条
                    const color = progress === 100
                      ? 'from-cyber-cyan to-green-400' // 完成: 青色→绿色渐变
                      : 'from-cyber-cyan to-[rgba(0,230,246,0.5)]'; // 进行中: 青色渐变
                    return (
                      <div className="relative h-1 bg-cyber-cyan/10 border-t border-cyber-cyan/20 mt-2 overflow-hidden">
                        <div
                          className={`absolute inset-y-0 left-0 bg-gradient-to-r ${color} transition-all duration-700`} // 进度变化动画: 700ms
                          style={{
                            width: `${progress}%`,
                            boxShadow: '0 0 8px rgba(0, 230, 246, 0.8)', // 进度条发光: 8px扩散
                          }}
                        />
                      </div>
                    );
                  })()}


                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}

// 🚀 React.memo 包裹：父组件 toast/scanning 等无关状态更新时，MediaTable 不重绘
export default memo(MediaTable);
