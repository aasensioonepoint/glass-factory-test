import { afterEach, describe, expect, it } from 'vitest';
import { createDb, type DbHandle } from '../client.ts';
import { migrate } from '../migrate.ts';
import { migration0001 } from './0001_mcd_v0.ts';

let handle: DbHandle | undefined;

afterEach(async () => {
  await handle?.client.close();
  handle?.release();
  handle = undefined;
});

interface Refs {
  acteur: number;
  lieu: number;
  cheval: number;
}

async function one(sql: string, params: unknown[] = []): Promise<number> {
  const res = await handle!.client.query<{ id: number }>(sql, params);
  return Number(res.rows[0]!.id);
}

async function seed(): Promise<Refs> {
  const acteur = await one("INSERT INTO acteur (nom) VALUES ('Vétérinaire fictif') RETURNING id");
  const ecurie = await one("INSERT INTO ecurie (nom) VALUES ('Écurie fictive') RETURNING id");
  const lieu = await one("INSERT INTO lieu (ecurie_id, libelle) VALUES ($1, 'Cour A') RETURNING id", [ecurie]);
  const cheval = await one("INSERT INTO cheval (nom) VALUES ('Cheval fictif') RETURNING id");
  return { acteur, lieu, cheval };
}

async function migrated(): Promise<Refs> {
  handle = createDb();
  await migrate(handle.client);
  return seed();
}

describe('migration 0002_schema_mission2', () => {
  it('runs after 0001 on a database already at 0001, and only once', async () => {
    handle = createDb();
    expect(await migrate(handle.client, [migration0001])).toEqual(['0001_mcd_v0']);
    expect(await migrate(handle.client)).toEqual(['0002_schema_mission2']);
    expect(await migrate(handle.client)).toEqual([]);
  });

  it('keeps the official engagement status untouched under statut_officiel (no conversion)', async () => {
    handle = createDb();
    await migrate(handle.client, [migration0001]);
    const { cheval } = await seed();
    const course = await one("INSERT INTO course (date_heure, nom) VALUES (now(), 'Prix fictif') RETURNING id");
    await handle.client.query(
      "INSERT INTO engagement (cheval_id, course_id, date_engagement, statut) VALUES ($1, $2, current_date, 'declare')",
      [cheval, course],
    );
    await migrate(handle.client);
    const row = await handle.client.query<{ statut_officiel: string; statut: string }>(
      'SELECT statut_officiel, statut FROM engagement',
    );
    expect(row.rows).toEqual([{ statut_officiel: 'declare', statut: 'brouillon' }]);
  });

  it('D5: a lot has no time column, needs ordre_passage, and is unique on (libelle, lieu_id, date)', async () => {
    const { acteur, lieu } = await migrated();
    await expect(
      handle!.client.query(
        "INSERT INTO lot (lieu_id, responsable_id, date, heure, libelle, ordre_passage) VALUES ($1, $2, current_date, '07:00', '1', 1)",
        [lieu, acteur],
      ),
    ).rejects.toMatchObject({ code: '42703' });
    await expect(
      handle!.client.query(
        "INSERT INTO lot (lieu_id, responsable_id, date, libelle) VALUES ($1, $2, current_date, '1')",
        [lieu, acteur],
      ),
    ).rejects.toMatchObject({ code: '23502' });
    const insert = "INSERT INTO lot (lieu_id, responsable_id, date, libelle, ordre_passage) VALUES ($1, $2, current_date, '1', $3)";
    await handle!.client.query(insert, [lieu, acteur, 1]);
    await expect(handle!.client.query(insert, [lieu, acteur, 2])).rejects.toMatchObject({ code: '23505' });
  });

  it('D6: a lifted restriction requires who, when and a non-blank reason', async () => {
    const { acteur, cheval } = await migrated();
    const insert =
      "INSERT INTO restriction (cheval_id, source, debut, statut, leve_par_id, leve_le, motif_levee) VALUES ($1, 'manuel', current_date, 'levee', $2, $3, $4)";
    await expect(handle!.client.query(insert, [cheval, acteur, new Date(), null])).rejects.toMatchObject({ code: '23514' });
    await expect(handle!.client.query(insert, [cheval, acteur, new Date(), '  '])).rejects.toMatchObject({ code: '23514' });
    await expect(handle!.client.query(insert, [cheval, null, new Date(), 'Contrôle négatif'])).rejects.toMatchObject({ code: '23514' });
    await expect(handle!.client.query(insert, [cheval, acteur, null, 'Contrôle négatif'])).rejects.toMatchObject({ code: '23514' });
    await handle!.client.query(insert, [cheval, acteur, new Date(), 'Contrôle négatif']);
  });

  it('D6: a restriction defaults to active and must reference its source unless manual', async () => {
    const { cheval } = await migrated();
    await expect(
      handle!.client.query("INSERT INTO restriction (cheval_id, source, debut) VALUES ($1, 'administration', current_date)", [cheval]),
    ).rejects.toMatchObject({ code: '23514' });
    await expect(
      handle!.client.query("INSERT INTO restriction (cheval_id, source, debut) VALUES ($1, 'rumeur', current_date)", [cheval]),
    ).rejects.toMatchObject({ code: '23514' });
    const id = await one(
      "INSERT INTO restriction (cheval_id, source, source_id, debut, fin_prevue) VALUES ($1, 'administration', 42, current_date, current_date - 1) RETURNING id",
      [cheval],
    );
    const row = await handle!.client.query<{ statut: string }>('SELECT statut FROM restriction WHERE id = $1', [id]);
    expect(row.rows).toEqual([{ statut: 'active' }]);
  });

  it('D6: mesure and regime_special accept valid rows and refuse an unknown type or an inverted period', async () => {
    const { acteur, cheval } = await migrated();
    await handle!.client.query(
      "INSERT INTO mesure (cheval_id, type, valeur, unite, auteur_id, date_reelle) VALUES ($1, 'temperature', 37.8, '°C', $2, now())",
      [cheval, acteur],
    );
    await expect(
      handle!.client.query(
        "INSERT INTO mesure (cheval_id, type, valeur, unite, auteur_id, date_reelle) VALUES ($1, 'humeur', 1, '-', $2, now())",
        [cheval, acteur],
      ),
    ).rejects.toMatchObject({ code: '23514' });
    await handle!.client.query(
      "INSERT INTO regime_special (cheval_id, description, debut) VALUES ($1, 'Sans avoine', current_date)",
      [cheval],
    );
    await expect(
      handle!.client.query(
        "INSERT INTO regime_special (cheval_id, description, debut, fin) VALUES ($1, 'Sans avoine', current_date, current_date - 1)",
        [cheval],
      ),
    ).rejects.toMatchObject({ code: '23514' });
  });

  it('Q1: produit.delai_retrait_jours is nullable (unknown period) and never negative', async () => {
    await migrated();
    await handle!.client.query("INSERT INTO produit (nom, delai_retrait_jours) VALUES ('Produit inconnu', NULL), ('Produit A', 7)");
    const rows = await handle!.client.query<{ nom: string; delai_retrait_jours: number | null }>(
      'SELECT nom, delai_retrait_jours FROM produit ORDER BY id',
    );
    expect(rows.rows).toEqual([
      { nom: 'Produit inconnu', delai_retrait_jours: null },
      { nom: 'Produit A', delai_retrait_jours: 7 },
    ]);
    await expect(handle!.client.query("INSERT INTO produit (nom, delai_retrait_jours) VALUES ('X', -1)")).rejects.toMatchObject({
      code: '23514',
    });
  });

  it('D8/D9/H1: common columns on scope-A tables, statut is the shared enum without "en retard"', async () => {
    await migrated();
    const cols = await handle!.client.query<{ table_name: string; column_name: string }>(
      `SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name IN ('auteur_id', 'date_reelle', 'date_reception', 'source', 'statut')
          AND table_name IN ('ration', 'acte_sante', 'administration', 'engagement', 'mesure', 'regime_special')`,
    );
    for (const table of ['ration', 'acte_sante', 'administration', 'engagement', 'mesure', 'regime_special']) {
      expect(cols.rows.filter((r) => r.table_name === table).map((r) => r.column_name).sort()).toEqual(
        ['auteur_id', 'date_reception', 'date_reelle', 'source', 'statut'],
      );
    }
    const labels = await handle!.client.query<{ label: string }>(
      "SELECT unnest(enum_range(NULL::statut_enregistrement))::text AS label",
    );
    expect(labels.rows.map((r) => r.label)).toEqual(['brouillon', 'valide', 'publie', 'realise', 'annule', 'corrige']);
    const typed = await handle!.client.query<{ table_name: string }>(
      `SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'statut' AND udt_name = 'statut_enregistrement' ORDER BY table_name`,
    );
    expect(typed.rows.map((r) => r.table_name)).toEqual(['acte_sante', 'administration', 'engagement', 'mesure', 'ration', 'regime_special']);
  });

  it('D8: the audit trail is append-only and needs a reason', async () => {
    const { acteur } = await migrated();
    await expect(
      handle!.client.query("INSERT INTO audit (objet, objet_id, motif, auteur_id) VALUES ('restriction', 1, '', $1)", [acteur]),
    ).rejects.toMatchObject({ code: '23514' });
    const id = await one(
      `INSERT INTO audit (objet, objet_id, avant, apres, motif, auteur_id)
       VALUES ('restriction', 1, '{"statut":"active"}', '{"statut":"levee"}', 'Contrôle négatif', $1) RETURNING id`,
      [acteur],
    );
    await expect(handle!.client.query("UPDATE audit SET motif = 'autre' WHERE id = $1", [id])).rejects.toThrow(/ajout seul/);
    await expect(handle!.client.query('DELETE FROM audit WHERE id = $1', [id])).rejects.toThrow(/ajout seul/);
    await expect(handle!.client.query('TRUNCATE audit')).rejects.toThrow(/ajout seul : TRUNCATE/);
    const left = await handle!.client.query<{ n: number }>('SELECT count(*)::int AS n FROM audit');
    expect(left.rows).toEqual([{ n: 1 }]);
  });

  it('D9: the six statut columns default to brouillon', async () => {
    await migrated();
    const defaults = await handle!.client.query<{ table_name: string; column_default: string | null }>(
      `SELECT table_name, column_default FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'statut' AND udt_name = 'statut_enregistrement' ORDER BY table_name`,
    );
    expect(defaults.rows).toEqual(
      ['acte_sante', 'administration', 'engagement', 'mesure', 'ration', 'regime_special'].map((table_name) => ({
        table_name,
        column_default: "'brouillon'::statut_enregistrement",
      })),
    );
  });

  it('D5: a lot refuses ordre_passage 0 and a NULL libelle', async () => {
    const { acteur, lieu } = await migrated();
    const insert = 'INSERT INTO lot (lieu_id, responsable_id, date, libelle, ordre_passage) VALUES ($1, $2, current_date, $3, $4)';
    await expect(handle!.client.query(insert, [lieu, acteur, '1', 0])).rejects.toMatchObject({ code: '23514' });
    await expect(handle!.client.query(insert, [lieu, acteur, null, 1])).rejects.toMatchObject({ code: '23502' });
  });

  it('D8: commande_sync refuses a second command with the same idempotency key', async () => {
    await migrated();
    const insert = 'INSERT INTO commande_sync (id_commande) VALUES ($1)';
    await handle!.client.query(insert, ['appareil-1:cmd-1']);
    await expect(handle!.client.query(insert, ['appareil-1:cmd-1'])).rejects.toMatchObject({ code: '23505' });
  });
});
