import type { FastifyInstance } from 'fastify';
import { sql, type SQL } from 'drizzle-orm';
import type { Db } from '../db/client.ts';
import { normaliserId, requireCompte, type CompteSession } from '../auth/session.ts';

/** Business day of the stable: the calendar date in Europe/Paris. */
export const FUSEAU = 'Europe/Paris';

/** How many measurements a horse file carries, latest first. */
export const NB_MESURES = 5;

const formatJour = new Intl.DateTimeFormat('en-CA', {
  timeZone: FUSEAU,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** `YYYY-MM-DD` of the instant `ms` in Europe/Paris. */
export function jourParis(ms: number): string {
  return formatJour.format(ms);
}

export interface ChevalResume {
  id: string;
  nom: string;
  sexe: string | null;
  dateNaissance: string | null;
  statut: string | null;
  cour: string | null;
}

export interface DossierCheval {
  id: string;
  nom: string;
  sexe: string | null;
  dateNaissance: string | null;
  statut: string | null;
  sire: string | null;
  sejour: { cour: string; depuis: string } | null;
  regime: { description: string } | null;
  mesures: Array<{ nature: string; valeur: string; date: string }>;
  restrictions?: Array<{ source: string; debut: string; finPrevue: string | null; statut: string }>;
}

/** Roles whose scope is the whole herd: every known role but cavalier and proprietaire. */
function voitToutEffectif(compte: CompteSession): boolean {
  return compte.roles.some((role) => role !== 'cavalier' && role !== 'proprietaire');
}

/**
 * SQL predicate on `c.id` (alias `c` = cheval): the union of what each role of the
 * compte sees. A compte with no known role sees nothing (fail-closed).
 */
function perimetre(compte: CompteSession, jour: string): SQL {
  if (voitToutEffectif(compte)) return sql`TRUE`;
  const conditions: SQL[] = [];
  if (compte.roles.includes('cavalier')) {
    // Today's assignments: the Paris date of date_heure, or the lot's date when it is unset.
    conditions.push(sql`c.id IN (
      SELECT s.cheval_id
      FROM affectation a
      JOIN seance s ON s.id = a.seance_id
      JOIN lot l ON l.id = s.lot_id
      WHERE a.acteur_id = CAST(${compte.acteurId} AS bigint)
        AND COALESCE((a.date_heure AT TIME ZONE ${FUSEAU})::date, l.date) = CAST(${jour} AS date))`);
  }
  if (compte.roles.includes('proprietaire')) {
    conditions.push(sql`c.id IN (
      SELECT d.cheval_id
      FROM detention d
      WHERE d.proprietaire_id = CAST(${compte.acteurId} AS bigint)
        AND d.date_debut <= CAST(${jour} AS date)
        AND (d.date_fin IS NULL OR d.date_fin >= CAST(${jour} AS date)))`);
  }
  if (conditions.length === 0) return sql`FALSE`;
  return sql.join(conditions, sql` OR `);
}

/** Current stay of `c.id` with its yard label: one row at most, latest start first. */
function sejourCourant(jour: string): SQL {
  return sql`LEFT JOIN LATERAL (
      SELECT li.libelle AS cour, se.date_debut::text AS depuis
      FROM sejour se JOIN lieu li ON li.id = se.lieu_id
      WHERE se.cheval_id = c.id
        AND se.date_debut <= CAST(${jour} AS date)
        AND (se.date_fin IS NULL OR se.date_fin >= CAST(${jour} AS date))
      ORDER BY se.date_debut DESC, se.id DESC
      LIMIT 1) sc ON TRUE`;
}

type LigneCheval = {
  id: string;
  nom: string;
  sexe: string | null;
  date_naissance: string | null;
  statut: string | null;
  cour: string | null;
};

/** French name order: the database collation (C in PGlite) would put « Éclair » after « Sable ». */
const ordreNom = new Intl.Collator('fr', { sensitivity: 'base' });

/** Horses within the compte's scope, sorted by name (French order), then by id. */
export async function listerChevaux(db: Db, compte: CompteSession, jour: string): Promise<ChevalResume[]> {
  const res = await db.execute<LigneCheval>(
    sql`SELECT c.id::text AS id, c.nom, c.sexe, c.date_naissance::text AS date_naissance, c.statut, sc.cour
        FROM cheval c
        ${sejourCourant(jour)}
        WHERE ${perimetre(compte, jour)}
        ORDER BY c.id`,
  );
  // Array.prototype.sort is stable: equal names keep the id order of the query.
  const lignes = [...res.rows].sort((x, y) => ordreNom.compare(x.nom, y.nom));
  return lignes.map((r) => ({
    id: r.id,
    nom: r.nom,
    sexe: r.sexe,
    dateNaissance: r.date_naissance,
    statut: r.statut,
    cour: r.cour,
  }));
}

/**
 * File of one horse, or `null` when it is unknown OR outside the compte's scope:
 * the caller cannot tell the two apart. `restrictions` is omitted when the compte
 * is a proprietaire only.
 */
export async function chargerDossier(
  db: Db,
  compte: CompteSession,
  chevalId: string,
  jour: string,
): Promise<DossierCheval | null> {
  const res = await db.execute<LigneCheval & { sire: string | null; depuis: string | null }>(
    sql`SELECT c.id::text AS id, c.nom, c.sexe, c.date_naissance::text AS date_naissance, c.statut, c.sire,
               sc.cour, sc.depuis
        FROM cheval c
        ${sejourCourant(jour)}
        WHERE c.id = CAST(${chevalId} AS bigint) AND (${perimetre(compte, jour)})`,
  );
  const ligne = res.rows[0];
  if (ligne === undefined) return null;

  const regimes = await db.execute<{ description: string }>(
    sql`SELECT description FROM regime_special
        WHERE cheval_id = CAST(${chevalId} AS bigint)
          AND statut NOT IN ('brouillon', 'annule')
          AND debut <= CAST(${jour} AS date)
          AND (fin IS NULL OR fin >= CAST(${jour} AS date))
        ORDER BY debut DESC, id DESC
        LIMIT 1`,
  );
  const mesures = await db.execute<{ nature: string; valeur: string; date: string }>(
    sql`SELECT type AS nature,
               trim_scale(valeur)::text || ' ' || unite AS valeur,
               to_char(date_reelle AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS date
        FROM mesure
        WHERE cheval_id = CAST(${chevalId} AS bigint) AND statut NOT IN ('brouillon', 'annule')
        ORDER BY date_reelle DESC, id DESC
        LIMIT ${NB_MESURES}`,
  );
  const regime = regimes.rows[0];
  const dossier: DossierCheval = {
    id: ligne.id,
    nom: ligne.nom,
    sexe: ligne.sexe,
    dateNaissance: ligne.date_naissance,
    statut: ligne.statut,
    sire: ligne.sire,
    sejour: ligne.cour === null || ligne.depuis === null ? null : { cour: ligne.cour, depuis: ligne.depuis },
    regime: regime === undefined ? null : { description: regime.description },
    mesures: mesures.rows.map((m) => ({ nature: m.nature, valeur: m.valeur, date: m.date })),
  };
  // C12: the owner does not see the detailed restrictions; any other role does.
  const proprietaireSeul = compte.roles.length > 0 && compte.roles.every((role) => role === 'proprietaire');
  if (!proprietaireSeul) {
    const restrictions = await db.execute<{ source: string; debut: string; fin_prevue: string | null; statut: string }>(
      sql`SELECT source, debut::text AS debut, fin_prevue::text AS fin_prevue, statut
          FROM restriction
          WHERE cheval_id = CAST(${chevalId} AS bigint)
          ORDER BY debut DESC, id DESC`,
    );
    dossier.restrictions = restrictions.rows.map((r) => ({
      source: r.source,
      debut: r.debut,
      finPrevue: r.fin_prevue,
      statut: r.statut,
    }));
  }
  return dossier;
}

const texte = { type: 'string' } as const;
const texteOuNull = { type: ['string', 'null'] } as const;

const resumeSchema = {
  type: 'object',
  properties: { id: texte, nom: texte, sexe: texteOuNull, dateNaissance: texteOuNull, statut: texteOuNull, cour: texteOuNull },
  required: ['id', 'nom', 'sexe', 'dateNaissance', 'statut', 'cour'],
  additionalProperties: false,
} as const;

const erreurSchema = {
  type: 'object',
  properties: { erreur: texte },
  required: ['erreur'],
} as const;

const dossierSchema = {
  type: 'object',
  properties: {
    id: texte,
    nom: texte,
    sexe: texteOuNull,
    dateNaissance: texteOuNull,
    statut: texteOuNull,
    sire: texteOuNull,
    sejour: {
      type: ['object', 'null'],
      properties: { cour: texte, depuis: texte },
      required: ['cour', 'depuis'],
      additionalProperties: false,
    },
    regime: {
      type: ['object', 'null'],
      properties: { description: texte },
      required: ['description'],
      additionalProperties: false,
    },
    mesures: {
      type: 'array',
      items: {
        type: 'object',
        properties: { nature: texte, valeur: texte, date: texte },
        required: ['nature', 'valeur', 'date'],
        additionalProperties: false,
      },
    },
    // Optional on purpose: absent for the proprietaire, never an empty array in its place.
    restrictions: {
      type: 'array',
      items: {
        type: 'object',
        properties: { source: texte, debut: texte, finPrevue: texteOuNull, statut: { type: 'string', enum: ['active', 'levee'] } },
        required: ['source', 'debut', 'finPrevue', 'statut'],
        additionalProperties: false,
      },
    },
  },
  required: ['id', 'nom', 'sexe', 'dateNaissance', 'statut', 'sire', 'sejour', 'regime', 'mesures'],
  additionalProperties: false,
} as const;

export interface ChevauxOptions {
  /** Clock in epoch milliseconds; tests freeze it. */
  maintenant?: () => number;
}

/**
 * Horse list and file, filtered SERVER-side by the caller's roles:
 *   GET /api/chevaux      → [{id, nom, sexe, dateNaissance, statut, cour}]; 401 without session
 *   GET /api/chevaux/:id  → file; 404 when unknown, malformed or outside the scope (never 403)
 * Scope: cavalier → today's assignments; proprietaire → current detention; any other
 * role → the whole herd; several roles → the union. Requires `registerAuth` first.
 */
export function registerChevaux(app: FastifyInstance, db: Db, options: ChevauxOptions = {}): void {
  const maintenant = options.maintenant ?? Date.now;

  app.get(
    '/api/chevaux',
    { schema: { response: { 200: { type: 'array', items: resumeSchema }, 401: erreurSchema } }, preHandler: requireCompte },
    async (request, reply) => {
      const compte = request.compte;
      if (compte === null) return reply.code(401).send({ erreur: 'non_autorise' });
      return listerChevaux(db, compte, jourParis(maintenant()));
    },
  );

  app.get<{ Params: { id: string } }>(
    '/api/chevaux/:id',
    { schema: { response: { 200: dossierSchema, 401: erreurSchema, 404: erreurSchema } }, preHandler: requireCompte },
    async (request, reply) => {
      const compte = request.compte;
      if (compte === null) return reply.code(401).send({ erreur: 'non_autorise' });
      const chevalId = normaliserId(request.params.id);
      const dossier = chevalId === null ? null : await chargerDossier(db, compte, chevalId, jourParis(maintenant()));
      if (dossier === null) return reply.code(404).send({ erreur: 'introuvable' });
      return dossier;
    },
  );
}
