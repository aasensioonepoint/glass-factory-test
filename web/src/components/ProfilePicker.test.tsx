import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { renderToString } from 'react-dom/server';
import { App } from '../App';
import { JETON_STORAGE_KEY, ROLES, creerClient } from '../api';
import type { ApiClient, Compte, JetonStorage, Persona, Resultat } from '../api';
import {
  ProfilePicker,
  ProfilePickerView,
  ROLE_LABELS,
  cibleFocus,
  focusLibre,
  roleLabel,
  vueProfil,
} from './ProfilePicker';
import type { VueProfil } from './ProfilePicker';

/*
 * Environnement Node, sans DOM : `renderToString` prouve le balisage ; pour le
 * conteneur (effets, clics, focus), `useState` et `useEffect` sont remplacés par
 * un magasin rejoué à chaque rendu, comme dans Navigation.test.tsx. Le magasin
 * garde aussi les nettoyages d'effet : `demonter()` les joue, comme React.
 */
const hooks = vi.hoisted(() => {
  const states: unknown[] = [];
  const deps: (readonly unknown[] | undefined)[] = [];
  const cleanups: ((() => void) | undefined)[] = [];
  let stateCursor = 0;
  let effectCursor = 0;
  return {
    reset(): void {
      states.length = 0;
      deps.length = 0;
      cleanups.length = 0;
    },
    begin(): void {
      stateCursor = 0;
      effectCursor = 0;
    },
    demonter(): void {
      for (const cleanup of cleanups) cleanup?.();
      cleanups.length = 0;
    },
    useState(initial: unknown): [unknown, (next: unknown) => void] {
      const slot = stateCursor++;
      if (!(slot in states)) {
        states[slot] = typeof initial === 'function' ? (initial as () => unknown)() : initial;
      }
      return [
        states[slot],
        (next: unknown) => {
          states[slot] =
            typeof next === 'function' ? (next as (prev: unknown) => unknown)(states[slot]) : next;
        },
      ];
    },
    useEffect(effect: () => void | (() => void), nextDeps?: readonly unknown[]): void {
      const slot = effectCursor++;
      const prev = deps[slot];
      const changed =
        prev === undefined ||
        nextDeps === undefined ||
        nextDeps.some((value, i) => !Object.is(value, prev[i]));
      if (changed) {
        deps[slot] = nextDeps;
        cleanups[slot]?.();
        const cleanup = effect();
        cleanups[slot] = typeof cleanup === 'function' ? cleanup : undefined;
      }
    },
  };
});

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return { ...actual, useState: hooks.useState, useEffect: hooks.useEffect };
});

type Props = Record<string, unknown> & { children?: ReactNode };
type Host = ReactElement<Props>;

function expand(node: ReactNode, out: Host[] = []): Host[] {
  if (Array.isArray(node)) {
    for (const child of node) expand(child as ReactNode, out);
    return out;
  }
  if (!isValidElement<Props>(node)) return out;
  if (typeof node.type === 'function') {
    return expand((node.type as (p: Props) => ReactNode)(node.props), out);
  }
  if (typeof node.type === 'string') out.push(node);
  return expand(node.props.children, out);
}

/** Texte rendu d'un élément : c'est son nom accessible quand il n'a pas d'aria-label. */
function texte(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map((n) => texte(n as ReactNode)).join('');
  if (isValidElement<Props>(node)) return texte(node.props.children);
  return '';
}

function boutons(tree: Host[]): Host[] {
  return tree.filter((el) => el.type === 'button');
}

function bouton(tree: Host[], libelle: string): Host {
  const hit = boutons(tree).find((el) => texte(el) === libelle);
  if (!hit) throw new Error(`bouton introuvable : ${libelle}`);
  return hit;
}

function cartes(tree: Host[]): Host[] {
  return boutons(tree).filter((el) => el.props['data-compte'] !== undefined);
}

function nieme<T>(liste: T[], i: number): T {
  const el = liste[i];
  if (el === undefined) throw new Error(`élément ${i} absent`);
  return el;
}

function click(el: Host): void {
  const onClick = el.props.onClick;
  if (typeof onClick !== 'function') throw new Error('aucun gestionnaire de clic');
  (onClick as () => void)();
}

function appeler(el: Host, prop: string): void {
  const handler = el.props[prop];
  if (typeof handler !== 'function') throw new Error(`aucun gestionnaire ${prop}`);
  (handler as () => void)();
}

function regionStatut(tree: Host[]): Host {
  const region = tree.find((el) => el.props.role === 'status');
  if (!region) throw new Error('région status absente');
  return region;
}

function statut(tree: Host[]): string {
  return texte(regionStatut(tree));
}

function style(el: Host): Record<string, unknown> {
  return (el.props.style ?? {}) as Record<string, unknown>;
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

const PERSONAS: Persona[] = [
  { compteId: '1', nom: 'Camille Morel', role: 'entraineur' },
  { compteId: '2', nom: 'Léa Garnier', role: 'veterinaire' },
  { compteId: 3, nom: 'Hugo Lambert', role: 'cavalier' },
];

const noop = () => {};

function vueElement(
  v: VueProfil,
  lang: 'fr' | 'en' = 'fr',
  extra: Partial<Record<string, () => void>> = {},
) {
  return (
    <ProfilePickerView
      lang={lang}
      vue={v}
      onChoisir={noop}
      onChanger={extra.onChanger ?? noop}
      onReessayer={extra.onReessayer ?? noop}
    />
  );
}

function vue(v: VueProfil, lang: 'fr' | 'en' = 'fr', extra: Partial<Record<string, () => void>> = {}) {
  const el = vueElement(v, lang, extra);
  return { html: renderToString(el), tree: expand(el) };
}

/** Un rendu de la vue seule, magasin de hooks rejoué depuis le début. */
function rendreVue(v: VueProfil): Host[] {
  hooks.begin();
  return expand(vueElement(v));
}

const LISTE: VueProfil = {
  etat: 'liste',
  personas: PERSONAS,
  enCours: null,
  erreurConnexion: false,
  sessionExpiree: false,
};

beforeEach(() => {
  hooks.reset();
  hooks.begin();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ProfilePickerView — états', () => {
  it('liste : chaque persona est un bouton dont le nom accessible est « nom, rôle »', () => {
    const { html, tree } = vue(LISTE);
    expect(html).toContain('<h2 id="profile-titre"');
    expect(html).toContain('aria-labelledby="profile-titre"');
    expect(html).toContain('aria-label="Camille Morel, Entraîneur"');
    const personas = boutons(tree);
    expect(personas).toHaveLength(3);
    expect(personas.map((b) => b.props['aria-label'])).toEqual([
      'Camille Morel, Entraîneur',
      'Léa Garnier, Vétérinaire',
      'Hugo Lambert, Cavalier',
    ]);
    for (const b of personas) {
      expect(b.props.type).toBe('button');
      // WCAG 2.5.3 : le texte visible figure, dans l'ordre, dans le nom accessible.
      expect(String(b.props['aria-label']).replace(',', '')).toBe(texte(b));
    }
    expect(statut(tree)).toBe('');
    expect(texte(tree.find((el) => el.type === 'p'))).toBe(
      'Choisissez un compte fictif pour explorer l’application.',
    );
  });

  it('liste en anglais : libellés de rôle locaux', () => {
    const { tree } = vue(LISTE, 'en');
    expect(boutons(tree).map((b) => b.props['aria-label'])).toEqual([
      'Camille Morel, Trainer',
      'Léa Garnier, Veterinarian',
      'Hugo Lambert, Work rider',
    ]);
  });

  it('chaque rôle du contrat a un libellé en français et en anglais', () => {
    for (const role of ROLES) {
      expect(roleLabel('fr', role)).toMatch(/\S/);
      expect(roleLabel('en', role)).toMatch(/\S/);
    }
    expect(Object.keys(ROLE_LABELS.fr).sort()).toEqual([...ROLES].sort());
  });

  it('chargement : panneau occupé, message annoncé, aucun bouton', () => {
    const { html, tree } = vue({ etat: 'chargement', reessai: false });
    expect(html).toContain('aria-busy="true"');
    expect(statut(tree)).toBe('Chargement des profils…');
    expect(boutons(tree)).toHaveLength(0);
  });

  it('rechargement : « Réessayer » reste monté, inerte, vu inerte et dit « Chargement… »', () => {
    const onReessayer = vi.fn();
    const { tree } = vue({ etat: 'chargement', reessai: true }, 'fr', { onReessayer });
    const b = bouton(tree, 'Chargement…');
    expect(b.props['aria-disabled']).toBe(true);
    expect(b.props.onClick).toBeUndefined();
    expect(style(b).cursor).toBe('not-allowed');
    expect(style(b).borderStyle).toBe('dashed');
    expect(onReessayer).not.toHaveBeenCalled();
    // L'intro ne revient pas pendant le rechargement.
    expect(tree.filter((el) => el.type === 'p')).toHaveLength(1);
  });

  it('vide : message, « Réessayer », pas d’intro', () => {
    const onReessayer = vi.fn();
    const { tree } = vue({ etat: 'vide' }, 'fr', { onReessayer });
    expect(statut(tree)).toBe('Aucun profil de démonstration n’est disponible.');
    click(bouton(tree, 'Réessayer'));
    expect(onReessayer).toHaveBeenCalledOnce();
    expect(tree.filter((el) => el.type === 'p')).toHaveLength(1);
  });

  it('erreur : le réseau et le serveur ont chacun leur message, sans intro', () => {
    const onReessayer = vi.fn();
    const reseau = vue({ etat: 'erreur', cause: 'reseau' }, 'fr', { onReessayer }).tree;
    expect(statut(reseau)).toBe('Les profils n’ont pas pu être chargés. Vérifiez la connexion.');
    click(bouton(reseau, 'Réessayer'));
    expect(onReessayer).toHaveBeenCalledOnce();
    const serveur = vue({ etat: 'erreur', cause: 'serveur' }).tree;
    expect(statut(serveur)).toBe('Le serveur n’a pas répondu. Réessayez.');
    expect(serveur.filter((el) => el.type === 'p')).toHaveLength(1);
  });

  it('connecté : la phrase de connexion est dans la région status et décrit « Changer de profil »', () => {
    const onChanger = vi.fn();
    const { html, tree } = vue(
      { etat: 'connecte', nom: 'Léa Garnier', roles: ['veterinaire'] },
      'fr',
      { onChanger },
    );
    expect(html).toContain('<strong>Léa Garnier</strong>');
    expect(statut(tree)).toBe('Connecté en tant que Léa Garnier — Vétérinaire');
    const changer = bouton(tree, 'Changer de profil');
    const id = regionStatut(tree).props.id;
    expect(typeof id).toBe('string');
    expect(changer.props['aria-describedby']).toBe(id);
    click(changer);
    expect(onChanger).toHaveBeenCalledOnce();
  });

  it('connecté sans nom : « Profil <rôle> », jamais le rôle tenu pour un nom', () => {
    const fr = vue({ etat: 'connecte', nom: null, roles: ['veterinaire'] }).tree;
    expect(statut(fr)).toBe('Connecté en tant que Profil Vétérinaire');
    const en = vue({ etat: 'connecte', nom: null, roles: ['proprietaire'] }, 'en').tree;
    expect(statut(en)).toBe('Signed in as Owner profile');
  });

  it('erreur de connexion, connexion en cours et session expirée sont annoncées', () => {
    expect(statut(vue({ ...LISTE, erreurConnexion: true }).tree)).toMatch(/connexion a échoué/);
    expect(statut(vue({ ...LISTE, enCours: '1' }).tree)).toBe('Connexion…');
    expect(statut(vue({ ...LISTE, sessionExpiree: true }).tree)).toBe(
      'Votre session a expiré, choisissez un profil.',
    );
  });

  it('connexion en cours : la carte choisie est occupée et marquée, les autres inertes', () => {
    // enCours numérique contre un compteId chaîne : même compte.
    const tree = vue({ ...LISTE, enCours: 1 }).tree;
    const [choisie, autre, troisieme] = cartes(tree);
    if (!choisie || !autre || !troisieme) throw new Error('cartes absentes');
    expect(choisie.props['aria-busy']).toBe(true);
    expect(choisie.props['aria-disabled']).toBeUndefined();
    expect(style(choisie).borderStyle).toBe('dashed');
    expect(texte(choisie)).toBe('Camille Morel Entraîneur · Connexion…');
    for (const b of [autre, troisieme]) {
      expect(b.props['aria-disabled']).toBe(true);
      expect(b.props['aria-busy']).toBeUndefined();
      expect(style(b).cursor).toBe('not-allowed');
    }
    // Hors connexion : aucune carte occupée ni inerte.
    for (const b of cartes(vue(LISTE).tree)) {
      expect(b.props['aria-busy']).toBeUndefined();
      expect(b.props['aria-disabled']).toBeUndefined();
    }
  });

  it('la ligne de statut garde sa hauteur même vide (pas de saut de la grille)', () => {
    for (const v of [LISTE, { ...LISTE, enCours: '1' }] as VueProfil[]) {
      expect(style(regionStatut(vue(v).tree)).minHeight).toBe('1lh');
    }
  });

  it('survol : cartes, « Réessayer » et « Changer de profil » se soulignent ; pas les inertes', () => {
    let tree = rendreVue(LISTE);
    appeler(nieme(cartes(tree), 0), 'onPointerEnter');
    tree = rendreVue(LISTE);
    expect(style(nieme(cartes(tree), 0)).textDecoration).toBe('underline');
    expect(style(nieme(cartes(tree), 1)).textDecoration).toBeUndefined();
    appeler(nieme(cartes(tree), 0), 'onPointerLeave');
    expect(style(nieme(cartes(rendreVue(LISTE)), 0)).textDecoration).toBeUndefined();

    for (const v of [
      { etat: 'erreur', cause: 'reseau' },
      { etat: 'connecte', nom: 'A', roles: ['cavalier'] },
    ] as VueProfil[]) {
      hooks.reset();
      appeler(nieme(boutons(rendreVue(v)), 0), 'onPointerEnter');
      expect(style(nieme(boutons(rendreVue(v)), 0)).textDecoration).toBe('underline');
    }

    hooks.reset();
    const enCours: VueProfil = { ...LISTE, enCours: '2' };
    appeler(nieme(cartes(rendreVue(enCours)), 0), 'onPointerEnter');
    expect(style(nieme(cartes(rendreVue(enCours)), 0)).textDecoration).toBeUndefined();
  });

  it('cibles ≥ 44 px et couleurs tirées des jetons seulement', () => {
    const arbres = [
      vue(LISTE).tree,
      vue({ ...LISTE, enCours: '1' }).tree,
      vue({ etat: 'erreur', cause: 'serveur' }).tree,
      vue({ etat: 'chargement', reessai: true }).tree,
      vue({ etat: 'connecte', nom: 'A', roles: ['cavalier'] }).tree,
    ];
    for (const tree of arbres) {
      for (const b of boutons(tree)) {
        expect(style(b).minHeight).toBe('var(--target-min)');
        expect(style(b).minWidth).toBe('var(--target-min)');
        // L'anneau de focus de styles.css passe par box-shadow : jamais écrasé en ligne.
        expect(style(b).boxShadow).toBeUndefined();
        expect(style(b).outline).toBeUndefined();
        // Les variantes changent borderStyle : jamais sous le raccourci `border`.
        expect(style(b).border).toBeUndefined();
        expect(style(b).borderStyle).toMatch(/^(solid|dashed)$/);
      }
      for (const el of tree) {
        const s = JSON.stringify(el.props.style ?? {});
        expect(s).not.toMatch(/#[0-9a-f]{3,8}\b|rgb/i);
        expect(s).not.toMatch(/--color-gold/);
      }
    }
  });
});

describe('vueProfil et focus — fonctions pures', () => {
  it('identifiants réconciliés : un compteId nombre retrouve le persona au compteId chaîne', () => {
    const v = vueProfil({
      verification: false,
      compte: { compteId: 2, roles: ['veterinaire'] },
      personas: { statut: 'pret', liste: PERSONAS },
      enCours: null,
      erreurConnexion: false,
      sessionExpiree: false,
    });
    expect(v).toEqual({ etat: 'connecte', nom: 'Léa Garnier', roles: ['veterinaire'] });
  });

  it('cibleFocus : premier persona, « Réessayer », titre ou « Changer de profil »', () => {
    expect(cibleFocus('ouverture', 'liste')).toEqual({ cible: 'premier', garder: false });
    expect(cibleFocus('ouverture', 'chargement')).toEqual({ cible: null, garder: true });
    expect(cibleFocus('ouverture', 'erreur')).toEqual({ cible: null, garder: false });
    expect(cibleFocus('retour', 'liste')).toEqual({ cible: 'premier', garder: false });
    expect(cibleFocus('retour', 'erreur')).toEqual({ cible: 'reessayer', garder: false });
    expect(cibleFocus('retour', 'vide')).toEqual({ cible: 'reessayer', garder: false });
    expect(cibleFocus('retour', 'chargement')).toEqual({ cible: 'titre', garder: true });
    expect(cibleFocus('reessai', 'chargement')).toEqual({ cible: null, garder: true });
    expect(cibleFocus('reessai', 'liste')).toEqual({ cible: 'premier', garder: false });
    expect(cibleFocus('connexion', 'connecte')).toEqual({ cible: 'changer', garder: false });
  });

  it('focusLibre : nulle part ou sur un élément posé par le panneau, jamais ailleurs', () => {
    const body = { id: 'body' } as unknown as Element;
    const titre = { id: 'titre' } as unknown as Element;
    const planning = { id: 'planning' } as unknown as Element;
    expect(focusLibre(null, [body])).toBe(true);
    expect(focusLibre(undefined, [body])).toBe(true);
    expect(focusLibre(body, [body])).toBe(true);
    expect(focusLibre(titre, [body, titre])).toBe(true);
    expect(focusLibre(planning, [body, titre])).toBe(false);
    expect(focusLibre(planning, [undefined, null])).toBe(false);
  });
});

/** Faux client : chaque méthode répond par la file qu'on lui donne. */
function fauxClient(opts: {
  jeton?: string | null;
  personas?: Resultat<Persona[]>[];
  connecter?: Resultat<Compte>[];
  moi?: Resultat<Compte>[];
}) {
  let jeton = opts.jeton ?? null;
  const client = {
    personas: vi.fn(async (signal?: AbortSignal) => {
      void signal;
      return opts.personas?.shift() ?? { ok: false as const, erreur: 'reseau' as const };
    }),
    connecter: vi.fn(async (compteId: Persona['compteId']) => {
      void compteId;
      const r: Resultat<Compte> = opts.connecter?.shift() ?? { ok: false, erreur: 'http' };
      if (r.ok) jeton = 'j';
      return r;
    }),
    moi: vi.fn(async (signal?: AbortSignal) => {
      void signal;
      const r: Resultat<Compte> = opts.moi?.shift() ?? { ok: false, erreur: 'non_autorise' };
      return r;
    }),
    deconnecter: vi.fn(() => {
      jeton = null;
    }),
    jeton: () => jeton,
  } satisfies ApiClient;
  return client;
}

function rendre(client: ApiClient, lang: 'fr' | 'en' = 'fr'): Host[] {
  hooks.begin();
  return expand(<ProfilePicker lang={lang} client={client} />);
}

/** Joue la ref de rappel d'un élément, comme React à l'attache (`null` au détachement). */
function attacher(el: Host, focus: (() => void) | null): void {
  const ref = el.props.ref;
  if (typeof ref !== 'function') throw new Error('aucune ref de rappel');
  (ref as (node: unknown) => void)(focus === null ? null : { focus });
}

function titreDe(tree: Host[]): Host {
  const h2 = tree.find((el) => el.type === 'h2');
  if (!h2) throw new Error('titre absent');
  return h2;
}

describe('ProfilePicker — conteneur', () => {
  it('sans session : liste, focus au premier persona, connexion, puis changement de profil', async () => {
    const client = fauxClient({
      personas: [{ ok: true, valeur: PERSONAS }],
      connecter: [{ ok: true, valeur: { compteId: '1', roles: ['entraineur'] } }],
    });
    expect(statut(rendre(client))).toBe('Chargement des profils…');
    await flush();

    let tree = rendre(client);
    const personas = cartes(tree);
    expect(personas.map(texte)[0]).toBe('Camille Morel Entraîneur');
    // Seul le premier persona reçoit la ref de focus.
    expect(personas.filter((b) => typeof b.props.ref === 'function')).toHaveLength(1);
    const focusPremier = vi.fn();
    attacher(nieme(personas, 0), focusPremier);
    rendre(client);
    expect(focusPremier).toHaveBeenCalledOnce();
    rendre(client); // un rendu de plus ne vole pas le focus
    expect(focusPremier).toHaveBeenCalledOnce();

    click(nieme(cartes(rendre(client)), 0));
    expect(client.connecter).toHaveBeenCalledWith('1');
    expect(statut(rendre(client))).toBe('Connexion…');
    await flush();

    tree = rendre(client);
    attacher(nieme(personas, 0), null); // la liste est démontée : React détache la ref
    expect(statut(tree)).toBe('Connecté en tant que Camille Morel — Entraîneur');
    const focusChanger = vi.fn();
    attacher(bouton(tree, 'Changer de profil'), focusChanger);
    rendre(client);
    expect(focusChanger).toHaveBeenCalledOnce();

    click(bouton(rendre(client), 'Changer de profil'));
    expect(client.deconnecter).toHaveBeenCalledOnce();
    tree = rendre(client);
    expect(cartes(tree)).toHaveLength(3);
    const focusRetour = vi.fn();
    attacher(nieme(cartes(tree), 0), focusRetour);
    rendre(client);
    expect(focusRetour).toHaveBeenCalledOnce();
    expect(focusPremier).toHaveBeenCalledOnce();
  });

  it('ouverture : le focus déjà pris ailleurs n’est jamais volé', async () => {
    const body = { nom: 'body' };
    vi.stubGlobal('document', { activeElement: { nom: 'Planning' }, body });
    const client = fauxClient({ personas: [{ ok: true, valeur: PERSONAS }] });
    rendre(client);
    await flush();
    const focus = vi.fn();
    attacher(nieme(cartes(rendre(client)), 0), focus);
    rendre(client);
    rendre(client);
    expect(focus).not.toHaveBeenCalled();
  });

  it('ouverture : focus resté sur <body>, le premier persona le prend', async () => {
    const body = { nom: 'body' };
    vi.stubGlobal('document', { activeElement: body, body });
    const client = fauxClient({ personas: [{ ok: true, valeur: PERSONAS }] });
    rendre(client);
    await flush();
    const focus = vi.fn();
    attacher(nieme(cartes(rendre(client)), 0), focus);
    rendre(client);
    expect(focus).toHaveBeenCalledOnce();
  });

  it('une seconde activation pendant la connexion est ignorée', async () => {
    const client = fauxClient({
      personas: [{ ok: true, valeur: PERSONAS }],
      connecter: [{ ok: true, valeur: { compteId: '1', roles: ['entraineur'] } }],
    });
    rendre(client);
    await flush();
    click(nieme(cartes(rendre(client)), 0));
    click(nieme(cartes(rendre(client)), 0)); // double clic
    click(nieme(cartes(rendre(client)), 1)); // autre carte pendant la requête
    expect(client.connecter).toHaveBeenCalledTimes(1);
    await flush();
  });

  it('« Changer de profil » quand la liste n’est pas là : le focus va à « Réessayer », jamais sur <body>', async () => {
    const client = fauxClient({
      jeton: 'j',
      moi: [{ ok: true, valeur: { compteId: 2, roles: ['veterinaire'] } }],
      personas: [{ ok: false, erreur: 'http' }],
    });
    rendre(client);
    await flush();
    let tree = rendre(client);
    expect(statut(tree)).toBe('Connecté en tant que Profil Vétérinaire');
    click(bouton(tree, 'Changer de profil'));
    tree = rendre(client);
    expect(statut(tree)).toBe('Le serveur n’a pas répondu. Réessayez.');
    const focus = vi.fn();
    attacher(bouton(tree, 'Réessayer'), focus);
    rendre(client);
    expect(focus).toHaveBeenCalledOnce();
  });

  it('« Changer de profil » pendant le chargement : le titre, puis le premier persona', async () => {
    const body = { nom: 'body' };
    const doc: { activeElement: unknown; body: unknown } = { activeElement: body, body };
    vi.stubGlobal('document', doc);
    let resoudre: (r: Resultat<Persona[]>) => void = noop;
    const client = fauxClient({
      jeton: 'j',
      moi: [{ ok: true, valeur: { compteId: '1', roles: ['entraineur'] } }],
    });
    client.personas.mockImplementationOnce(
      () => new Promise<Resultat<Persona[]>>((r) => (resoudre = r)),
    );
    rendre(client);
    await flush();
    click(bouton(rendre(client), 'Changer de profil'));
    const tree = rendre(client);
    expect(statut(tree)).toBe('Chargement des profils…');
    const titre = { focus: vi.fn(() => (doc.activeElement = titre)) };
    (titreDe(tree).props.ref as (n: unknown) => void)(titre);
    rendre(client);
    expect(titre.focus).toHaveBeenCalledOnce();
    resoudre({ ok: true, valeur: PERSONAS });
    await flush();
    const focus = vi.fn();
    attacher(nieme(cartes(rendre(client)), 0), focus);
    rendre(client);
    expect(focus).toHaveBeenCalledOnce();
  });

  it('un échec de connexion garde la liste et l’annonce', async () => {
    const client = fauxClient({ personas: [{ ok: true, valeur: PERSONAS }], connecter: [] });
    rendre(client);
    await flush();
    click(nieme(cartes(rendre(client)), 1));
    await flush();
    const tree = rendre(client);
    expect(cartes(tree)).toHaveLength(3);
    expect(statut(tree)).toMatch(/connexion a échoué/);
  });

  it('erreur réseau puis « Réessayer » recharge les profils', async () => {
    const client = fauxClient({
      personas: [{ ok: false, erreur: 'reseau' }, { ok: true, valeur: [] }],
    });
    rendre(client);
    await flush();
    expect(statut(rendre(client))).toBe(
      'Les profils n’ont pas pu être chargés. Vérifiez la connexion.',
    );
    click(bouton(rendre(client), 'Réessayer'));
    const pendant = rendre(client);
    expect(statut(pendant)).toBe('Chargement des profils…');
    expect(bouton(pendant, 'Chargement…').props['aria-disabled']).toBe(true);
    await flush();
    expect(statut(rendre(client))).toBe('Aucun profil de démonstration n’est disponible.');
    expect(client.personas).toHaveBeenCalledTimes(2);
  });

  it('le démontage abandonne la requête en vol ; sa réponse tardive est ignorée', async () => {
    const client = fauxClient({ personas: [{ ok: false, erreur: 'reseau' }] });
    rendre(client);
    const signal = client.personas.mock.calls[0]?.[0];
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal?.aborted).toBe(false);
    hooks.demonter();
    expect(signal?.aborted).toBe(true);
    await flush();
    expect(statut(rendre(client))).toBe('Chargement des profils…');
  });

  it('le démontage abandonne aussi la relecture de session (/api/moi)', async () => {
    const client = fauxClient({
      jeton: 'j',
      moi: [{ ok: true, valeur: { compteId: '1', roles: ['entraineur'] } }],
    });
    rendre(client);
    const signal = client.moi.mock.calls[0]?.[0];
    expect(signal).toBeInstanceOf(AbortSignal);
    hooks.demonter();
    expect(signal?.aborted).toBe(true);
    await flush();
    // Réponse arrivée après l'abandon : ignorée, la vérification n'est pas close.
    expect(statut(rendre(client))).toBe('Chargement des profils…');
  });

  it('session reprise refusée par le serveur (401) : la session est vidée, le sélecteur le dit', async () => {
    const storage: JetonStorage & { data: Map<string, string> } = {
      data: new Map([[JETON_STORAGE_KEY, 'perime']]),
      getItem(k) {
        return this.data.get(k) ?? null;
      },
      setItem(k, v) {
        this.data.set(k, v);
      },
      removeItem(k) {
        this.data.delete(k);
      },
    };
    const fetch = vi.fn(async (url: string) =>
      url === '/api/moi'
        ? new Response('{}', { status: 401 })
        : new Response(JSON.stringify(PERSONAS), { status: 200 }),
    );
    const client = creerClient({ fetch, storage });
    expect(statut(rendre(client))).toBe('Chargement des profils…'); // vérification en cours
    await flush();
    const tree = rendre(client);
    expect(cartes(tree)).toHaveLength(3);
    expect(statut(tree)).toBe('Votre session a expiré, choisissez un profil.');
    expect(client.jeton()).toBeNull();
    expect(storage.data.has(JETON_STORAGE_KEY)).toBe(false);
  });

  it('session reprise acceptée : connecté, nom retrouvé dans la liste malgré un compteId de type différent', async () => {
    const fetch = vi.fn(async (url: string) =>
      url === '/api/moi'
        ? new Response(JSON.stringify({ compteId: '3', acteurId: 9, roles: ['cavalier'] }))
        : new Response(JSON.stringify(PERSONAS)),
    );
    const storage: JetonStorage = {
      getItem: () => 'valide',
      setItem: noop,
      removeItem: noop,
    };
    const client = creerClient({ fetch, storage });
    rendre(client, 'en');
    await flush();
    const tree = rendre(client, 'en');
    expect(statut(tree)).toBe('Signed in as Hugo Lambert — Work rider');
  });
});

describe('App — sélecteur sans session', () => {
  it('le h1 est conservé et le sélecteur visible sous lui', async () => {
    vi.stubGlobal('document', { documentElement: { lang: '' } });
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: noop });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(PERSONAS))),
    );
    const html = renderToString(<App />);
    expect(html).toContain('<h1>Aujourd’hui</h1><section aria-labelledby="profile-titre"');
    expect(html).toContain('Profil de démonstration');
    await flush();
  });
});
