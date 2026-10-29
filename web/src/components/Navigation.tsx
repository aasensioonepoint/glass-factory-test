import { LANGS, NAV_KEYS, t } from '../i18n';
import type { FocusEvent } from 'react';
import type { Lang, NavKey } from '../i18n';

export interface NavigationProps {
  lang: Lang;
  active: NavKey;
  onNavigate: (key: NavKey) => void;
  onLangChange: (lang: Lang) => void;
}

/* Nom complet de chaque langue, dans sa propre langue (endonyme) : il ne suit
 * pas la langue de l'interface. Il commence par le code visible (« FR », « EN »),
 * ce qui tient WCAG 2.5.3 (le libellé visible est dans le nom accessible). */
const LANG_NAMES: Record<Lang, string> = {
  fr: 'Français',
  en: 'English',
};

/* La liste défile quand les libellés ne tiennent pas (texte à 200 %, écran
 * étroit). Mesuré sous Chromium : une entrée À MOITIÉ visible qui reçoit le focus
 * clavier n'est pas ramenée dans la vue ; on la ramène au bord le plus proche. */
function revealFocused(event: FocusEvent<HTMLButtonElement>): void {
  event.currentTarget.scrollIntoView({ block: 'nearest', inline: 'nearest' });
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
                onFocus={revealFocused}
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
              aria-label={LANG_NAMES[code]}
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
