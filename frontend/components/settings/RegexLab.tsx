'use client';

import { useState } from 'react';
import type { I18nKey } from '@/lib/i18n';
import { useSettings } from '@/hooks/useSettings';
import { NeuralInput, NeuralSection, NeuralTextarea } from './NeuralPrimitives';
import { api } from '@/lib/api';

interface Props {
  t: (key: I18nKey) => string;
}

export default function RegexLab({ t }: Props) {
  const { config, updateSetting, refreshSettings } = useSettings();
  const [testInput, setTestInput] = useState('电影名称.2024.1080p.BluRay.x264-TEAM.mkv');
  const [regex, setRegex] = useState('\\.(\\d{4})\\.');
  const [result, setResult] = useState('');
  const [highlightParts, setHighlightParts] = useState<{ text: string; matched: boolean }[] | null>(null);
  const [resetting, setResetting] = useState(false);

  if (!config) return null;

  const regexRules = config.settings.filename_clean_regex ?? '';
  const setRegexRules = (value: string) => updateSetting('filename_clean_regex', value);

  const testRegex = () => {
    try {
      let pattern = regex.trim();
      let flags = 'g';
      const slashMatch = pattern.match(/^\/(.+)\/([a-z]*)$/i);
      if (slashMatch) { pattern = slashMatch[1]; flags = slashMatch[2] || 'g'; }
      if (!flags.includes('g')) flags += 'g';
      const re = new RegExp(pattern, flags);
      const parts: { text: string; matched: boolean }[] = [];
      let lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(testInput)) !== null) {
        if (m[0] === '') { re.lastIndex++; continue; }
        if (m.index > lastIndex) parts.push({ text: testInput.slice(lastIndex, m.index), matched: false });
        parts.push({ text: m[0], matched: true });
        lastIndex = m.index + m[0].length;
      }
      if (lastIndex < testInput.length) parts.push({ text: testInput.slice(lastIndex), matched: false });
      if (parts.some(p => p.matched)) {
        setHighlightParts(parts);
        const debugMatches = [...testInput.matchAll(re)];
        setResult(`${t('regex_match_ok')}: ${JSON.stringify(debugMatches.map(x => Array.from(x)))}`);
      } else {
        setHighlightParts(null);
        setResult(t('regex_no_match'));
      }
    } catch (error) {
      setResult(`${t('regex_error')}: ${error}`);
      setHighlightParts(null);
    }
  };

  const handleReset = async () => {
    if (!confirm(t('regex_reset_confirm'))) return;
    setResetting(true);
    try {
      const res = await api.resetSettings('regex');
      if (res.success) {
        await refreshSettings();
        alert('正则清洗规则已重置为工业级默认值（15条规则）');
      } else {
        alert(`重置失败: ${res.message || '未知错误'}`);
      }
    } catch (error) {
      alert(`重置失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-6">
      <NeuralSection title={t('regex_lab_title')}>
        <p className="text-cyber-cyan/70 text-sm">{t('regex_lab_desc')}</p>
      </NeuralSection>

      <NeuralSection title={t('regex_system_rules')}>
        <NeuralTextarea label={t('regex_filename_clean_regex')} value={regexRules} onChange={(e) => setRegexRules(e.target.value)} rows={12} className="text-sm resize-y" placeholder="# 每行一条正则规则" />
        <p className="text-cyber-cyan/50 text-xs mt-2">修改后点击页面顶部的「保存配置」按钮生效</p>
      </NeuralSection>

      <NeuralSection title={t('regex_test_signal')}>
        <NeuralInput label={t('regex_test_filename')} type="text" value={testInput} onChange={(e) => setTestInput(e.target.value)} />
      </NeuralSection>

      <NeuralSection title="PATTERN">
        <NeuralInput label={t('regex_expression')} type="text" value={regex} onChange={(e) => setRegex(e.target.value)} />
      </NeuralSection>

      <button onClick={testRegex} className="w-full py-3 bg-transparent border-2 border-cyber-cyan text-cyber-cyan font-bold uppercase tracking-widest hover:bg-cyber-cyan hover:text-black transition-all" style={{ boxShadow: '0 0 20px rgba(0, 230, 246, 0.35), inset 0 0 20px rgba(0, 230, 246, 0.08)' }}>
        {t('regex_test_btn')}
      </button>

      {result && (
        <NeuralSection title={t('regex_result_title')}>
          <pre className="text-cyber-cyan font-mono text-sm whitespace-pre-wrap">{result}</pre>
          {highlightParts && (
            <div>
              <div className="text-cyber-cyan/70 text-xs mb-2">{t('regex_preview_highlight')}</div>
              <div className="font-mono text-sm whitespace-pre-wrap break-all">
                {highlightParts.map((p, idx) => (
                  <span key={idx} className={p.matched ? 'bg-[rgba(0,230,246,0.25)] text-cyber-cyan px-0.5 line-through decoration-cyber-cyan' : ''}>{p.text}</span>
                ))}
              </div>
            </div>
          )}
        </NeuralSection>
      )}

      <div className="flex gap-4">
        <button onClick={handleReset} disabled={resetting} className="px-6 py-3 bg-transparent border-2 border-cyber-red text-cyber-red font-bold uppercase tracking-widest hover:bg-cyber-red hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed" style={{ boxShadow: '0 0 20px rgba(255, 1, 60, 0.35), inset 0 0 20px rgba(255, 1, 60, 0.08)' }}>
          {resetting ? '重置中...' : t('btn_reset_defaults')}
        </button>
      </div>

      <NeuralSection title={t('regex_common_title')}>
        <div className="space-y-2 text-sm text-cyber-cyan/70">
          <div><code className="text-cyber-cyan">\\.(\\d</code> - {t('regex_pattern_year')}</div>
          <div><code className="text-cyber-cyan">\\.(1080p|720p|4K)\\.</code> - {t('regex_pattern_res')}</div>
          <div><code className="text-cyber-cyan">\\.(BluRay|WEB-DL|HDTV)\\.</code> - {t('regex_pattern_source')}</div>
        </div>
      </NeuralSection>
    </div>
  );
}
