'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import type { SettingsConfig } from '@/types';
import type { I18nKey } from '@/lib/i18n';
import { NeuralInput, NeuralSection, NeuralTextarea } from './NeuralPrimitives';

interface Props {
  config: SettingsConfig;
  setConfig: (c: SettingsConfig) => void;
  t: (key: I18nKey) => string;
}

export default function PersonaSettings({ config, setConfig, t }: Props) {
  const [resetting, setResetting] = useState(false);

  const updateSetting = (key: string, value: string) => {
    setConfig({
      ...config,
      settings: {
        ...config.settings,
        [key]: value
      }
    });
  };

  const handleReset = async () => {
    if (!confirm(t('persona_reset_confirm'))) {
      return;
    }

    setResetting(true);
    try {
      const result = await api.resetSettings('ai');
      
      if (result.success) {
        alert(t('persona_reset_success'));
        const freshConfig = await api.getSettings();
        setConfig(freshConfig);
      } else {
        alert(`${t('alert_save_fail')}: ${result.message || '未知错误'}`);
      }
    } catch (error) {
      console.error('Reset failed:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      alert(`${t('alert_save_fail')}: ${errorMessage}`);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-6">
      <NeuralSection title={t('persona_identity')}>
        <NeuralInput
          label={t('persona_ai_name')}
          type="text"
          value={config.settings.ai_name || ''}
          onChange={(e) => updateSetting('ai_name', e.target.value)}
          placeholder={t('persona_ai_name_placeholder')}
        />
      </NeuralSection>

      <NeuralSection title={t('persona_persona_section')}>
        <NeuralTextarea
          label={t('persona_persona')}
          value={config.settings.ai_persona || ''}
          onChange={(e) => updateSetting('ai_persona', e.target.value)}
          placeholder={t('persona_persona_placeholder')}
          rows={4}
        />
      </NeuralSection>

      <NeuralSection title={t('persona_expert_archive_section')}>
        <NeuralTextarea
          label={t('persona_expert_rules')}
          value={config.settings.expert_archive_rules || ''}
          onChange={(e) => updateSetting('expert_archive_rules', e.target.value)}
          placeholder={t('persona_expert_placeholder')}
          rows={12}
          className="text-sm"
        />
      </NeuralSection>

      <NeuralSection title={t('persona_router_section')}>
        <NeuralTextarea
          label={t('persona_router_rules')}
          value={config.settings.master_router_rules || ''}
          onChange={(e) => updateSetting('master_router_rules', e.target.value)}
          placeholder={t('persona_router_placeholder')}
          rows={12}
          className="text-sm"
        />
      </NeuralSection>

      <div className="flex gap-4">
        <button
          onClick={handleReset}
          disabled={resetting}
          className="px-6 py-3 bg-transparent border-2 border-cyber-red text-cyber-red font-bold uppercase tracking-widest hover:bg-cyber-red hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            boxShadow: '0 0 20px rgba(255, 1, 60, 0.35), inset 0 0 20px rgba(255, 1, 60, 0.08)',
          }}
        >
          {resetting ? t('persona_resetting') : t('btn_reset_defaults')}
        </button>
      </div>

      <NeuralSection title={t('persona_signal')}>
        <p className="text-cyber-cyan/70 text-sm">{t('persona_tip')}</p>
      </NeuralSection>
    </div>
  );
}
