import { randomBytes } from 'node:crypto';
import type { FastifyInstance } from 'fastify';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildApp } from '../app.ts';
import { DUREE_JETON_S, signerJeton } from '../auth/session.ts';
import { createDb, type DbHandle } from '../db/client.ts';
import { migrate } from '../db/migrate.ts';

let handle: DbHandle | undefined;
let app: FastifyInstance | undefined;

afterEach(async () => {
  vi.unstubAllEnvs();
  await app?.close();
  app = undefined;
  await handle?.client.close();
  handle?.release();
  handle = undefined;
});

async function demarrer(): Promise<{ app: FastifyInstance; h: DbHandle }> {
  handle = createDb();
  await migrate(handle.client);
  app = buildApp({ db: handle.db });
  return { app, h: handle };
}

/** Inserts its own comptes (never the T2 seed). Returns compte ids by actor name. */
async function peupler(h: DbHandle, comptes: Record<string, string[]>): Promise<Record<string, string>> {
  const ecurie = await h.client.query<{ id: string }>(
    "INSERT INTO ecurie (nom) VALUES ('Écurie test') RETURNING id::text AS id",
  );
  const ecurieId = ecurie.rows[0]?.id;
  const ids: Record<string, string> = {};
  for (const [nom, roles] of Object.entries(comptes)) {
    const acteur = await h.client.query<{ id: string }>('INSERT INTO acteur (nom) VALUES ($1) RETURNING id::text AS id', [
      nom,
    ]);
    const compte = await h.client.query<{ id: string }>(
      'INSERT INTO compte (acteur_id, login) VALUES ($1, $2) RETURNING id::text AS id',
      [acteur.rows[0]?.id, `login-${nom}`],
    );
    const compteId = compte.rows[0]?.id ?? '';
    ids[nom] = compteId;
    for (const libelle of roles) {
      await h.client.query('INSERT INTO role (libelle) VALUES ($1) ON CONFLICT (libelle) DO NOTHING', [libelle]);
      await h.client.query(
        'INSERT INTO habilitation (compte_id, role_id, ecurie_id) SELECT $1, id, $2 FROM role WHERE libelle = $3',
        [compteId, ecurieId, libelle],
      );
    }
  }
  return ids;
}

describe('GET /api/personas', () => {
  it('lists one persona per compte, under its first role in the fixed order, without auth', async () => {
    const { app: a, h } = await demarrer();
    const ids = await peupler(h, {
      Durand: ['veterinaire', 'entraineur'],
      Martin: ['cavalier'],
      // Two habilitations on the same role (two stables would give the same): still one persona.
      Petit: ['proprietaire', 'proprietaire'],
      SansRole: [],
      Inconnu: ['role_hors_contrat'],
    });
    const res = await a.inject({ method: 'GET', url: '/api/personas' });
    expect(res.statusCode).toBe(200);
    const personas = res.json<{ compteId: string; nom: string; role: string }[]>();
    expect(personas).toEqual([
      { compteId: ids.Durand, nom: 'Durand', role: 'entraineur' },
      { compteId: ids.Martin, nom: 'Martin', role: 'cavalier' },
      { compteId: ids.Petit, nom: 'Petit', role: 'proprietaire' },
    ]);
    expect(new Set(personas.map((p) => p.compteId)).size).toBe(personas.length);
  });
});

describe('POST /api/session and GET /api/moi', () => {
  it('opens a session whose token reads back the compte, roles from the database', async () => {
    const { app: a, h } = await demarrer();
    const ids = await peupler(h, { Durand: ['veterinaire', 'entraineur'] });
    const res = await a.inject({ method: 'POST', url: '/api/session', payload: { compteId: ids.Durand } });
    expect(res.statusCode).toBe(200);
    const { jeton, compte } = res.json<{ jeton: string; compte: Record<string, unknown> }>();
    expect(jeton).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
    expect(compte).toEqual({
      compteId: ids.Durand,
      acteurId: expect.stringMatching(/^[1-9][0-9]*$/),
      nom: 'Durand',
      roles: ['entraineur', 'veterinaire'],
    });
    const moi = await a.inject({ method: 'GET', url: '/api/moi', headers: { authorization: `Bearer ${jeton}` } });
    expect(moi.statusCode).toBe(200);
    expect(moi.json()).toEqual(compte);
  });

  it('accepts the compte id as a number too', async () => {
    const { app: a, h } = await demarrer();
    const ids = await peupler(h, { Martin: ['cavalier'] });
    // Raw JSON body: the id travels as a JSON number, never as a quoted string.
    const brut = `{"compteId":${ids.Martin}}`;
    expect(typeof JSON.parse(brut).compteId).toBe('number');
    const res = await a.inject({
      method: 'POST',
      url: '/api/session',
      headers: { 'content-type': 'application/json' },
      payload: brut,
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ compte: { compteId: ids.Martin, roles: ['cavalier'] } });
  });

  it('refuses an unsafe integer instead of letting it round to another compte', async () => {
    const { app: a } = await demarrer();
    const res = await a.inject({
      method: 'POST',
      url: '/api/session',
      headers: { 'content-type': 'application/json' },
      payload: '{"compteId":9007199254740993}',
    });
    expect(res.statusCode).toBe(400);
  });

  it('answers 404 for an unknown compte, 400 for a malformed id', async () => {
    const { app: a } = await demarrer();
    const poster = (payload: unknown) => a.inject({ method: 'POST', url: '/api/session', payload: payload as object });
    expect((await poster({ compteId: '999999' })).statusCode).toBe(404);
    const mauvais = [
      {},
      { compteId: '0' },
      { compteId: 'abc' },
      { compteId: '99999999999999999999' },
      { compteId: 1.5 },
      { compteId: true },
      { compteId: null },
      { compteId: {} },
    ];
    for (const corps of mauvais) {
      expect((await poster(corps)).statusCode, JSON.stringify(corps)).toBe(400);
    }
  });

  it('GET /api/moi: 401 without token, with a token altered by one character, or expired', async () => {
    const cle = randomBytes(32).toString('base64url');
    vi.stubEnv('GRAFFARD_CLE_SIGNATURE', cle);
    const { app: a, h } = await demarrer();
    const ids = await peupler(h, { Martin: ['cavalier'] });
    const moi = (jeton?: string) =>
      a.inject({
        method: 'GET',
        url: '/api/moi',
        headers: jeton === undefined ? {} : { authorization: `Bearer ${jeton}` },
      });

    const ouvert = await a.inject({ method: 'POST', url: '/api/session', payload: { compteId: ids.Martin } });
    const { jeton } = ouvert.json<{ jeton: string }>();
    expect((await moi(jeton)).statusCode).toBe(200);
    expect((await moi()).statusCode).toBe(401);
    const dernier = jeton.at(-1) === 'A' ? 'B' : 'A';
    expect((await moi(`${jeton.slice(0, -1)}${dernier}`)).statusCode).toBe(401);

    // Signed with the very key the app read from the environment, but 12 h old.
    const ancien = signerJeton(ids.Martin ?? '', Buffer.from(cle, 'utf8'), Date.now() - DUREE_JETON_S * 1000);
    expect((await moi(ancien)).statusCode).toBe(401);
    // Control: the same key and a fresh clock pass, so the 401 above is the expiry.
    const frais = signerJeton(ids.Martin ?? '', Buffer.from(cle, 'utf8'));
    expect((await moi(frais)).statusCode).toBe(200);
  });

  it('GET /api/health keeps working without a token', async () => {
    const { app: a } = await demarrer();
    const res = await a.inject({ method: 'GET', url: '/api/health' });
    expect(res.statusCode).toBe(200);
  });
});
