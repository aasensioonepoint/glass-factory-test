import { useEffect, useState } from 'react';
import type { ComponentPropsWithRef, CSSProperties, ReactNode, Ref } from 'react';
import { api, memeCompte } from '../api';
import type { ApiClient, Compte, CompteId, ErreurApi, Persona, Role } from '../api';
import type { Lang } from '../i18n';

/*
 * Sélecteur de profil de démonstration (D4-A) — aucune maquette ne le couvre.
 * Panneau dans <main>, sous le h1, dans le contexte d'empilement racine : rien
 * n'y est positionné, « + Ajouter » (fixe, z 20) reste au-dessus.
 *
 * Styles : aucune classe de styles.css ne convient à un bouton sur fond ivoire
 * (.lang__item est dessiné pour le bleu nuit, .add est fixe) et styles.css est
 * hors du write-set. Les styles sont donc des objets en ligne qui ne lisent QUE
 * les jetons (--color-navy, --color-ivory, --target-min) : bleu nuit sur ivoire,
 * 12,66:1 ; l'or n'est pas employé. L'anneau de focus est celui de styles.css
 * (button:focus-visible, double anneau ivoire puis bleu nuit) : aucun style en
 * ligne ne pose `box-shadow` ni `outline`, qui l'écraseraient. Le survol
 * (soulignement, comme .nav__item:hover) est un état React, faute de classe.
 */

const TEXTES = {
  fr: {
    titre: 'Profil de démonstration',
    intro: 'Choisissez un compte fictif pour explorer l’application.',
    chargement: 'Chargement des profils…',
    chargementCourt: 'Chargement…',
    vide: 'Aucun profil de démonstration n’est disponible.',
    erreurReseau: 'Les profils n’ont pas pu être chargés. Vérifiez la connexion.',
    erreurServeur: 'Le serveur n’a pas répondu. Réessayez.',
    reessayer: 'Réessayer',
    connexion: 'Connexion…',
    erreurConnexion: 'La connexion a échoué. Choisissez de nouveau un profil.',
    sessionExpiree: 'Votre session a expiré, choisissez un profil.',
    connecte: 'Connecté en tant que',
    profilSansNom: 'Profil {role}',
    sansRole: 'sans rôle',
    changer: 'Changer de profil',
    listeLabel: 'Profils disponibles',
  },
  en: {
    titre: 'Demo profile',
    intro: 'Choose a fictitious account to explore the app.',
    chargement: 'Loading profiles…',
    chargementCourt: 'Loading…',
    vide: 'No demo profile is available.',
    erreurReseau: 'Profiles could not be loaded. Check your connection.',
    erreurServeur: 'The server did not respond. Try again.',
    reessayer: 'Try again',
    connexion: 'Signing in…',
    erreurConnexion: 'Sign-in failed. Choose a profile again.',
    sessionExpiree: 'Your session has expired, choose a profile.',
    connecte: 'Signed in as',
    profilSansNom: '{role} profile',
    sansRole: 'no role',
    changer: 'Switch profile',
    listeLabel: 'Available profiles',
  },
} satisfies Record<Lang, Record<string, string>>;

export const ROLE_LABELS = {
  fr: {
    entraineur: 'Entraîneur',
    assistant_entraineur: 'Assistant entraîneur',
    cavalier: 'Cavalier',
    veterinaire: 'Vétérinaire',
    charge_engagements: 'Chargé des engagements',
    proprietaire: 'Propriétaire',
  },
  en: {
    entraineur: 'Trainer',
    assistant_entraineur: 'Assistant trainer',
    cavalier: 'Work rider',
    veterinaire: 'Veterinarian',
    charge_engagements: 'Entries manager',
    proprietaire: 'Owner',
  },
} satisfies Record<Lang, Record<Role, string>>;

export function roleLabel(lang: Lang, role: Role): string {
  return ROLE_LABELS[lang][role];
}

/** Nom accessible d'un persona : son nom puis son rôle, dans l'ordre affiché. */
export function personaLabel(lang: Lang, persona: Persona): string {
  return `${persona.nom}, ${roleLabel(lang, persona.role)}`;
}

/** Un échec de chargement : le réseau n'a rien rendu, ou le serveur a mal répondu. */
export type CauseErreur = 'reseau' | 'serveur';

export function causeErreur(erreur: ErreurApi): CauseErreur {
  return erreur === 'reseau' ? 'reseau' : 'serveur';
}

/** Ce que le panneau montre ; un seul état à la fois. */
export type VueProfil =
  /** `reessai` : rechargement demandé par « Réessayer », qui reste monté et garde le focus. */
  | { etat: 'chargement'; reessai: boolean }
  | { etat: 'erreur'; cause: CauseErreur }
  | { etat: 'vide' }
  | {
      etat: 'liste';
      personas: Persona[];
      enCours: CompteId | null;
      erreurConnexion: boolean;
      sessionExpiree: boolean;
    }
  | { etat: 'connecte'; nom: string | null; roles: Role[] };

export type EtatPersonas =
  | { statut: 'chargement'; reessai: boolean }
  | { statut: 'erreur'; cause: CauseErreur }
  | { statut: 'pret'; liste: Persona[] };

/** Dérive la vue de l'état du conteneur (pas de seconde source de vérité). */
export function vueProfil(etat: {
  verification: boolean;
  compte: Compte | null;
  personas: EtatPersonas;
  enCours: CompteId | null;
  erreurConnexion: boolean;
  sessionExpiree: boolean;
}): VueProfil {
  if (etat.verification) return { etat: 'chargement', reessai: false };
  if (etat.compte !== null) {
    const { compteId, roles, nom } = etat.compte;
    // L'identifiant arrive en chaîne ou en nombre selon la route : comparé en chaîne.
    const persona =
      etat.personas.statut === 'pret'
        ? etat.personas.liste.find((p) => memeCompte(p.compteId, compteId))
        : undefined;
    return { etat: 'connecte', nom: nom ?? persona?.nom ?? null, roles };
  }
  if (etat.personas.statut === 'chargement') {
    return { etat: 'chargement', reessai: etat.personas.reessai };
  }
  if (etat.personas.statut === 'erreur') return { etat: 'erreur', cause: etat.personas.cause };
  if (etat.personas.liste.length === 0) return { etat: 'vide' };
  return {
    etat: 'liste',
    personas: etat.personas.liste,
    enCours: etat.enCours,
    erreurConnexion: etat.erreurConnexion,
    sessionExpiree: etat.sessionExpiree,
  };
}

/*
 * Focus (INTERACTION focus=) : un déplacement attendu, jamais un vol.
 *   ouverture — premier chargement : le premier persona, si personne n'a encore
 *               pris le focus ;
 *   retour    — après « Changer de profil » : le premier persona quand la liste
 *               est là, « Réessayer » en erreur ou à vide, le titre du panneau
 *               pendant le chargement (puis le premier persona) ;
 *   reessai   — après « Réessayer » : le premier persona si la liste arrive ;
 *   connexion — après un profil choisi : « Changer de profil ».
 */
export type FocusAttendu = 'ouverture' | 'retour' | 'reessai' | 'connexion';

export type CibleFocus = 'premier' | 'changer' | 'reessayer' | 'titre';

/** Cible du focus attendu dans cet état ; `garder` : l'attente survit à ce déplacement. */
export function cibleFocus(
  attendu: FocusAttendu,
  etat: VueProfil['etat'],
): { cible: CibleFocus | null; garder: boolean } {
  switch (attendu) {
    case 'ouverture':
      if (etat === 'liste') return { cible: 'premier', garder: false };
      return { cible: null, garder: etat === 'chargement' };
    case 'retour':
      if (etat === 'liste') return { cible: 'premier', garder: false };
      if (etat === 'erreur' || etat === 'vide') return { cible: 'reessayer', garder: false };
      if (etat === 'chargement') return { cible: 'titre', garder: true };
      return { cible: null, garder: false };
    case 'reessai':
      if (etat === 'liste') return { cible: 'premier', garder: false };
      if (etat === 'erreur' || etat === 'vide') return { cible: 'reessayer', garder: false };
      return { cible: null, garder: etat === 'chargement' };
    case 'connexion':
      return { cible: etat === 'connecte' ? 'changer' : null, garder: false };
  }
}

/**
 * Le focus est-il libre ? Oui s'il n'est nulle part (`null`, `<body>`) ou sur un
 * élément que le panneau y a lui-même posé ; sinon quelqu'un l'a pris, et le
 * déplacer serait le voler.
 */
export function focusLibre(
  actif: Element | null | undefined,
  libres: readonly (Element | null | undefined)[],
): boolean {
  if (actif === null || actif === undefined) return true;
  return libres.some((el) => el !== null && el !== undefined && el === actif);
}

const sectionStyle: CSSProperties = { marginTop: '1.5rem', maxWidth: '60rem' };

const titreStyle: CSSProperties = { margin: 0, fontSize: '1.25rem', lineHeight: 1.3 };

const texteStyle: CSSProperties = { margin: '0.25rem 0 0', overflowWrap: 'anywhere' };

/** Une ligne réservée même vide : un message qui arrive ne pousse pas la grille. */
export const statutStyle: CSSProperties = { ...texteStyle, minHeight: '1lh' };

const listeStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 16rem), 1fr))',
  gap: '0.75rem',
  margin: '1rem 0 0',
  padding: 0,
  listStyle: 'none',
};

/** Bouton contour : bleu nuit sur ivoire (12,66:1), cible ≥ 44 px (--target-min). */
export const boutonStyle: CSSProperties = {
  display: 'block',
  width: '100%',
  height: '100%', // une rangée de la grille garde des cartes de même hauteur
  minHeight: 'var(--target-min)',
  minWidth: 'var(--target-min)',
  padding: '0.625rem 1rem',
  // Bordure en trois propriétés, jamais le raccourci `border` : les variantes
  // changent `borderStyle`, et React ne sait pas retirer une longhand sous un
  // raccourci (mesuré : avertissement « don't mix shorthand and non-shorthand »).
  borderWidth: '2px',
  borderStyle: 'solid',
  borderColor: 'var(--color-navy)',
  borderRadius: '0.75rem',
  background: 'var(--color-ivory)',
  color: 'var(--color-navy)',
  textAlign: 'start',
  overflowWrap: 'anywhere',
};

/** Carte choisie, connexion en cours : contour tireté, curseur d'attente. */
export const carteEnCoursStyle: CSSProperties = {
  ...boutonStyle,
  borderStyle: 'dashed',
  cursor: 'progress',
};

/** Autre carte pendant la connexion : inerte. */
export const carteInerteStyle: CSSProperties = { ...boutonStyle, cursor: 'not-allowed' };

const boutonActionStyle: CSSProperties = {
  ...boutonStyle,
  display: 'inline-block',
  width: 'auto',
  height: 'auto',
  marginTop: '0.75rem',
  fontWeight: 600,
};

/*
 * « Réessayer » pendant le rechargement : inerte et vu comme tel — contour
 * tireté, curseur interdit, libellé « Chargement… ». Pas d'opacité : aucun
 * jeton n'en définit, et le texte garde son contraste de 12,66:1.
 */
export const boutonActionInerteStyle: CSSProperties = {
  ...boutonActionStyle,
  borderStyle: 'dashed',
  cursor: 'not-allowed',
};

/** Survol : le soulignement de la coque (.nav__item:hover, .lang__item:hover, .add:hover). */
export const survolStyle: CSSProperties = {
  textDecoration: 'underline',
  textUnderlineOffset: '0.25em',
};

const nomStyle: CSSProperties = { display: 'block', fontWeight: 700 };

const roleStyle: CSSProperties = { display: 'block', fontSize: '0.875rem' };

type BoutonSurvolProps = Omit<ComponentPropsWithRef<'button'>, 'type'> & {
  /** Inerte (aria-disabled) : pas de survol. */
  inerte?: boolean;
};

/** Bouton qui souligne son texte au survol du pointeur. */
function BoutonSurvol({ style, inerte = false, ...props }: BoutonSurvolProps) {
  const [survol, setSurvol] = useState(false);
  return (
    <button
      type="button"
      {...props}
      style={survol && !inerte ? { ...style, ...survolStyle } : style}
      onPointerEnter={() => setSurvol(true)}
      onPointerLeave={() => setSurvol(false)}
    />
  );
}

export interface ProfilePickerViewProps {
  lang: Lang;
  vue: VueProfil;
  onChoisir: (persona: Persona) => void;
  onChanger: () => void;
  onReessayer: () => void;
  /** Reçoit le premier persona. */
  premierRef?: Ref<HTMLButtonElement>;
  /** Reçoit « Changer de profil ». */
  changerRef?: Ref<HTMLButtonElement>;
  /** Reçoit « Réessayer ». */
  reessayerRef?: Ref<HTMLButtonElement>;
  /** Reçoit le titre du panneau (focalisable par script seulement). */
  titreRef?: Ref<HTMLHeadingElement>;
}

/** Phrase de connexion : le nom en gras ; sans nom, « Profil <rôle> », jamais le rôle seul. */
function phraseConnecte(lang: Lang, nom: string | null, roles: Role[]): ReactNode {
  const textes = TEXTES[lang];
  const libelleRoles =
    roles.length > 0 ? roles.map((role) => roleLabel(lang, role)).join(', ') : textes.sansRole;
  if (nom === null) {
    return (
      <>
        {textes.connecte} <strong>{textes.profilSansNom.replace('{role}', libelleRoles)}</strong>
      </>
    );
  }
  return (
    <>
      {textes.connecte} <strong>{nom}</strong>
      {roles.length > 0 && ` — ${libelleRoles}`}
    </>
  );
}

/** Contenu de la région vivante : tout changement d'état y est annoncé, connexion comprise. */
function statut(lang: Lang, vue: VueProfil): ReactNode {
  const textes = TEXTES[lang];
  switch (vue.etat) {
    case 'chargement':
      return textes.chargement;
    case 'erreur':
      return vue.cause === 'reseau' ? textes.erreurReseau : textes.erreurServeur;
    case 'vide':
      return textes.vide;
    case 'liste':
      if (vue.enCours !== null) return textes.connexion;
      if (vue.erreurConnexion) return textes.erreurConnexion;
      return vue.sessionExpiree ? textes.sessionExpiree : '';
    case 'connecte':
      return phraseConnecte(lang, vue.nom, vue.roles);
  }
}

const STATUT_ID = 'profile-statut';

/** Vue pure : props → rendu. */
export function ProfilePickerView({
  lang,
  vue,
  onChoisir,
  onChanger,
  onReessayer,
  premierRef,
  changerRef,
  reessayerRef,
  titreRef,
}: ProfilePickerViewProps) {
  const textes = TEXTES[lang];
  const intro = vue.etat === 'liste' || (vue.etat === 'chargement' && !vue.reessai);
  const reessai = vue.etat === 'chargement' && vue.reessai;
  const avecReessayer = vue.etat === 'erreur' || vue.etat === 'vide' || reessai;
  return (
    <section
      aria-labelledby="profile-titre"
      aria-busy={vue.etat === 'chargement'}
      style={sectionStyle}
    >
      <h2 id="profile-titre" ref={titreRef} tabIndex={-1} style={titreStyle}>
        {textes.titre}
      </h2>
      {intro && <p style={texteStyle}>{textes.intro}</p>}
      {/* Région vivante permanente : un message qui change y est annoncé. */}
      <p id={STATUT_ID} role="status" style={statutStyle}>
        {statut(lang, vue)}
      </p>
      {vue.etat === 'connecte' && (
        <BoutonSurvol
          ref={changerRef}
          style={boutonActionStyle}
          aria-describedby={STATUT_ID}
          onClick={onChanger}
        >
          {textes.changer}
        </BoutonSurvol>
      )}
      {avecReessayer && (
        <BoutonSurvol
          ref={reessayerRef}
          style={reessai ? boutonActionInerteStyle : boutonActionStyle}
          inerte={reessai}
          aria-disabled={reessai ? true : undefined}
          onClick={reessai ? undefined : onReessayer}
        >
          {reessai ? textes.chargementCourt : textes.reessayer}
        </BoutonSurvol>
      )}
      {vue.etat === 'liste' && (
        <ul style={listeStyle} aria-label={textes.listeLabel}>
          {vue.personas.map((persona, index) => {
            const choisi = vue.enCours !== null && memeCompte(vue.enCours, persona.compteId);
            const inerte = vue.enCours !== null && !choisi;
            return (
              <li key={String(persona.compteId)}>
                {/* Nom accessible = « nom, rôle » : explicite, il reprend le texte visible
                 * dans son ordre (WCAG 2.5.3) ; la virgule marque une pause à la lecture. */}
                <BoutonSurvol
                  ref={index === 0 ? premierRef : undefined}
                  style={choisi ? carteEnCoursStyle : inerte ? carteInerteStyle : boutonStyle}
                  inerte={vue.enCours !== null}
                  aria-label={personaLabel(lang, persona)}
                  aria-busy={choisi ? true : undefined}
                  aria-disabled={inerte ? true : undefined}
                  data-compte={String(persona.compteId)}
                  onClick={() => onChoisir(persona)}
                >
                  <span style={nomStyle}>{persona.nom}</span>{' '}
                  <span style={roleStyle}>
                    {roleLabel(lang, persona.role)}
                    {choisi && <span aria-hidden="true"> · {textes.connexion}</span>}
                  </span>
                </BoutonSurvol>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export interface ProfilePickerProps {
  lang: Lang;
  client?: ApiClient;
  /**
   * Compte connecté qui change : connexion, « Changer de profil », session
   * reprise relue (acceptée ou refusée). Lu au moment de l'appel depuis le rendu
   * qui a lancé la requête : passer une fonction stable (un setter d'état).
   */
  onCompteChange?: (compte: Compte | null) => void;
}

/**
 * Conteneur : appelle l'API, tient l'état, rend la vue. N'emploie que useState
 * et useEffect (les éléments à focaliser arrivent par un setter d'état servant
 * de ref de rappel) : `Navigation.test.tsx` déplie <App /> hors de React.
 */
export function ProfilePicker({ lang, client = api, onCompteChange }: ProfilePickerProps) {
  const [personas, setPersonas] = useState<EtatPersonas>({
    statut: 'chargement',
    reessai: false,
  });
  const [tentative, setTentative] = useState(0);
  const [verification, setVerification] = useState(() => client.jeton() !== null);
  const [compte, setCompte] = useState<Compte | null>(null);
  const [enCours, setEnCours] = useState<CompteId | null>(null);
  const [erreurConnexion, setErreurConnexion] = useState(false);
  const [sessionExpiree, setSessionExpiree] = useState(false);
  const [attendu, setAttendu] = useState<FocusAttendu | null>('ouverture');
  const [premier, setPremier] = useState<HTMLButtonElement | null>(null);
  const [changer, setChanger] = useState<HTMLButtonElement | null>(null);
  const [reessayerEl, setReessayerEl] = useState<HTMLButtonElement | null>(null);
  const [titre, setTitre] = useState<HTMLHeadingElement | null>(null);

  // Le démontage (ou le double montage de StrictMode) abandonne la requête.
  useEffect(() => {
    const controle = new AbortController();
    void client.personas(controle.signal).then((r) => {
      if (controle.signal.aborted) return;
      setPersonas(
        r.ok ? { statut: 'pret', liste: r.valeur } : { statut: 'erreur', cause: causeErreur(r.erreur) },
      );
    });
    return () => controle.abort();
  }, [client, tentative]);

  // Session reprise de sessionStorage : relue auprès du serveur ; tout échec la vide,
  // jamais un jeton gardé en silence (401 : session expirée ; sinon : connexion échouée).
  useEffect(() => {
    if (client.jeton() === null) return;
    const controle = new AbortController();
    void client.moi(controle.signal).then((r) => {
      if (controle.signal.aborted) return;
      if (r.ok) {
        setCompte(r.valeur);
        onCompteChange?.(r.valeur);
      } else {
        client.deconnecter();
        onCompteChange?.(null);
        if (r.erreur === 'non_autorise') setSessionExpiree(true);
        else setErreurConnexion(true);
      }
      setVerification(false);
    });
    return () => controle.abort();
    // `onCompteChange` n'est pas une dépendance : une fonction en ligne relancerait
    // /api/moi à chaque rendu (voir ProfilePickerProps).
  }, [client]);

  const vue = vueProfil({ verification, compte, personas, enCours, erreurConnexion, sessionExpiree });

  // Focus attendu : déplacé seulement s'il est libre, sinon l'attente est abandonnée.
  useEffect(() => {
    if (attendu === null) return;
    const { cible, garder } = cibleFocus(attendu, vue.etat);
    if (cible !== null) {
      const elements = { premier, changer, reessayer: reessayerEl, titre };
      const element = elements[cible];
      if (element === null) return; // ref pas encore attachée : le rendu suivant la porte
      const doc = typeof document === 'undefined' ? undefined : document;
      const poses = attendu === 'retour' ? [titre] : attendu === 'reessai' ? [reessayerEl] : [];
      if (!focusLibre(doc?.activeElement, [doc?.body, ...poses])) {
        setAttendu(null);
        return;
      }
      element.focus();
    }
    if (!garder) setAttendu(null);
  }, [attendu, vue.etat, premier, changer, reessayerEl, titre]);

  function choisir(persona: Persona): void {
    if (enCours !== null) return; // une seconde activation pendant la requête est ignorée
    setEnCours(persona.compteId);
    setErreurConnexion(false);
    setSessionExpiree(false);
    void client.connecter(persona.compteId).then((r) => {
      setEnCours(null);
      if (r.ok) {
        setCompte(r.valeur);
        setAttendu('connexion');
        onCompteChange?.(r.valeur);
      } else {
        setErreurConnexion(true);
      }
    });
  }

  function changerDeProfil(): void {
    client.deconnecter();
    setCompte(null);
    setErreurConnexion(false);
    setAttendu('retour');
    onCompteChange?.(null);
  }

  function reessayer(): void {
    setPersonas({ statut: 'chargement', reessai: true });
    setTentative((n) => n + 1);
    setAttendu('reessai');
  }

  return (
    <ProfilePickerView
      lang={lang}
      vue={vue}
      onChoisir={choisir}
      onChanger={changerDeProfil}
      onReessayer={reessayer}
      premierRef={setPremier}
      changerRef={setChanger}
      reessayerRef={setReessayerEl}
      titreRef={setTitre}
    />
  );
}
