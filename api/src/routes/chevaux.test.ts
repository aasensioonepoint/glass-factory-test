import type { FastifyInstance } from 'fastify';
import { afterEach, describe, expect, it } from 'vitest';
import { buildApp } from '../app.ts';
import type { Role } from '../auth/session.ts';
import { createDb, type DbHandle } from '../db/client.ts';
import { migrate } from '../db/migrate.ts';
import { jour, seed } from '../db/seed.ts';
import { jourParis } from './chevaux.ts';

/** Fixed clock: midday local time, so the local and the Paris date agree. */
const NOW = new Date(2026, 9, 29, 12, 0, 0);

let handle: DbHandle | undefined;
let app: FastifyInstance | undefined;

afterEach(async () => {
  await app?.close();
  app = undefined;
  await handle?.client.close();
  handle?.release();
  handle = undefined;
});

interface Contexte {
  app: FastifyInstance;
  h: DbHandle;
  chevaux: Record<string, string>;
  acteurs: Record<Role, string>;
}

/** Migrated in-memory base, T2 seed anchored on NOW, app on a clock frozen at `horloge`. */
async function demarrer(horloge: Date = NOW): Promise<Contexte> {
  handle = createDb();
  await migrate(handle.client);
  await seed(handle.client, NOW);
  app = buildApp({ db: handle.db, maintenant: () => horloge.getTime() });
  const chevaux = await handle.client.query<{ id: string; nom: string }>('SELECT id::text AS id, nom FROM cheval');
  const acteurs = await handle.client.query<{ id: string; libelle: Role }>(
    `SELECT a.id::text AS id, r.libelle FROM acteur a
     JOIN compte c ON c.acteur_id = a.id
     JOIN habilitation hb ON hb.compte_id = c.id
     JOIN role r ON r.id = hb.role_id`,
  );
  return {
    app,
    h: handle,
    chevaux: Object.fromEntries(chevaux.rows.map((r) => [r.nom, r.id])),
    acteurs: Object.fromEntries(acteurs.rows.map((r) => [r.libelle, r.id])) as Record<Role, string>,
  };
}

/** Signs in through the real auth: persona list, then POST /api/session. */
async function jeton(a: FastifyInstance, role: Role): Promise<string> {
  const personas = (await a.inject({ method: 'GET', url: '/api/personas' })).json<Array<{ compteId: string; role: Role }>>();
  const persona = personas.find((p) => p.role === role);
  if (persona === undefined) throw new Error(`persona ${role} absente`);
  const res = await a.inject({ method: 'POST', url: '/api/session', payload: { compteId: persona.compteId } });
  expect(res.statusCode).toBe(200);
  return res.json<{ jeton: string }>().jeton;
}

async function get(a: FastifyInstance, url: string, cle?: string) {
  return a.inject({ method: 'GET', url, headers: cle === undefined ? {} : { authorization: `Bearer ${cle}` } });
}

async function noms(a: FastifyInstance, role: Role): Promise<string[]> {
  const res = await get(a, '/api/chevaux', await jeton(a, role));
  expect(res.statusCode).toBe(200);
  return res.json<Array<{ nom: string }>>().map((c) => c.nom);
}

describe('jourParis', () => {
  it('reads the calendar date in Europe/Paris, not in UTC', () => {
    // 23:30 UTC on 29 October 2026 is already 30 October in Paris (UTC+1 in winter).
    expect(jourParis(Date.UTC(2026, 9, 29, 23, 30))).toBe('2026-10-30');
    expect(jourParis(Date.UTC(2026, 9, 29, 22, 30))).toBe('2026-10-29');
  });
});

describe('GET /api/chevaux', () => {
  it('answers 401 without a session', async () => {
    const { app: a } = await demarrer();
    const res = await get(a, '/api/chevaux');
    expect(res.statusCode).toBe(401);
    expect(res.json()).toEqual({ erreur: 'non_autorise' });
  });

  it("gives the cavalier the 2 horses of today's assignments only, not another rider's", async () => {
    const { app: a, h, chevaux, acteurs } = await demarrer();
    // Today's assignment of ANOTHER actor on a horse of its own: never the cavalier's.
    const lot = await h.client.query<{ id: string }>("SELECT id::text AS id FROM lot WHERE libelle = 'Lot 1'");
    const seance = await h.client.query<{ id: string }>(
      "INSERT INTO seance (cheval_id, lot_id, exercice) VALUES ($1, $2, 'trot') RETURNING id::text AS id",
      [chevaux['Nuage Modèle'], lot.rows[0]?.id],
    );
    await h.client.query("INSERT INTO affectation (seance_id, acteur_id, date_heure, fonction) VALUES ($1, $2, $3, 'cavalier')", [
      seance.rows[0]?.id,
      acteurs.assistant_entraineur,
      NOW,
    ]);
    expect(await noms(a, 'cavalier')).toEqual(['Éclair Démo', 'Sable Factice']);
  });

  it("gives the cavalier nothing on another day: yesterday's assignments do not count", async () => {
    const lendemain = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate() + 1, 12);
    const { app: a } = await demarrer(lendemain);
    expect(await noms(a, 'cavalier')).toEqual([]);
  });

  it('gives the proprietaire the horses of his current detention, not an ended one', async () => {
    const { app: a, h, chevaux, acteurs } = await demarrer();
    await h.client.query(
      'INSERT INTO detention (cheval_id, proprietaire_id, date_debut, date_fin, quote_part) VALUES ($1, $2, $3, $4, 100)',
      [chevaux['Nuage Modèle'], acteurs.proprietaire, jour(NOW, -400), jour(NOW, -1)],
    );
    expect(await noms(a, 'proprietaire')).toEqual(['Brume de Test', 'Comète Fictive']);
  });

  it.each(['entraineur', 'assistant_entraineur', 'veterinaire', 'charge_engagements'] as const)(
    'gives %s the whole herd of 6, with raw codes and the current yard',
    async (role) => {
      const { app: a } = await demarrer();
      const res = await get(a, '/api/chevaux', await jeton(a, role));
      expect(res.statusCode).toBe(200);
      const liste = res.json<Array<Record<string, unknown>>>();
      expect(liste).toHaveLength(6);
      const comete = liste.find((c) => c.nom === 'Comète Fictive');
      expect(comete).toEqual({
        id: expect.stringMatching(/^[1-9][0-9]*$/),
        nom: 'Comète Fictive',
        sexe: 'F',
        dateNaissance: `${NOW.getFullYear() - 3}-04-01`,
        statut: 'a_l_entrainement',
        cour: 'Cour des Tilleuls fictifs',
      });
    },
  );

  it('gives a compte with several roles the union of what each role sees', async () => {
    const { app: a, h, chevaux, acteurs } = await demarrer();
    await h.client.query(
      'INSERT INTO detention (cheval_id, proprietaire_id, date_debut, quote_part) VALUES ($1, $2, $3, 100)',
      [chevaux['Orage Simulé'], acteurs.cavalier, jour(NOW, -10)],
    );
    await h.client.query(
      `INSERT INTO habilitation (compte_id, role_id, ecurie_id)
       SELECT c.id, r.id, (SELECT min(id) FROM ecurie) FROM compte c, role r
       WHERE c.acteur_id = CAST($1 AS bigint) AND r.libelle = 'proprietaire'`,
      [acteurs.cavalier],
    );
    expect(await noms(a, 'cavalier')).toEqual(['Éclair Démo', 'Orage Simulé', 'Sable Factice']);
  });
});

describe('GET /api/chevaux/:id', () => {
  it('answers 401 without a session', async () => {
    const { app: a, chevaux } = await demarrer();
    expect((await get(a, `/api/chevaux/${chevaux['Comète Fictive']}`)).statusCode).toBe(401);
  });

  it('gives the proprietaire his own horse WITHOUT the restrictions field', async () => {
    const { app: a, h, chevaux } = await demarrer();
    await h.client.query("INSERT INTO restriction (cheval_id, source, debut) VALUES ($1, 'manuel', $2)", [
      chevaux['Comète Fictive'],
      jour(NOW),
    ]);
    const res = await get(a, `/api/chevaux/${chevaux['Comète Fictive']}`, await jeton(a, 'proprietaire'));
    expect(res.statusCode).toBe(200);
    const dossier = res.json<Record<string, unknown>>();
    expect(Object.hasOwn(dossier, 'restrictions')).toBe(false);
    expect(dossier).toMatchObject({
      id: chevaux['Comète Fictive'],
      nom: 'Comète Fictive',
      sire: null,
      sejour: { cour: 'Cour des Tilleuls fictifs', depuis: jour(NOW, -60) },
      regime: null,
      mesures: [{ nature: 'poids', valeur: '478.5 kg', date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/) }],
    });
  });

  it('answers 404, never 403, for a horse the proprietaire does not hold, an unknown or a malformed id', async () => {
    const { app: a, chevaux } = await demarrer();
    const cle = await jeton(a, 'proprietaire');
    for (const id of [chevaux['Éclair Démo'], '999999', 'abc', '0', '01', '-1', '99999999999999999999']) {
      const res = await get(a, `/api/chevaux/${id}`, cle);
      expect(res.statusCode, `id ${id}`).toBe(404);
      expect(res.json()).toEqual({ erreur: 'introuvable' });
    }
  });

  it("answers 404 to the cavalier outside today's assignments, the file with restrictions inside", async () => {
    const { app: a, h, chevaux } = await demarrer();
    await h.client.query("INSERT INTO restriction (cheval_id, source, debut, fin_prevue) VALUES ($1, 'manuel', $2, $3)", [
      chevaux['Éclair Démo'],
      jour(NOW, -1),
      jour(NOW, 5),
    ]);
    const cle = await jeton(a, 'cavalier');
    expect((await get(a, `/api/chevaux/${chevaux['Comète Fictive']}`, cle)).statusCode).toBe(404);
    const res = await get(a, `/api/chevaux/${chevaux['Éclair Démo']}`, cle);
    expect(res.statusCode).toBe(200);
    expect(res.json<{ restrictions: unknown }>().restrictions).toEqual([
      { source: 'manuel', debut: jour(NOW, -1), finPrevue: jour(NOW, 5), statut: 'active' },
    ]);
  });

  it('gives the entraineur any horse, with its current regime and an empty restrictions list', async () => {
    const { app: a, chevaux } = await demarrer();
    const res = await get(a, `/api/chevaux/${chevaux['Brume de Test']}`, await jeton(a, 'entraineur'));
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({
      nom: 'Brume de Test',
      sexe: 'M',
      regime: { description: 'Ration réduite en foin, eau à volonté' },
      mesures: [],
      restrictions: [],
    });
  });

  it('lists the measurements latest first, a few only', async () => {
    const { app: a, h, chevaux, acteurs } = await demarrer();
    for (let i = 1; i <= 7; i += 1) {
      await h.client.query(
        "INSERT INTO mesure (cheval_id, type, valeur, unite, auteur_id, date_reelle, statut) VALUES ($1, 'temperature', $2, '°C', $3, $4, 'valide')",
        [chevaux['Nuage Modèle'], 37 + i / 10, acteurs.assistant_entraineur, new Date(NOW.getTime() - i * 3_600_000)],
      );
    }
    const res = await get(a, `/api/chevaux/${chevaux['Nuage Modèle']}`, await jeton(a, 'veterinaire'));
    const mesures = res.json<{ mesures: Array<{ valeur: string }> }>().mesures;
    expect(mesures.map((m) => m.valeur)).toEqual(['37.1 °C', '37.2 °C', '37.3 °C', '37.4 °C', '37.5 °C']);
  });
});
