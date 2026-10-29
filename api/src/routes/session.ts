import type { FastifyInstance } from 'fastify';
import { sql } from 'drizzle-orm';
import type { Db } from '../db/client.ts';
import { chargerCompte, estRole, normaliserId, requireCompte, ROLES, type Role } from '../auth/session.ts';

const id = { type: 'string' } as const;
const role = { type: 'string', enum: [...ROLES] } as const;

const compteSchema = {
  type: 'object',
  properties: {
    compteId: id,
    acteurId: id,
    nom: { type: 'string' },
    roles: { type: 'array', items: role },
  },
  required: ['compteId', 'acteurId', 'nom', 'roles'],
  additionalProperties: false,
} as const;

const erreurSchema = {
  type: 'object',
  properties: { erreur: { type: 'string' } },
  required: ['erreur'],
} as const;

const personasSchema = {
  response: {
    200: {
      type: 'array',
      items: {
        type: 'object',
        properties: { compteId: id, nom: { type: 'string' }, role },
        required: ['compteId', 'nom', 'role'],
        additionalProperties: false,
      },
    },
  },
} as const;

const sessionSchema = {
  body: {
    type: 'object',
    // validé par normaliserId, sans coercion Ajv : a typed schema lets Ajv turn
    // 9007199254740993 into "9007199254740992" (another compte) before the check.
    properties: { compteId: {} },
    required: ['compteId'],
  },
  response: {
    200: {
      type: 'object',
      properties: { jeton: { type: 'string' }, compte: compteSchema },
      required: ['jeton', 'compte'],
      additionalProperties: false,
    },
    // No 400 schema: Fastify's own validation error has another shape and must serialize as is.
    404: erreurSchema,
  },
} as const;

const moiSchema = { response: { 200: compteSchema, 401: erreurSchema } } as const;

export interface Persona {
  compteId: string;
  nom: string;
  role: Role;
}

/**
 * One persona per compte holding at least one known role; a compte with several
 * habilitations shows under its first role in the order of ROLES.
 */
export async function listerPersonas(db: Db): Promise<Persona[]> {
  const lignes = await db.execute<{ compte_id: string; nom: string; libelle: string }>(
    sql`SELECT c.id::text AS compte_id, a.nom, r.libelle
        FROM compte c
        JOIN acteur a ON a.id = c.acteur_id
        JOIN habilitation h ON h.compte_id = c.id
        JOIN role r ON r.id = h.role_id
        ORDER BY c.id`,
  );
  const parCompte = new Map<string, Persona>();
  for (const { compte_id: compteId, nom, libelle } of lignes.rows) {
    if (!estRole(libelle)) continue;
    const actuel = parCompte.get(compteId);
    if (actuel === undefined || ROLES.indexOf(libelle) < ROLES.indexOf(actuel.role)) {
      parCompte.set(compteId, { compteId, nom, role: libelle });
    }
  }
  return [...parCompte.values()];
}

/**
 * Demo persona login (D4-A): no password, any listed compte may open a session.
 *   GET  /api/personas            → [{compteId, nom, role}], public
 *   POST /api/session {compteId}  → {jeton, compte}; 400 malformed id, 404 unknown compte
 *   GET  /api/moi                 → compte; 401 without a valid token
 * Requires `registerAuth` on the same app first.
 */
export function registerSession(app: FastifyInstance, db: Db): void {
  app.get('/api/personas', { schema: personasSchema }, async () => listerPersonas(db));

  app.post<{ Body: { compteId: unknown } }>(
    '/api/session',
    { schema: sessionSchema },
    async (request, reply) => {
      const compteId = normaliserId(request.body.compteId);
      if (compteId === null) return reply.code(400).send({ erreur: 'compte_invalide' });
      const compte = await chargerCompte(db, compteId);
      if (compte === null) return reply.code(404).send({ erreur: 'compte_inconnu' });
      return { jeton: app.signerJeton(compte.compteId), compte };
    },
  );

  app.get('/api/moi', { schema: moiSchema, preHandler: requireCompte }, async (request, reply) => {
    const session = request.compte;
    const compte = session === null ? null : await chargerCompte(db, session.compteId);
    if (compte === null) return reply.code(401).send({ erreur: 'non_autorise' });
    return compte;
  });
}
