/**
 * ============================================================================
 * PathsSettings - 路径管理配置组件
 * ============================================================================
 * 
 * [组件职责]
 * 管理媒体库扫描路径配置，包括下载源（PT 客户端目录）和媒体库（Jellyfin/Plex 目录）
 * 
 * [布局架构]
 * 
 * 1. 已配置路径列表 (Grid 5列布局)
 *    ┌─────────┬─────────┬──────────┬─────────┬─────────┐
 *    │ 开关区  │ 类型区  │  路径区  │ 分类区  │ 操作区  │
 *    │ 160px   │ 120px   │   1fr    │ 120px   │ 100px   │
 *    └─────────┴─────────┴──────────┴─────────┴─────────┘
 *    - 开关区: NeuralCoreSwitch (在线/离线 + DOWNLOAD/LIBRARY 状态文字)
 *    - 类型区: 下拉选择器 (下载源/媒体库)
 *    - 路径区: 文本输入框 (弹性布局，自动填充剩余空间)
 *    - 分类区: 下拉选择器 (Movie/TV/Mixed)
 *    - 操作区: 删除按钮 (红色警示风格)
 *    - 列间距: 24px (gap-6)
 *    - 容器最小宽度: 900px (防止窗口过小时挤压变形)
 * 
 * 2. 添加新路径表单 (Grid 4列布局)
 *    ┌─────────┬─────────┬──────────┬─────────┐
 *    │ 类型区  │ 分类区  │  路径区  │ 按钮区  │
 *    │ 200px   │ 200px   │   1fr    │  auto   │
 *    └─────────┴─────────┴──────────┴─────────┘
 *    - 类型区/分类区: 200px 固定宽度，比上方更宽敞
 *    - 路径区: 弹性布局
 *    - 按钮区: 自适应宽度
 *    - 列间距: 24px (与上方保持一致)
 * 
 * [响应式设计]
 * - 移动端 (< lg): 单列垂直堆叠 (grid-cols-1)
 * - 桌面端 (≥ lg): 多列横向布局 (grid-cols-[...])
 * 
 * [赛博视觉元素]
 * - 删除按钮: 红色边框 + 红色发光 (rgba(255, 0, 60, 0.3))
 * - 添加按钮: 青色边框 + 双层发光 (外层 + 内层 inset)
 * - 禁用路径: 灰度滤镜 + 60% 透明度
 * 
 * ============================================================================
 */
'use client';
import { useState } from 'react';
import { FolderOpen } from 'lucide-react';
import type { I18nKey } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { useSettings } from '@/hooks/useSettings';
import { NeuralCoreSwitch, NeuralInput, NeuralSection, NeuralSelect } from './NeuralPrimitives';

interface Props {
  t: (key: I18nKey) => string;
}

export default function PathsSettings({ t }: Props) {
  const { config, setConfig } = useSettings();
  const [newPath, setNewPath] = useState('');
  const [newType, setNewType] = useState('download');
  const [newCategory, setNewCategory] = useState('mixed');

  if (!config) return null;

  const updatePathDetail = (index: number, field: string, value: unknown) => {
    const updatedPaths = [...config.paths];
    updatedPaths[index] = { ...updatedPaths[index], [field]: value };
    setConfig({ ...config, paths: updatedPaths });
  };

  const addPath = () => {
    if (newPath && !config.paths.some(p => p.path === newPath)) {
      const maxId = config.paths.reduce((max, p) => Math.max(max, p.id || 0), 0);
      setConfig({ ...config, paths: [...config.paths, { id: maxId + 1, type: newType, path: newPath, category: newCategory, enabled: true }] });
      setNewPath('');
    }
  };

  const removePath = (pathToRemove: string) => {
    setConfig({ ...config, paths: config.paths.filter(p => p.path !== pathToRemove) });
  };

  const togglePathEnabled = (index: number) => {
    const updatedPaths = [...config.paths];
    updatedPaths[index].enabled = !updatedPaths[index].enabled;
    setConfig({ ...config, paths: updatedPaths });
  };

  return (
    <div className="space-y-6"> {/* 主容器：垂直间距 24px */}
      {/* 约束提示区域 */}
      <NeuralSection title={t('paths_constraint')}>
        <p className="text-cyber-cyan/70 text-sm">{t('paths_storage_tip')}</p>
      </NeuralSection>
      
      {/* 已配置路径列表区域 */}
      <div>
        <h3 className="text-cyber-cyan/80 font-semibold uppercase tracking-widest mb-4">
          {t('paths_scan_paths')}
        </h3>
        <div className="space-y-4"> {/* 路径卡片间距 16px */}
          {config.paths.map((pathItem, index) => (
            <NeuralSection 
              key={index} 
              title={`PATH_${String(pathItem.id ?? index).padStart(2, '0')}`} 
              className={cn(!pathItem.enabled && 'opacity-60 grayscale')} 
            >
              {/* 
                ═══════════════════════════════════════════════════════════════
                已配置路径 Grid 布局 (5列)
                ═══════════════════════════════════════════════════════════════
                列1 (160px): 开关组件
                  - 显示在线/离线状态
                  - 显示 DOWNLOAD/LIBRARY 类型文字
                  - 固定宽度确保文字不换行
                
                列2 (120px): 类型选择器
                  - 下载源 (download)
                  - 媒体库 (library)
                
                列3 (1fr): 路径输入框
                  - 弹性布局，占用所有剩余空间
                  - 最小宽度由容器 min-w-[900px] 保证
                
                列4 (120px): 分类选择器
                  - Movie (电影)
                  - TV (剧集)
                  - Mixed (混合，仅下载源可用)
                
                列5 (100px): 删除按钮
                  - 红色警示风格
                  - 固定宽度防止文字挤压
                
                gap-6: 列间距 24px
                min-w-[900px]: 容器最小宽度，防止窗口缩小时挤压变形
                items-end: 所有列底部对齐
                ═══════════════════════════════════════════════════════════════
              */}
              <div className="grid grid-cols-1 lg:grid-cols-[160px,120px,1fr,120px,100px] gap-6 items-end min-w-[900px]">
                {/* 列1: 开关组件 (160px) */}
                <NeuralCoreSwitch 
                  active={!!pathItem.enabled} 
                  onToggle={() => togglePathEnabled(index)} 
                  size={72} 
                  label={pathItem.enabled ? t('basic_online') : t('basic_offline')} 
                  statusText={pathItem.type.toUpperCase()} 
                />
                
                {/* 列2: 类型选择器 (120px) */}
                <NeuralSelect 
                  label={t('paths_type_label')} 
                  value={pathItem.type} 
                  onChange={(e) => updatePathDetail(index, 'type', e.target.value)}
                >
                  <option value="download">{t('paths_type_discovery')}</option>
                  <option value="library">{t('paths_type_storage')}</option>
                </NeuralSelect>
                
                {/* 列3: 路径输入框 (1fr - 弹性) */}
                <NeuralInput 
                  label={t('paths_path_label')} 
                  type="text" 
                  value={pathItem.path} 
                  onChange={(e) => updatePathDetail(index, 'path', e.target.value)} 
                />
                
                {/* 列4: 分类选择器 (120px) */}
                <NeuralSelect 
                  label={t('paths_category_label')} 
                  value={pathItem.category || 'movie'} 
                  onChange={(e) => updatePathDetail(index, 'category', e.target.value)}
                >
                  <option value="movie">{t('paths_cat_movie')}</option>
                  <option value="tv">{t('paths_cat_tv')}</option>
                  {pathItem.type !== 'library' && <option value="mixed">{t('paths_cat_mixed')}</option>}
                </NeuralSelect>
                
                {/* 列5: 删除按钮 (100px) - 红色警示风格 */}
                <button 
                  type="button" 
                  onClick={() => removePath(pathItem.path)} 
                  className="px-4 py-3 bg-transparent border border-cyber-red/40 text-cyber-red/80 hover:text-white hover:bg-cyber-red hover:border-cyber-red transition-all whitespace-nowrap" 
                  style={{ 
                    boxShadow: '0 0 18px rgba(255, 0, 60, 0.3)' // 红色发光：18px 扩散半径，30% 透明度
                  }}
                >
                  <span className="inline-flex items-center gap-2">
                    <FolderOpen size={18} />
                    {t('paths_delete_btn')}
                  </span>
                </button>
              </div>
            </NeuralSection>
          ))}
        </div>
      </div>
      
      {/* 添加新路径表单区域 */}
      <NeuralSection title={t('paths_add_new')}>
        {/* 
          ═══════════════════════════════════════════════════════════════
          添加新路径 Grid 布局 (4列)
          ═══════════════════════════════════════════════════════════════
          列1 (200px): 类型选择器
            - 下载源 (download)
            - 媒体库 (library)
            - 比上方已配置路径更宽 (200px vs 120px)，视觉更舒适
          
          列2 (200px): 分类选择器
            - Movie (电影)
            - TV (剧集)
            - Mixed (混合，仅下载源可用)
            - 与类型选择器等宽，保持视觉对称
          
          列3 (1fr): 路径输入框
            - 弹性布局，占用所有剩余空间
            - 用户输入新路径的主要区域
          
          列4 (auto): 添加按钮
            - 自适应宽度，根据按钮文字自动调整
            - 青色霓虹风格，双层发光效果
          
          gap-6: 列间距 24px (与上方已配置路径保持一致)
          items-end: 所有列底部对齐
          
          响应式：
          - 移动端 (< lg): grid-cols-1 单列垂直堆叠
          - 桌面端 (≥ lg): grid-cols-[200px,200px,1fr,auto] 四列横向布局
          ═══════════════════════════════════════════════════════════════
        */}
        <div className="grid grid-cols-1 lg:grid-cols-[200px,200px,1fr,auto] gap-6 items-end">
          {/* 列1: 类型选择器 (200px) */}
          <NeuralSelect 
            value={newType} 
            onChange={(e) => setNewType(e.target.value)} 
            label={t('paths_type_label')}
          >
            <option value="download">{t('paths_type_discovery')}</option>
            <option value="library">{t('paths_type_storage')}</option>
          </NeuralSelect>
          
          {/* 列2: 分类选择器 (200px) */}
          <NeuralSelect 
            value={newCategory} 
            onChange={(e) => setNewCategory(e.target.value)} 
            label={t('paths_category_label')}
          >
            <option value="movie">{t('paths_cat_movie')}</option>
            <option value="tv">{t('paths_cat_tv')}</option>
            {newType !== 'library' && <option value="mixed">{t('paths_cat_mixed')}</option>}
          </NeuralSelect>
          
          {/* 列3: 路径输入框 (1fr - 弹性) */}
          <NeuralInput 
            type="text" 
            value={newPath} 
            onChange={(e) => setNewPath(e.target.value)} 
            placeholder={t('paths_placeholder')} 
            label={t('paths_path_label')} 
          />
          
          {/* 列4: 添加按钮 (auto - 自适应) - 青色霓虹风格 */}
          <button 
            type="button" 
            onClick={addPath} 
            className="px-6 py-3 bg-transparent border-2 border-cyber-cyan text-cyber-cyan font-bold uppercase tracking-widest hover:bg-cyber-cyan hover:text-black transition-all" 
            style={{ 
              boxShadow: '0 0 20px rgba(0, 230, 246, 0.35), inset 0 0 20px rgba(0, 230, 246, 0.08)' 
              // 双层发光效果：
              // - 外层：20px 扩散半径，35% 透明度（环境光晕）
              // - 内层 (inset)：20px 扩散半径，8% 透明度（内部微光）
            }}
          >
            {t('paths_add_btn')}
          </button>
        </div>
      </NeuralSection>
    </div>
  );
}
