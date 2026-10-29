import { afterEach, describe, expect, it } from 'vitest';
import { createDb, type DbHandle } from './client.ts';
import { migrate } from './migrate.ts';
import { ROLES_DEMO, seed } from './seed.ts';

let handle: DbHandle | undefined;

afterEach(async () => {
  await handle?.client.close();
  handle?.release();
  handle = undefined;
});

async function seeded(now = new Date()): Promise<DbHandle> {
  handle = createDb();
  await migrate(handle.client);
  expect(await seed(handle.client, now)).toBe(true);
  return handle;
}

async function count(sql: string, params: unknown[] = []): Promise<number> {
  const res = await handle!.client.query<{ n: number }>(`SELECT count(*)::int AS n FROM (${sql}) q`, params);
  return res.rows[0]!.n;
}

const TABLES = [
  'ecurie',
  'lieu',
  'acteur',
  'compte',
  'role',
  'habilitation',
  'cheval',
  'sejour',
  'detention',
  'lot',
  'seance',
  'affectation',
  'produit',
  'regime_special',
  'acte_sante',
  'administration',
  'course',
  'engagement',
  'mesure',
];

async function counts(): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  for (const table of TABLES) out[table] = await count(`SELECT 1 FROM ${table}`);
  return out;
}

describe('seed (demo data)', () => {
  it('creates 6 accounts with the 6 exact distinct roles', async () => {
    await seeded();
    const res = await handle!.client.query<{ libelle: string }>(
      `SELECT r.libelle FROM compte c
         JOIN habilitation h ON h.compte_id = c.id
         JOIN role r ON r.id = h.role_id
       ORDER BY r.libelle`,
    );
    expect(await count('SELECT 1 FROM compte')).toBe(6);
    expect(res.rows.map((row) => row.libelle)).toEqual([...ROLES_DEMO].sort());
    expect(new Set(res.rows.map((row) => row.libelle)).size).toBe(6);
  });

  it('inserts nothing on a second call', async () => {
    await seeded();
    const before = await counts();
    expect(await seed(handle!.client)).toBe(false);
    expect(await counts()).toEqual(before);
  });

  it('gives the rider 2 horses through assignments dated today', async () => {
    const now = new Date();
    await seeded(now);
    const debut = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const fin = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const n = await count(
      `SELECT DISTINCT s.cheval_id FROM affectation a
         JOIN seance s ON s.id = a.seance_id
         JOIN compte c ON c.acteur_id = a.acteur_id
         JOIN habilitation h ON h.compte_id = c.id
         JOIN role r ON r.id = h.role_id
       WHERE r.libelle = 'cavalier' AND a.date_heure >= $1 AND a.date_heure < $2`,
      [debut, fin],
    );
    expect(n).toBe(2);
  });

  it('gives the owner 2 current detentions', async () => {
    await seeded();
    const n = await count(
      `SELECT 1 FROM detention d
         JOIN compte c ON c.acteur_id = d.proprietaire_id
         JOIN habilitation h ON h.compte_id = c.id
         JOIN role r ON r.id = h.role_id
       WHERE r.libelle = 'proprietaire' AND d.date_fin IS NULL`,
    );
    expect(n).toBe(2);
  });

  it('has products with delays 7, 2 and one NULL', async () => {
    await seeded();
    const res = await handle!.client.query<{ d: number | null }>(
      'SELECT delai_retrait_jours AS d FROM produit ORDER BY d NULLS LAST',
    );
    expect(res.rows.map((row) => row.d)).toEqual([2, 7, null]);
  });

  it('puts every horse in a current stay in a yard, with planned and overdue care', async () => {
    const now = new Date();
    await seeded(now);
    expect(await count('SELECT 1 FROM cheval')).toBe(6);
    expect(
      await count(
        `SELECT DISTINCT s.cheval_id FROM sejour s JOIN lieu l ON l.id = s.lieu_id
         WHERE s.date_fin IS NULL AND l.type_lieu = 'cour'`,
      ),
    ).toBe(6);
    expect(await count("SELECT 1 FROM administration WHERE statut = 'valide' AND date_heure < $1", [now])).toBe(1);
    expect(await count("SELECT 1 FROM engagement WHERE statut = 'brouillon'")).toBe(1);
    expect(await count('SELECT 1 FROM regime_special')).toBe(2);
    expect(await count('SELECT 1 FROM mesure WHERE date_reelle < $1', [now])).toBe(3);
  });
});
