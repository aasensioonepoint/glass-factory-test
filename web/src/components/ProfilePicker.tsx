import { useEffect, useState } from 'react';
import type { CSSProperties, Ref } from 'react';
import { api } from '../api';
import type { ApiClient, Compte, CompteId, Persona, Role } from '../api';
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
 * (button:focus-visible, double anneau ivoire puis bleu nuit).
 */

const TEXTES = {
  fr: {
    titre: 'Profil de démonstration',
    intro: 'Choisissez un compte fictif pour explorer l’application.',
    chargement: 'Chargement des profils…',
    vide: 'Aucun profil de démonstration n’est disponible.',
    erreur: 'Les profils n’ont pas pu être chargés. Vérifiez la connexion.',
    reessayer: 'Réessayer',
    connexion: 'Connexion…',
    erreurConnexion: 'La connexion a échoué. Choisissez de nouveau un profil.',
    connecte: 'Connecté en tant que',
    changer: 'Changer de profil',
    listeLabel: 'Profils disponibles',
  },
  en: {
    titre: 'Demo profile',
    intro: 'Choose a fictitious account to explore the app.',
    chargement: 'Loading profiles…',
    vide: 'No demo profile is available.',
    erreur: 'Profiles could not be loaded. Check your connection.',
    reessayer: 'Try again',
    connexion: 'Signing in…',
    erreurConnexion: 'Sign-in failed. Choose a profile again.',
    connecte: 'Signed in as',
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

/** Ce que le panneau montre ; un seul état à la fois. */
export type VueProfil =
  /** `reessai` : rechargement demandé par « Réessayer », qui reste monté et garde le focus. */
  | { etat: 'chargement'; reessai: boolean }
  | { etat: 'erreur' }
  | { etat: 'vide' }
  | { etat: 'liste'; personas: Persona[]; enCours: CompteId | null; erreurConnexion: boolean }
  | { etat: 'connecte'; nom: string | null; roles: Role[] };

export type EtatPersonas =
  | { statut: 'chargement'; reessai: boolean }
  | { statut: 'erreur' }
  | { statut: 'pret'; liste: Persona[] };

/** Dérive la vue de l'état du conteneur (pas de seconde source de vérité). */
export function vueProfil(etat: {
  verification: boolean;
  compte: Compte | null;
  personas: EtatPersonas;
  enCours: CompteId | null;
  erreurConnexion: boolean;
}): VueProfil {
  if (etat.verification) return { etat: 'chargement', reessai: false };
  if (etat.compte !== null) {
    const { compteId, roles, nom } = etat.compte;
    const persona =
      etat.personas.statut === 'pret'
        ? etat.personas.liste.find((p) => p.compteId === compteId)
        : undefined;
    return { etat: 'connecte', nom: nom ?? persona?.nom ?? null, roles };
  }
  if (etat.personas.statut === 'chargement') {
    return { etat: 'chargement', reessai: etat.personas.reessai };
  }
  if (etat.personas.statut === 'erreur') return { etat: 'erreur' };
  if (etat.personas.liste.length === 0) return { etat: 'vide' };
  return {
    etat: 'liste',
    personas: etat.personas.liste,
    enCours: etat.enCours,
    erreurConnexion: etat.erreurConnexion,
  };
}

const sectionStyle: CSSProperties = { marginTop: '1.5rem', maxWidth: '60rem' };

const titreStyle: CSSProperties = { margin: 0, fontSize: '1.25rem', lineHeight: 1.3 };

const texteStyle: CSSProperties = { margin: '0.25rem 0 0', overflowWrap: 'anywhere' };

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
  border: '2px solid var(--color-navy)',
  borderRadius: '0.75rem',
  background: 'var(--color-ivory)',
  color: 'var(--color-navy)',
  textAlign: 'start',
  overflowWrap: 'anywhere',
};

const boutonActionStyle: CSSProperties = {
  ...boutonStyle,
  display: 'inline-block',
  width: 'auto',
  height: 'auto',
  marginTop: '0.75rem',
  fontWeight: 600,
};

const nomStyle: CSSProperties = { display: 'block', fontWeight: 700 };

const roleStyle: CSSProperties = { display: 'block', fontSize: '0.875rem' };

export interface ProfilePickerViewProps {
  lang: Lang;
  vue: VueProfil;
  onChoisir: (persona: Persona) => void;
  onChanger: () => void;
  onReessayer: () => void;
  /** Reçoit le premier persona : il prend le focus à l'ouverture de la liste. */
  premierRef?: Ref<HTMLButtonElement>;
  /** Reçoit « Changer de profil ». */
  changerRef?: Ref<HTMLButtonElement>;
}

function message(lang: Lang, vue: VueProfil): string {
  const textes = TEXTES[lang];
  switch (vue.etat) {
    case 'chargement':
      return textes.chargement;
    case 'erreur':
      return textes.erreur;
    case 'vide':
      return textes.vide;
    case 'liste':
      if (vue.enCours !== null) return textes.connexion;
      return vue.erreurConnexion ? textes.erreurConnexion : '';
    case 'connecte':
      return '';
  }
}

/** Vue pure : props → rendu. */
export function ProfilePickerView({
  lang,
  vue,
  onChoisir,
  onChanger,
  onReessayer,
  premierRef,
  changerRef,
}: ProfilePickerViewProps) {
  const textes = TEXTES[lang];
  return (
    <section
      aria-labelledby="profile-titre"
      aria-busy={vue.etat === 'chargement'}
      style={sectionStyle}
    >
      <h2 id="profile-titre" style={titreStyle}>
        {textes.titre}
      </h2>
      {vue.etat === 'connecte' ? (
        <>
          <p style={texteStyle}>
            {textes.connecte}{' '}
            {vue.nom !== null && <strong>{vue.nom}</strong>}
            {vue.nom !== null && vue.roles.length > 0 && ' — '}
            {vue.roles.map((role) => roleLabel(lang, role)).join(', ')}
          </p>
          <button type="button" ref={changerRef} style={boutonActionStyle} onClick={onChanger}>
            {textes.changer}
          </button>
        </>
      ) : (
        <p style={texteStyle}>{textes.intro}</p>
      )}
      {/* Région vivante permanente : un message qui change y est annoncé. */}
      <p role="status" style={texteStyle}>
        {message(lang, vue)}
      </p>
      {(vue.etat === 'erreur' || (vue.etat === 'chargement' && vue.reessai)) && (
        <button
          type="button"
          style={boutonActionStyle}
          aria-disabled={vue.etat === 'chargement' ? true : undefined}
          onClick={vue.etat === 'erreur' ? onReessayer : undefined}
        >
          {textes.reessayer}
        </button>
      )}
      {vue.etat === 'liste' && (
        <ul style={listeStyle} aria-label={textes.listeLabel}>
          {vue.personas.map((persona, index) => (
            <li key={String(persona.compteId)}>
              {/* Nom accessible = « nom, rôle » : explicite, il reprend le texte visible
               * dans son ordre (WCAG 2.5.3) ; la virgule marque une pause à la lecture. */}
              <button
                type="button"
                ref={index === 0 ? premierRef : undefined}
                style={boutonStyle}
                aria-label={personaLabel(lang, persona)}
                data-compte={String(persona.compteId)}
                onClick={() => onChoisir(persona)}
              >
                <span style={nomStyle}>{persona.nom}</span>{' '}
                <span style={roleStyle}>{roleLabel(lang, persona.role)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export interface ProfilePickerProps {
  lang: Lang;
  client?: ApiClient;
}

/**
 * Conteneur : appelle l'API, tient l'état, rend la vue. N'emploie que useState
 * et useEffect (les éléments à focaliser arrivent par un setter d'état servant
 * de ref de rappel) : `Navigation.test.tsx` déplie <App /> hors de React.
 */
export function ProfilePicker({ lang, client = api }: ProfilePickerProps) {
  const [personas, setPersonas] = useState<EtatPersonas>({
    statut: 'chargement',
    reessai: false,
  });
  const [tentative, setTentative] = useState(0);
  const [verification, setVerification] = useState(() => client.jeton() !== null);
  const [compte, setCompte] = useState<Compte | null>(null);
  const [enCours, setEnCours] = useState<CompteId | null>(null);
  const [erreurConnexion, setErreurConnexion] = useState(false);
  const [connexionChoisie, setConnexionChoisie] = useState(false);
  const [premier, setPremier] = useState<HTMLButtonElement | null>(null);
  const [changer, setChanger] = useState<HTMLButtonElement | null>(null);

  useEffect(() => {
    let actif = true;
    void client.personas().then((r) => {
      if (actif) setPersonas(r.ok ? { statut: 'pret', liste: r.valeur } : { statut: 'erreur' });
    });
    return () => {
      actif = false;
    };
  }, [client, tentative]);

  // Session reprise de sessionStorage : relue auprès du serveur ; un 401 la vide.
  useEffect(() => {
    if (client.jeton() === null) return;
    let actif = true;
    void client.moi().then((r) => {
      if (!actif) return;
      if (r.ok) setCompte(r.valeur);
      setVerification(false);
    });
    return () => {
      actif = false;
    };
  }, [client]);

  // INTERACTION focus= : le premier persona prend le focus à l'ouverture de la liste.
  useEffect(() => {
    premier?.focus();
  }, [premier]);

  // Après une connexion choisie, la liste disparaît : le focus va à « Changer de profil ».
  useEffect(() => {
    if (connexionChoisie) changer?.focus();
  }, [changer, connexionChoisie]);

  function choisir(persona: Persona): void {
    if (enCours !== null) return;
    setEnCours(persona.compteId);
    setErreurConnexion(false);
    void client.connecter(persona.compteId).then((r) => {
      setEnCours(null);
      if (r.ok) {
        setCompte(r.valeur);
        setConnexionChoisie(true);
      } else {
        setErreurConnexion(true);
      }
    });
  }

  function changerDeProfil(): void {
    client.deconnecter();
    setCompte(null);
    setConnexionChoisie(false);
    setErreurConnexion(false);
  }

  function reessayer(): void {
    setPersonas({ statut: 'chargement', reessai: true });
    setTentative((n) => n + 1);
  }

  const vue = vueProfil({ verification, compte, personas, enCours, erreurConnexion });

  return (
    <ProfilePickerView
      lang={lang}
      vue={vue}
      onChoisir={choisir}
      onChanger={changerDeProfil}
      onReessayer={reessayer}
      premierRef={setPremier}
      changerRef={setChanger}
    />
  );
}
