import type { PGlite, Transaction } from '@electric-sql/pglite';

/**
 * Demo data, ENTIRELY fictional: no real person, horse or stable name.
 * No password, key or secret: an account is only a login (T3 picks a persona).
 * Role labels are EXACT: web/src/api.ts ROLES and T3 read them via habilitation -> role.
 */
export const ROLES_DEMO = [
  'entraineur',
  'assistant_entraineur',
  'cavalier',
  'veterinaire',
  'charge_engagements',
  'proprietaire',
] as const;

export type RoleDemo = (typeof ROLES_DEMO)[number];

type Id = number | bigint | string;

const PERSONAS: Record<RoleDemo, { nom: string; login: string }> = {
  entraineur: { nom: 'Camille Fictif', login: 'demo.entraineur' },
  assistant_entraineur: { nom: 'Dominique Exemple', login: 'demo.assistant' },
  cavalier: { nom: 'Sacha Imaginaire', login: 'demo.cavalier' },
  veterinaire: { nom: 'Dr Alix Inventé', login: 'demo.veterinaire' },
  charge_engagements: { nom: 'Morgan Supposé', login: 'demo.engagements' },
  proprietaire: { nom: 'Claude Hypothèse', login: 'demo.proprietaire' },
};

const CHEVAUX = ['Comète Fictive', 'Brume de Test', 'Éclair Démo', 'Sable Factice', 'Orage Simulé', 'Nuage Modèle'];

/** Local calendar date `YYYY-MM-DD`, `days` away from `ref`. */
export function jour(ref: Date, days = 0): string {
  const d = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate() + days);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Local instant on the day `days` away from `ref`, at `hour`:00. */
function instant(ref: Date, days: number, hour: number): Date {
  return new Date(ref.getFullYear(), ref.getMonth(), ref.getDate() + days, hour);
}

async function ins(tx: Transaction, sql: string, params: unknown[] = []): Promise<Id> {
  const res = await tx.query<{ id: Id }>(`${sql} RETURNING id`, params);
  return res.rows[0]!.id;
}

/**
 * Seeds the demo data in ONE transaction when table `compte` is empty; a second
 * call inserts nothing. Dates are relative to `now` (default: seed time).
 * Returns true when the data was inserted.
 */
export async function seed(client: PGlite, now: Date = new Date()): Promise<boolean> {
  return client.transaction(async (tx) => {
    const existing = await tx.query<{ n: number }>('SELECT count(*)::int AS n FROM compte');
    if (existing.rows[0]!.n > 0) return false;

    const ecurie = await ins(tx, "INSERT INTO ecurie (nom, statut) VALUES ('Écurie des Essais', 'active')");
    const courA = await ins(
      tx,
      "INSERT INTO lieu (ecurie_id, libelle, type_lieu, capacite) VALUES ($1, 'Cour des Tilleuls fictifs', 'cour', 20)",
      [ecurie],
    );
    const courB = await ins(
      tx,
      "INSERT INTO lieu (ecurie_id, libelle, type_lieu, capacite) VALUES ($1, 'Cour du Moulin fictif', 'cour', 20)",
      [ecurie],
    );

    const acteur = {} as Record<RoleDemo, Id>;
    for (const role of ROLES_DEMO) {
      const { nom, login } = PERSONAS[role];
      // A role may pre-exist without any account: reuse it rather than crash on UNIQUE.
      const roleId = await ins(
        tx,
        'INSERT INTO role (libelle) VALUES ($1) ON CONFLICT (libelle) DO UPDATE SET libelle = EXCLUDED.libelle',
        [role],
      );
      const acteurId = await ins(
        tx,
        "INSERT INTO acteur (nom, type_acteur, roles_metier) VALUES ($1, 'personne', ARRAY[$2]::text[])",
        [nom, role],
      );
      const compteId = await ins(tx, "INSERT INTO compte (acteur_id, login, etat) VALUES ($1, $2, 'actif')", [
        acteurId,
        login,
      ]);
      await ins(tx, 'INSERT INTO habilitation (compte_id, role_id, ecurie_id) VALUES ($1, $2, $3)', [
        compteId,
        roleId,
        ecurie,
      ]);
      acteur[role] = acteurId;
    }

    const chevaux: Id[] = [];
    for (const [i, nom] of CHEVAUX.entries()) {
      const cheval = await ins(
        tx,
        "INSERT INTO cheval (nom, sexe, date_naissance, statut) VALUES ($1, $2, $3, 'a_l_entrainement')",
        [nom, i % 2 === 0 ? 'F' : 'M', `${now.getFullYear() - 3 - (i % 3)}-04-0${i + 1}`],
      );
      // Every horse has a current stay (date_fin NULL) in one of the two yards.
      await ins(tx, "INSERT INTO sejour (cheval_id, lieu_id, date_debut, motif) VALUES ($1, $2, $3, 'entrainement')", [
        cheval,
        i < 3 ? courA : courB,
        jour(now, -60),
      ]);
      chevaux.push(cheval);
    }
    const [c1, c2, c3, c4, c5] = chevaux as [Id, Id, Id, Id, Id, Id];

    // The owner holds horses 1 and 2 (current detention, date_fin NULL).
    for (const cheval of [c1, c2]) {
      await ins(
        tx,
        'INSERT INTO detention (cheval_id, proprietaire_id, date_debut, quote_part) VALUES ($1, $2, $3, 100)',
        [cheval, acteur.proprietaire, jour(now, -365)],
      );
    }

    // The rider gets horses 3 and 4 through today's assignments on today's sessions.
    const lot = await ins(
      tx,
      "INSERT INTO lot (lieu_id, responsable_id, date, libelle, ordre_passage) VALUES ($1, $2, $3, 'Lot 1', 1)",
      [courA, acteur.entraineur, jour(now)],
    );
    for (const cheval of [c3, c4]) {
      const seance = await ins(
        tx,
        "INSERT INTO seance (cheval_id, lot_id, exercice, travail_prevu) VALUES ($1, $2, 'canter', '2 tours au petit galop')",
        [cheval, lot],
      );
      await ins(
        tx,
        "INSERT INTO affectation (seance_id, acteur_id, date_heure, fonction, consigne) VALUES ($1, $2, $3, 'cavalier', 'Allure régulière')",
        [seance, acteur.cavalier, instant(now, 0, 7)],
      );
    }

    const p7 = await ins(
      tx,
      "INSERT INTO produit (nom, categorie, unite, delai_retrait_jours) VALUES ('Anti-inflammatoire fictif A', 'medicament', 'ml', 7)",
    );
    const p2 = await ins(
      tx,
      "INSERT INTO produit (nom, categorie, unite, delai_retrait_jours) VALUES ('Antibiotique fictif B', 'medicament', 'ml', 2)",
    );
    await ins(
      tx,
      "INSERT INTO produit (nom, categorie, unite, delai_retrait_jours) VALUES ('Complément fictif C', 'autre', 'g', NULL)",
    );

    for (const [cheval, description] of [
      [c2, 'Ration réduite en foin, eau à volonté'],
      [c5, 'Repos au paddock, pas de travail monté'],
    ] as const) {
      await ins(
        tx,
        "INSERT INTO regime_special (cheval_id, description, debut, valide_par_id, auteur_id, statut) VALUES ($1, $2, $3, $4, $5, 'valide')",
        [cheval, description, jour(now, -2), acteur.veterinaire, acteur.veterinaire],
      );
    }

    // Planned administrations (statut valide, date_reelle NULL: planned, not done).
    // "En retard" is computed (D9): the one of yesterday is overdue. Today's one stays
    // later the same day: not before 20:00, at least 1 h ahead, never past 23:59:59.999.
    const todayLater = new Date(
      Math.max(
        instant(now, 0, 20).getTime(),
        Math.min(now.getTime() + 3_600_000, instant(now, 1, 0).getTime() - 1),
      ),
    );
    const plans: Array<[Id, Id, number, Date]> = [
      [c5, p2, 2, instant(now, -1, 9)],
      [c1, p7, 7, todayLater],
    ];
    for (const [cheval, produit, delai, quand] of plans) {
      const acte = await ins(
        tx,
        `INSERT INTO acte_sante (cheval_id, intervenant_id, date_heure, type_acte, soin, delai_retrait_jours, auteur_id, statut)
         VALUES ($1, $2, $3, 'soin', 'Traitement planifié', $4, $5, 'valide')`,
        [cheval, acteur.veterinaire, quand, delai, acteur.veterinaire],
      );
      await ins(
        tx,
        `INSERT INTO administration (acte_id, produit_id, date_heure, dose, unite, voie, auteur_id, statut)
         VALUES ($1, $2, $3, 5, 'ml', 'IV', $4, 'valide')`,
        [acte, produit, quand, acteur.veterinaire],
      );
    }

    // A race in 3 days, with a draft entry on horse 1, treated today (7-day product).
    const course = await ins(
      tx,
      "INSERT INTO course (date_heure, nom, hippodrome, pays, distance) VALUES ($1, 'Prix de la Démonstration', 'Hippodrome Imaginaire', 'FR', 2000)",
      [instant(now, 3, 14)],
    );
    await ins(
      tx,
      "INSERT INTO engagement (cheval_id, course_id, date_engagement, auteur_id, statut) VALUES ($1, $2, $3, $4, 'brouillon')",
      [c1, course, jour(now), acteur.charge_engagements],
    );

    const mesures: Array<[Id, 'poids' | 'temperature', number, string, number]> = [
      [c1, 'poids', 478.5, 'kg', -3],
      [c3, 'temperature', 37.8, '°C', -2],
      [c4, 'poids', 502, 'kg', -1],
    ];
    for (const [cheval, type, valeur, unite, days] of mesures) {
      await ins(
        tx,
        "INSERT INTO mesure (cheval_id, type, valeur, unite, auteur_id, date_reelle, statut) VALUES ($1, $2, $3, $4, $5, $6, 'valide')",
        [cheval, type, valeur, unite, acteur.assistant_entraineur, instant(now, days, 8)],
      );
    }
    return true;
  });
}

/**
 * Day (`YYYY-MM-DD`) the demo data is anchored on: the date of the seeded 'Lot 1'.
 * Null when no demo data exists. The seed runs once, so this day goes stale.
 */
export async function jourDesDonnees(client: PGlite): Promise<string | null> {
  const res = await client.query<{ d: string | null }>("SELECT min(date)::text AS d FROM lot WHERE libelle = 'Lot 1'");
  return res.rows[0]?.d ?? null;
}
