'use client';

import { useState, useEffect, useRef } from 'react';
import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralSection, NeuralInput, NeuralHint } from './NeuralPrimitives';

interface Props {
  t: (key: I18nKey) => string;
}

const CYAN = 'var(--cyber-cyan)';
const FONT_A = '"Advent Pro", sans-serif';

export default function InferenceSettings({ t }: Props) {
  const { config, updateSetting } = useSettings();
  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  // 🚀 极致渲染性能优化：本地 State 与全局 Context 的缓冲隔离策略。
  // 1. 本地拦截：用户击键时仅更新 localState，阻断 SettingsContext 全局重绘
  // -> 2. 最终同步：仅在 onBlur（失去焦点）时调用 updateSetting 提交全局配置
  // -> 3. 体验加固：Context 重绘会触发所有订阅组件重渲染，高频输入必须本地缓冲后批量提交
  const [localCloudUrl, setLocalCloudUrl] = useState('');
  const [localCloudModel, setLocalCloudModel] = useState('');
  const [localLocalUrl, setLocalLocalUrl] = useState('');
  const [localLocalModel, setLocalLocalModel] = useState('');
  // API 密钥本地缓冲（同上，防止 paste 事件中 e.target 被 React 回收导致 null.value 崩溃）
  const [localCloudKey, setLocalCloudKey] = useState('');
  const [localLocalKey, setLocalLocalKey] = useState('');

  // 用 ref 追踪上一次 config 来源，防止 config 外部变化时覆盖用户正在输入的内容
  const syncedRef = useRef(false);

  useEffect(() => {
    if (!config) return;
    // 仅在首次加载或外部 config 被 refreshSettings 替换时同步
    if (!syncedRef.current) {
      setLocalCloudUrl((config.settings.llm_cloud_url as string) ?? '');
      setLocalCloudModel((config.settings.llm_cloud_model as string) ?? '');
      setLocalLocalUrl((config.settings.llm_local_url as string) ?? '');
      setLocalLocalModel((config.settings.llm_local_model as string) ?? '');
      setLocalCloudKey((config.settings.llm_cloud_key as string) ?? '');
      setLocalLocalKey((config.settings.llm_local_key as string) ?? '');
      syncedRef.current = true;
    }
  }, [config]);

  if (!config) return null;

  // 物理开关状态（默认云端开、本地关）
  const cloudEnabled = config.settings.llm_cloud_enabled ?? true;
  const localEnabled = config.settings.llm_local_enabled ?? false;

  // localKeyState / setter 按 key 路由，防止 paste 时 e.target 被 React 合成事件回收
  const getLocalKeyValue = (key: string): string => {
    if (key === 'llm_cloud_key') return localCloudKey;
    if (key === 'llm_local_key') return localLocalKey;
    return (config.settings[key as keyof typeof config.settings] as string) ?? '';
  };
  const setLocalKeyValue = (key: string, val: string) => {
    if (key === 'llm_cloud_key') setLocalCloudKey(val);
    else if (key === 'llm_local_key') setLocalLocalKey(val);
  };

  const renderKeyInput = (key: string, label: string, placeholder?: string) => {
    const value = getLocalKeyValue(key);
    const isVisible = focusedKey === key;
    return (
      <div>
        <label
          className="block text-xs font-semibold uppercase tracking-[0.25em] mb-3"
          style={{ color: 'rgba(0,230,246,0.7)', fontFamily: FONT_A }}
        >
          {label}
        </label>
        <input
          type={isVisible ? 'text' : 'password'}
          value={value}
          onChange={(e) => {
            // 立即提取 value，防止合成事件在异步 setState 前被回收（paste 崩溃根因）
            const val = e.currentTarget.value;
            setLocalKeyValue(key, val);
          }}
          onFocus={() => setFocusedKey(key)}
          onBlur={(e) => {
            setFocusedKey(null);
            // onBlur 才 flush 到全局 Context（与其他字段保持一致）
            updateSetting(key, e.currentTarget.value);
          }}
          placeholder={placeholder ?? label}
          className="w-full px-4 py-3 bg-black/40 border-0 border-l-2 border-cyber-cyan/40 text-cyber-cyan placeholder-cyber-cyan/40 focus:outline-none focus:bg-black/60 text-base font-hacked transition-all"
          style={{
            boxShadow: 'inset 0 0 20px rgba(0,0,0,0.6)',
            fontFamily: isVisible ? 'monospace' : undefined,
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLInputElement).style.boxShadow =
              '0 0 20px rgba(0,230,246,0.4), inset 0 0 20px rgba(0,230,246,0.1)';
          }}
          onMouseLeave={(e) => {
            if (focusedKey !== key)
              (e.currentTarget as HTMLInputElement).style.boxShadow =
                'inset 0 0 20px rgba(0,0,0,0.6)';
          }}
        />
      </div>
    );
  };

  // 动态状态横幅内容
  const renderStatusBanner = () => {
    if (cloudEnabled && localEnabled) {
      return (
        <>
          <span
            className="inline-block w-2 h-2 rounded-full mr-2 animate-pulse"
            style={{ background: CYAN, boxShadow: `0 0 6px ${CYAN}`, verticalAlign: 'middle' }}
          />
          <span className="font-bold uppercase tracking-wider" style={{ color: CYAN }}>
            {t('inference_dual_engine_active').split(' — ')[0]}
          </span>
          {' — ' + t('inference_dual_engine_active').split(' — ').slice(1).join(' — ')}
        </>
      );
    }
    if (cloudEnabled && !localEnabled) {
      return (
        <>
          <span
            className="inline-block w-2 h-2 rounded-full mr-2"
            style={{ background: 'rgba(0,230,246,0.35)', verticalAlign: 'middle' }}
          />
          <span className="font-bold uppercase tracking-wider">{t('inference_single_cloud')}</span>
          {' — ' + t('inference_single_cloud_desc')}
        </>
      );
    }
    if (!cloudEnabled && localEnabled) {
      return (
        <>
          <span
            className="inline-block w-2 h-2 rounded-full mr-2"
            style={{ background: 'rgba(0,230,246,0.35)', verticalAlign: 'middle' }}
          />
          <span className="font-bold uppercase tracking-wider">{t('inference_single_local')}</span>
          {' — ' + t('inference_single_local_desc')}
        </>
      );
    }
    return (
      <>
        <span
          className="inline-block w-2 h-2 rounded-full mr-2 animate-pulse"
          style={{ background: '#ef4444', verticalAlign: 'middle' }}
        />
        <span className="font-bold uppercase tracking-wider" style={{ color: '#f87171' }}>
          {t('inference_all_offline')}
        </span>
        {' — ' + t('inference_all_offline_desc')}
      </>
    );
  };

  return (
    <div className="space-y-6">

      {/* ── 独立物理开关面板 ── */}
      <NeuralSection title={t('inference_title')}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">

          {/* 云端引擎开关卡片 */}
          <button
            type="button"
            onClick={() => updateSetting('llm_cloud_enabled', !cloudEnabled)}
            className="relative text-left p-5 border-l-2 transition-all duration-200"
            style={{
              background: cloudEnabled ? 'rgba(0,230,246,0.08)' : 'rgba(0,0,0,0.25)',
              borderColor: cloudEnabled ? CYAN : 'rgba(0,230,246,0.15)',
              boxShadow: cloudEnabled
                ? '0 0 30px rgba(0,230,246,0.18), inset 0 0 20px rgba(0,230,246,0.05)'
                : 'none',
              opacity: cloudEnabled ? 1 : 0.6,
            }}
          >
            {cloudEnabled && (
              <span
                className="absolute top-3 right-3 w-2 h-2 rounded-full animate-pulse"
                style={{ background: CYAN, boxShadow: `0 0 8px ${CYAN}` }}
              />
            )}
            <div
              className="text-xs uppercase tracking-[0.2em] font-semibold mb-1"
              style={{
                color: cloudEnabled ? CYAN : '#6b7280',
                fontFamily: FONT_A,
                textShadow: cloudEnabled ? `0 0 10px ${CYAN}` : 'none',
              }}
            >
              {t('inference_cloud')}
            </div>
            <div
              className="text-xs mb-2"
              style={{ color: 'rgba(255,255,255,0.4)', fontFamily: FONT_A }}
            >
              {t('inference_cloud_desc')}
            </div>
            <div
              className="text-[10px] tracking-widest uppercase font-bold"
              style={{ color: cloudEnabled ? CYAN : '#6b7280', fontFamily: FONT_A }}
            >
              {cloudEnabled ? t('inference_status_online') : t('inference_status_offline')}
            </div>
          </button>

          {/* 本地引擎开关卡片 */}
          <button
            type="button"
            onClick={() => updateSetting('llm_local_enabled', !localEnabled)}
            className="relative text-left p-5 border-l-2 transition-all duration-200"
            style={{
              background: localEnabled ? 'rgba(0,230,246,0.08)' : 'rgba(0,0,0,0.25)',
              borderColor: localEnabled ? CYAN : 'rgba(0,230,246,0.15)',
              boxShadow: localEnabled
                ? '0 0 30px rgba(0,230,246,0.18), inset 0 0 20px rgba(0,230,246,0.05)'
                : 'none',
              opacity: localEnabled ? 1 : 0.6,
            }}
          >
            {localEnabled && (
              <span
                className="absolute top-3 right-3 w-2 h-2 rounded-full animate-pulse"
                style={{ background: CYAN, boxShadow: `0 0 8px ${CYAN}` }}
              />
            )}
            <div
              className="text-xs uppercase tracking-[0.2em] font-semibold mb-1"
              style={{
                color: localEnabled ? CYAN : '#6b7280',
                fontFamily: FONT_A,
                textShadow: localEnabled ? `0 0 10px ${CYAN}` : 'none',
              }}
            >
              {t('inference_local')}
            </div>
            <div
              className="text-xs mb-2"
              style={{ color: 'rgba(255,255,255,0.4)', fontFamily: FONT_A }}
            >
              {t('inference_local_desc')}
            </div>
            <div
              className="text-[10px] tracking-widest uppercase font-bold"
              style={{ color: localEnabled ? CYAN : '#6b7280', fontFamily: FONT_A }}
            >
              {localEnabled ? t('inference_status_online') : t('inference_status_offline')}
            </div>
          </button>
        </div>

        {/* 动态阵列状态横幅 */}
        <div
          className="px-4 py-3 border-l-2 text-xs leading-relaxed transition-all duration-300"
          style={{
            borderColor:
              cloudEnabled && localEnabled
                ? 'rgba(0,230,246,0.6)'
                : !cloudEnabled && !localEnabled
                ? '#ef4444'
                : 'rgba(0,230,246,0.18)',
            background:
              cloudEnabled && localEnabled
                ? 'rgba(0,230,246,0.06)'
                : !cloudEnabled && !localEnabled
                ? 'rgba(239,68,68,0.05)'
                : 'rgba(0,0,0,0.2)',
            color:
              cloudEnabled && localEnabled
                ? 'rgba(0,230,246,0.85)'
                : !cloudEnabled && !localEnabled
                ? 'rgba(248,113,113,0.9)'
                : 'rgba(0,230,246,0.5)',
            fontFamily: FONT_A,
          }}
        >
          {renderStatusBanner()}
        </div>
      </NeuralSection>

      {/* ── 云端 LLM 配置 ── */}
      <NeuralSection title={t('inference_cloud_config')}>
        <div className="grid grid-cols-1 gap-5">
          {/* 🚀 本地 state + onBlur 同步，阻断击键触发 Context 全局重绘 */}
          <NeuralInput
            label={t('inference_api_url')}
            type="text"
            value={localCloudUrl}
            onChange={(e) => setLocalCloudUrl(e.target.value)}
            onBlur={() => updateSetting('llm_cloud_url', localCloudUrl)}
            placeholder={t('inference_cloud_url_placeholder')}
          />
          {renderKeyInput('llm_cloud_key', t('inference_api_key'), t('inference_cloud_key_placeholder'))}
          <NeuralInput
            label={t('inference_model')}
            type="text"
            value={localCloudModel}
            onChange={(e) => setLocalCloudModel(e.target.value)}
            onBlur={() => updateSetting('llm_cloud_model', localCloudModel)}
            placeholder={t('inference_cloud_model_placeholder')}
          />
        </div>
      </NeuralSection>

      {/* ── 本地边缘节点配置 ── */}
      <NeuralSection title={t('inference_local_config')}>
        <div className="grid grid-cols-1 gap-5">
          <NeuralInput
            label={t('inference_api_url')}
            type="text"
            value={localLocalUrl}
            onChange={(e) => setLocalLocalUrl(e.target.value)}
            onBlur={() => updateSetting('llm_local_url', localLocalUrl)}
            placeholder={t('inference_local_url_placeholder')}
          />
          {renderKeyInput('llm_local_key', t('inference_api_key'), t('inference_local_key_placeholder'))}
          <NeuralInput
            label={t('inference_model')}
            type="text"
            value={localLocalModel}
            onChange={(e) => setLocalLocalModel(e.target.value)}
            onBlur={() => updateSetting('llm_local_model', localLocalModel)}
            placeholder={t('inference_local_model_placeholder')}
          />
        </div>
      </NeuralSection>

      {/* ── 信号区 ── */}
      <NeuralSection title={t('inference_signal')}>
        <NeuralHint>{t('inference_tip')}</NeuralHint>
      </NeuralSection>

    </div>
  );
}
