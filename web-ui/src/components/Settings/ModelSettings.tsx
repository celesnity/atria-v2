import { CircleCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Model Settings Tab
 *
 * Shows information about environment-based model configuration.
 * Sensitive config (API keys, model names, base URLs) are configured via .env file,
 * not through the UI.
 */

export function ModelSettings() {
  const { t } = useTranslation('settings');

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Environment Configuration Banner (DESIGN.md: lime block) */}
      <div className="rounded-md p-6 bg-block-lime border border-lime-200">
        <div className="flex gap-4">
          <div className="flex-shrink-0">
            <CircleCheck className="w-6 h-6 text-ink" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-ink mb-2">
              {t('model.title')}
            </h3>
            <p className="text-sm text-ink/85 leading-relaxed mb-4">
              {t('model.description')}
            </p>

            <div className="bg-surface-soft rounded p-3 mb-4">
              <p className="text-xs font-mono text-ink/80">
                <span className="block font-semibold mb-2">{t('model.envVarsTitle')}</span>
                <span className="block">OPENAI_API_KEY=sk-...</span>
                <span className="block">OPENAI_MODEL_NAME=gpt-4o</span>
                <span className="block">OPENAI_API_BASE_URL=https://api.openai.com/v1</span>
                <span className="block text-ink/60"># Optional:</span>
                <span className="block">OPENAI_MODEL_THINKING=o1</span>
                <span className="block">OPENAI_MODEL_VISION=gpt-4o</span>
              </p>
            </div>

            <button
              onClick={() => window.open('/.env.example', '_blank')}
              className="text-xs font-medium px-4 py-2 bg-surface-soft text-ink hover:bg-surface-soft rounded-md transition-colors active:scale-[0.98] whitespace-nowrap"
            >
              {t('model.viewEnvExample')}
            </button>
          </div>
        </div>
      </div>

      {/* Additional Info */}
      <div className="border border-hairline rounded-md p-4 bg-canvas">
        <h4 className="text-sm font-semibold text-ink mb-3">{t('model.whyEnvTitle')}</h4>
        <ul className="text-xs text-ink/70 space-y-2">
          <li className="flex gap-2">
            <span className="text-ink/50 flex-shrink-0">•</span>
            <span>{t('model.reasonSecurity')}</span>
          </li>
          <li className="flex gap-2">
            <span className="text-ink/50 flex-shrink-0">•</span>
            <span>{t('model.reasonFlexibility')}</span>
          </li>
          <li className="flex gap-2">
            <span className="text-ink/50 flex-shrink-0">•</span>
            <span>{t('model.reasonConsistency')}</span>
          </li>
        </ul>
      </div>

      {/* Persona Settings Link */}
      <div className="border border-hairline rounded-md p-4 bg-canvas">
        <p className="text-sm text-ink/70 mb-3">
          {t('model.personasLink')}
        </p>
      </div>
    </div>
  );
}
