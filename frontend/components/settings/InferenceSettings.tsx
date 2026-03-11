'use client';

import type { SettingsConfig } from '@/types';
import type { I18nKey } from '@/lib/i18n';
import { NeuralCoreSwitch, NeuralInput, NeuralSection } from './NeuralPrimitives';

interface Props {
  config: SettingsConfig;
  setConfig: (c: SettingsConfig) => void;
  t: (key: I18nKey) => string;
}

export default function InferenceSettings({ config, setConfig, t }: Props) {
  const updateSetting = (key: string, value: string) => {
    setConfig({
      ...config,
      settings: {
        ...config.settings,
        [key]: value
      }
    });
  };

  const isCloud = config.settings.llm_provider === 'cloud';
  const isLocal = config.settings.llm_provider === 'local';

  return (
    <div className="space-y-6">
      <NeuralSection title={t('inference_title')}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <NeuralCoreSwitch
            active={isCloud}
            onToggle={() => updateSetting('llm_provider', isCloud ? 'local' : 'cloud')}
            size={76}
            label={t('inference_cloud')}
            statusText={t('inference_cloud_desc')}
          />
          <NeuralCoreSwitch
            active={isLocal}
            onToggle={() => updateSetting('llm_provider', isLocal ? 'cloud' : 'local')}
            size={76}
            label={t('inference_local')}
            statusText={t('inference_local_desc')}
          />
        </div>
      </NeuralSection>

      <div className="space-y-4">
        <NeuralSection title={t('inference_cloud_config')}>
          <div className="grid grid-cols-1 gap-6">
            <NeuralInput
              label={t('inference_api_url')}
              type="text"
              value={config.settings.llm_cloud_url}
              onChange={(e) => updateSetting('llm_cloud_url', e.target.value)}
              placeholder={t('inference_cloud_url_placeholder')}
            />
            <NeuralInput
              label={t('inference_api_key')}
              type="password"
              value={config.settings.llm_cloud_key}
              onChange={(e) => updateSetting('llm_cloud_key', e.target.value)}
              placeholder={t('inference_cloud_key_placeholder')}
            />
            <NeuralInput
              label={t('inference_model')}
              type="text"
              value={config.settings.llm_cloud_model}
              onChange={(e) => updateSetting('llm_cloud_model', e.target.value)}
              placeholder={t('inference_cloud_model_placeholder')}
            />
          </div>
        </NeuralSection>
      </div>

      <div className="space-y-4">
        <NeuralSection title={t('inference_local_config')}>
          <div className="grid grid-cols-1 gap-6">
            <NeuralInput
              label={t('inference_api_url')}
              type="text"
              value={config.settings.llm_local_url}
              onChange={(e) => updateSetting('llm_local_url', e.target.value)}
              placeholder={t('inference_local_url_placeholder')}
            />
            <NeuralInput
              label={t('inference_api_key')}
              type="password"
              value={config.settings.llm_local_key}
              onChange={(e) => updateSetting('llm_local_key', e.target.value)}
              placeholder={t('inference_local_key_placeholder')}
            />
            <NeuralInput
              label={t('inference_model')}
              type="text"
              value={config.settings.llm_local_model}
              onChange={(e) => updateSetting('llm_local_model', e.target.value)}
              placeholder={t('inference_local_model_placeholder')}
            />
          </div>
        </NeuralSection>
      </div>

      <NeuralSection title={t('inference_signal')}>
        <p className="text-cyber-cyan/70 text-sm">{t('inference_tip')}</p>
      </NeuralSection>
    </div>
  );
}
