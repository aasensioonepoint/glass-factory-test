import { createHmac, randomBytes } from 'node:crypto';
import Fastify, { type FastifyInstance } from 'fastify';
import { afterEach, describe, expect, it } from 'vitest';
import { createDb, type DbHandle } from '../db/client.ts';
import { migrate } from '../db/migrate.ts';
import {
  cleDeSignature,
  DUREE_JETON_S,
  normaliserId,
  registerAuth,
  requireRole,
  signerJeton,
  verifierJeton,
} from './session.ts';

const T0 = Date.UTC(2026, 9, 29, 8, 0, 0);

function altererCaractere(jeton: string, i: number): string {
  const c = jeton[i];
  const remplacant = c === 'A' ? 'B' : 'A';
  return `${jeton.slice(0, i)}${remplacant}${jeton.slice(i + 1)}`;
}

describe('signerJeton / verifierJeton', () => {
  const cle = randomBytes(32);

  it('round-trips the compte id and has the base64url(payload).base64url(mac) shape', () => {
    const jeton = signerJeton('42', cle, T0);
    expect(jeton).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$/);
    const [payload] = jeton.split('.');
    expect(JSON.parse(Buffer.from(payload ?? '', 'base64url').toString('utf8'))).toEqual({
      compteId: '42',
      exp: T0 / 1000 + DUREE_JETON_S,
    });
    expect(verifierJeton(jeton, cle, T0)).toBe('42');
  });

  it('refuses a token altered at ANY single character, payload or MAC', () => {
    const jeton = signerJeton('42', cle, T0);
    for (let i = 0; i < jeton.length; i += 1) {
      if (jeton[i] === '.') continue;
      expect(verifierJeton(altererCaractere(jeton, i), cle, T0), `position ${i}`).toBeNull();
    }
  });

  it('refuses a token signed with another key', () => {
    expect(verifierJeton(signerJeton('42', randomBytes(32), T0), cle, T0)).toBeNull();
  });

  it('expires after 12 h, not before', () => {
    const jeton = signerJeton('42', cle, T0);
    expect(verifierJeton(jeton, cle, T0 + DUREE_JETON_S * 1000 - 1000)).toBe('42');
    expect(verifierJeton(jeton, cle, T0 + DUREE_JETON_S * 1000)).toBeNull();
  });

  it('refuses malformed tokens without throwing', () => {
    for (const mauvais of ['', '.', 'abc', 'a.b.c', '.abc', 'abc.', 'é.é']) {
      expect(verifierJeton(mauvais, cle, T0)).toBeNull();
    }
  });

  it('refuses a correctly signed payload that is not {compteId, exp}', () => {
    const forger = (contenu: unknown): string => {
      const payload = Buffer.from(JSON.stringify(contenu), 'utf8').toString('base64url');
      return `${payload}.${createHmac('sha256', cle).update(payload).digest('base64url')}`;
    };
    const exp = T0 / 1000 + 60;
    expect(verifierJeton(forger({ compteId: '7', exp }), cle, T0)).toBe('7');
    expect(verifierJeton(forger({ compteId: '0', exp }), cle, T0)).toBeNull();
    expect(verifierJeton(forger({ compteId: '7' }), cle, T0)).toBeNull();
    expect(verifierJeton(forger({ compteId: '7', exp: String(exp) }), cle, T0)).toBeNull();
    expect(verifierJeton(forger(null), cle, T0)).toBeNull();
  });
});

describe('normaliserId', () => {
  it('accepts positive bigint ids as string or safe number, refuses the rest', () => {
    expect(normaliserId('12')).toBe('12');
    expect(normaliserId(12)).toBe('12');
    expect(normaliserId('9223372036854775807')).toBe('9223372036854775807');
    for (const mauvais of ['9223372036854775808', '012', '0', '-1', '1.5', ' 1', 1.5, -3, null, {}]) {
      expect(normaliserId(mauvais), String(mauvais)).toBeNull();
    }
  });
});

describe('cleDeSignature', () => {
  it('draws a random 32-byte key when the variable is absent or empty', () => {
    const a = cleDeSignature({});
    const b = cleDeSignature({ GRAFFARD_CLE_SIGNATURE: '' });
    expect(a).toHaveLength(32);
    expect(b).toHaveLength(32);
    expect(a.equals(b)).toBe(false);
  });

  it('uses the variable when set, refuses one shorter than 32 bytes', () => {
    const valeur = randomBytes(32).toString('base64url');
    expect(cleDeSignature({ GRAFFARD_CLE_SIGNATURE: valeur }).toString('utf8')).toBe(valeur);
    expect(() => cleDeSignature({ GRAFFARD_CLE_SIGNATURE: valeur.slice(0, 31) })).toThrow(/trop courte/);
  });
});

describe('registerAuth + requireRole', () => {
  let handle: DbHandle | undefined;
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
    await handle?.client.close();
    handle?.release();
    handle = undefined;
  });

  /** One stable, the given roles, one compte per entry. Returns compte ids by actor name. */
  async function peupler(h: DbHandle, comptes: Record<string, string[]>): Promise<Record<string, string>> {
    const ecurie = await h.client.query<{ id: string }>(
      "INSERT INTO ecurie (nom) VALUES ('Écurie test') RETURNING id::text AS id",
    );
    const ecurieId = ecurie.rows[0]?.id;
    const ids: Record<string, string> = {};
    for (const [nom, roles] of Object.entries(comptes)) {
      const acteur = await h.client.query<{ id: string }>(
        'INSERT INTO acteur (nom) VALUES ($1) RETURNING id::text AS id',
        [nom],
      );
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

  async function monter(cle: Buffer, maintenant: () => number): Promise<FastifyInstance> {
    handle = createDb();
    await migrate(handle.client);
    const instance = Fastify({ logger: false });
    registerAuth(instance, handle.db, { cle, maintenant });
    instance.get('/qui', async (request) => ({ compte: request.compte }));
    instance.get('/soins', { preHandler: requireRole('veterinaire') }, async () => ({ ok: true }));
    app = instance;
    return instance;
  }

  it('sets request.compte from a valid token, roles re-read from the database', async () => {
    const cle = randomBytes(32);
    const a = await monter(cle, () => T0);
    const ids = await peupler(handle as DbHandle, { Vet: ['veterinaire', 'cavalier'] });
    const jeton = signerJeton(ids.Vet ?? '', cle, T0);
    const res = await a.inject({ url: '/qui', headers: { authorization: `Bearer ${jeton}` } });
    expect(res.json()).toEqual({
      compte: { compteId: ids.Vet, acteurId: expect.any(String), roles: ['cavalier', 'veterinaire'] },
    });
    // Revoke the habilitation: the same token now carries no role.
    await handle?.client.query('DELETE FROM habilitation WHERE compte_id = $1', [ids.Vet]);
    const apres = await a.inject({ url: '/qui', headers: { authorization: `Bearer ${jeton}` } });
    expect(apres.json()).toMatchObject({ compte: { roles: [] } });
  });

  it('leaves request.compte null without a token, with garbage, or for a deleted compte', async () => {
    const cle = randomBytes(32);
    const a = await monter(cle, () => T0);
    expect((await a.inject({ url: '/qui' })).json()).toEqual({ compte: null });
    expect((await a.inject({ url: '/qui', headers: { authorization: 'Bearer x.y' } })).json()).toEqual({
      compte: null,
    });
    const fantome = signerJeton('999999', cle, T0);
    expect((await a.inject({ url: '/qui', headers: { authorization: `Bearer ${fantome}` } })).json()).toEqual({
      compte: null,
    });
  });

  it('requireRole: 401 without token, altered or expired token; 403 for the cavalier; 200 for the vet', async () => {
    const cle = randomBytes(32);
    let horloge = T0;
    const a = await monter(cle, () => horloge);
    const ids = await peupler(handle as DbHandle, { Cav: ['cavalier'], Vet: ['veterinaire'] });
    const cavalier = signerJeton(ids.Cav ?? '', cle, T0);
    const veto = signerJeton(ids.Vet ?? '', cle, T0);
    const appel = (jeton?: string) =>
      a.inject({ url: '/soins', headers: jeton === undefined ? {} : { authorization: `Bearer ${jeton}` } });

    expect((await appel()).statusCode).toBe(401);
    expect((await appel(altererCaractere(veto, veto.length - 1))).statusCode).toBe(401);
    expect((await appel(altererCaractere(veto, 3))).statusCode).toBe(401);
    expect((await appel(cavalier)).statusCode).toBe(403);
    expect((await appel(veto)).statusCode).toBe(200);

    horloge = T0 + DUREE_JETON_S * 1000;
    expect((await appel(veto)).statusCode).toBe(401);
  });
});
