'use client';
import { cn } from '@/lib/utils';

interface Props {
  label: string;
  description: string;
  value: string;
  onChange: (val: string) => void;
  t: (key: string) => string;
}

export function LanguageSelector({ label, description, value, onChange, t }: Props) {
  return (
    <div className="flex flex-col space-y-2">
      <div>
        <label className="text-sm font-medium text-cyber-cyan">{label}</label>
        <p className="text-xs text-gray-400 mt-1">{description}</p>
      </div>
      <div className="flex gap-2">
        {['zh', 'en'].map((lang) => (
          <button
            key={lang}
            onClick={() => onChange(lang)}
            className={cn(
              "px-4 py-2 rounded text-sm font-mono transition-all border",
              value === lang
                ? "bg-cyber-cyan/20 border-cyber-cyan text-cyber-cyan shadow-[0_0_10px_rgba(0,230,246,0.3)]"
                : "bg-transparent border-gray-700 text-gray-400 hover:border-gray-500"
            )}
          >
            {t(`lang_${lang}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
