import { useEffect, useState } from 'react';
import { Navigation } from './components/Navigation';
import { LANGS, t } from './i18n';
import type { Lang, NavKey } from './i18n';

/** Clé de la langue choisie dans le stockage local (persistance entre deux lancements). */
export const LANG_STORAGE_KEY = 'graffard.lang';

const DEFAULT_LANG: Lang = 'fr';

type LangStorage = Pick<Storage, 'getItem' | 'setItem'>;

/** Le stockage local, ou `null` s'il est absent ou refusé (navigation privée, politique du site). */
function localStore(): LangStorage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** Langue enregistrée, ou le français par défaut — jamais `navigator.language` (décision pilote). */
export function readStoredLang(storage: LangStorage | null): Lang {
  try {
    const stored = storage?.getItem(LANG_STORAGE_KEY);
    return LANGS.find((code) => code === stored) ?? DEFAULT_LANG;
  } catch {
    return DEFAULT_LANG;
  }
}

/** Enregistre la langue ; un échec du stockage est silencieux : la session continue. */
export function storeLang(storage: LangStorage | null, lang: Lang): void {
  try {
    storage?.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    // Quota plein ou stockage refusé : la langue reste celle de la session.
  }
}

/** Reporte la langue sur <html> (WCAG 3.1.1), hors de la racine React. */
export function syncDocumentLang(root: Pick<HTMLElement, 'lang'>, lang: Lang): void {
  root.lang = lang;
}

export function App() {
  const [lang, setLang] = useState<Lang>(() => readStoredLang(localStore()));
  const [active, setActive] = useState<NavKey>('today');

  // <html> est hors de la racine React : l'effet synchronise un système externe.
  useEffect(() => {
    syncDocumentLang(document.documentElement, lang);
  }, [lang]);

  function changeLang(next: Lang): void {
    setLang(next);
    storeLang(localStore(), next);
  }

  return (
    <>
      <Navigation lang={lang} active={active} onNavigate={setActive} onLangChange={changeLang} />
      <main className="main">
        <h1>{t(lang, active)}</h1>
      </main>
    </>
  );
}
