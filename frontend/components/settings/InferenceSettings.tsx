'use client';

import { useState } from 'react';
import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralCoreSwitch, NeuralInput, NeuralSection } from './NeuralPrimitives';

interface Props {
  t: (key: I18nKey) => string;
}

export default function InferenceSettings({ t }: Props) {
  const { config, updateSetting } = useSettings();
  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  if (!config) return null;

  const isCloud = config.settings.llm_provider === 'cloud';
  const isLocal = config.settings.llm_provider === 'local';

  const renderKeyInput = (key: string, label: string) => {
    const value = config.settings[key as keyof typeof config.settings] as string;
    const isVisible = focusedKey === key;
    return (
      <div className="relative">
        <label className="text-sm font-medium text-cyber-cyan block mb-2">{label}</label>
        <input
          type={isVisible ? 'text' : 'password'}
          value={value}
          onChange={(e) => updateSetting(key, e.target.value)}
          onFocus={() => setFocusedKey(key)}
          onBlur={() => setFocusedKey(null)}
          placeholder={label}
          className="w-full px-4 py-2 bg-black/30 border border-cyber-cyan/30 rounded text-cyber-cyan placeholder-gray-500 focus:outline-none focus:border-cyber-cyan/60 text-base overflow-x-auto"
          style={{ fontFamily: isVisible ? 'monospace' : 'inherit' }}
        />
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <NeuralSection title={t('inference_title')}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <NeuralCoreSwitch active={isCloud} onToggle={() => updateSetting('llm_provider', isCloud ? 'local' : 'cloud')} size={76} label={t('inference_cloud')} statusText={t('inference_cloud_desc')} />
          <NeuralCoreSwitch active={isLocal} onToggle={() => updateSetting('llm_provider', isLocal ? 'cloud' : 'local')} size={76} label={t('inference_local')} statusText={t('inference_local_desc')} />
        </div>
      </NeuralSection>

      <NeuralSection title={t('inference_cloud_config')}>
        <div className="grid grid-cols-1 gap-6">
          <NeuralInput label={t('inference_api_url')} type="text" value={config.settings.llm_cloud_url} onChange={(e) => updateSetting('llm_cloud_url', e.target.value)} placeholder={t('inference_cloud_url_placeholder')} />
          {renderKeyInput('llm_cloud_key', t('inference_api_key'))}
          <NeuralInput label={t('inference_model')} type="text" value={config.settings.llm_cloud_model} onChange={(e) => updateSetting('llm_cloud_model', e.target.value)} placeholder={t('inference_cloud_model_placeholder')} />
        </div>
      </NeuralSection>

      <NeuralSection title={t('inference_local_config')}>
        <div className="grid grid-cols-1 gap-6">
          <NeuralInput label={t('inference_api_url')} type="text" value={config.settings.llm_local_url} onChange={(e) => updateSetting('llm_local_url', e.target.value)} placeholder={t('inference_local_url_placeholder')} />
          {renderKeyInput('llm_local_key', t('inference_api_key'))}
          <NeuralInput label={t('inference_model')} type="text" value={config.settings.llm_local_model} onChange={(e) => updateSetting('llm_local_model', e.target.value)} placeholder={t('inference_local_model_placeholder')} />
        </div>
      </NeuralSection>

      <NeuralSection title={t('inference_signal')}>
        <p className="text-cyber-cyan/70 text-sm">{t('inference_tip')}</p>
      </NeuralSection>
    </div>
  );
}
