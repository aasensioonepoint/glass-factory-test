import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { renderToString } from 'react-dom/server';
import { App, clientPartage } from '../App';
import { api } from '../api';
import type { ApiClient, Compte, Persona, Resultat } from '../api';
import { ProfilePicker } from '../components/ProfilePicker';
import {
  Horses,
  HorsesView,
  cibleFocusChevaux,
  focaliserDossier,
  formatDate,
  libelleCheval,
  libelleCode,
  lireChevaux,
  lireDossier,
  vueChevaux,
} from './Horses';
import type { ChevalResume, DossierCheval, Fetch, HorsesProps, VueListe } from './Horses';

/*
 * Environnement Node, sans DOM. `renderToString` prouve le balisage ; pour le
 * conteneur, `useState` et `useEffect` sont remplacés par un magasin rangé PAR
 * INSTANCE de composant (chemin dans l'arbre + nom), comme React : dans App,
 * Horses prend la place de ProfilePicker, et un magasin positionnel leur ferait
 * partager des cases. Une instance absente d'un rendu est démontée (nettoyages
 * d'effet joués).
 */
const hooks = vi.hoisted(() => {
  interface Instance {
    states: unknown[];
    deps: (readonly unknown[] | undefined)[];
    cleanups: ((() => void) | undefined)[];
    s: number;
    e: number;
  }
  const instances = new Map<string, Instance>();
  const vues = new Set<string>();
  let courante: Instance | null = null;

  function demonter(cle: string, instance: Instance): void {
    for (const cleanup of instance.cleanups) cleanup?.();
    instances.delete(cle);
  }

  function instance(): Instance {
    if (courante === null) throw new Error('hook appelé hors d’un composant');
    return courante;
  }

  return {
    reset(): void {
      for (const [cle, i] of [...instances]) demonter(cle, i);
      vues.clear();
      courante = null;
    },
    debutRendu(): void {
      vues.clear();
    },
    finRendu(): void {
      for (const [cle, i] of [...instances]) if (!vues.has(cle)) demonter(cle, i);
    },
    entrer(cle: string): void {
      let i = instances.get(cle);
      if (i === undefined) {
        i = { states: [], deps: [], cleanups: [], s: 0, e: 0 };
        instances.set(cle, i);
      }
      i.s = 0;
      i.e = 0;
      vues.add(cle);
      courante = i;
    },
    sortir(): void {
      courante = null;
    },
    useState(initial: unknown): [unknown, (next: unknown) => void] {
      const i = instance();
      const slot = i.s++;
      if (!(slot in i.states)) {
        i.states[slot] = typeof initial === 'function' ? (initial as () => unknown)() : initial;
      }
      return [
        i.states[slot],
        (next: unknown) => {
          i.states[slot] =
            typeof next === 'function' ? (next as (prev: unknown) => unknown)(i.states[slot]) : next;
        },
      ];
    },
    useEffect(effect: () => void | (() => void), nextDeps?: readonly unknown[]): void {
      const i = instance();
      const slot = i.e++;
      const prev = i.deps[slot];
      const changed =
        prev === undefined ||
        nextDeps === undefined ||
        nextDeps.some((value, k) => !Object.is(value, prev[k]));
      if (changed) {
        i.deps[slot] = nextDeps;
        i.cleanups[slot]?.();
        const cleanup = effect();
        i.cleanups[slot] = typeof cleanup === 'function' ? cleanup : undefined;
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

function expand(node: ReactNode, out: Host[], chemin: string): Host[] {
  if (Array.isArray(node)) {
    node.forEach((child: ReactNode, i) => {
      const cle = isValidElement(child) && child.key !== null ? child.key : String(i);
      expand(child, out, `${chemin}[${cle}]`);
    });
    return out;
  }
  if (!isValidElement<Props>(node)) return out;
  if (typeof node.type === 'function') {
    const cle = `${chemin}/${node.type.name}`;
    hooks.entrer(cle);
    const rendu = (node.type as (p: Props) => ReactNode)(node.props);
    hooks.sortir();
    return expand(rendu, out, cle);
  }
  if (typeof node.type === 'string') out.push(node);
  return expand(node.props.children, out, `${chemin}/${String(node.type)}`);
}

/** Un rendu complet : les instances absentes sont démontées. */
function rendre(el: ReactElement): Host[] {
  hooks.debutRendu();
  const tree = expand(el, [], 'racine');
  hooks.finRendu();
  return tree;
}

function texte(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map((n) => texte(n as ReactNode)).join('');
  if (isValidElement<Props>(node)) {
    // Un composant (<Quand>) est déplié pour lire son texte rendu.
    if (typeof node.type === 'function') {
      return texte((node.type as (p: Props) => ReactNode)(node.props));
    }
    return texte(node.props.children);
  }
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

function chevaux(tree: Host[]): Host[] {
  return boutons(tree).filter((el) => el.props['data-cheval'] !== undefined);
}

function click(el: Host | undefined): void {
  const onClick = el?.props.onClick;
  if (typeof onClick !== 'function') throw new Error('aucun gestionnaire de clic');
  (onClick as () => void)();
}

function parId(tree: Host[], id: string): Host {
  const hit = tree.find((el) => el.props.id === id);
  if (!hit) throw new Error(`élément #${id} absent`);
  return hit;
}

/** Texte des régions status de la grille, dans l'ordre (liste puis dossier). */
function statuts(tree: Host[]): string[] {
  return tree
    .filter((el) => el.props.role === 'status' && el.props.id !== 'horses-session')
    .map((el) => texte(el));
}

/** Région permanente de la session : son texte, ou une erreur si elle manque. */
function statutSession(tree: Host[]): string {
  const el = tree.find((e) => e.props.id === 'horses-session');
  if (!el) throw new Error('région horses-session absente');
  expect(el.props.role).toBe('status');
  return texte(el);
}

function titres(tree: Host[], niveau: 'h1' | 'h2' | 'h3'): string[] {
  return tree.filter((el) => el.type === niveau).map((el) => texte(el));
}

/** Joue la ref de rappel d'un élément, comme React à l'attache. */
function attacher(el: Host, focus: (options?: FocusOptions) => void, scrollIntoView?: () => void): void {
  const ref = el.props.ref;
  if (typeof ref !== 'function') throw new Error('aucune ref de rappel');
  (ref as (node: unknown) => void)(scrollIntoView ? { focus, scrollIntoView } : { focus });
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

const noop = () => {};

const COMPTE: Compte = { compteId: '1', roles: ['entraineur'] };

const LISTE: ChevalResume[] = [
  {
    id: 'c1',
    nom: 'Galop Royal',
    sexe: 'M',
    dateNaissance: '2021-04-02',
    statut: 'En entraînement',
    cour: 'Cour A',
  },
  { id: 'c2', nom: 'Belle Attente', sexe: 'F', dateNaissance: null, statut: null, cour: null },
  { id: 'c3', nom: 'King’s Mind', sexe: null, dateNaissance: null, statut: 'Repos', cour: null },
];

/** Dossier d'un compte propriétaire : le champ `restrictions` est ABSENT. */
const DOSSIER: DossierCheval = {
  id: 'c1',
  nom: 'Galop Royal',
  sexe: 'M',
  dateNaissance: '2021-04-02',
  statut: 'En entraînement',
  sire: 'Lope de Vega',
  sejour: { cour: 'Cour A', depuis: '2025-03-12' },
  regime: { description: 'Foin à volonté, 3 kg d’orge matin et soir' },
  mesures: [
    { nature: 'Poids', valeur: '512 kg', date: '2025-04-24' },
    { nature: 'Température', valeur: '37,8 °C', date: '2025-04-23' },
  ],
};

const DOSSIER_RESTREINT = {
  ...DOSSIER,
  restrictions: [
    { source: 'Équipazone 100 mg/ml', debut: '2025-04-24', finPrevue: '2025-04-27', statut: 'active' },
    { source: 'Vaccin grippe', debut: '2025-01-10', finPrevue: null, statut: 'levee' },
  ],
};

function json(corps: unknown, status = 200): Response {
  return new Response(JSON.stringify(corps), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** Faux fetch : une réponse par chemin, consommée dans l'ordre ; inconnu → 500. */
function fauxFetch(routes: Record<string, (() => Response)[]>) {
  return vi.fn<Fetch>(async (url) => {
    const suivante = routes[url]?.shift();
    return suivante ? suivante() : new Response('', { status: 500 });
  });
}

function fauxClient(jeton: string | null = 'j') {
  let courant = jeton;
  const client = {
    personas: vi.fn(async () => ({ ok: true as const, valeur: [] as Persona[] })),
    connecter: vi.fn(async () => ({ ok: false as const, erreur: 'http' as const })),
    moi: vi.fn(async () => ({ ok: false as const, erreur: 'non_autorise' as const })),
    deconnecter: vi.fn(() => {
      courant = null;
    }),
    jeton: () => courant,
  } satisfies ApiClient;
  /** Une autre session remplace le jeton (connexion dans un autre composant). */
  return Object.assign(client, {
    poser: (suivant: string | null) => {
      courant = suivant;
    },
  });
}

/** Réponse retenue : le test décide quand elle arrive. */
function differee() {
  let livrer: (r: Response) => void = noop;
  const promesse = new Promise<Response>((resolve) => {
    livrer = resolve;
  });
  return { promesse, livrer: (r: Response) => livrer(r) };
}

interface Montage {
  client?: ApiClient;
  fetcher: Fetch;
  compte?: Compte | null;
  onConnexion?: () => void;
  onSessionPerdue?: () => void;
  lang?: 'fr' | 'en';
}

function ecran(m: Montage): ReactElement<HorsesProps> {
  return (
    <Horses
      lang={m.lang ?? 'fr'}
      compte={m.compte === undefined ? COMPTE : m.compte}
      client={m.client ?? fauxClient()}
      fetcher={m.fetcher}
      onConnexion={m.onConnexion ?? noop}
      onSessionPerdue={m.onSessionPerdue ?? noop}
    />
  );
}

beforeEach(() => {
  hooks.reset();
});

afterEach(() => {
  hooks.reset();
  api.deconnecter();
  vi.unstubAllGlobals();
});

describe('Horses — liste', () => {
  it('rend la liste reçue telle quelle, avec le jeton Bearer et un signal', async () => {
    const fetcher = fauxFetch({ '/api/chevaux': [() => json(LISTE)] });
    const el = ecran({ fetcher });
    let tree = rendre(el);
    expect(statuts(tree)[0]).toBe('Chargement des chevaux…');
    expect(parId(tree, 'horses-liste-titre').type).toBe('h2');
    await flush();

    const appel = fetcher.mock.calls[0];
    expect(appel?.[0]).toBe('/api/chevaux');
    expect(appel?.[1].method).toBe('GET');
    expect((appel?.[1].headers as Record<string, string>).Authorization).toBe('Bearer j');
    expect(appel?.[1].signal).toBeInstanceOf(AbortSignal);

    tree = rendre(el);
    const liste = chevaux(tree);
    // Aucun filtre côté client : les trois chevaux reçus, dans l'ordre reçu.
    expect(liste.map((b) => b.props['data-cheval'])).toEqual(['c1', 'c2', 'c3']);
    expect(liste.map(texte)).toEqual([
      'Galop Royal En entraînement · Cour A',
      'Belle Attente',
      'King’s Mind Repos',
    ]);
    for (const b of liste) {
      expect(b.props.type).toBe('button');
      expect(b.props['aria-current']).toBeUndefined();
      expect(b.props['aria-controls']).toBe('horses-dossier');
    }
    // Nom accessible « nom, statut · cour » : la virgule marque la pause.
    expect(liste.map((b) => b.props['aria-label'])).toEqual([
      'Galop Royal, En entraînement · Cour A',
      'Belle Attente',
      'King’s Mind, Repos',
    ]);
    expect(statuts(tree)).toEqual(['', 'Choisissez un cheval dans la liste pour ouvrir son dossier.']);
    expect(titres(tree, 'h2')).toEqual(['Liste des chevaux', 'Dossier']);
  });

  it('pendant le chargement, le panneau dossier n’invite pas à choisir', () => {
    const tree = rendre(ecran({ fetcher: vi.fn<Fetch>(() => new Promise<Response>(noop)) }));
    expect(statuts(tree)).toEqual(['Chargement des chevaux…', '']);
  });

  it('vide : message, ni « Réessayer » ni invitation à choisir', async () => {
    const fetcher = fauxFetch({ '/api/chevaux': [() => json([])] });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    const tree = rendre(el);
    expect(statuts(tree)).toEqual(['Aucun cheval dans votre périmètre.', '']);
    expect(boutons(tree)).toHaveLength(0);
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('erreur : « Réessayer » reste monté, inerte (« Chargement… »), garde le focus ; liste reçue : premier cheval', async () => {
    const fetcher = fauxFetch({
      '/api/chevaux': [() => json({}, 503), () => json({}, 503), () => json(LISTE)],
    });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    let tree = rendre(el);
    expect(statuts(tree)).toEqual(['Le serveur n’a pas répondu. Réessayez.', '']);
    const focusReessayer = vi.fn();
    attacher(bouton(tree, 'Réessayer'), focusReessayer);
    const position = tree.indexOf(bouton(tree, 'Réessayer'));

    click(bouton(tree, 'Réessayer'));
    tree = rendre(el);
    // Même place dans l'arbre, inerte : React garde le nœud, et le focus avec lui.
    const inerte = bouton(tree, 'Chargement…');
    expect(tree.indexOf(inerte)).toBe(position);
    expect(inerte.props['aria-disabled']).toBe(true);
    expect(inerte.props.onClick).toBeUndefined();
    expect(statuts(tree)[0]).toBe('Chargement des chevaux…');

    await flush(); // second échec : le bouton redevient « Réessayer », à la même place
    tree = rendre(el);
    expect(tree.indexOf(bouton(tree, 'Réessayer'))).toBe(position);
    expect(bouton(tree, 'Réessayer').props['aria-disabled']).toBeUndefined();
    expect(focusReessayer).not.toHaveBeenCalled(); // rien ne le lui a pris

    click(bouton(tree, 'Réessayer'));
    rendre(el);
    await flush(); // succès : le focus va au premier cheval
    tree = rendre(el);
    const focusPremier = vi.fn();
    attacher(chevaux(tree)[0] as Host, focusPremier);
    rendre(el);
    expect(focusPremier).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('réponse hors contrat (identifiant numérique) : erreur serveur, jamais une liste partielle', async () => {
    const fetcher = fauxFetch({ '/api/chevaux': [() => json([{ id: 1, nom: 'X' }])] });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    const tree = rendre(el);
    expect(chevaux(tree)).toHaveLength(0);
    expect(statuts(tree)[0]).toBe('Le serveur n’a pas répondu. Réessayez.');
  });

  it('réseau en panne : message réseau', async () => {
    const fetcher = vi.fn<Fetch>(async () => {
      throw new TypeError('fetch failed');
    });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    expect(statuts(rendre(el))[0]).toBe(
      'Les chevaux n’ont pas pu être chargés. Vérifiez la connexion.',
    );
  });
});

describe('Horses — dossier', () => {
  async function ouvrir(dossier: unknown, status = 200) {
    const fetcher = fauxFetch({
      '/api/chevaux': [() => json(LISTE)],
      '/api/chevaux/c1': [() => json(dossier, status)],
    });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    const focus = vi.fn();
    attacher(parId(rendre(el), 'horses-dossier-titre'), focus);
    // React rend de nouveau après l'attache de la ref : le gestionnaire voit le titre.
    click(chevaux(rendre(el))[0]);
    const pendant = rendre(el);
    return { el, fetcher, focus, pendant };
  }

  /** Balisage du dossier tel que rendu : la vue de l'instance montée, hors magasin. */
  function html(el: ReactElement<HorsesProps>): string {
    hooks.entrer('racine/Horses');
    const vue = Horses(el.props);
    hooks.sortir();
    return renderToString(vue);
  }

  it('au choix : focus au titre du dossier, chargement annoncé, puis mesures et régime', async () => {
    const { el, fetcher, focus, pendant } = await ouvrir(DOSSIER);
    expect(focus).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[1]?.[0]).toBe('/api/chevaux/c1');
    expect(texte(parId(pendant, 'horses-dossier-titre'))).toBe('Galop Royal');
    expect(statuts(pendant)[1]).toBe('Chargement du dossier…');
    expect(chevaux(pendant)[0]?.props['aria-current']).toBe('true');
    await flush();

    const tree = rendre(el);
    expect(statuts(tree)[1]).toBe('');
    expect(titres(tree, 'h3')).toEqual(['Identité', 'Régime', 'Mesures']);
    const balisage = html(el);
    expect(balisage).toContain('Foin à volonté, 3 kg d’orge matin et soir');
    expect(balisage).toContain('<td>Poids</td><td class="horses__valeur">512 kg</td>');
    // Colonne Date des mesures : style « medium » pour toutes ses lignes.
    expect(balisage).toContain('<time dateTime="2025-04-24">24 avr. 2025</time>');
    expect(balisage).toContain('<time dateTime="2021-04-02">2 avril 2021</time>');
    expect(balisage).toContain('Lope de Vega');
    // `<!-- -->` : séparateur de deux nœuds texte voisins dans le rendu serveur.
    expect(balisage).toMatch(
      /Cour A(<!-- -->)?, depuis le <time dateTime="2025-03-12">12 mars 2025<\/time>/,
    );
    expect(balisage).toContain('<th scope="col">Nature</th>');
  });

  it('champ restrictions ABSENT (propriétaire) : aucun bloc restrictions', async () => {
    const { el } = await ouvrir(DOSSIER);
    await flush();
    const tree = rendre(el);
    expect(titres(tree, 'h3')).not.toContain('Restrictions');
    expect(html(el)).not.toContain('horses-restrictions');
  });

  it('champ restrictions présent : bloc avec statut, fin prévue ou « Non fixée »', async () => {
    const { el } = await ouvrir(DOSSIER_RESTREINT);
    await flush();
    const tree = rendre(el);
    expect(titres(tree, 'h3')).toEqual(['Identité', 'Régime', 'Mesures', 'Restrictions']);
    const balisage = html(el);
    expect(balisage).toContain('horses__badge horses__badge--active">Active</span>');
    expect(balisage).toContain('class="horses__badge">Levée</span>');
    expect(balisage).toContain('<dd>Non fixée</dd>');
    expect(balisage).toContain('<time dateTime="2025-04-27">27 avril 2025</time>');
  });

  it('404 : « hors de votre périmètre », sans dossier ni « Réessayer »', async () => {
    const { el } = await ouvrir({ message: 'introuvable' }, 404);
    await flush();
    const tree = rendre(el);
    expect(statuts(tree)[1]).toBe('Ce cheval est hors de votre périmètre.');
    expect(texte(parId(tree, 'horses-dossier-titre'))).toBe('Galop Royal');
    expect(titres(tree, 'h3')).toEqual([]);
    expect(boutons(tree).filter((b) => texte(b) === 'Réessayer')).toHaveLength(0);
  });

  it('erreur serveur sur le dossier : « Réessayer » relance le même cheval, reste monté puis rend le focus au titre', async () => {
    const fetcher = fauxFetch({
      '/api/chevaux': [() => json(LISTE)],
      '/api/chevaux/c1': [() => json({}, 503), () => json(DOSSIER)],
    });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    click(chevaux(rendre(el))[0]);
    rendre(el);
    await flush();
    let tree = rendre(el);
    expect(statuts(tree)[1]).toBe('Le serveur n’a pas répondu. Réessayez.');
    const position = tree.indexOf(bouton(tree, 'Réessayer'));
    click(bouton(tree, 'Réessayer'));
    tree = rendre(el);
    expect(statuts(tree)[1]).toBe('Chargement du dossier…');
    const inerte = bouton(tree, 'Chargement…');
    expect(tree.indexOf(inerte)).toBe(position);
    expect(inerte.props['aria-disabled']).toBe(true);
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe('/api/chevaux/c1');
    const focusTitre = vi.fn();
    attacher(parId(tree, 'horses-dossier-titre'), focusTitre);
    await flush();
    tree = rendre(el);
    expect(titres(tree, 'h3')).toEqual(['Identité', 'Régime', 'Mesures']);
    expect(focusTitre).toHaveBeenCalledOnce();
  });

  it('dès 768 px, le choix focalise le titre SANS défilement du focus (preventScroll), puis au plus près', async () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q === '(min-width: 768px)' }));
    const fetcher = fauxFetch({
      '/api/chevaux': [() => json(LISTE)],
      '/api/chevaux/c1': [() => json(DOSSIER)],
    });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    const focus = vi.fn();
    const scrollIntoView = vi.fn();
    attacher(parId(rendre(el), 'horses-dossier-titre'), focus, scrollIntoView);
    click(chevaux(rendre(el))[0]);
    expect(focus).not.toHaveBeenCalled(); // pas dans le gestionnaire : après le rendu
    rendre(el);
    expect(focus).toHaveBeenCalledExactlyOnceWith({ preventScroll: true });
    expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: 'nearest', inline: 'nearest' });
  });

  it('sous 768 px, le dossier empilé vient en haut de l’écran', () => {
    const focus = vi.fn();
    const scrollIntoView = vi.fn();
    focaliserDossier({ focus, scrollIntoView }, false);
    expect(focus).toHaveBeenCalledExactlyOnceWith({ preventScroll: true });
    expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: 'start' });
  });

  it('un changement de cheval abandonne la requête du précédent', async () => {
    const fetcher = fauxFetch({
      '/api/chevaux': [() => json(LISTE)],
      '/api/chevaux/c1': [() => json(DOSSIER)],
      '/api/chevaux/c2': [() => json({ ...DOSSIER, id: 'c2', nom: 'Belle Attente' })],
    });
    const el = ecran({ fetcher });
    rendre(el);
    await flush();
    click(chevaux(rendre(el))[0]);
    rendre(el);
    const premier = fetcher.mock.calls[1]?.[1].signal;
    click(chevaux(rendre(el))[1]);
    rendre(el);
    expect(premier?.aborted).toBe(true);
    await flush();
    const tree = rendre(el);
    expect(texte(parId(tree, 'horses-dossier-titre'))).toBe('Belle Attente');
    expect(chevaux(tree)[1]?.props['aria-current']).toBe('true');
    expect(chevaux(tree)[0]?.props['aria-current']).toBeUndefined();
  });
});

describe('Horses — session', () => {
  it('non connecté : « Connexion requise », bouton vers le sélecteur, aucune requête', () => {
    const fetcher = fauxFetch({});
    const onConnexion = vi.fn();
    const tree = rendre(ecran({ fetcher, compte: null, onConnexion }));
    expect(titres(tree, 'h2')).toEqual(['Connexion requise']);
    expect(statutSession(tree)).toBe('Connectez-vous pour consulter les chevaux.');
    expect(statuts(tree)).toEqual([]);
    const b = bouton(tree, 'Choisir un profil');
    expect(b.props['aria-describedby']).toBe('horses-session');
    click(b);
    expect(onConnexion).toHaveBeenCalledOnce();
    expect(fetcher).not.toHaveBeenCalled();
    expect(chevaux(tree)).toHaveLength(0);
  });

  it('compte connu mais jeton absent : non connecté, aucune requête', () => {
    const fetcher = fauxFetch({});
    const tree = rendre(ecran({ fetcher, client: fauxClient(null) }));
    expect(titres(tree, 'h2')).toEqual(['Connexion requise']);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('401 : session vidée, App prévenue ; la région permanente change de texte, le focus va à « Choisir un profil »', async () => {
    const client = fauxClient();
    const onSessionPerdue = vi.fn();
    const fetcher = fauxFetch({ '/api/chevaux': [() => json({}, 401)] });
    const el = ecran({ fetcher, client, onSessionPerdue });
    let tree = rendre(el);
    // Région présente AVANT le refus, vide, à la place qu'elle gardera.
    expect(statutSession(tree)).toBe('');
    const position = tree.findIndex((e) => e.props.id === 'horses-session');
    await flush();
    tree = rendre(el);
    expect(client.deconnecter).toHaveBeenCalledOnce();
    expect(onSessionPerdue).toHaveBeenCalledOnce();
    expect(statutSession(tree)).toBe('Votre session a expiré, connectez-vous de nouveau.');
    // Après le h2 « Connexion requise », inséré avant elle : une place plus loin, même parent.
    expect(tree.findIndex((e) => e.props.id === 'horses-session')).toBe(position + 1);
    const focus = vi.fn();
    attacher(bouton(tree, 'Choisir un profil'), focus);
    rendre(el);
    expect(focus).toHaveBeenCalledOnce();
    rendre(el);
    expect(focus).toHaveBeenCalledOnce(); // l'attente est retombée
  });

  it('401 pour un jeton déjà remplacé : rien n’est vidé, la liste est redemandée avec le nouveau jeton', async () => {
    const client = fauxClient('ancien');
    const onSessionPerdue = vi.fn();
    const reponse = differee();
    const auth: string[] = [];
    const fetcher = vi.fn<Fetch>(async (_url, init) => {
      auth.push((init.headers as Record<string, string>).Authorization ?? '');
      return auth.length === 1 ? reponse.promesse : json(LISTE);
    });
    const el = ecran({ fetcher, client, onSessionPerdue });
    rendre(el);
    client.poser('nouveau'); // une connexion ailleurs pendant la requête
    reponse.livrer(json({}, 401));
    await flush();
    rendre(el);
    await flush();
    const tree = rendre(el);
    expect(client.deconnecter).not.toHaveBeenCalled();
    expect(onSessionPerdue).not.toHaveBeenCalled();
    expect(auth).toEqual(['Bearer ancien', 'Bearer nouveau']);
    expect(chevaux(tree)).toHaveLength(3);
  });

  it('session en cours de relecture : chargement, jamais « Connexion requise », aucune requête', () => {
    const fetcher = fauxFetch({});
    const el = (
      <Horses lang="fr" compte={null} verification client={fauxClient()} fetcher={fetcher} onConnexion={noop} />
    );
    const tree = rendre(el);
    expect(titres(tree, 'h2')).toEqual(['Liste des chevaux', 'Dossier']);
    expect(statuts(tree)).toEqual(['Chargement des chevaux…', '']);
    expect(statutSession(tree)).toBe('');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('le démontage abandonne la requête en vol', () => {
    const fetcher = vi.fn<Fetch>(() => new Promise<Response>(noop));
    rendre(ecran({ fetcher }));
    const signal = fetcher.mock.calls[0]?.[1].signal;
    expect(signal?.aborted).toBe(false);
    hooks.reset();
    expect(signal?.aborted).toBe(true);
  });

  it('en anglais', () => {
    const tree = rendre(ecran({ fetcher: fauxFetch({}), compte: null, lang: 'en' }));
    expect(statutSession(tree)).toBe('Sign in to view the horses.');
    expect(boutons(tree).map(texte)).toEqual(['Choose a profile']);
  });
});

describe('Horses — contrat et formatage (fonctions pures)', () => {
  it('lireDossier : restrictions absentes restent absentes, présentes et vides restent vides', () => {
    const sans = lireDossier(DOSSIER);
    expect(sans).not.toBeNull();
    expect(sans !== null && 'restrictions' in sans).toBe(false);
    expect(lireDossier({ ...DOSSIER, restrictions: [] })?.restrictions).toEqual([]);
    expect(lireDossier({ ...DOSSIER, restrictions: [{ source: 'x', debut: 'y', statut: 'autre' }] })).toBeNull();
    expect(lireDossier({ ...DOSSIER, mesures: undefined })).toBeNull();
    expect(lireDossier({ ...DOSSIER, sejour: { cour: 'A' } })).toBeNull();
    expect(lireDossier({ ...DOSSIER, id: 7 })).toBeNull();
  });

  it('lireChevaux : nullables omis lus comme absents, type faux refusé', () => {
    expect(lireChevaux([{ id: 'a', nom: 'A' }])).toEqual([
      { id: 'a', nom: 'A', sexe: null, dateNaissance: null, statut: null, cour: null },
    ]);
    expect(lireChevaux([{ id: 'a', nom: 'A', cour: 3 }])).toBeNull();
    expect(lireChevaux({})).toBeNull();
  });

  it('formatDate : date du jour en UTC, valeur illisible rendue telle quelle', () => {
    expect(formatDate('fr', '2025-03-12')).toBe('12 mars 2025');
    expect(formatDate('en', '2025-03-12')).toBe('12 March 2025');
    expect(formatDate('fr', '2025-02-31')).toBe('2025-02-31');
    expect(formatDate('fr', 'hier')).toBe('hier');
    // Une colonne, un style de date : jour et date-heure partagent « medium ».
    expect(formatDate('fr', '2025-03-12', 'medium')).toBe('12 mars 2025');
    expect(formatDate('fr', '2025-03-12T08:00:00Z', 'medium')).toMatch(/^12 mars 2025/);
    expect(formatDate('fr', '2025-03-12T08:00:00Z', 'long')).toMatch(/^12 mars 2025/);
  });

  it('<time dateTime> pour une valeur ISO lisible seulement', () => {
    const vue = (mesures: DossierCheval['mesures']) =>
      renderToString(
        <HorsesView
          lang="fr"
          vue={{ etat: 'connecte', liste: { etat: 'vide' }, dossier: { etat: 'dossier', dossier: { ...DOSSIER, mesures } } }}
          onChoisir={noop}
          onReessayerListe={noop}
          onReessayerDossier={noop}
          onConnexion={noop}
        />,
      );
    const html = vue([
      { nature: 'poids', valeur: '478,5 kg', date: 'hier' },
      { nature: 'temperature', valeur: '37,8 °C', date: '2025-04-23' },
    ]);
    expect(html).toContain('<td>hier</td>');
    expect(html).not.toContain('dateTime="hier"');
    expect(html).toContain('<time dateTime="2025-04-23">23 avr. 2025</time>');
  });

  it('codes bruts de la graine : libellés FR/EN, code inconnu rendu tel quel', () => {
    expect(libelleCode('fr', 'statut', 'a_l_entrainement')).toBe('À l’entraînement');
    expect(libelleCode('en', 'statut', 'a_l_entrainement')).toBe('In training');
    expect(libelleCode('fr', 'sexe', 'F')).toBe('Femelle');
    expect(libelleCode('fr', 'sexe', 'M')).toBe('Mâle');
    expect(libelleCode('en', 'sexe', 'F')).toBe('Female');
    expect(libelleCode('en', 'sexe', 'M')).toBe('Male');
    expect(libelleCode('fr', 'nature', 'poids')).toBe('Poids');
    expect(libelleCode('en', 'nature', 'temperature')).toBe('Temperature');
    expect(libelleCode('fr', 'statut', 'au_repos')).toBe('au_repos');
    expect(libelleCode('fr', 'sexe', 'constructor')).toBe('constructor');
    expect(
      libelleCheval('fr', { ...(LISTE[0] as ChevalResume), statut: 'a_l_entrainement', cour: 'Cour A' }),
    ).toBe('Galop Royal, À l’entraînement · Cour A');
  });

  it('le dossier montre les libellés des codes (sexe, statut, nature de mesure)', () => {
    const html = renderToString(
      <HorsesView
        lang="en"
        vue={{
          etat: 'connecte',
          liste: { etat: 'vide' },
          dossier: {
            etat: 'dossier',
            dossier: {
              ...DOSSIER,
              sexe: 'F',
              statut: 'a_l_entrainement',
              mesures: [{ nature: 'poids', valeur: '478.5 kg', date: '2025-04-24' }],
            },
          },
        }}
        onChoisir={noop}
        onReessayerListe={noop}
        onReessayerDossier={noop}
        onConnexion={noop}
      />,
    );
    expect(html).toContain('<dd>Female</dd>');
    expect(html).toContain('<dd>In training</dd>');
    expect(html).toContain('<td>Weight</td>');
    expect(html).not.toContain('a_l_entrainement');
  });

  it('vueChevaux : liste en erreur ou vide → le dossier attend, il n’invite pas', () => {
    const base = { connecte: true, sessionExpiree: false, choix: null, dossier: null };
    const erreur = vueChevaux({ ...base, liste: { statut: 'erreur', cause: 'reseau' } });
    const vide = vueChevaux({ ...base, liste: { statut: 'pret', chevaux: [] } });
    const pleine = vueChevaux({ ...base, liste: { statut: 'pret', chevaux: LISTE } });
    expect(erreur.etat === 'connecte' && erreur.dossier).toEqual({ etat: 'attente' });
    expect(vide.etat === 'connecte' && vide.dossier).toEqual({ etat: 'attente' });
    expect(pleine.etat === 'connecte' && pleine.dossier).toEqual({ etat: 'invite' });
  });

  it('cibleFocusChevaux : réessai gardé en chargement, rendu au bouton en erreur', () => {
    const reessai = (liste: VueListe) =>
      cibleFocusChevaux('reessai-liste', { etat: 'connecte', liste, dossier: { etat: 'attente' } });
    expect(reessai({ etat: 'chargement', reessai: true })).toEqual({ cible: null, garder: true });
    expect(reessai({ etat: 'erreur', cause: 'serveur' })).toEqual({ cible: null, garder: false });
    expect(reessai({ etat: 'vide' })).toEqual({ cible: 'titre-liste', garder: false });
    expect(cibleFocusChevaux('session', { etat: 'non_connecte', sessionExpiree: true })).toEqual({
      cible: 'connexion',
      garder: false,
    });
  });

  function feuille(): string {
    const html = renderToString(
      <HorsesView
        lang="fr"
        vue={{ etat: 'non_connecte', sessionExpiree: false }}
        onChoisir={noop}
        onReessayerListe={noop}
        onReessayerDossier={noop}
        onConnexion={noop}
      />,
    );
    return /<style[^>]*>([\s\S]*?)<\/style>/.exec(html)?.[1] ?? '';
  }

  /** Règles CSS à plat (sélecteur, corps), media queries dépliées. */
  function regles(css: string): { selecteur: string; corps: string; media: string | null }[] {
    const out: { selecteur: string; corps: string; media: string | null }[] = [];
    const re = /@media\s*([^{]+)\{((?:[^{}]*\{[^{}]*\})*)\s*\}|([^{}@]+)\{([^{}]*)\}/g;
    for (const m of css.matchAll(re)) {
      if (m[1] !== undefined && m[2] !== undefined) {
        for (const r of m[2].matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
          out.push({ selecteur: (r[1] ?? '').trim(), corps: r[2] ?? '', media: m[1].trim() });
        }
      } else if (m[3] !== undefined) {
        out.push({ selecteur: m[3].trim(), corps: m[4] ?? '', media: null });
      }
    }
    return out;
  }

  it('la feuille de l’écran ne lit que les jetons, sans or ni couleur en dur', () => {
    const css = feuille();
    expect(css).toContain('var(--color-navy)');
    expect(css).toContain('min-height:var(--target-min)');
    expect(css).toContain('@media (min-width:768px)');
    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b|rgb|--color-gold/i);
    // Aucun anneau posé sur un bouton : c'est celui de styles.css.
    for (const r of regles(css)) {
      if (/outline|box-shadow/.test(r.corps)) expect(r.selecteur).not.toMatch(/button|cheval|action/);
    }
  });

  it('titre focalisé par script : double anneau de la coque (jetons --ring-*), jamais celui du navigateur', () => {
    const r = regles(feuille()).find((x) => x.selecteur.includes("[tabindex='-1']:focus-visible"));
    expect(r?.selecteur).toBe(".horses-ecran h2[tabindex='-1']:focus-visible");
    expect(r?.corps).toContain('outline:2px solid transparent');
    expect(r?.corps).toContain(
      'box-shadow:0 0 0 var(--ring-inner) var(--color-ivory),0 0 0 calc(var(--ring-inner) + var(--ring-outer)) var(--color-navy)',
    );
  });

  it('dès 768 px, la liste est une colonne collante qui défile seule ; sous 768 px, rien de collant', () => {
    const toutes = regles(feuille());
    const liste = toutes.find((x) => x.selecteur === '.horses__panneau--liste');
    expect(liste?.media).toBe('(min-width:768px)');
    expect(liste?.corps).toContain('position:sticky');
    expect(liste?.corps).toMatch(/top:calc\(var\(--safe-top\) \+ var\(--bar-h\)/);
    expect(liste?.corps).toMatch(/max-height:calc\(100dvh - /);
    expect(liste?.corps).toMatch(/max-height:calc\(100vh - /); // repli sans dvh
    expect(liste?.corps).toContain('overflow-y:auto');
    expect(toutes.filter((x) => x.media === null && x.corps.includes('sticky'))).toEqual([]);
    // Sous 768 px, un dossier choisi réserve sa hauteur : son titre peut venir en haut.
    const choisi = toutes.find((x) => x.selecteur === '.horses__panneau--choisi');
    expect(choisi?.media).toBe('(max-width:767.98px)');
    expect(choisi?.corps).toContain('min-height:calc(100dvh - 13rem)');
  });

  it('mesures : une valeur longue sans espace se coupe (overflow-wrap:anywhere), jamais de débordement à 360 px', () => {
    // Sélecteur (0,2,0) : il doit battre `.horses__table td` (0,1,1), mesuré en direct.
    const valeur = regles(feuille()).find((x) => x.selecteur === '.horses__table .horses__valeur');
    expect(valeur?.corps).toBe('overflow-wrap:anywhere');
    const html = renderToString(
      <HorsesView
        lang="fr"
        vue={{ etat: 'connecte', liste: { etat: 'vide' }, dossier: { etat: 'dossier', dossier: DOSSIER } }}
        onChoisir={noop}
        onReessayerListe={noop}
        onReessayerDossier={noop}
        onConnexion={noop}
      />,
    );
    expect(html).toContain('<td class="horses__valeur">512 kg</td>');
  });
});

describe('App — relecture de session partagée', () => {
  it('clientPartage : une seule /api/moi pour deux lecteurs ; l’abandon de l’un ne coupe pas l’autre', async () => {
    let livrer: (r: Resultat<Compte>) => void = noop;
    const base = {
      ...fauxClient('j'),
      moi: vi.fn(
        () =>
          new Promise<Resultat<Compte>>((resolve) => {
            livrer = resolve;
          }),
      ),
    } satisfies ApiClient;
    const client = clientPartage(base);
    const controle = new AbortController();
    const premier = client.moi(controle.signal);
    const second = client.moi(new AbortController().signal);
    controle.abort();
    livrer({ ok: true, valeur: COMPTE });
    expect(await premier).toEqual({ ok: false, erreur: 'annule' });
    expect(await second).toEqual({ ok: true, valeur: COMPTE });
    expect(base.moi).toHaveBeenCalledOnce();
  });
});

describe('ProfilePicker — onCompteChange', () => {
  it('connexion puis « Changer de profil » : compte, puis null', async () => {
    const onCompteChange = vi.fn();
    const client = {
      ...fauxClient(null),
      personas: vi.fn(async () => ({
        ok: true as const,
        valeur: [{ compteId: '1', nom: 'Camille Morel', role: 'entraineur' }] as Persona[],
      })),
      connecter: vi.fn(async (): Promise<Resultat<Compte>> => ({ ok: true, valeur: COMPTE })),
    } satisfies ApiClient;
    const el = <ProfilePicker lang="fr" client={client} onCompteChange={onCompteChange} />;
    rendre(el);
    await flush();
    click(boutons(rendre(el)).find((b) => b.props['data-compte'] === '1'));
    await flush();
    expect(onCompteChange).toHaveBeenLastCalledWith(COMPTE);
    click(bouton(rendre(el), 'Changer de profil'));
    expect(onCompteChange).toHaveBeenLastCalledWith(null);
    expect(onCompteChange).toHaveBeenCalledTimes(2);
  });

  it('session reprise : acceptée → compte ; refusée → null', async () => {
    for (const [moi, attendu] of [
      [{ ok: true, valeur: COMPTE }, COMPTE],
      [{ ok: false, erreur: 'non_autorise' }, null],
    ] as const) {
      hooks.reset();
      const onCompteChange = vi.fn();
      const client = {
        ...fauxClient('j'),
        moi: vi.fn(async (): Promise<Resultat<Compte>> => moi),
      } satisfies ApiClient;
      rendre(<ProfilePicker lang="fr" client={client} onCompteChange={onCompteChange} />);
      await flush();
      expect(onCompteChange).toHaveBeenCalledExactlyOnceWith(attendu);
    }
  });
});

describe('App — entrée « Chevaux »', () => {
  function stubApp(fetch: (url: string, init?: RequestInit) => Promise<Response>) {
    vi.stubGlobal('document', { documentElement: { lang: '' } });
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: noop });
    vi.stubGlobal('fetch', vi.fn(fetch));
  }

  function h1(tree: Host[]): Host {
    const el = tree.find((e) => e.type === 'h1');
    if (!el) throw new Error('h1 absent');
    return el;
  }

  function nav(tree: Host[], key: string): Host {
    const el = tree.find((e) => e.props['data-nav'] === key);
    if (!el) throw new Error(`entrée ${key} absente`);
    return el;
  }

  it('sans session : « Connexion requise », retour au sélecteur, h1 focalisé à chaque navigation', async () => {
    stubApp(async () => json([]));
    let tree = rendre(<App />);
    expect(h1(tree).props.tabIndex).toBeUndefined(); // premier rendu inchangé
    const focus = vi.fn();
    attacher(h1(tree), focus);
    rendre(<App />);
    expect(focus).not.toHaveBeenCalled(); // l'ouverture ne vole pas le focus

    click(nav(tree, 'horses'));
    tree = rendre(<App />);
    expect(texte(h1(tree))).toBe('Chevaux');
    expect(h1(tree).props.tabIndex).toBe(-1);
    expect(focus).toHaveBeenCalledOnce();
    tree = rendre(<App />); // le rendu qui suit le focus (l'attente retombe), comme React
    expect(focus).toHaveBeenCalledOnce();
    expect(titres(tree, 'h2')).toEqual(['Connexion requise']);
    expect(tree.some((e) => e.props.id === 'profile-titre')).toBe(false);

    click(bouton(tree, 'Choisir un profil'));
    tree = rendre(<App />);
    expect(texte(h1(tree))).toBe('Aujourd’hui');
    expect(focus).toHaveBeenCalledTimes(2);
    expect(tree.some((e) => e.props.id === 'profile-titre')).toBe(true);
    await flush();
  });

  it('connexion par le sélecteur, puis « Chevaux » charge la liste avec le jeton de la session', async () => {
    const chevauxAppel = vi.fn();
    stubApp(async (url, init) => {
      if (url === '/api/personas') {
        return json([{ compteId: '1', nom: 'Camille Morel', role: 'entraineur' }]);
      }
      if (url === '/api/session') return json({ jeton: 'tok', compte: COMPTE });
      if (url === '/api/chevaux') {
        chevauxAppel((init?.headers as Record<string, string>).Authorization);
        return json(LISTE);
      }
      return new Response('', { status: 500 });
    });
    rendre(<App />);
    await flush();
    click(boutons(rendre(<App />)).find((b) => b.props['data-compte'] === '1'));
    await flush();
    let tree = rendre(<App />);
    expect(statuts(tree)[0]).toBe('Connecté en tant que Camille Morel — Entraîneur');

    click(nav(tree, 'horses'));
    rendre(<App />);
    await flush();
    tree = rendre(<App />);
    expect(chevauxAppel).toHaveBeenCalledExactlyOnceWith('Bearer tok');
    expect(chevaux(tree)).toHaveLength(3);
  });

  it('rechargement avec un jeton valide, droit vers « Chevaux » : chargement, jamais « Connexion requise », puis la liste', async () => {
    const moi = differee();
    const appels: string[] = [];
    stubApp(async (url, init) => {
      appels.push(url);
      if (url === '/api/session') return json({ jeton: 'tok', compte: COMPTE });
      if (url === '/api/personas') return json([]);
      if (url === '/api/moi') return moi.promesse;
      if (url === '/api/chevaux') {
        expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer tok');
        return json(LISTE);
      }
      return new Response('', { status: 500 });
    });
    // Le jeton repris de sessionStorage au lancement (ici : posé avant le montage).
    expect((await api.connecter('1')).ok).toBe(true);
    appels.length = 0;

    let tree = rendre(<App />);
    click(tree.find((e) => e.props['data-nav'] === 'horses'));
    tree = rendre(<App />); // ProfilePicker démonté : SON attente de /api/moi est abandonnée
    expect(titres(tree, 'h2')).toEqual(['Liste des chevaux', 'Dossier']);
    expect(statuts(tree)).toEqual(['Chargement des chevaux…', '']);
    expect(statutSession(tree)).toBe(''); // ni « Connectez-vous… » ni « session expirée »

    moi.livrer(json(COMPTE));
    await flush();
    rendre(<App />);
    await flush();
    tree = rendre(<App />);
    expect(chevaux(tree)).toHaveLength(3);
    // Une seule relecture : App et ProfilePicker ont partagé la même requête.
    expect(appels.filter((u) => u === '/api/moi')).toHaveLength(1);
  });

  it('rechargement avec un jeton refusé (401) : « Connexion requise » après la réponse, pas avant', async () => {
    const moi = differee();
    stubApp(async (url) => {
      if (url === '/api/session') return json({ jeton: 'tok', compte: COMPTE });
      if (url === '/api/personas') return json([]);
      if (url === '/api/moi') return moi.promesse;
      return new Response('', { status: 500 });
    });
    expect((await api.connecter('1')).ok).toBe(true);
    let tree = rendre(<App />);
    click(tree.find((e) => e.props['data-nav'] === 'horses'));
    tree = rendre(<App />);
    expect(statuts(tree)[0]).toBe('Chargement des chevaux…');
    moi.livrer(json({}, 401));
    await flush();
    tree = rendre(<App />);
    expect(titres(tree, 'h2')).toEqual(['Connexion requise']);
    expect(api.jeton()).toBeNull();
  });
});
