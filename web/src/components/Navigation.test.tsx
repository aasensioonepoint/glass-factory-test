import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { renderToString } from 'react-dom/server';
import { App, LANG_STORAGE_KEY, readStoredLang, storeLang } from '../App';
import { Navigation } from './Navigation';
import type { Lang, NavKey } from '../i18n';

/*
 * L'environnement de test est Node, sans DOM : `renderToString` ne joue ni les
 * effets ni les clics. Pour prouver le câblage (clic → état → <html lang> et
 * stockage), `useState` et `useEffect` sont remplacés par un magasin minimal
 * rejoué à chaque rendu ; le reste de React est intact.
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

/** Déplie l'arbre : appelle les composants fonctions, collecte les éléments hôtes. */
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

/** Un « lancement » ou un nouveau rendu de l'application. */
function renderApp(): Host[] {
  hooks.begin();
  return expand(<App />);
}

function find(tree: Host[], predicate: (props: Props) => boolean): Host {
  const hit = tree.find((el) => predicate(el.props));
  if (!hit) throw new Error('élément introuvable');
  return hit;
}

function click(el: Host): void {
  const onClick = el.props.onClick;
  if (typeof onClick !== 'function') throw new Error('aucun gestionnaire de clic');
  (onClick as () => void)();
}

function heading(tree: Host[]): unknown {
  return tree.find((el) => el.type === 'h1')?.props.children;
}

class MemoryStorage {
  readonly data = new Map<string, string>();
  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
}

class RefusingStorage {
  getItem(): string | null {
    throw new Error('SecurityError');
  }
  setItem(): void {
    throw new Error('QuotaExceededError');
  }
}

const noop = () => {};

function render(lang: Lang, active: NavKey): string {
  return renderToString(
    <Navigation lang={lang} active={active} onNavigate={noop} onLangChange={noop} />,
  );
}

let root: { lang: string };
let store: MemoryStorage;

beforeEach(() => {
  hooks.reset();
  hooks.begin();
  root = { lang: '' };
  store = new MemoryStorage();
  vi.stubGlobal('document', { documentElement: root });
  vi.stubGlobal('localStorage', store);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Navigation', () => {
  it('affiche les six entrées en français et « + Ajouter »', () => {
    const html = render('fr', 'today');
    for (const label of ['Aujourd’hui', 'Planning', 'Chevaux', 'Santé', 'Courses', 'Plus']) {
      expect(html).toContain(`>${label}</button>`);
    }
    expect(html.match(/data-nav="/g)).toHaveLength(6);
    expect(html).toContain('>+ Ajouter</button>');
    expect(html).toContain('aria-label="Navigation principale"');
  });

  it('affiche les six entrées en anglais et « + Add »', () => {
    const html = render('en', 'today');
    for (const label of ['Today', 'Planning', 'Horses', 'Health', 'Races', 'More']) {
      expect(html).toContain(`>${label}</button>`);
    }
    expect(html).toContain('>+ Add</button>');
    expect(html).toContain('aria-label="Main navigation"');
  });

  it('marque l’entrée active, la langue pressée et démarre en français', () => {
    const html = render('en', 'horses');
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/data-nav="horses" aria-current="page"/);
    expect(html).toMatch(/lang="en" aria-label="English" aria-pressed="true">EN</);
    expect(html).toMatch(/lang="fr" aria-label="Français" aria-pressed="false">FR</);
    // « + Ajouter » est frère de <nav>, jamais dans la barre.
    expect(html).toMatch(/<\/nav><button type="button" class="add">/);

    expect(renderToString(<App />)).toContain('<h1>Aujourd’hui</h1>');
  });

  it('transmet chaque clic à son gestionnaire', () => {
    const onNavigate = vi.fn();
    const onLangChange = vi.fn();
    const tree = expand(
      <Navigation lang="fr" active="today" onNavigate={onNavigate} onLangChange={onLangChange} />,
    );
    click(find(tree, (p) => p['data-nav'] === 'races'));
    click(find(tree, (p) => p.lang === 'en'));
    expect(onNavigate).toHaveBeenCalledWith('races');
    expect(onLangChange).toHaveBeenCalledWith('en');
  });

  it('ramène dans la vue l’entrée qui reçoit le focus', () => {
    const tree = expand(
      <Navigation lang="fr" active="today" onNavigate={noop} onLangChange={noop} />,
    );
    const entries = tree.filter((el) => typeof el.props['data-nav'] === 'string');
    expect(entries).toHaveLength(6);
    for (const entry of entries) {
      const scrollIntoView = vi.fn();
      const onFocus = entry.props.onFocus;
      if (typeof onFocus !== 'function') throw new Error('aucun gestionnaire de focus');
      (onFocus as (e: unknown) => void)({ currentTarget: { scrollIntoView } });
      expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
    }
  });
});

describe('App — langue', () => {
  it('démarre en français, sur <html lang> aussi, quand rien n’est enregistré', () => {
    const tree = renderApp();
    expect(heading(tree)).toBe('Aujourd’hui');
    expect(root.lang).toBe('fr');
  });

  it('un clic sur EN passe l’interface et <html lang> en anglais', () => {
    click(find(renderApp(), (p) => p.lang === 'en'));
    const tree = renderApp();
    expect(heading(tree)).toBe('Today');
    expect(root.lang).toBe('en');
    expect(find(tree, (p) => p.lang === 'en').props['aria-pressed']).toBe(true);

    click(find(tree, (p) => p['data-nav'] === 'horses'));
    expect(heading(renderApp())).toBe('Horses');
  });

  it('retrouve la langue choisie au lancement suivant', () => {
    click(find(renderApp(), (p) => p.lang === 'en'));
    expect(store.data.get(LANG_STORAGE_KEY)).toBe('en');

    hooks.reset(); // nouveau lancement : l'état React repart de zéro, le stockage reste.
    root.lang = '';
    const tree = renderApp();
    expect(heading(tree)).toBe('Today');
    expect(root.lang).toBe('en');
  });

  it('reste en français, sans erreur, quand le stockage refuse ou contient autre chose', () => {
    vi.stubGlobal('localStorage', new RefusingStorage());
    const tree = renderApp();
    expect(heading(tree)).toBe('Aujourd’hui');
    expect(() => click(find(tree, (p) => p.lang === 'en'))).not.toThrow();
    expect(heading(renderApp())).toBe('Today');

    const junk = new MemoryStorage();
    junk.setItem(LANG_STORAGE_KEY, 'de');
    expect(readStoredLang(junk)).toBe('fr');
    expect(readStoredLang(null)).toBe('fr');
    expect(() => storeLang(new RefusingStorage(), 'en')).not.toThrow();
  });
});
