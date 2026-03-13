'use client';

import { useState } from 'react';
import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralInput, NeuralSection } from './NeuralPrimitives';

interface Props {
  t: (key: I18nKey) => string;
}

export default function APISettings({ t }: Props) {
  const { config, updateSetting } = useSettings();
  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  if (!config) return null;

  const renderKeyInput = (key: string, label: string) => {
    const value = (config.settings[key as keyof typeof config.settings] as string) || '';
    const isVisible = focusedKey === key;
    return (
      <div className="relative">
        <label className="text-sm font-medium text-cyber-cyan block mb-2">{label}</label>
        <input
          type={isVisible ? 'text' : 'password'}
          value={value}
          onChange={(e) => updateSetting(key, e.currentTarget.value)}
          onFocus={() => setFocusedKey(key)}
          onBlur={() => setFocusedKey(null)}
          placeholder={`输入 ${label}...`}
          className="w-full px-4 py-2 bg-black/30 border border-cyber-cyan/30 rounded text-cyber-cyan placeholder-gray-500 focus:outline-none focus:border-cyber-cyan/60 text-base overflow-x-auto"
          style={{ fontFamily: isVisible ? 'monospace' : 'inherit' }}
        />
      </div>
    );
  };

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
            <NeuralInput label={t('api_radarr_url')} type="text" value={(config.settings.radarr_url as string) || ''} onChange={(e) => updateSetting('radarr_url', e.currentTarget.value)} placeholder={t('api_radarr_url_placeholder')} />
            {renderKeyInput('radarr_api_key', t('api_radarr_key'))}
          </div>
        </NeuralSection>
        <NeuralSection title={t('api_sonarr_section')}>
          <div className="space-y-4">
            <NeuralInput label={t('api_sonarr_url')} type="text" value={(config.settings.sonarr_url as string) || ''} onChange={(e) => updateSetting('sonarr_url', e.currentTarget.value)} placeholder={t('api_sonarr_url_placeholder')} />
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
