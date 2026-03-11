'use client';

import type { SettingsConfig } from '@/types';
import type { I18nKey } from '@/lib/i18n';
import { NeuralCoreSwitch, NeuralInput, NeuralSection, NeuralSelect } from './NeuralPrimitives';

interface Props {
  config: SettingsConfig;
  setConfig: (c: SettingsConfig) => void;
  t: (key: I18nKey) => string;
}

export default function BasicSettings({ config, setConfig, t }: Props) {
  const updateSetting = (key: string, value: string | number | boolean) => {
    setConfig({
      ...config,
      settings: {
        ...config.settings,
        [key]: value
      }
    });
  };

  const handleLogout = () => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('token');
      window.location.replace('/');
    }
  };

  return (
    <div className="space-y-8">
      <NeuralSection title={t('basic_interface')}>
        <NeuralSelect
          label={t('basic_ui_lang')}
          value={config.settings.ui_lang ?? 'zh'}
          onChange={(e) => updateSetting('ui_lang', e.target.value)}
        >
          <option value="zh">{t('basic_ui_lang_zh')}</option>
          <option value="en">{t('basic_ui_lang_en')}</option>
        </NeuralSelect>
      </NeuralSection>

      <div className="space-y-4">
        <NeuralSection title={t('basic_section_patrol')}>
          <NeuralCoreSwitch
            active={!!(config.settings.cron_enabled ?? false)}
            onToggle={() => updateSetting('cron_enabled', !(config.settings.cron_enabled ?? false))}
            size={76}
            label={t('basic_cron_enabled')}
            statusText={`${t('basic_cron_enabled_desc')} · ${
              config.settings.cron_enabled ? t('basic_online') : t('basic_offline')
            }`}
          />
          <div className="mt-6">
            <NeuralInput
              label={t('basic_cron_interval_min')}
              type="number"
              min={1}
              value={String(config.settings.cron_interval_min ?? 60)}
              onChange={(e) =>
                updateSetting('cron_interval_min', parseInt(e.target.value, 10) || 60)
              }
              hint={t('basic_cron_interval_min_hint')}
            />
          </div>
        </NeuralSection>
      </div>

      <div className="space-y-4">
        <NeuralSection title={t('basic_section_auto_flow')}>
          <NeuralCoreSwitch
            active={!!config.settings.auto_process_enabled}
            onToggle={() =>
              updateSetting('auto_process_enabled', !config.settings.auto_process_enabled)
            }
            size={76}
            label={t('basic_auto_process_enabled')}
            statusText={`${t('basic_auto_process_enabled_desc')} · ${
              config.settings.auto_process_enabled ? t('basic_online') : t('basic_offline')
            }`}
          />

          {config.settings.auto_process_enabled && (
            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
              <NeuralCoreSwitch
                active={!!config.settings.auto_scrape}
                onToggle={() => updateSetting('auto_scrape', !config.settings.auto_scrape)}
                size={76}
                label={t('basic_auto_scrape_label')}
                statusText={t('basic_auto_scrape_desc')}
                className="items-start"
              />
              <NeuralCoreSwitch
                active={!!config.settings.auto_subtitles}
                onToggle={() => updateSetting('auto_subtitles', !config.settings.auto_subtitles)}
                size={76}
                label={t('basic_auto_subtitles_label')}
                statusText={t('basic_auto_subtitles_desc')}
                className="items-start"
              />
            </div>
          )}
        </NeuralSection>
      </div>

      <div className="space-y-4">
        <NeuralSection title={t('basic_section_filesize_filter')}>
          <NeuralInput
            label={t('basic_min_size')}
            type="number"
            min={0}
            value={String(config.settings.min_size_mb ?? 50)}
            onChange={(e) => {
              const val = parseInt(e.target.value, 10);
              updateSetting('min_size_mb', isNaN(val) ? 0 : val);
            }}
            hint={t('basic_min_size_hint')}
          />
        </NeuralSection>
      </div>

      <div className="pt-6 mt-6 border-t border-cyber-red/40">
        <h3 className="text-cyber-red font-semibold text-lg mb-3">
          {t('settings_security_title')}
        </h3>
        <p className="text-white/60 text-sm mb-4">
          {t('settings_logout_desc')}
        </p>
        <button
          type="button"
          onClick={handleLogout}
          className="w-full py-3 rounded-lg bg-cyber-red text-white font-bold tracking-wide shadow-[0_0_16px_rgba(255,0,76,0.6)] hover:shadow-[0_0_24px_rgba(255,0,76,0.9)] hover:brightness-110 transition-all"
        >
          {t('btn_logout')}
        </button>
      </div>
    </div>
  );
}
