'use client';

import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralCoreSwitch, NeuralInput, NeuralSection, NeuralSelect } from './NeuralPrimitives';

interface Props {
  t: (key: I18nKey) => string;
}

type LangKey = 'subtitle_lang' | 'poster_lang' | 'rename_lang';

interface LangDualSwitchProps {
  title: string;
  description: string;
  settingKey: LangKey;
  value: string;
  onUpdate: (key: LangKey, val: string) => void;
  t: (key: I18nKey) => string;
}

function LangDualSwitch({ title, description, settingKey, value, onUpdate, t }: LangDualSwitchProps) {
  const isZh = value === 'zh';
  const isEn = value === 'en';
  return (
    <div className="py-5 border-b border-cyber-cyan/10 last:border-b-0">
      <div className="mb-4">
        <div className="text-cyber-cyan/80 text-xs font-semibold uppercase tracking-[0.25em] mb-1" style={{ fontFamily: 'var(--font-advent, inherit)' }}>
          {title}
        </div>
        <div className="text-cyber-cyan/40 text-xs">{description}</div>
      </div>
      <div className="flex flex-row gap-8">
        <NeuralCoreSwitch active={isZh} onToggle={() => onUpdate(settingKey, 'zh')} size={56} label={t('lang_zh')} statusText={isZh ? t('basic_online') : t('basic_offline')} />
        <NeuralCoreSwitch active={isEn} onToggle={() => onUpdate(settingKey, 'en')} size={56} label={t('lang_en')} statusText={isEn ? t('basic_online') : t('basic_offline')} />
      </div>
    </div>
  );
}

export default function BasicSettings({ t }: Props) {
  const { config, updateSetting } = useSettings();
  if (!config) return null;

  const handleLogout = () => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('token');
      window.location.replace('/');
    }
  };

  return (
    <div className="space-y-8">
      <NeuralSection title={t('basic_interface')}>
        <NeuralSelect label={t('basic_ui_lang')} value={config.settings.ui_lang ?? 'zh'} onChange={(e) => updateSetting('ui_lang', e.target.value)}>
          <option value="zh">{t('basic_ui_lang_zh')}</option>
          <option value="en">{t('basic_ui_lang_en')}</option>
        </NeuralSelect>
      </NeuralSection>

      <NeuralSection title="LANG · MATRIX">
        <LangDualSwitch title={t('setting_subtitle_lang')} description={t('setting_subtitle_lang_desc')} settingKey="subtitle_lang" value={config.settings.subtitle_lang ?? 'zh'} onUpdate={(key, val) => updateSetting(key, val)} t={t} />
        <LangDualSwitch title={t('setting_poster_lang')} description={t('setting_poster_lang_desc')} settingKey="poster_lang" value={config.settings.poster_lang ?? 'zh'} onUpdate={(key, val) => updateSetting(key, val)} t={t} />
        <LangDualSwitch title={t('setting_rename_lang')} description={t('setting_rename_lang_desc')} settingKey="rename_lang" value={config.settings.rename_lang ?? 'zh'} onUpdate={(key, val) => updateSetting(key, val)} t={t} />
      </NeuralSection>

      <NeuralSection title={t('basic_section_patrol')}>
        <div className="flex flex-col space-y-6">
          <div className="flex flex-row gap-6">
            <NeuralCoreSwitch
              active={!!(config.settings.cron_enabled ?? false)}
              onToggle={() => updateSetting('cron_enabled', !(config.settings.cron_enabled ?? false))}
              size={76} label={t('basic_cron_enabled')}
              statusText={`${t('basic_cron_enabled_desc')} · ${config.settings.cron_enabled ? t('basic_online') : t('basic_offline')}`}
            />
            <NeuralCoreSwitch 
              active={!!config.settings.auto_scrape} 
              onToggle={() => updateSetting('auto_scrape', !config.settings.auto_scrape)} 
              size={76} 
              label={t('basic_auto_scrape_label')} 
              statusText={t('basic_auto_scrape_desc')} 
            />
            <NeuralCoreSwitch 
              active={!!config.settings.auto_subtitles} 
              onToggle={() => updateSetting('auto_subtitles', !config.settings.auto_subtitles)} 
              size={76} 
              label={t('basic_auto_subtitles_label')} 
              statusText={t('basic_auto_subtitles_desc')} 
            />
          </div>
          <div className="border-t border-cyber-cyan/10 pt-6">
            <NeuralInput label={t('basic_cron_interval_min')} type="number" min={1} value={String(config.settings.cron_interval_min ?? 60)} onChange={(e) => updateSetting('cron_interval_min', parseInt(e.target.value, 10) || 60)} hint={t('basic_cron_interval_min_hint')} />
          </div>
        </div>
      </NeuralSection>

      <NeuralSection title={t('basic_section_filesize_filter')}>
        <NeuralInput label={t('basic_min_size')} type="number" min={0} value={String(config.settings.min_size_mb ?? 50)} onChange={(e) => { const val = parseInt(e.target.value, 10); updateSetting('min_size_mb', isNaN(val) ? 0 : val); }} hint={t('basic_min_size_hint')} />
      </NeuralSection>

      <div className="pt-6 mt-6 border-t border-cyber-red/40">
        <h3 className="text-cyber-red font-semibold text-lg mb-3">{t('settings_security_title')}</h3>
        <p className="text-white/60 text-sm mb-4">{t('settings_logout_desc')}</p>
        <button type="button" onClick={handleLogout} className="w-full py-3 rounded-lg bg-cyber-red text-white font-bold tracking-wide shadow-[0_0_16px_rgba(255,0,76,0.6)] hover:shadow-[0_0_24px_rgba(255,0,76,0.9)] hover:brightness-110 transition-all">
          {t('btn_logout')}
        </button>
      </div>
    </div>
  );
}
