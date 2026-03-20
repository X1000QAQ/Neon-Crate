'use client';

import { useState } from 'react';
import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralInput, NeuralSection } from './NeuralPrimitives';

interface Props {
  t: (key: I18nKey) => string;
}

// 本地缓冲：受控输入先写组件 state，失焦或提交时再写父级，降低全树重渲染
// onBlur 失焦时才 flush 到全局 Context，彻底终结击键触发的全组件重绘。
const API_KEYS = ['tmdb_api_key', 'os_api_key', 'radarr_api_key', 'sonarr_api_key'] as const;
const URL_KEYS = ['radarr_url', 'sonarr_url'] as const;
type ApiKey = typeof API_KEYS[number];
type UrlKey = typeof URL_KEYS[number];
type LocalKey = ApiKey | UrlKey;

export default function APISettings({ t }: Props) {
  const { config, updateSetting } = useSettings();
  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  // 本地缓冲 state：key → 当前输入框内容
  const [localValues, setLocalValues] = useState<Partial<Record<LocalKey, string>>>({});

  if (!config) return null;

  // 读取优先级：localValues（用户正在输入）> config.settings（全局）
  const getVal = (key: LocalKey): string => {
    if (key in localValues) return localValues[key] ?? '';
    return (config.settings[key as keyof typeof config.settings] as string) || '';
  };

  const renderKeyInput = (key: ApiKey, label: string) => {
    const isVisible = focusedKey === key;
    return (
      <div className="relative">
        <label className="text-sm font-medium text-cyber-cyan block mb-2">{label}</label>
        <input
          type={isVisible ? 'text' : 'password'}
          value={getVal(key)}
          onChange={(e) => {
            // 事件边界：在异步 setState 前同步读取 e.target.value，避免合成事件池回收导致空读
            const val = e.currentTarget.value;
            setLocalValues(prev => ({ ...prev, [key]: val }));
          }}
          onFocus={() => setFocusedKey(key)}
          onBlur={(e) => {
            setFocusedKey(null);
            // onBlur 才 flush 到全局 Context
            updateSetting(key, e.currentTarget.value);
          }}
          placeholder={`输入 ${label}...`}
          className="w-full px-4 py-2 bg-black/30 border border-cyber-cyan/30 rounded text-cyber-cyan placeholder-gray-500 focus:outline-none focus:border-cyber-cyan/60 text-base overflow-x-auto"
          style={{ fontFamily: isVisible ? 'monospace' : 'inherit' }}
        />
      </div>
    );
  };

  const renderUrlInput = (key: UrlKey, label: string, placeholder: string) => (
    <div className="relative">
      <label className="text-sm font-medium text-cyber-cyan block mb-2">{label}</label>
      <input
        type="text"
        value={getVal(key)}
        onChange={(e) => {
            // 事件边界：在异步 setState 前同步读取 e.target.value，避免合成事件池回收导致空读
            const val = e.currentTarget.value;
            setLocalValues(prev => ({ ...prev, [key]: val }));
          }}
        onBlur={(e) => updateSetting(key, e.currentTarget.value)}
        placeholder={placeholder}
        className="w-full px-4 py-2 bg-black/30 border border-cyber-cyan/30 rounded text-cyber-cyan placeholder-gray-500 focus:outline-none focus:border-cyber-cyan/60 text-base overflow-x-auto"
      />
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <NeuralSection title={t('api_tmdb_section')}>
          {renderKeyInput('tmdb_api_key', t('api_tmdb_key'))}
        </NeuralSection>
        <NeuralSection title={t('api_opensubtitles_section')}>
          {renderKeyInput('os_api_key', t('api_os_key'))}
        </NeuralSection>
        <NeuralSection title={t('api_radarr_section')}>
          <div className="space-y-4">
            {renderUrlInput('radarr_url', t('api_radarr_url'), t('api_radarr_url_placeholder'))}
            {renderKeyInput('radarr_api_key', t('api_radarr_key'))}
          </div>
        </NeuralSection>
        <NeuralSection title={t('api_sonarr_section')}>
          <div className="space-y-4">
            {renderUrlInput('sonarr_url', t('api_sonarr_url'), t('api_sonarr_url_placeholder'))}
            {renderKeyInput('sonarr_api_key', t('api_sonarr_key'))}
          </div>
        </NeuralSection>
      </div>
      <NeuralSection title={t('api_signal')}>
        <p className="text-cyber-cyan/70 text-sm">{t('api_tip')}</p>
      </NeuralSection>
    </div>
  );
}
