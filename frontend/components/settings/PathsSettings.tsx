'use client';
import { useState } from 'react';
import { FolderOpen } from 'lucide-react';
import type { SettingsConfig } from '@/types';
import type { I18nKey } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { NeuralCoreSwitch, NeuralInput, NeuralSection, NeuralSelect } from './NeuralPrimitives';
interface Props {
  config: SettingsConfig;
  setConfig: (c: SettingsConfig) => void;
  t: (key: I18nKey) => string;
}
export default function PathsSettings({ config, setConfig, t }: Props) {
  const [newPath, setNewPath] = useState('');
  const [newType, setNewType] = useState('download');
  const [newCategory, setNewCategory] = useState('mixed');
  const updatePathDetail = (index: number, field: string, value: any) => {
    const updatedPaths = [...config.paths];
    updatedPaths[index] = { ...updatedPaths[index], [field]: value };
    setConfig({ ...config, paths: updatedPaths });
  };
  const addPath = () => {
    if (newPath && !config.paths.some(p => p.path === newPath)) {
      const maxId = config.paths.reduce((max, p) => Math.max(max, p.id || 0), 0);
      setConfig({
        ...config,
        paths: [...config.paths, { id: maxId + 1, type: newType, path: newPath, category: newCategory, enabled: true }]
      });
      setNewPath('');
    }
  };
  const removePath = (pathToRemove: string) => {
    setConfig({
      ...config,
      paths: config.paths.filter(p => p.path !== pathToRemove)
    });
  };
  const togglePathEnabled = (index: number) => {
    const updatedPaths = [...config.paths];
    updatedPaths[index].enabled = !updatedPaths[index].enabled;
    setConfig({ ...config, paths: updatedPaths });
  };
  return (
    <div className="space-y-6">
      <NeuralSection title={t('paths_constraint')}>
        <p className="text-cyber-cyan/70 text-sm">{t('paths_storage_tip')}</p>
      </NeuralSection>
      
      <div>
        <h3 className="text-cyber-cyan/80 font-semibold uppercase tracking-widest mb-4">
          {t('paths_scan_paths')}
        </h3>
        <div className="space-y-4">
          {config.paths.map((pathItem, index) => (
            <NeuralSection
              key={index}
              title={`PATH_${String(pathItem.id ?? index).padStart(2, '0')}`}
              className={cn(!pathItem.enabled && 'opacity-60 grayscale')}
            >
              <div className="grid grid-cols-1 lg:grid-cols-[auto,minmax(100px,0.4fr),minmax(200px,1.3fr),minmax(80px,0.5fr),auto] gap-4 items-end">
                <NeuralCoreSwitch
                  active={!!pathItem.enabled}
                  onToggle={() => togglePathEnabled(index)}
                  size={72}
                  label={pathItem.enabled ? t('basic_online') : t('basic_offline')}
                  statusText={pathItem.type.toUpperCase()}
                />
                <NeuralSelect
                  label={t('paths_type_discovery')}
                  value={pathItem.type}
                  onChange={(e) => updatePathDetail(index, 'type', e.target.value)}
                >
                  <option value="download">{t('paths_type_discovery')}</option>
                  <option value="library">{t('paths_type_storage')}</option>
                </NeuralSelect>
                <NeuralInput
                  label={t('paths_path_label')}
                  type="text"
                  value={pathItem.path}
                  onChange={(e) => updatePathDetail(index, 'path', e.target.value)}
                />
                <NeuralSelect
                  label={t('paths_category_label')}
                  value={pathItem.category || 'movie'}
                  onChange={(e) => updatePathDetail(index, 'category', e.target.value)}
                >
                  <option value="movie">{t('paths_cat_movie')}</option>
                  <option value="tv">{t('paths_cat_tv')}</option>
                  {pathItem.type !== 'library' && (
                    <option value="mixed">{t('paths_cat_mixed')}</option>
                  )}
                </NeuralSelect>
                <button
                  type="button"
                  onClick={() => removePath(pathItem.path)}
                  className="px-4 py-3 bg-transparent border border-cyber-cyan/30 text-cyber-cyan/70 hover:text-black hover:bg-cyber-cyan transition-all whitespace-nowrap"
                  style={{
                    boxShadow: '0 0 18px rgba(0, 230, 246, 0.2)',
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
      <NeuralSection title={t('paths_add_new')}>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr,1fr,2fr,auto] gap-4 items-end">
          <NeuralSelect value={newType} onChange={(e) => setNewType(e.target.value)} label={t('paths_type_label')}>
            <option value="download">{t('paths_type_discovery')}</option>
            <option value="library">{t('paths_type_storage')}</option>
          </NeuralSelect>
          <NeuralSelect
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            label={t('paths_category_label')}
          >
            <option value="movie">{t('paths_cat_movie')}</option>
            <option value="tv">{t('paths_cat_tv')}</option>
            {newType !== 'library' && <option value="mixed">{t('paths_cat_mixed')}</option>}
          </NeuralSelect>
          <NeuralInput
            type="text"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            placeholder={t('paths_placeholder')}
            label={t('paths_path_label')}
          />
          <button
            type="button"
            onClick={addPath}
            className="px-6 py-3 bg-transparent border-2 border-cyber-cyan text-cyber-cyan font-bold uppercase tracking-widest hover:bg-cyber-cyan hover:text-black transition-all"
            style={{
              boxShadow: '0 0 20px rgba(0, 230, 246, 0.35), inset 0 0 20px rgba(0, 230, 246, 0.08)',
            }}
          >
            {t('paths_add_btn')}
          </button>
        </div>
      </NeuralSection>
    </div>
  );
}
