import { useEffect, useState } from 'react';
import { Navigation } from './components/Navigation';
import { ProfilePicker } from './components/ProfilePicker';
import { Horses } from './screens/Horses';
import { api } from './api';
import type { ApiClient, Compte, Resultat } from './api';
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

/** Suit une réponse partagée ; l'abandon de CET appelant rend `annule` sans couper la requête. */
function suivre<T>(reponse: Promise<Resultat<T>>, signal?: AbortSignal): Promise<Resultat<T>> {
  if (signal === undefined) return reponse;
  if (signal.aborted) return Promise.resolve({ ok: false, erreur: 'annule' });
  return new Promise((resolve) => {
    const abandon = (): void => resolve({ ok: false, erreur: 'annule' });
    signal.addEventListener('abort', abandon, { once: true });
    void reponse.then((r) => {
      signal.removeEventListener('abort', abandon);
      resolve(r);
    });
  });
}

/**
 * Client de l'application dont la relecture de session (`/api/moi`) en vol est
 * PARTAGÉE : App et ProfilePicker lisent la même réponse, une seule requête part
 * pour un même jeton. Le démontage de ProfilePicker (navigation vers un écran)
 * n'abandonne que SON attente, jamais la requête qu'App attend aussi.
 */
export function clientPartage(client: ApiClient): ApiClient {
  let enVol: { jeton: string; reponse: Promise<Resultat<Compte>> } | null = null;
  return {
    personas: (signal) => client.personas(signal),
    connecter: (compteId, signal) => client.connecter(compteId, signal),
    deconnecter: () => client.deconnecter(),
    jeton: () => client.jeton(),
    moi(signal) {
      const jeton = client.jeton();
      if (jeton === null) return client.moi(signal);
      if (enVol === null || enVol.jeton !== jeton) {
        // Sans signal d'appelant : bornée par le délai du client (api.ts).
        const courant = { jeton, reponse: client.moi() };
        enVol = courant;
        void courant.reponse.then(() => {
          if (enVol === courant) enVol = null;
        });
      }
      return suivre(enVol.reponse, signal);
    },
  };
}

/*
 * Écrans branchés : « horses » rend le dossier cheval ; les autres entrées
 * gardent le sélecteur de profil (inchangé, en attendant leurs écrans). Le
 * compte connecté vit ici : relu par App au lancement quand un jeton existe
 * (quel que soit l'écran montré), puis rapporté par ProfilePicker, lu par Horses.
 * Focus (INTERACTION de TW) : au changement d'entrée, le h1 de l'écran ; il ne
 * devient focalisable (tabindex -1) qu'à la première navigation, pour que le
 * premier rendu reste tel quel et que l'ouverture ne vole aucun focus. Focalisé
 * par script, il porte le double anneau de la coque (jetons --ring-*).
 */
const CSS_APP = `.main h1[tabindex='-1']:focus-visible{outline:2px solid transparent;outline-offset:2px;box-shadow:0 0 0 var(--ring-inner) var(--color-ivory),0 0 0 calc(var(--ring-inner) + var(--ring-outer)) var(--color-navy)}`;

export function App() {
  const [lang, setLang] = useState<Lang>(() => readStoredLang(localStore()));
  const [active, setActive] = useState<NavKey>('today');
  const [client] = useState<ApiClient>(() => clientPartage(api));
  const [compte, setCompte] = useState<Compte | null>(null);
  const [verification, setVerification] = useState(() => client.jeton() !== null);
  const [titre, setTitre] = useState<HTMLHeadingElement | null>(null);
  const [navigue, setNavigue] = useState(false);
  const [focusTitre, setFocusTitre] = useState(false);

  // <html> est hors de la racine React : l'effet synchronise un système externe.
  useEffect(() => {
    syncDocumentLang(document.documentElement, lang);
  }, [lang]);

  // Session reprise : relue ici, pour que tout écran la connaisse, pas seulement
  // celui qui monte ProfilePicker. Une réponse pour un jeton déjà remplacé (une
  // connexion entre-temps) est ignorée ; un refus laisse le compte vide.
  useEffect(() => {
    const jeton = client.jeton();
    if (jeton === null) return;
    const controle = new AbortController();
    void client.moi(controle.signal).then((r) => {
      if (controle.signal.aborted) return;
      setVerification(false);
      if (client.jeton() !== jeton) return;
      setCompte(r.ok ? r.valeur : null);
    });
    return () => controle.abort();
  }, [client]);

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

  /** Un compte rapporté par ProfilePicker clôt aussi la relecture : c'est la même réponse. */
  function compteRapporte(suivant: Compte | null): void {
    setCompte(suivant);
    setVerification(false);
  }

  return (
    <>
      <style href="graffard-app" precedence="default">
        {CSS_APP}
      </style>
      <Navigation lang={lang} active={active} onNavigate={naviguer} onLangChange={changeLang} />
      <main className="main">
        <h1 ref={setTitre} tabIndex={navigue ? -1 : undefined}>
          {t(lang, active)}
        </h1>
        {active === 'horses' ? (
          <Horses
            lang={lang}
            compte={compte}
            verification={verification}
            client={client}
            onConnexion={() => naviguer('today')}
            onSessionPerdue={() => setCompte(null)}
          />
        ) : (
          <ProfilePicker lang={lang} client={client} onCompteChange={compteRapporte} />
        )}
      </main>
    </>
  );
}
