import { useEffect, useState } from 'react';
import { Navigation } from './components/Navigation';
import { ProfilePicker } from './components/ProfilePicker';
import { Horses } from './screens/Horses';
import type { Compte } from './api';
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

/*
 * Écrans branchés : « horses » rend le dossier cheval ; les autres entrées
 * gardent le sélecteur de profil (inchangé, en attendant leurs écrans). Le
 * compte connecté vit ici, rapporté par ProfilePicker, lu par Horses.
 * Focus (INTERACTION de TW) : au changement d'entrée, le h1 de l'écran ; il ne
 * devient focalisable (tabindex -1) qu'à la première navigation, pour que le
 * premier rendu reste tel quel et que l'ouverture ne vole aucun focus.
 */
export function App() {
  const [lang, setLang] = useState<Lang>(() => readStoredLang(localStore()));
  const [active, setActive] = useState<NavKey>('today');
  const [compte, setCompte] = useState<Compte | null>(null);
  const [titre, setTitre] = useState<HTMLHeadingElement | null>(null);
  const [navigue, setNavigue] = useState(false);
  const [focusTitre, setFocusTitre] = useState(false);

  // <html> est hors de la racine React : l'effet synchronise un système externe.
  useEffect(() => {
    syncDocumentLang(document.documentElement, lang);
  }, [lang]);

  // Le focus est un système externe : déplacé une fois par navigation, quand le h1 est attaché.
  useEffect(() => {
    if (!focusTitre || titre === null) return;
    titre.focus();
    setFocusTitre(false);
  }, [focusTitre, titre]);

  function changeLang(next: Lang): void {
    setLang(next);
    storeLang(localStore(), next);
  }

  function naviguer(key: NavKey): void {
    setActive(key);
    setNavigue(true);
    setFocusTitre(true);
  }

  return (
    <>
      <Navigation lang={lang} active={active} onNavigate={naviguer} onLangChange={changeLang} />
      <main className="main">
        <h1 ref={setTitre} tabIndex={navigue ? -1 : undefined}>
          {t(lang, active)}
        </h1>
        {active === 'horses' ? (
          <Horses
            lang={lang}
            compte={compte}
            onConnexion={() => naviguer('today')}
            onSessionPerdue={() => setCompte(null)}
          />
        ) : (
          <ProfilePicker lang={lang} onCompteChange={setCompte} />
        )}
      </main>
    </>
  );
}
