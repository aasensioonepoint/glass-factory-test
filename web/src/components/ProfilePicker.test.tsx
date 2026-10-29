import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { renderToString } from 'react-dom/server';
import { App } from '../App';
import { JETON_STORAGE_KEY, ROLES, creerClient } from '../api';
import type { ApiClient, JetonStorage, Persona, Resultat } from '../api';
import {
  ProfilePicker,
  ProfilePickerView,
  ROLE_LABELS,
  roleLabel,
} from './ProfilePicker';
import type { VueProfil } from './ProfilePicker';

/*
 * Environnement Node, sans DOM : `renderToString` prouve le balisage ; pour le
 * conteneur (effets, clics, focus), `useState` et `useEffect` sont remplacés par
 * un magasin rejoué à chaque rendu, comme dans Navigation.test.tsx.
 */
const hooks = vi.hoisted(() => {
  const states: unknown[] = [];
  const deps: (readonly unknown[] | undefined)[] = [];
  let stateCursor = 0;
  let effectCursor = 0;
  return {
    reset(): void {
      states.length = 0;
      deps.length = 0;
    },
    begin(): void {
      stateCursor = 0;
      effectCursor = 0;
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
    useEffect(effect: () => void, nextDeps?: readonly unknown[]): void {
      const slot = effectCursor++;
      const prev = deps[slot];
      const changed =
        prev === undefined ||
        nextDeps === undefined ||
        nextDeps.some((value, i) => !Object.is(value, prev[i]));
      if (changed) {
        deps[slot] = nextDeps;
        effect();
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

function click(el: Host): void {
  const onClick = el.props.onClick;
  if (typeof onClick !== 'function') throw new Error('aucun gestionnaire de clic');
  (onClick as () => void)();
}

function statut(tree: Host[]): string {
  const region = tree.find((el) => el.props.role === 'status');
  if (!region) throw new Error('région status absente');
  return texte(region);
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

const PERSONAS: Persona[] = [
  { compteId: '1', nom: 'Camille Morel', role: 'entraineur' },
  { compteId: '2', nom: 'Léa Garnier', role: 'veterinaire' },
  { compteId: 3, nom: 'Hugo Lambert', role: 'cavalier' },
];

const noop = () => {};

function vue(v: VueProfil, lang: 'fr' | 'en' = 'fr', extra: Partial<Record<string, () => void>> = {}) {
  const el = (
    <ProfilePickerView
      lang={lang}
      vue={v}
      onChoisir={noop}
      onChanger={extra.onChanger ?? noop}
      onReessayer={extra.onReessayer ?? noop}
    />
  );
  return { html: renderToString(el), tree: expand(el) };
}

const LISTE: VueProfil = { etat: 'liste', personas: PERSONAS, enCours: null, erreurConnexion: false };

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

  it('rechargement après erreur : « Réessayer » reste monté, inerte, et garde le focus', () => {
    const onReessayer = vi.fn();
    const { tree } = vue({ etat: 'chargement', reessai: true }, 'fr', { onReessayer });
    const b = bouton(tree, 'Réessayer');
    expect(b.props['aria-disabled']).toBe(true);
    expect(b.props.onClick).toBeUndefined();
    expect(onReessayer).not.toHaveBeenCalled();
  });

  it('vide : message, aucun bouton', () => {
    const { tree } = vue({ etat: 'vide' });
    expect(statut(tree)).toBe('Aucun profil de démonstration n’est disponible.');
    expect(boutons(tree)).toHaveLength(0);
  });

  it('erreur réseau : message et « Réessayer »', () => {
    const onReessayer = vi.fn();
    const { tree } = vue({ etat: 'erreur' }, 'fr', { onReessayer });
    expect(statut(tree)).toMatch(/n’ont pas pu être chargés/);
    click(bouton(tree, 'Réessayer'));
    expect(onReessayer).toHaveBeenCalledOnce();
  });

  it('connecté : nom et rôle affichés, « Changer de profil »', () => {
    const onChanger = vi.fn();
    const { html, tree } = vue(
      { etat: 'connecte', nom: 'Léa Garnier', roles: ['veterinaire'] },
      'fr',
      { onChanger },
    );
    expect(html).toContain('<strong>Léa Garnier</strong>');
    expect(texte(tree.find((el) => el.type === 'p'))).toBe(
      'Connecté en tant que Léa Garnier — Vétérinaire',
    );
    click(bouton(tree, 'Changer de profil'));
    expect(onChanger).toHaveBeenCalledOnce();
    const sansNom = vue({ etat: 'connecte', nom: null, roles: ['proprietaire'] }, 'en').tree;
    expect(texte(sansNom.find((el) => el.type === 'p'))).toBe('Signed in as Owner');
  });

  it('erreur de connexion et connexion en cours sont annoncées', () => {
    expect(statut(vue({ ...LISTE, erreurConnexion: true }).tree)).toMatch(/connexion a échoué/);
    expect(statut(vue({ ...LISTE, enCours: '1' }).tree)).toBe('Connexion…');
  });

  it('cibles ≥ 44 px et couleurs tirées des jetons seulement', () => {
    const arbres = [
      vue(LISTE).tree,
      vue({ etat: 'erreur' }).tree,
      vue({ etat: 'connecte', nom: 'A', roles: ['cavalier'] }).tree,
    ];
    for (const tree of arbres) {
      for (const b of boutons(tree)) {
        const style = b.props.style as Record<string, unknown>;
        expect(style.minHeight).toBe('var(--target-min)');
        expect(style.minWidth).toBe('var(--target-min)');
      }
      for (const el of tree) {
        const style = JSON.stringify(el.props.style ?? {});
        expect(style).not.toMatch(/#[0-9a-f]{3,8}\b|rgb/i);
        expect(style).not.toMatch(/--color-gold/);
      }
    }
  });
});

/** Faux client : chaque méthode répond par la file qu'on lui donne. */
function fauxClient(opts: {
  jeton?: string | null;
  personas?: Resultat<Persona[]>[];
  connecter?: Resultat<{ compteId: string; roles: ['entraineur'] }>[];
}) {
  let jeton = opts.jeton ?? null;
  const client = {
    personas: vi.fn(async () => opts.personas?.shift() ?? { ok: false as const, erreur: 'reseau' as const }),
    connecter: vi.fn(async () => {
      const r = opts.connecter?.shift() ?? { ok: false as const, erreur: 'http' as const };
      if (r.ok) jeton = 'j';
      return r;
    }),
    moi: vi.fn(async () => ({ ok: false as const, erreur: 'non_autorise' as const })),
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

function attacher(el: Host, focus: () => void): void {
  const ref = el.props.ref;
  if (typeof ref !== 'function') throw new Error('aucune ref de rappel');
  (ref as (node: unknown) => void)({ focus });
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
    const personas = boutons(tree);
    expect(personas.map(texte)[0]).toBe('Camille Morel Entraîneur');
    // Seul le premier persona reçoit la ref de focus.
    expect(personas.filter((b) => typeof b.props.ref === 'function')).toHaveLength(1);
    const focusPremier = vi.fn();
    attacher(personas[0] as Host, focusPremier);
    rendre(client);
    expect(focusPremier).toHaveBeenCalledOnce();
    rendre(client); // un rendu de plus ne vole pas le focus
    expect(focusPremier).toHaveBeenCalledOnce();

    click(bouton(rendre(client), 'Camille Morel Entraîneur'));
    expect(client.connecter).toHaveBeenCalledWith('1');
    expect(statut(rendre(client))).toBe('Connexion…');
    await flush();

    tree = rendre(client);
    expect(texte(tree.find((el) => el.type === 'p'))).toBe(
      'Connecté en tant que Camille Morel — Entraîneur',
    );
    const focusChanger = vi.fn();
    attacher(bouton(tree, 'Changer de profil'), focusChanger);
    rendre(client);
    expect(focusChanger).toHaveBeenCalledOnce();

    click(bouton(rendre(client), 'Changer de profil'));
    expect(client.deconnecter).toHaveBeenCalledOnce();
    tree = rendre(client);
    expect(boutons(tree)).toHaveLength(3);
    const focusRetour = vi.fn();
    attacher(boutons(tree)[0] as Host, focusRetour);
    rendre(client);
    expect(focusRetour).toHaveBeenCalledOnce();
  });

  it('un échec de connexion garde la liste et l’annonce', async () => {
    const client = fauxClient({ personas: [{ ok: true, valeur: PERSONAS }], connecter: [] });
    rendre(client);
    await flush();
    click(bouton(rendre(client), 'Léa Garnier Vétérinaire'));
    await flush();
    const tree = rendre(client);
    expect(boutons(tree)).toHaveLength(3);
    expect(statut(tree)).toMatch(/connexion a échoué/);
  });

  it('erreur réseau puis « Réessayer » recharge les profils', async () => {
    const client = fauxClient({
      personas: [{ ok: false, erreur: 'reseau' }, { ok: true, valeur: [] }],
    });
    rendre(client);
    await flush();
    click(bouton(rendre(client), 'Réessayer'));
    const pendant = rendre(client);
    expect(statut(pendant)).toBe('Chargement des profils…');
    expect(bouton(pendant, 'Réessayer').props['aria-disabled']).toBe(true);
    await flush();
    expect(statut(rendre(client))).toBe('Aucun profil de démonstration n’est disponible.');
    expect(client.personas).toHaveBeenCalledTimes(2);
  });

  it('session reprise refusée par le serveur (401) : la session est vidée, le sélecteur revient', async () => {
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
    expect(boutons(tree)).toHaveLength(3);
    expect(client.jeton()).toBeNull();
    expect(storage.data.has(JETON_STORAGE_KEY)).toBe(false);
  });

  it('session reprise acceptée : connecté, nom retrouvé dans la liste des personas', async () => {
    const fetch = vi.fn(async (url: string) =>
      url === '/api/moi'
        ? new Response(JSON.stringify({ compteId: 3, acteurId: 9, roles: ['cavalier'] }))
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
    expect(texte(tree.find((el) => el.type === 'p'))).toBe('Signed in as Hugo Lambert — Work rider');
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
