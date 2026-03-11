'use client';

import type { SettingsConfig } from '@/types';
import type { I18nKey } from '@/lib/i18n';
import { NeuralInput, NeuralSection } from './NeuralPrimitives';

interface Props {
  config: SettingsConfig;
  setConfig: (c: SettingsConfig) => void;
  t: (key: I18nKey) => string;
}

export default function APISettings({ config, setConfig, t }: Props) {
  const updateSetting = (key: string, value: string) => {
    setConfig({
      ...config,
      settings: {
        ...config.settings,
        [key]: value
      }
    });
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <NeuralSection title={t('api_tmdb_section')}>
          <NeuralInput
            label={t('api_tmdb_key')}
            type="password"
            value={config.settings.tmdb_api_key}
            onChange={(e) => updateSetting('tmdb_api_key', e.target.value)}
          />
        </NeuralSection>

        <NeuralSection title={t('api_opensubtitles_section')}>
          <NeuralInput
            label={t('api_os_key')}
            type="password"
            value={config.settings.os_api_key}
            onChange={(e) => updateSetting('os_api_key', e.target.value)}
          />
        </NeuralSection>

        <NeuralSection title={t('api_radarr_section')}>
          <div className="space-y-6">
            <NeuralInput
              label={t('api_radarr_url')}
              type="text"
              value={config.settings.radarr_url}
              onChange={(e) => updateSetting('radarr_url', e.target.value)}
              placeholder={t('api_radarr_url_placeholder')}
            />
            <NeuralInput
              label={t('api_radarr_key')}
              type="password"
              value={config.settings.radarr_api_key}
              onChange={(e) => updateSetting('radarr_api_key', e.target.value)}
            />
          </div>
        </NeuralSection>

        <NeuralSection title={t('api_sonarr_section')}>
          <div className="space-y-6">
            <NeuralInput
              label={t('api_sonarr_url')}
              type="text"
              value={config.settings.sonarr_url}
              onChange={(e) => updateSetting('sonarr_url', e.target.value)}
              placeholder={t('api_sonarr_url_placeholder')}
            />
            <NeuralInput
              label={t('api_sonarr_key')}
              type="password"
              value={config.settings.sonarr_api_key}
              onChange={(e) => updateSetting('sonarr_api_key', e.target.value)}
            />
          </div>
        </NeuralSection>
      </div>

      <NeuralSection title={t('api_signal')}>
        <p className="text-cyber-cyan/70 text-sm">{t('api_tip')}</p>
      </NeuralSection>
    </div>
  );
}
