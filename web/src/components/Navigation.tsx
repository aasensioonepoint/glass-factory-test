import { LANGS, NAV_KEYS, t } from '../i18n';
import type { Lang, NavKey } from '../i18n';

export interface NavigationProps {
  lang: Lang;
  active: NavKey;
  onNavigate: (key: NavKey) => void;
  onLangChange: (lang: Lang) => void;
}

/**
 * Coque de navigation : six entrées et la bascule FR/EN dans <nav>, puis
 * « + Ajouter » FRÈRE de <nav> (hors de la barre), dans le même contexte
 * d'empilement racine. Ordre de focus = ordre DOM.
 */
export function Navigation({ lang, active, onNavigate, onLangChange }: NavigationProps) {
  return (
    <>
      <nav className="nav" aria-label={t(lang, 'navLabel')}>
        <ul className="nav__list">
          {NAV_KEYS.map((key) => (
            <li key={key}>
              <button
                type="button"
                className="nav__item"
                data-nav={key}
                aria-current={key === active ? 'page' : undefined}
                onClick={() => onNavigate(key)}
              >
                {t(lang, key)}
              </button>
            </li>
          ))}
        </ul>
        <div className="lang" role="group" aria-label={t(lang, 'langLabel')}>
          {LANGS.map((code) => (
            <button
              key={code}
              type="button"
              className="lang__item"
              lang={code}
              aria-pressed={code === lang}
              onClick={() => onLangChange(code)}
            >
              {code.toUpperCase()}
            </button>
          ))}
        </div>
      </nav>
      <button type="button" className="add">
        {t(lang, 'add')}
      </button>
    </>
  );
}
