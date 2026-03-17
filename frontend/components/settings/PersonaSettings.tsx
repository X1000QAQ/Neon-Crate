'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralInput, NeuralSection, NeuralTextarea } from './NeuralPrimitives';
import NeuralConfirmModal from './NeuralConfirmModal';

interface Props {
  t: (key: I18nKey) => string;
}

export default function PersonaSettings({ t }: Props) {
  const { config, updateSetting, refreshSettings } = useSettings();
  const [resetting, setResetting] = useState(false);
  const [resetModal, setResetModal] = useState(false);

  if (!config) return null;

  const handleReset = async () => {
    setResetModal(false);
    setResetting(true);
    try {
      const result = await api.resetSettings('ai');
      if (result.success) {
        // [C-04 修复] 删除 alert()，改为安全的 console 日志，成功反馈由父层 Toast 承接
        console.info('[PersonaSettings] reset success:', t('persona_reset_success'));
        await refreshSettings();
      } else {
        // [S-05 修复] '未知错误' → t('error_unknown')
        console.error('[PersonaSettings] reset failed:', result.message || t('error_unknown'));
      }
    } catch (error) {
      console.error('[PersonaSettings] reset error:', error instanceof Error ? error.message : t('error_unknown'));
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-6">
      <NeuralConfirmModal
        isOpen={resetModal}
        title={t('modal_confirm')}
        message={t('persona_reset_confirm')}
        confirmLabel={t('modal_confirm')}
        cancelLabel={t('modal_cancel')}
        variant="warning"
        onConfirm={handleReset}
        onCancel={() => setResetModal(false)}
      />

      <NeuralSection title={t('persona_identity')}>
        <NeuralInput label={t('persona_ai_name')} type="text" value={config.settings.ai_name || ''} onChange={(e) => updateSetting('ai_name', e.target.value)} placeholder={t('persona_ai_name_placeholder')} />
      </NeuralSection>

      <NeuralSection title={t('persona_persona_section')}>
        <NeuralTextarea label={t('persona_persona')} value={config.settings.ai_persona || ''} onChange={(e) => updateSetting('ai_persona', e.target.value)} placeholder={t('persona_persona_placeholder')} rows={4} />
      </NeuralSection>

      <NeuralSection title={t('persona_expert_archive_section')}>
        <NeuralTextarea label={t('persona_expert_rules')} value={config.settings.expert_archive_rules || ''} onChange={(e) => updateSetting('expert_archive_rules', e.target.value)} placeholder={t('persona_expert_placeholder')} rows={12} className="text-sm" />
      </NeuralSection>

      <NeuralSection title={t('persona_router_section')}>
        <NeuralTextarea label={t('persona_router_rules')} value={config.settings.master_router_rules || ''} onChange={(e) => updateSetting('master_router_rules', e.target.value)} placeholder={t('persona_router_placeholder')} rows={12} className="text-sm" />
      </NeuralSection>

      <div className="flex gap-4">
        <button
          onClick={() => setResetModal(true)}
          disabled={resetting}
          className="px-6 py-3 bg-transparent border-2 border-cyber-red text-cyber-red font-bold uppercase tracking-widest hover:bg-cyber-red hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ boxShadow: '0 0 20px rgba(255, 1, 60, 0.35), inset 0 0 20px rgba(255, 1, 60, 0.08)' }}
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
