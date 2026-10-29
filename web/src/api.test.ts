import { describe, expect, it, vi } from 'vitest';
import { JETON_STORAGE_KEY, creerClient, lireCompte, lirePersonas } from './api';
import type { JetonStorage } from './api';

class MemoryStorage implements JetonStorage {
  readonly data = new Map<string, string>();
  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
  removeItem(key: string): void {
    this.data.delete(key);
  }
}

class RefusingStorage implements JetonStorage {
  getItem(): string | null {
    throw new Error('SecurityError');
  }
  setItem(): void {
    throw new Error('QuotaExceededError');
  }
  removeItem(): void {
    throw new Error('SecurityError');
  }
}

interface Appel {
  url: string;
  init: RequestInit;
}

/** `fetch` simulé : une réponse par appel, dans l'ordre ; chaque appel est noté. */
function fauxFetch(...reponses: (Response | Error)[]) {
  const appels: Appel[] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    appels.push({ url, init });
    const suivante = reponses.shift();
    if (suivante === undefined) throw new Error('appel inattendu');
    if (suivante instanceof Error) throw suivante;
    return suivante;
  });
  return { fetch, appels };
}

function json(corps: unknown, status = 200): Response {
  return new Response(JSON.stringify(corps), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function entetes(appel: Appel | undefined): Record<string, string> {
  return (appel?.init.headers ?? {}) as Record<string, string>;
}

const PERSONAS = [
  { compteId: '1', nom: 'Camille Morel', role: 'entraineur' },
  { compteId: 2, nom: 'Léa Garnier', role: 'veterinaire' },
];
const COMPTE = { compteId: '1', acteurId: '7', roles: ['entraineur'] };

describe('api — personas', () => {
  it('lit GET /api/personas sans jeton et valide la liste', async () => {
    const { fetch, appels } = fauxFetch(json(PERSONAS));
    const client = creerClient({ fetch, storage: new MemoryStorage() });
    const r = await client.personas();
    expect(r).toEqual({ ok: true, valeur: PERSONAS });
    expect(appels[0]?.url).toBe('/api/personas');
    expect(appels[0]?.init.method).toBe('GET');
    expect(entetes(appels[0]).Accept).toBe('application/json');
    expect(entetes(appels[0]).Authorization).toBeUndefined();
  });

  it('distingue réseau, HTTP et réponse hors contrat', async () => {
    const { fetch } = fauxFetch(
      new TypeError('Failed to fetch'),
      json({ message: 'boom' }, 500),
      new Response('<html>', { status: 200 }),
      json([{ compteId: '1', nom: 'X', role: 'palefrenier' }]),
    );
    const client = creerClient({ fetch });
    expect(await client.personas()).toEqual({ ok: false, erreur: 'reseau' });
    expect(await client.personas()).toEqual({ ok: false, erreur: 'http' });
    expect(await client.personas()).toEqual({ ok: false, erreur: 'reponse_invalide' });
    expect(await client.personas()).toEqual({ ok: false, erreur: 'reponse_invalide' });
  });
});

describe('api — session', () => {
  it('connecter : POST {compteId}, garde le jeton en mémoire et en stockage, puis l’envoie', async () => {
    const storage = new MemoryStorage();
    const { fetch, appels } = fauxFetch(json({ jeton: 'abc.def', compte: COMPTE }), json(COMPTE));
    const client = creerClient({ fetch, storage });

    const r = await client.connecter('1');
    expect(r).toEqual({ ok: true, valeur: { compteId: '1', roles: ['entraineur'] } });
    expect(appels[0]?.url).toBe('/api/session');
    expect(appels[0]?.init.method).toBe('POST');
    expect(appels[0]?.init.body).toBe('{"compteId":"1"}');
    expect(entetes(appels[0])['Content-Type']).toBe('application/json');
    expect(client.jeton()).toBe('abc.def');
    expect(storage.data.get(JETON_STORAGE_KEY)).toBe('abc.def');

    expect(await client.moi()).toEqual({ ok: true, valeur: { compteId: '1', roles: ['entraineur'] } });
    expect(appels[1]?.url).toBe('/api/moi');
    expect(entetes(appels[1]).Authorization).toBe('Bearer abc.def');
  });

  it('une réponse 401 vide la session, en mémoire et en stockage', async () => {
    const storage = new MemoryStorage();
    storage.setItem(JETON_STORAGE_KEY, 'perime');
    const { fetch, appels } = fauxFetch(json({ message: 'expiré' }, 401));
    const client = creerClient({ fetch, storage });
    expect(client.jeton()).toBe('perime'); // session reprise au lancement

    expect(await client.moi()).toEqual({ ok: false, erreur: 'non_autorise' });
    expect(entetes(appels[0]).Authorization).toBe('Bearer perime');
    expect(client.jeton()).toBeNull();
    expect(storage.data.has(JETON_STORAGE_KEY)).toBe(false);
  });

  it('un 401 sur n’importe quelle route vide aussi la session', async () => {
    const storage = new MemoryStorage();
    storage.setItem(JETON_STORAGE_KEY, 'perime');
    const { fetch } = fauxFetch(json({}, 401));
    const client = creerClient({ fetch, storage });
    expect(await client.personas()).toEqual({ ok: false, erreur: 'non_autorise' });
    expect(client.jeton()).toBeNull();
    expect(storage.data.size).toBe(0);
  });

  it('connecter n’envoie pas un ancien jeton et refuse une session hors contrat', async () => {
    const storage = new MemoryStorage();
    storage.setItem(JETON_STORAGE_KEY, 'ancien');
    const { fetch, appels } = fauxFetch(json({ jeton: '', compte: COMPTE }));
    const client = creerClient({ fetch, storage });
    expect(await client.connecter(2)).toEqual({ ok: false, erreur: 'reponse_invalide' });
    expect(entetes(appels[0]).Authorization).toBeUndefined();
    expect(appels[0]?.init.body).toBe('{"compteId":2}');
    expect(client.jeton()).toBe('ancien');
  });

  it('moi sans jeton ne part pas sur le réseau', async () => {
    const { fetch } = fauxFetch();
    const client = creerClient({ fetch });
    expect(await client.moi()).toEqual({ ok: false, erreur: 'non_autorise' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('deconnecter oublie le jeton', async () => {
    const storage = new MemoryStorage();
    const { fetch } = fauxFetch(json({ jeton: 'j', compte: COMPTE }));
    const client = creerClient({ fetch, storage });
    await client.connecter('1');
    client.deconnecter();
    expect(client.jeton()).toBeNull();
    expect(storage.data.size).toBe(0);
  });

  it('un stockage refusé ne casse rien : le jeton reste en mémoire', async () => {
    const { fetch } = fauxFetch(json({ jeton: 'j', compte: COMPTE }), json({}, 401));
    const client = creerClient({ fetch, storage: new RefusingStorage() });
    expect(client.jeton()).toBeNull();
    expect((await client.connecter('1')).ok).toBe(true);
    expect(client.jeton()).toBe('j');
    expect((await client.moi()).ok).toBe(false);
    expect(client.jeton()).toBeNull();
  });
});

describe('api — validation des formes', () => {
  it('lirePersonas refuse ce qui sort du contrat', () => {
    expect(lirePersonas(PERSONAS)).toEqual(PERSONAS);
    expect(lirePersonas([])).toEqual([]);
    expect(lirePersonas({})).toBeNull();
    expect(lirePersonas([null])).toBeNull();
    expect(lirePersonas([{ compteId: '', nom: 'A', role: 'cavalier' }])).toBeNull();
    expect(lirePersonas([{ compteId: 1.5, nom: 'A', role: 'cavalier' }])).toBeNull();
    expect(lirePersonas([{ compteId: '1', nom: '', role: 'cavalier' }])).toBeNull();
  });

  it('lireCompte lit compteId et roles, le nom s’il est fourni', () => {
    expect(lireCompte(COMPTE)).toEqual({ compteId: '1', roles: ['entraineur'] });
    expect(lireCompte({ compteId: 3, roles: [], nom: 'Z' })).toEqual({ compteId: 3, roles: [], nom: 'Z' });
    expect(lireCompte({ compteId: '1', roles: ['admin'] })).toBeNull();
    expect(lireCompte({ compteId: '1', roles: 'entraineur' })).toBeNull();
    expect(lireCompte({ compteId: '1', roles: [], nom: 4 })).toBeNull();
    expect(lireCompte([])).toBeNull();
  });
});
