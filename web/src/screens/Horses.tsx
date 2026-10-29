import { useEffect, useState } from 'react';
import type { ReactNode, Ref } from 'react';
import { DELAI_REQUETE_MS, api } from '../api';
import type { ApiClient, Compte } from '../api';
import { focusLibre } from '../components/ProfilePicker';
import type { Lang } from '../i18n';

/*
 * Écran 03 « Chevaux » : liste persistante à gauche, dossier à droite (empilés
 * sous 768 px), contrat de T7 :
 *   GET /api/chevaux      → [{id, nom, sexe, dateNaissance, statut, cour}]
 *   GET /api/chevaux/:id  → {id, nom, sexe, dateNaissance, statut, sire, sejour,
 *                            regime, mesures, restrictions?}
 * Le filtrage par rôle est fait par le serveur, JAMAIS ici : la liste reçue est
 * affichée telle quelle, et le bloc restrictions n'existe que si le champ est
 * présent (absent pour le propriétaire). 404 = hors périmètre.
 *
 * `api.ts` n'expose pas de GET authentifié générique : la requête est faite ici,
 * avec ses conventions (jeton Bearer du client, AbortSignal borné par
 * DELAI_REQUETE_MS, réponse validée avant d'atteindre l'interface). Un 401 vide
 * la session par `client.deconnecter()` seulement si le jeton refusé est encore
 * celui du client (même règle que api.ts) ; sinon la requête est relancée avec
 * le jeton courant.
 *
 * Aucune maquette lisible (écran 03 en EMF) : la coque et les cartes reprennent
 * les jetons de styles.css et le style de ProfilePicker (bleu nuit sur ivoire,
 * 12,66:1 ; l'or n'est pas employé, 2,36:1 sur ivoire). Le gris (#56666d) n'est
 * pas un jeton déclaré : il n'est pas employé. La feuille de l'écran est un
 * <style> React 19 (hoisté, dédoublonné par `href`) : styles.css est hors du
 * write-set, et un style en ligne ne porte ni media query ni :hover.
 */

const TEXTES = {
  fr: {
    listeTitre: 'Liste des chevaux',
    chargementListe: 'Chargement des chevaux…',
    videListe: 'Aucun cheval dans votre périmètre.',
    erreurListeReseau: 'Les chevaux n’ont pas pu être chargés. Vérifiez la connexion.',
    erreurServeur: 'Le serveur n’a pas répondu. Réessayez.',
    reessayer: 'Réessayer',
    chargementCourt: 'Chargement…',
    dossier: 'Dossier',
    invite: 'Choisissez un cheval dans la liste pour ouvrir son dossier.',
    chargementDossier: 'Chargement du dossier…',
    erreurDossierReseau: 'Le dossier n’a pas pu être chargé. Vérifiez la connexion.',
    horsPerimetre: 'Ce cheval est hors de votre périmètre.',
    identite: 'Identité',
    sexe: 'Sexe',
    naissance: 'Date de naissance',
    statut: 'Statut',
    pere: 'Père',
    sejour: 'Séjour',
    sejourValeur: '{cour}, depuis le {date}',
    regime: 'Régime',
    aucunRegime: 'Aucun régime renseigné.',
    mesures: 'Mesures',
    nature: 'Nature',
    valeur: 'Valeur',
    date: 'Date',
    aucuneMesure: 'Aucune mesure enregistrée.',
    restrictions: 'Restrictions',
    aucuneRestriction: 'Aucune restriction.',
    source: 'Source',
    debut: 'Début',
    finPrevue: 'Fin prévue',
    sansFin: 'Non fixée',
    active: 'Active',
    levee: 'Levée',
    nonRenseigne: 'Non renseigné',
    connexionTitre: 'Connexion requise',
    nonConnecte: 'Connectez-vous pour consulter les chevaux.',
    sessionExpiree: 'Votre session a expiré, connectez-vous de nouveau.',
    choisirProfil: 'Choisir un profil',
  },
  en: {
    listeTitre: 'Horse list',
    chargementListe: 'Loading horses…',
    videListe: 'No horse in your scope.',
    erreurListeReseau: 'Horses could not be loaded. Check your connection.',
    erreurServeur: 'The server did not respond. Try again.',
    reessayer: 'Try again',
    chargementCourt: 'Loading…',
    dossier: 'File',
    invite: 'Choose a horse in the list to open its file.',
    chargementDossier: 'Loading the file…',
    erreurDossierReseau: 'The file could not be loaded. Check your connection.',
    horsPerimetre: 'This horse is outside your scope.',
    identite: 'Identity',
    sexe: 'Sex',
    naissance: 'Date of birth',
    statut: 'Status',
    pere: 'Sire',
    sejour: 'Yard',
    sejourValeur: '{cour}, since {date}',
    regime: 'Diet',
    aucunRegime: 'No diet recorded.',
    mesures: 'Measurements',
    nature: 'Type',
    valeur: 'Value',
    date: 'Date',
    aucuneMesure: 'No measurement recorded.',
    restrictions: 'Restrictions',
    aucuneRestriction: 'No restriction.',
    source: 'Source',
    debut: 'Start',
    finPrevue: 'Planned end',
    sansFin: 'Not set',
    active: 'Active',
    levee: 'Lifted',
    nonRenseigne: 'Not recorded',
    connexionTitre: 'Sign-in required',
    nonConnecte: 'Sign in to view the horses.',
    sessionExpiree: 'Your session has expired, sign in again.',
    choisirProfil: 'Choose a profile',
  },
} satisfies Record<Lang, Record<string, string>>;

type Textes = (typeof TEXTES)[Lang];

/*
 * Codes bruts de l'API (graine `api/src/db/seed.ts`) → libellés. Un code inconnu
 * est montré tel quel : jamais un libellé inventé pour une valeur non prévue.
 */
const CODES = {
  fr: {
    statut: { a_l_entrainement: 'À l’entraînement' },
    sexe: { F: 'Femelle', M: 'Mâle' },
    nature: { poids: 'Poids', temperature: 'Température' },
  },
  en: {
    statut: { a_l_entrainement: 'In training' },
    sexe: { F: 'Female', M: 'Male' },
    nature: { poids: 'Weight', temperature: 'Temperature' },
  },
} satisfies Record<Lang, Record<'statut' | 'sexe' | 'nature', Record<string, string>>>;

export type ChampCode = keyof (typeof CODES)[Lang];

/** Libellé d'un code connu, sinon le code brut (`Object.hasOwn` : jamais `constructor`). */
export function libelleCode(lang: Lang, champ: ChampCode, code: string): string {
  const table: Record<string, string> = CODES[lang][champ];
  return Object.hasOwn(table, code) ? (table[code] ?? code) : code;
}

/* ---------- Contrat de T7 : formes validées ---------- */

export interface ChevalResume {
  id: string;
  nom: string;
  sexe: string | null;
  dateNaissance: string | null;
  statut: string | null;
  cour: string | null;
}

export interface Mesure {
  nature: string;
  valeur: string;
  date: string;
}

export interface Restriction {
  source: string;
  debut: string;
  finPrevue: string | null;
  statut: 'active' | 'levee';
}

export interface DossierCheval {
  id: string;
  nom: string;
  sexe: string | null;
  dateNaissance: string | null;
  statut: string | null;
  sire: string | null;
  sejour: { cour: string; depuis: string } | null;
  regime: { description: string } | null;
  mesures: Mesure[];
  /** Absent pour le propriétaire : absent ici aussi, jamais un tableau vide. */
  restrictions?: Restriction[];
}

/** Valeur hors contrat : la réponse entière est refusée. */
const HORS_CONTRAT = Symbol('hors-contrat');

function enregistrement(valeur: unknown): valeur is Record<string, unknown> {
  return typeof valeur === 'object' && valeur !== null && !Array.isArray(valeur);
}

function chaineNonVide(valeur: unknown): valeur is string {
  return typeof valeur === 'string' && valeur !== '';
}

/** `string | null` du contrat ; un champ omis est lu comme `null`. */
function chaineOuNull(valeur: unknown): string | null | typeof HORS_CONTRAT {
  if (valeur === null || valeur === undefined) return null;
  return typeof valeur === 'string' ? valeur : HORS_CONTRAT;
}

/** Liste validée, ou `null` si la forme ne tient pas le contrat. */
export function lireChevaux(valeur: unknown): ChevalResume[] | null {
  if (!Array.isArray(valeur)) return null;
  const chevaux: ChevalResume[] = [];
  for (const item of valeur) {
    if (!enregistrement(item) || !chaineNonVide(item.id) || !chaineNonVide(item.nom)) return null;
    const sexe = chaineOuNull(item.sexe);
    const dateNaissance = chaineOuNull(item.dateNaissance);
    const statut = chaineOuNull(item.statut);
    const cour = chaineOuNull(item.cour);
    if (
      sexe === HORS_CONTRAT ||
      dateNaissance === HORS_CONTRAT ||
      statut === HORS_CONTRAT ||
      cour === HORS_CONTRAT
    ) {
      return null;
    }
    chevaux.push({ id: item.id, nom: item.nom, sexe, dateNaissance, statut, cour });
  }
  return chevaux;
}

function lireMesures(valeur: unknown): Mesure[] | null {
  if (!Array.isArray(valeur)) return null;
  const mesures: Mesure[] = [];
  for (const m of valeur) {
    if (!enregistrement(m)) return null;
    const { nature, valeur: v, date } = m;
    if (typeof nature !== 'string' || typeof v !== 'string' || typeof date !== 'string') return null;
    mesures.push({ nature, valeur: v, date });
  }
  return mesures;
}

function lireRestrictions(valeur: unknown): Restriction[] | null {
  if (!Array.isArray(valeur)) return null;
  const restrictions: Restriction[] = [];
  for (const r of valeur) {
    if (!enregistrement(r)) return null;
    const finPrevue = chaineOuNull(r.finPrevue);
    if (
      typeof r.source !== 'string' ||
      typeof r.debut !== 'string' ||
      finPrevue === HORS_CONTRAT ||
      (r.statut !== 'active' && r.statut !== 'levee')
    ) {
      return null;
    }
    restrictions.push({ source: r.source, debut: r.debut, finPrevue, statut: r.statut });
  }
  return restrictions;
}

/** Dossier validé, ou `null` si la forme ne tient pas le contrat. */
export function lireDossier(valeur: unknown): DossierCheval | null {
  if (!enregistrement(valeur) || !chaineNonVide(valeur.id) || !chaineNonVide(valeur.nom)) {
    return null;
  }
  const sexe = chaineOuNull(valeur.sexe);
  const dateNaissance = chaineOuNull(valeur.dateNaissance);
  const statut = chaineOuNull(valeur.statut);
  const sire = chaineOuNull(valeur.sire);
  if (
    sexe === HORS_CONTRAT ||
    dateNaissance === HORS_CONTRAT ||
    statut === HORS_CONTRAT ||
    sire === HORS_CONTRAT
  ) {
    return null;
  }
  let sejour: DossierCheval['sejour'] = null;
  if (valeur.sejour !== null && valeur.sejour !== undefined) {
    const s = valeur.sejour;
    if (!enregistrement(s) || typeof s.cour !== 'string' || typeof s.depuis !== 'string') {
      return null;
    }
    sejour = { cour: s.cour, depuis: s.depuis };
  }
  let regime: DossierCheval['regime'] = null;
  if (valeur.regime !== null && valeur.regime !== undefined) {
    const r = valeur.regime;
    if (!enregistrement(r) || typeof r.description !== 'string') return null;
    regime = { description: r.description };
  }
  const mesures = lireMesures(valeur.mesures);
  if (mesures === null) return null;
  const dossier: DossierCheval = {
    id: valeur.id,
    nom: valeur.nom,
    sexe,
    dateNaissance,
    statut,
    sire,
    sejour,
    regime,
    mesures,
  };
  // Champ ABSENT : pas de bloc. Présent mais hors contrat : réponse refusée.
  if (valeur.restrictions !== undefined) {
    const restrictions = lireRestrictions(valeur.restrictions);
    if (restrictions === null) return null;
    dossier.restrictions = restrictions;
  }
  return dossier;
}

/* ---------- Requête authentifiée ---------- */

/** `introuvable` : 404, le cheval est hors du périmètre du compte. */
export type ErreurChevaux =
  | 'reseau'
  | 'non_autorise'
  | 'introuvable'
  | 'http'
  | 'reponse_invalide'
  | 'annule';

export type ResultatChevaux<T> = { ok: true; valeur: T } | { ok: false; erreur: ErreurChevaux };

export type Fetch = (input: string, init: RequestInit) => Promise<Response>;

/** Référence stable : un `fetch` par défaut recréé à chaque rendu relancerait les effets. */
const fetchNavigateur: Fetch = (input, init) => globalThis.fetch(input, init);

/** Signal de l'appelant, borné par le délai quand le moteur le permet (comme api.ts). */
function signalBorne(appelant: AbortSignal, delaiMs: number): AbortSignal {
  if (typeof AbortSignal.timeout !== 'function' || typeof AbortSignal.any !== 'function') {
    return appelant;
  }
  return AbortSignal.any([appelant, AbortSignal.timeout(delaiMs)]);
}

export async function lireApi<T>(
  fetcher: Fetch,
  chemin: string,
  jeton: string,
  signal: AbortSignal,
  lire: (valeur: unknown) => T | null,
  delaiMs: number = DELAI_REQUETE_MS,
): Promise<ResultatChevaux<T>> {
  if (signal.aborted) return { ok: false, erreur: 'annule' };
  let reponse: Response;
  try {
    reponse = await fetcher(chemin, {
      method: 'GET',
      headers: { Accept: 'application/json', Authorization: `Bearer ${jeton}` },
      signal: signalBorne(signal, delaiMs),
    });
  } catch {
    return { ok: false, erreur: signal.aborted ? 'annule' : 'reseau' };
  }
  if (reponse.status === 401) return { ok: false, erreur: 'non_autorise' };
  if (reponse.status === 404) return { ok: false, erreur: 'introuvable' };
  if (!reponse.ok) return { ok: false, erreur: 'http' };
  let brut: unknown;
  try {
    brut = (await reponse.json()) as unknown;
  } catch {
    return { ok: false, erreur: signal.aborted ? 'annule' : 'reponse_invalide' };
  }
  const valeur = lire(brut);
  return valeur === null ? { ok: false, erreur: 'reponse_invalide' } : { ok: true, valeur };
}

/* ---------- Vue dérivée ---------- */

export type CauseErreur = 'reseau' | 'serveur';

function cause(erreur: ErreurChevaux): CauseErreur {
  return erreur === 'reseau' ? 'reseau' : 'serveur';
}

/** `reessai` : rechargement demandé par « Réessayer », qui reste monté (inerte) et garde le focus. */
export type EtatListe =
  | { statut: 'chargement'; reessai: boolean }
  | { statut: 'erreur'; cause: CauseErreur }
  | { statut: 'pret'; chevaux: ChevalResume[] };

/** État du dossier, attaché à l'identifiant demandé : un dossier d'un autre cheval n'est jamais montré. */
export type EtatDossier =
  | { id: string; statut: 'chargement'; reessai: boolean }
  | { id: string; statut: 'erreur'; cause: CauseErreur }
  | { id: string; statut: 'introuvable' }
  | { id: string; statut: 'pret'; dossier: DossierCheval };

export type VueListe =
  | { etat: 'chargement'; reessai: boolean }
  | { etat: 'erreur'; cause: CauseErreur }
  | { etat: 'vide' }
  | { etat: 'liste'; chevaux: ChevalResume[]; choisi: string | null };

/**
 * `invite` : la liste est là, rien n'est choisi. `attente` : la liste n'est pas
 * là (chargement, vide, erreur) — le panneau n'invite pas à choisir.
 */
export type VueDossier =
  | { etat: 'invite' }
  | { etat: 'attente' }
  | { etat: 'chargement'; nom: string; reessai: boolean }
  | { etat: 'erreur'; nom: string; cause: CauseErreur }
  | { etat: 'introuvable'; nom: string }
  | { etat: 'dossier'; dossier: DossierCheval };

export type VueChevaux =
  | { etat: 'non_connecte'; sessionExpiree: boolean }
  | { etat: 'connecte'; liste: VueListe; dossier: VueDossier };

export interface Choix {
  id: string;
  nom: string;
}

/** Dérive la vue de l'état du conteneur (pas de seconde source de vérité). */
export function vueChevaux(etat: {
  /** Session reprise en cours de relecture (App) : l'écran attend, il ne conclut rien. */
  verification?: boolean;
  connecte: boolean;
  sessionExpiree: boolean;
  liste: EtatListe;
  choix: Choix | null;
  dossier: EtatDossier | null;
}): VueChevaux {
  if (etat.verification === true) {
    return {
      etat: 'connecte',
      liste: { etat: 'chargement', reessai: false },
      dossier: { etat: 'attente' },
    };
  }
  if (!etat.connecte) return { etat: 'non_connecte', sessionExpiree: etat.sessionExpiree === true };
  const { liste: l, choix, dossier: d } = etat;
  const liste: VueListe =
    l.statut === 'chargement'
      ? { etat: 'chargement', reessai: l.reessai }
      : l.statut === 'erreur'
        ? { etat: 'erreur', cause: l.cause }
        : l.chevaux.length === 0
          ? { etat: 'vide' }
          : { etat: 'liste', chevaux: l.chevaux, choisi: choix?.id ?? null };
  let dossier: VueDossier;
  if (choix === null) dossier = liste.etat === 'liste' ? { etat: 'invite' } : { etat: 'attente' };
  else if (d === null || d.id !== choix.id) {
    dossier = { etat: 'chargement', nom: choix.nom, reessai: false };
  } else if (d.statut === 'chargement') {
    dossier = { etat: 'chargement', nom: choix.nom, reessai: d.reessai };
  } else if (d.statut === 'erreur') dossier = { etat: 'erreur', nom: choix.nom, cause: d.cause };
  else if (d.statut === 'introuvable') dossier = { etat: 'introuvable', nom: choix.nom };
  else dossier = { etat: 'dossier', dossier: d.dossier };
  return { etat: 'connecte', liste, dossier };
}

/*
 * Focus (INTERACTION focus=liste, puis dossier au choix d'un cheval) : un
 * déplacement attendu, jamais un vol (même règle que ProfilePicker).
 *   reessai-liste   — « Réessayer » reste monté et garde le focus pendant le
 *                     rechargement et après un nouvel échec ; liste reçue : le
 *                     premier cheval ; liste vide : le titre de la liste ;
 *   reessai-dossier — idem ; dossier reçu ou 404 : le titre du dossier ;
 *   session         — 401 en cours d'écran : « Choisir un profil », qui
 *                     remplace la grille (sinon le focus tomberait sur <body>) ;
 *   choix           — un cheval choisi : le titre du dossier, APRÈS le rendu
 *                     qui réserve la hauteur du panneau (sous 768 px, sans elle
 *                     le défilement vers le titre est plafonné).
 */
export type AttenteFocus = 'reessai-liste' | 'reessai-dossier' | 'session' | 'choix';

export type CibleFocusChevaux = 'premier' | 'titre-liste' | 'titre-dossier' | 'connexion';

/** Cible du focus attendu dans cette vue ; `garder` : l'attente survit à ce rendu. */
export function cibleFocusChevaux(
  attente: AttenteFocus,
  vue: VueChevaux,
): { cible: CibleFocusChevaux | null; garder: boolean } {
  if (attente === 'session') {
    return { cible: vue.etat === 'non_connecte' ? 'connexion' : null, garder: false };
  }
  if (vue.etat !== 'connecte') return { cible: null, garder: false };
  if (attente === 'choix') {
    const choisi = vue.dossier.etat !== 'invite' && vue.dossier.etat !== 'attente';
    return { cible: choisi ? 'titre-dossier' : null, garder: false };
  }
  if (attente === 'reessai-liste') {
    switch (vue.liste.etat) {
      case 'chargement':
        return { cible: null, garder: true };
      case 'liste':
        return { cible: 'premier', garder: false };
      case 'vide':
        return { cible: 'titre-liste', garder: false };
      case 'erreur':
        return { cible: null, garder: false }; // « Réessayer » a gardé le focus
    }
  }
  if (attente === 'reessai-dossier') {
    switch (vue.dossier.etat) {
      case 'chargement':
        return { cible: null, garder: true };
      case 'dossier':
      case 'introuvable':
        return { cible: 'titre-dossier', garder: false };
      default:
        return { cible: null, garder: false };
    }
  }
  return { cible: null, garder: false };
}

/** Dès 768 px, la liste est une colonne collante qui défile seule (voir CSS). */
export const MEDIA_LARGE = '(min-width: 768px)';

function ecranLarge(): boolean {
  return typeof globalThis.matchMedia === 'function' && globalThis.matchMedia(MEDIA_LARGE).matches;
}

type Focalisable = Pick<HTMLElement, 'focus'> & Partial<Pick<HTMLElement, 'scrollIntoView'>>;

/**
 * Titre du dossier focalisé, jamais avec le défilement implicite du focus (que
 * le navigateur place où il veut : mesuré à 360 px, titre à 558 px sur 780, le
 * dossier hors de vue). Dès 768 px : défilement minimal qui montre le titre —
 * la liste, collante, garde sa position et son propre défilement. Sous 768 px :
 * le dossier, empilé sous la liste, vient en haut de l'écran (sous la pastille,
 * par le scroll-padding de la coque) ; la liste n'est pas re-rendue, sa
 * position reste où le choix l'a laissée, et Maj+Tab y ramène au cheval choisi.
 */
export function focaliserDossier(titre: Focalisable, large: boolean = ecranLarge()): void {
  titre.focus({ preventScroll: true });
  titre.scrollIntoView?.(large ? { block: 'nearest', inline: 'nearest' } : { block: 'start' });
}

/* ---------- Formatage ---------- */

const JOUR = /^(\d{4})-(\d{2})-(\d{2})$/;

type DateLue = { type: 'jour'; date: Date } | { type: 'instant'; t: number };

/** Date du contrat lue : jour AAAA-MM-JJ réel, ou date-heure ISO ; sinon `null`. */
function lireDate(valeur: string): DateLue | null {
  const m = JOUR.exec(valeur);
  if (m !== null) {
    const [annee, mois, jour] = [Number(m[1]), Number(m[2]), Number(m[3])];
    const d = new Date(Date.UTC(annee, mois - 1, jour));
    if (d.getUTCFullYear() !== annee || d.getUTCMonth() !== mois - 1 || d.getUTCDate() !== jour) {
      return null;
    }
    return { type: 'jour', date: d };
  }
  if (/^\d{4}-\d{2}-\d{2}T/.test(valeur)) {
    const t = Date.parse(valeur);
    if (!Number.isNaN(t)) return { type: 'instant', t };
  }
  return null;
}

export type StyleDate = 'long' | 'medium';

/**
 * Date du contrat au format de la langue. Un jour est formaté en UTC : jamais
 * décalé d'un jour par le fuseau. Une date-heure ISO est montrée à l'heure
 * locale, avec le MÊME style de date que les jours de sa colonne. Une valeur
 * illisible est montrée telle quelle, jamais inventée.
 */
export function formatDate(lang: Lang, valeur: string, style: StyleDate = 'long'): string {
  const locale = lang === 'fr' ? 'fr-FR' : 'en-GB';
  const lue = lireDate(valeur);
  if (lue === null) return valeur;
  if (lue.type === 'jour') {
    return new Intl.DateTimeFormat(locale, { dateStyle: style, timeZone: 'UTC' }).format(lue.date);
  }
  return new Intl.DateTimeFormat(locale, { dateStyle: style, timeStyle: 'short' }).format(lue.t);
}

/** `<time dateTime>` pour une valeur ISO lisible seulement ; sinon le texte brut. */
function Quand({ lang, valeur, style }: { lang: Lang; valeur: string; style?: StyleDate }) {
  if (lireDate(valeur) === null) return <>{valeur}</>;
  return <time dateTime={valeur}>{formatDate(lang, valeur, style)}</time>;
}

/* ---------- Styles ---------- */

/*
 * Mobile d'abord : une colonne ; dès 768 px (le point de rupture de la coque),
 * liste à gauche, collante sous la barre haute, avec son propre défilement ;
 * dossier à droite. Cibles ≥ 44 px (--target-min). Le focus d'un bouton est
 * l'anneau de styles.css (button:focus-visible) : aucune règle ici ne pose
 * outline ni box-shadow sur un bouton. Les titres focalisés par script
 * (tabindex -1) reçoivent le même double anneau (jetons --ring-*), sans quoi
 * l'anneau du navigateur (2,14:1 sur ivoire, mesuré par design-review) reste.
 * Le défilement de la liste porte une marge intérieure de 6 px (≥ 5 px
 * d'anneau), compensée par une marge négative : l'anneau n'est pas rogné.
 * Sous 768 px, un cheval choisi réserve au dossier une hauteur d'écran moins
 * 13rem (scroll-padding haut 68 px + marge basse de .main 144 px = 212 px ≤
 * 208 + 4) : sans elle, le dossier encore vide laisse un document trop court
 * et le défilement vers son titre est plafonné (mesuré : 558 px sur 780).
 */
const HAUT_LISTE =
  'var(--safe-top) + var(--bar-h) + var(--bar-rim) + var(--scrollbar-allowance) + var(--scroll-slack)';

const CSS = `
.horses-ecran{min-width:0}
.horses{display:grid;gap:1.5rem;margin-top:1.5rem}
@media (min-width:768px){.horses{grid-template-columns:minmax(14rem,1fr) minmax(0,2fr);align-items:start}.horses__panneau--liste{position:sticky;top:calc(${HAUT_LISTE});max-height:calc(100vh - (${HAUT_LISTE}) - 1.5rem);max-height:calc(100dvh - (${HAUT_LISTE}) - 1.5rem);overflow-y:auto;overscroll-behavior:contain;padding:.375rem;margin:-.375rem}}
.horses__panneau{min-width:0}
@media (max-width:767.98px){.horses__panneau--choisi{min-height:calc(100vh - 13rem);min-height:calc(100dvh - 13rem)}}
.horses__connexion{margin-top:1.5rem}
.horses__titre{margin:0;font-size:1.25rem;line-height:1.3;overflow-wrap:anywhere}
.horses-ecran h2[tabindex='-1']:focus-visible{outline:2px solid transparent;outline-offset:2px;box-shadow:0 0 0 var(--ring-inner) var(--color-ivory),0 0 0 calc(var(--ring-inner) + var(--ring-outer)) var(--color-navy)}
.horses__statut{margin:.25rem 0 0;min-height:1lh;overflow-wrap:anywhere}
.horses__session:empty{min-height:0;margin:0}
.horses__texte{margin:.25rem 0 0;overflow-wrap:anywhere}
.horses__liste{display:grid;gap:.5rem;margin:.75rem 0 0;padding:0;list-style:none}
.horses__cheval,.horses__action{min-height:var(--target-min);min-width:var(--target-min);padding:.625rem 1rem;border:2px solid var(--color-navy);border-radius:.75rem;background:var(--color-ivory);color:var(--color-navy);text-align:start;overflow-wrap:anywhere}
.horses__cheval{display:block;width:100%}
.horses__action{display:inline-block;margin-top:.75rem;font-weight:600}
.horses__action[aria-disabled='true']{border-style:dashed;cursor:not-allowed}
.horses__cheval:hover,.horses__action:not([aria-disabled='true']):hover{text-decoration:underline;text-underline-offset:.25em}
.horses__cheval[aria-current='true']{background:var(--color-navy);color:var(--color-ivory)}
.horses__nom{display:block;font-weight:700}
.horses__detail{display:block;font-size:.875rem}
.horses__carte{margin-top:1rem;padding:1rem;border:1px solid var(--color-navy);border-radius:.75rem}
.horses__sous-titre{margin:0 0 .5rem;font-size:1.0625rem;line-height:1.3}
.horses__champs{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:.25rem 1rem;margin:0}
.horses__champs dt{font-weight:600}
.horses__champs dd{margin:0;overflow-wrap:anywhere}
.horses__table{width:100%;border-collapse:collapse}
.horses__table th,.horses__table td{padding:.375rem .5rem;border-bottom:1px solid var(--color-navy);text-align:start;vertical-align:top;overflow-wrap:break-word}
.horses__table .horses__valeur{overflow-wrap:anywhere}
.horses__table th{font-weight:600}
.horses__restrictions{display:grid;gap:.75rem;margin:0;padding:0;list-style:none}
.horses__badge{display:inline-block;margin-bottom:.25rem;padding:0 .625rem;border:1px solid var(--color-navy);border-radius:999px;font-size:.875rem;font-weight:700}
.horses__badge--active{background:var(--color-navy);color:var(--color-ivory)}
@media (forced-colors:active){.horses__cheval[aria-current='true']{text-decoration:underline;text-decoration-thickness:var(--indicator)}.horses__badge--active{border-width:var(--indicator)}}
`;

/* ---------- Vue ---------- */

function messageListe(textes: Textes, vue: VueListe): string {
  switch (vue.etat) {
    case 'chargement':
      return textes.chargementListe;
    case 'erreur':
      return vue.cause === 'reseau' ? textes.erreurListeReseau : textes.erreurServeur;
    case 'vide':
      return textes.videListe;
    case 'liste':
      return '';
  }
}

function messageDossier(textes: Textes, vue: VueDossier): string {
  switch (vue.etat) {
    case 'invite':
      return textes.invite;
    case 'attente':
      return '';
    case 'chargement':
      return textes.chargementDossier;
    case 'erreur':
      return vue.cause === 'reseau' ? textes.erreurDossierReseau : textes.erreurServeur;
    case 'introuvable':
      return textes.horsPerimetre;
    case 'dossier':
      return '';
  }
}

/** Une absence est montrée comme une absence, jamais comme une valeur. */
function ouAbsent(textes: Textes, valeur: string | null, rendu?: (v: string) => ReactNode): ReactNode {
  if (valeur === null || valeur === '') return textes.nonRenseigne;
  return rendu ? rendu(valeur) : valeur;
}

/** Nom accessible d'un cheval : « nom, statut · cour » — la virgule marque une pause. */
export function libelleCheval(lang: Lang, cheval: ChevalResume): string {
  const details = detailsCheval(lang, cheval);
  return details.length > 0 ? `${cheval.nom}, ${details.join(' · ')}` : cheval.nom;
}

function detailsCheval(lang: Lang, cheval: ChevalResume): string[] {
  const details: string[] = [];
  if (cheval.statut !== null && cheval.statut !== '') {
    details.push(libelleCode(lang, 'statut', cheval.statut));
  }
  if (cheval.cour !== null && cheval.cour !== '') details.push(cheval.cour);
  return details;
}

function Dossier({ lang, dossier }: { lang: Lang; dossier: DossierCheval }) {
  const textes = TEXTES[lang];
  const { sejour, regime, mesures, restrictions } = dossier;
  return (
    <>
      <section className="horses__carte" aria-labelledby="horses-identite">
        <h3 id="horses-identite" className="horses__sous-titre">
          {textes.identite}
        </h3>
        <dl className="horses__champs">
          <dt>{textes.sexe}</dt>
          <dd>{ouAbsent(textes, dossier.sexe, (v) => libelleCode(lang, 'sexe', v))}</dd>
          <dt>{textes.naissance}</dt>
          <dd>{ouAbsent(textes, dossier.dateNaissance, (v) => <Quand lang={lang} valeur={v} />)}</dd>
          <dt>{textes.statut}</dt>
          <dd>{ouAbsent(textes, dossier.statut, (v) => libelleCode(lang, 'statut', v))}</dd>
          <dt>{textes.pere}</dt>
          <dd>{ouAbsent(textes, dossier.sire)}</dd>
          <dt>{textes.sejour}</dt>
          <dd>
            {sejour === null
              ? textes.nonRenseigne
              : textes.sejourValeur
                  .split(/(\{cour\}|\{date\})/)
                  .map((part, i) =>
                    part === '{cour}' ? (
                      sejour.cour
                    ) : part === '{date}' ? (
                      <Quand key={i} lang={lang} valeur={sejour.depuis} />
                    ) : (
                      part
                    ),
                  )}
          </dd>
        </dl>
      </section>
      <section className="horses__carte" aria-labelledby="horses-regime">
        <h3 id="horses-regime" className="horses__sous-titre">
          {textes.regime}
        </h3>
        <p className="horses__texte">{regime === null ? textes.aucunRegime : regime.description}</p>
      </section>
      <section className="horses__carte" aria-labelledby="horses-mesures">
        <h3 id="horses-mesures" className="horses__sous-titre">
          {textes.mesures}
        </h3>
        {mesures.length === 0 ? (
          <p className="horses__texte">{textes.aucuneMesure}</p>
        ) : (
          <table className="horses__table" aria-labelledby="horses-mesures">
            <thead>
              <tr>
                <th scope="col">{textes.nature}</th>
                <th scope="col">{textes.valeur}</th>
                <th scope="col">{textes.date}</th>
              </tr>
            </thead>
            <tbody>
              {mesures.map((m, i) => (
                <tr key={`${m.date}|${m.nature}|${i}`}>
                  <td>{libelleCode(lang, 'nature', m.nature)}</td>
                  {/* Seule la valeur (saisie libre) se coupe n'importe où : sa largeur
                   * minimale tombe à un caractère, les mots des autres colonnes restent entiers. */}
                  <td className="horses__valeur">{m.valeur}</td>
                  <td>
                    <Quand lang={lang} valeur={m.date} style="medium" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {restrictions !== undefined && (
        <section className="horses__carte" aria-labelledby="horses-restrictions">
          <h3 id="horses-restrictions" className="horses__sous-titre">
            {textes.restrictions}
          </h3>
          {restrictions.length === 0 ? (
            <p className="horses__texte">{textes.aucuneRestriction}</p>
          ) : (
            <ul className="horses__restrictions">
              {restrictions.map((r, i) => (
                <li key={`${r.debut}|${r.source}|${i}`}>
                  <span
                    className={
                      r.statut === 'active' ? 'horses__badge horses__badge--active' : 'horses__badge'
                    }
                  >
                    {r.statut === 'active' ? textes.active : textes.levee}
                  </span>
                  <dl className="horses__champs">
                    <dt>{textes.source}</dt>
                    <dd>{r.source}</dd>
                    <dt>{textes.debut}</dt>
                    <dd>
                      <Quand lang={lang} valeur={r.debut} />
                    </dd>
                    <dt>{textes.finPrevue}</dt>
                    <dd>
                      {r.finPrevue === null ? textes.sansFin : <Quand lang={lang} valeur={r.finPrevue} />}
                    </dd>
                  </dl>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}

export interface HorsesViewProps {
  lang: Lang;
  vue: VueChevaux;
  onChoisir: (cheval: ChevalResume) => void;
  onReessayerListe: () => void;
  onReessayerDossier: () => void;
  onConnexion: () => void;
  /** Reçoit le titre du dossier (focalisable par script seulement). */
  titreDossierRef?: Ref<HTMLHeadingElement>;
  /** Reçoit le titre de la liste (focalisable par script seulement). */
  titreListeRef?: Ref<HTMLHeadingElement>;
  /** Reçoit le premier cheval de la liste. */
  premierRef?: Ref<HTMLButtonElement>;
  /** Reçoivent « Réessayer » (liste, dossier) et « Choisir un profil ». */
  reessayerListeRef?: Ref<HTMLButtonElement>;
  reessayerDossierRef?: Ref<HTMLButtonElement>;
  connexionRef?: Ref<HTMLButtonElement>;
}

const SESSION_ID = 'horses-session';

/** « Réessayer », inerte et libellé « Chargement… » pendant le rechargement qu'il a lancé. */
function BoutonReessayer({
  textes,
  enCours,
  onReessayer,
  boutonRef,
}: {
  textes: Textes;
  enCours: boolean;
  onReessayer: () => void;
  boutonRef?: Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={boutonRef}
      type="button"
      className="horses__action"
      aria-disabled={enCours ? true : undefined}
      onClick={enCours ? undefined : onReessayer}
    >
      {enCours ? textes.chargementCourt : textes.reessayer}
    </button>
  );
}

/**
 * Vue pure : props → rendu. La région `horses-session` est PERMANENTE, à la même
 * place dans les deux mises en page : un 401 en cours d'écran y change le texte
 * (annoncé), il n'y insère pas une région déjà remplie.
 */
export function HorsesView({
  lang,
  vue,
  onChoisir,
  onReessayerListe,
  onReessayerDossier,
  onConnexion,
  titreDossierRef,
  titreListeRef,
  premierRef,
  reessayerListeRef,
  reessayerDossierRef,
  connexionRef,
}: HorsesViewProps) {
  const textes = TEXTES[lang];
  const nonConnecte = vue.etat === 'non_connecte';
  const messageSession = nonConnecte
    ? vue.sessionExpiree
      ? textes.sessionExpiree
      : textes.nonConnecte
    : null;
  return (
    <div className="horses-ecran">
      <style href="graffard-horses" precedence="default">
        {CSS}
      </style>
      {nonConnecte && (
        <h2 id="horses-connexion" className="horses__titre horses__connexion">
          {textes.connexionTitre}
        </h2>
      )}
      <p id={SESSION_ID} role="status" className="horses__statut horses__session">
        {messageSession}
      </p>
      {vue.etat === 'non_connecte' ? (
        <button
          ref={connexionRef}
          type="button"
          className="horses__action"
          aria-describedby={SESSION_ID}
          onClick={onConnexion}
        >
          {textes.choisirProfil}
        </button>
      ) : (
        <Grille
          textes={textes}
          lang={lang}
          liste={vue.liste}
          dossier={vue.dossier}
          onChoisir={onChoisir}
          onReessayerListe={onReessayerListe}
          onReessayerDossier={onReessayerDossier}
          titreDossierRef={titreDossierRef}
          titreListeRef={titreListeRef}
          premierRef={premierRef}
          reessayerListeRef={reessayerListeRef}
          reessayerDossierRef={reessayerDossierRef}
        />
      )}
    </div>
  );
}

function Grille({
  textes,
  lang,
  liste,
  dossier,
  onChoisir,
  onReessayerListe,
  onReessayerDossier,
  titreDossierRef,
  titreListeRef,
  premierRef,
  reessayerListeRef,
  reessayerDossierRef,
}: {
  textes: Textes;
  lang: Lang;
  liste: VueListe;
  dossier: VueDossier;
  onChoisir: (cheval: ChevalResume) => void;
  onReessayerListe: () => void;
  onReessayerDossier: () => void;
  titreDossierRef?: Ref<HTMLHeadingElement>;
  titreListeRef?: Ref<HTMLHeadingElement>;
  premierRef?: Ref<HTMLButtonElement>;
  reessayerListeRef?: Ref<HTMLButtonElement>;
  reessayerDossierRef?: Ref<HTMLButtonElement>;
}) {
  const titreDossier =
    dossier.etat === 'invite' || dossier.etat === 'attente'
      ? textes.dossier
      : dossier.etat === 'dossier'
        ? dossier.dossier.nom
        : dossier.nom;
  const reessaiListe = liste.etat === 'chargement' && liste.reessai;
  const reessaiDossier = dossier.etat === 'chargement' && dossier.reessai;
  return (
    <div className="horses">
      <section
        className="horses__panneau horses__panneau--liste"
        aria-labelledby="horses-liste-titre"
        aria-busy={liste.etat === 'chargement'}
      >
        <h2 id="horses-liste-titre" ref={titreListeRef} tabIndex={-1} className="horses__titre">
          {textes.listeTitre}
        </h2>
        <p role="status" className="horses__statut">
          {messageListe(textes, liste)}
        </p>
        {/* Erreur seulement : une liste vide est une réponse, pas un échec à relancer. */}
        {(liste.etat === 'erreur' || reessaiListe) && (
          <BoutonReessayer
            textes={textes}
            enCours={reessaiListe}
            onReessayer={onReessayerListe}
            boutonRef={reessayerListeRef}
          />
        )}
        {liste.etat === 'liste' && (
          <ul className="horses__liste">
            {liste.chevaux.map((cheval, index) => {
              const details = detailsCheval(lang, cheval);
              return (
                <li key={cheval.id}>
                  <button
                    ref={index === 0 ? premierRef : undefined}
                    type="button"
                    className="horses__cheval"
                    aria-label={libelleCheval(lang, cheval)}
                    aria-current={cheval.id === liste.choisi ? 'true' : undefined}
                    aria-controls="horses-dossier"
                    data-cheval={cheval.id}
                    onClick={() => onChoisir(cheval)}
                  >
                    <span className="horses__nom">{cheval.nom}</span>
                    {details.length > 0 && (
                      <>
                        {' '}
                        <span className="horses__detail">{details.join(' · ')}</span>
                      </>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section
        id="horses-dossier"
        className={
          dossier.etat === 'invite' || dossier.etat === 'attente'
            ? 'horses__panneau'
            : 'horses__panneau horses__panneau--choisi'
        }
        aria-labelledby="horses-dossier-titre"
        aria-busy={dossier.etat === 'chargement'}
      >
        <h2 id="horses-dossier-titre" ref={titreDossierRef} tabIndex={-1} className="horses__titre">
          {titreDossier}
        </h2>
        <p role="status" className="horses__statut">
          {messageDossier(textes, dossier)}
        </p>
        {(dossier.etat === 'erreur' || reessaiDossier) && (
          <BoutonReessayer
            textes={textes}
            enCours={reessaiDossier}
            onReessayer={onReessayerDossier}
            boutonRef={reessayerDossierRef}
          />
        )}
        {dossier.etat === 'dossier' && <Dossier lang={lang} dossier={dossier.dossier} />}
      </section>
    </div>
  );
}

/* ---------- Conteneur ---------- */

export interface HorsesProps {
  lang: Lang;
  /** Compte connecté (tenu par App) ; `null` : personne. */
  compte: Compte | null;
  /**
   * Session reprise en cours de relecture par App (`/api/moi`) : l'écran montre
   * son chargement, jamais « Connexion requise » avant la réponse.
   */
  verification?: boolean;
  /** Ramène au sélecteur de profil. */
  onConnexion: () => void;
  /** La session a été refusée (401) : le jeton est déjà oublié. */
  onSessionPerdue?: () => void;
  client?: ApiClient;
  fetcher?: Fetch;
  delaiMs?: number;
}

/**
 * Conteneur : appelle l'API, tient l'état, rend la vue. N'emploie que useState
 * et useEffect (les tests déplient l'arbre hors de React, hooks remplacés).
 * Focus (INTERACTION) : l'ordre DOM met la liste juste après le h1 de l'écran,
 * que App focalise au changement d'entrée ; au choix d'un cheval, le focus passe
 * au titre du dossier. Tous les déplacements (choix, réessai, 401) passent par
 * une attente jouée dans un effet, après le rendu qui place la cible : voir
 * `cibleFocusChevaux`.
 */
export function Horses({
  lang,
  compte,
  verification = false,
  onConnexion,
  onSessionPerdue,
  client = api,
  fetcher = fetchNavigateur,
  delaiMs = DELAI_REQUETE_MS,
}: HorsesProps) {
  const [liste, setListe] = useState<EtatListe>({ statut: 'chargement', reessai: false });
  const [choix, setChoix] = useState<Choix | null>(null);
  const [dossier, setDossier] = useState<EtatDossier | null>(null);
  const [tentativeListe, setTentativeListe] = useState(0);
  const [tentativeDossier, setTentativeDossier] = useState(0);
  const [sessionExpiree, setSessionExpiree] = useState(false);
  const [attente, setAttente] = useState<AttenteFocus | null>(null);
  const [titreDossier, setTitreDossier] = useState<HTMLHeadingElement | null>(null);
  const [titreListe, setTitreListe] = useState<HTMLHeadingElement | null>(null);
  const [premier, setPremier] = useState<HTMLButtonElement | null>(null);
  const [reessayerListeEl, setReessayerListeEl] = useState<HTMLButtonElement | null>(null);
  const [reessayerDossierEl, setReessayerDossierEl] = useState<HTMLButtonElement | null>(null);
  const [connexionEl, setConnexionEl] = useState<HTMLButtonElement | null>(null);

  const connecte = !verification && compte !== null && client.jeton() !== null;
  const choixId = choix?.id ?? null;

  /**
   * 401 : seul le jeton ENVOYÉ est refusé. S'il est encore celui du client, la
   * session est vidée ; sinon une session plus récente a été ouverte entre-temps,
   * et la requête est relancée avec elle.
   */
  function refus(jetonEnvoye: string, relancer: () => void): void {
    if (client.jeton() !== jetonEnvoye) {
      relancer();
      return;
    }
    client.deconnecter();
    setSessionExpiree(true);
    setAttente('session');
    onSessionPerdue?.();
  }

  // Le démontage (ou un nouveau choix) abandonne la requête en vol.
  useEffect(() => {
    if (!connecte) return;
    const jeton = client.jeton();
    if (jeton === null) return;
    const controle = new AbortController();
    void lireApi(fetcher, '/api/chevaux', jeton, controle.signal, lireChevaux, delaiMs).then((r) => {
      if (controle.signal.aborted) return;
      if (r.ok) setListe({ statut: 'pret', chevaux: r.valeur });
      else if (r.erreur === 'non_autorise') refus(jeton, () => setTentativeListe((n) => n + 1));
      else setListe({ statut: 'erreur', cause: cause(r.erreur) });
    });
    return () => controle.abort();
    // `refus` n'est pas une dépendance : nouvelle à chaque rendu, elle relancerait
    // la requête à chaque rendu. Elle lit le `onSessionPerdue` du rendu qui a
    // lancé la requête.
  }, [connecte, client, fetcher, delaiMs, tentativeListe]);

  useEffect(() => {
    if (!connecte || choixId === null) return;
    const jeton = client.jeton();
    if (jeton === null) return;
    const id = choixId;
    const controle = new AbortController();
    const chemin = `/api/chevaux/${encodeURIComponent(id)}`;
    void lireApi(fetcher, chemin, jeton, controle.signal, lireDossier, delaiMs).then((r) => {
      if (controle.signal.aborted) return;
      if (r.ok) setDossier({ id, statut: 'pret', dossier: r.valeur });
      else if (r.erreur === 'non_autorise') refus(jeton, () => setTentativeDossier((n) => n + 1));
      else if (r.erreur === 'introuvable') setDossier({ id, statut: 'introuvable' });
      else setDossier({ id, statut: 'erreur', cause: cause(r.erreur) });
    });
    return () => controle.abort();
  }, [connecte, client, fetcher, delaiMs, choixId, tentativeDossier]);

  const vue = vueChevaux({ verification, connecte, sessionExpiree, liste, choix, dossier });

  const focusAttendu = attente === null ? null : cibleFocusChevaux(attente, vue);
  const cible = focusAttendu?.cible ?? null;
  const garder = focusAttendu?.garder ?? false;

  // Focus attendu : déplacé seulement s'il est libre, sinon l'attente est abandonnée.
  useEffect(() => {
    if (attente === null) return;
    if (cible !== null) {
      const elements = {
        premier,
        'titre-liste': titreListe,
        'titre-dossier': titreDossier,
        connexion: connexionEl,
      };
      const element = elements[cible];
      if (element === null) return; // ref pas encore attachée : le rendu suivant la porte
      const doc = typeof document === 'undefined' ? undefined : document;
      const pose =
        attente === 'reessai-liste'
          ? reessayerListeEl
          : attente === 'reessai-dossier'
            ? reessayerDossierEl
            : null;
      // `choix` suit un clic du même tour : le focus est sur le cheval choisi, il est attendu.
      if (attente !== 'choix' && !focusLibre(doc?.activeElement, [doc?.body, pose])) {
        setAttente(null);
        return;
      }
      if (cible === 'titre-dossier') focaliserDossier(element);
      else element.focus();
    }
    if (!garder) setAttente(null);
  }, [
    attente,
    cible,
    garder,
    premier,
    titreListe,
    titreDossier,
    connexionEl,
    reessayerListeEl,
    reessayerDossierEl,
  ]);

  function choisir(cheval: ChevalResume): void {
    if (choix?.id !== cheval.id) {
      setChoix({ id: cheval.id, nom: cheval.nom });
      setDossier({ id: cheval.id, statut: 'chargement', reessai: false });
    }
    setAttente('choix');
  }

  function reessayerListe(): void {
    setListe({ statut: 'chargement', reessai: true });
    setTentativeListe((n) => n + 1);
    setAttente('reessai-liste');
  }

  function reessayerDossier(): void {
    if (choix === null) return;
    setDossier({ id: choix.id, statut: 'chargement', reessai: true });
    setTentativeDossier((n) => n + 1);
    setAttente('reessai-dossier');
  }

  return (
    <HorsesView
      lang={lang}
      vue={vue}
      onChoisir={choisir}
      onReessayerListe={reessayerListe}
      onReessayerDossier={reessayerDossier}
      onConnexion={onConnexion}
      titreDossierRef={setTitreDossier}
      titreListeRef={setTitreListe}
      premierRef={setPremier}
      reessayerListeRef={setReessayerListeEl}
      reessayerDossierRef={setReessayerDossierEl}
      connexionRef={setConnexionEl}
    />
  );
}
