import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { sql } from 'drizzle-orm';
import type { Db } from '../db/client.ts';

/** Application role labels seeded by T2, verbatim; the web client refuses any other. */
export const ROLES = [
  'entraineur',
  'assistant_entraineur',
  'cavalier',
  'veterinaire',
  'charge_engagements',
  'proprietaire',
] as const;

export type Role = (typeof ROLES)[number];

export function estRole(valeur: string): valeur is Role {
  return (ROLES as readonly string[]).includes(valeur);
}

/** Token lifetime: 12 h, in seconds. */
export const DUREE_JETON_S = 12 * 60 * 60;

/** Minimum length of a key supplied through the environment (bytes). */
const CLE_MIN_OCTETS = 32;

/** bigint ids travel as decimal strings: no precision loss, `CompteId = string | number` on the web side. */
const ID_DECIMAL = /^[1-9][0-9]{0,18}$/;
const BIGINT_MAX = 9223372036854775807n;

/** A bigint id as a canonical decimal string, or `null` when out of shape or out of range. */
export function normaliserId(valeur: unknown): string | null {
  let texte: string;
  if (typeof valeur === 'number') {
    if (!Number.isSafeInteger(valeur)) return null;
    texte = String(valeur);
  } else if (typeof valeur === 'string') {
    texte = valeur;
  } else {
    return null;
  }
  if (!ID_DECIMAL.test(texte) || BigInt(texte) > BIGINT_MAX) return null;
  return texte;
}

/**
 * Signing key: `GRAFFARD_CLE_SIGNATURE` when set, otherwise a random key drawn now
 * (tokens are lost on restart, accepted). A key shorter than 32 bytes is refused.
 */
export function cleDeSignature(env: NodeJS.ProcessEnv = process.env): Buffer {
  const valeur = env.GRAFFARD_CLE_SIGNATURE;
  if (valeur === undefined || valeur === '') return randomBytes(CLE_MIN_OCTETS);
  const cle = Buffer.from(valeur, 'utf8');
  if (cle.length < CLE_MIN_OCTETS) {
    throw new Error(`GRAFFARD_CLE_SIGNATURE trop courte : ${CLE_MIN_OCTETS} octets au moins`);
  }
  return cle;
}

function mac(cle: Buffer, payload: string): string {
  return createHmac('sha256', cle).update(payload).digest('base64url');
}

function secondes(maintenantMs: number): number {
  return Math.floor(maintenantMs / 1000);
}

/** `base64url(payload).base64url(mac)`, payload `{compteId, exp}` (exp in epoch seconds). */
export function signerJeton(compteId: string, cle: Buffer, maintenantMs: number = Date.now()): string {
  const payload = Buffer.from(
    JSON.stringify({ compteId, exp: secondes(maintenantMs) + DUREE_JETON_S }),
    'utf8',
  ).toString('base64url');
  return `${payload}.${mac(cle, payload)}`;
}

/**
 * The compte id a token carries, or `null` if it is malformed, forged or expired.
 * The MAC is compared on its canonical base64url text, in constant time, after a
 * length check: a lenient base64 decode can never let an altered character through.
 */
export function verifierJeton(jeton: string, cle: Buffer, maintenantMs: number = Date.now()): string | null {
  const parties = jeton.split('.');
  if (parties.length !== 2) return null;
  const [payload, recu] = parties as [string, string];
  if (payload === '' || recu === '') return null;
  const attendu = Buffer.from(mac(cle, payload), 'utf8');
  const fourni = Buffer.from(recu, 'utf8');
  if (fourni.length !== attendu.length || !timingSafeEqual(fourni, attendu)) return null;
  let contenu: unknown;
  try {
    contenu = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
  } catch {
    return null;
  }
  if (typeof contenu !== 'object' || contenu === null) return null;
  const { compteId, exp } = contenu as Record<string, unknown>;
  const id = normaliserId(compteId);
  if (id === null || typeof exp !== 'number' || !Number.isSafeInteger(exp)) return null;
  if (exp <= secondes(maintenantMs)) return null;
  return id;
}

/** Authenticated caller; roles are always re-read from the database. */
export interface CompteSession {
  compteId: string;
  acteurId: string;
  roles: Role[];
}

export interface CompteDetail extends CompteSession {
  nom: string;
}

/** Roles in the fixed order of ROLES, unknown labels dropped. */
export function trierRoles(libelles: readonly string[]): Role[] {
  return ROLES.filter((role) => libelles.includes(role));
}

/** The compte with its actor name and its roles (habilitation → role), or `null` if unknown. */
export async function chargerCompte(db: Db, compteId: string): Promise<CompteDetail | null> {
  const comptes = await db.execute<{ compte_id: string; acteur_id: string; nom: string }>(
    sql`SELECT c.id::text AS compte_id, a.id::text AS acteur_id, a.nom
        FROM compte c JOIN acteur a ON a.id = c.acteur_id
        WHERE c.id = CAST(${compteId} AS bigint)`,
  );
  const ligne = comptes.rows[0];
  if (ligne === undefined) return null;
  const roles = await db.execute<{ libelle: string }>(
    sql`SELECT DISTINCT r.libelle
        FROM habilitation h JOIN role r ON r.id = h.role_id
        WHERE h.compte_id = CAST(${compteId} AS bigint)`,
  );
  return {
    compteId: ligne.compte_id,
    acteurId: ligne.acteur_id,
    nom: ligne.nom,
    roles: trierRoles(roles.rows.map((row) => row.libelle)),
  };
}

declare module 'fastify' {
  interface FastifyRequest {
    /** Set by the auth hook: `null` without a valid token for an existing compte. */
    compte: CompteSession | null;
  }
  interface FastifyInstance {
    /** Signs a session token with the key drawn at registration. */
    signerJeton: (compteId: string) => string;
  }
}

function jetonPorteur(request: FastifyRequest): string | null {
  const entete = request.headers.authorization;
  if (typeof entete !== 'string') return null;
  const correspondance = /^Bearer ([^\s]+)$/.exec(entete);
  return correspondance?.[1] ?? null;
}

export interface AuthOptions {
  /** Signing key; defaults to `cleDeSignature()` read once, here. */
  cle?: Buffer;
  /** Clock in epoch milliseconds; tests freeze it. */
  maintenant?: () => number;
}

/**
 * Decorates the app with `signerJeton` and every request with `compte`.
 * An absent or invalid token leaves `compte` null; it never fails a public route.
 */
export function registerAuth(app: FastifyInstance, db: Db, options: AuthOptions = {}): void {
  const cle = options.cle ?? cleDeSignature();
  const maintenant = options.maintenant ?? Date.now;
  app.decorate('signerJeton', (compteId: string) => signerJeton(compteId, cle, maintenant()));
  app.decorateRequest('compte', null);
  app.addHook('onRequest', async (request) => {
    request.compte = null;
    const jeton = jetonPorteur(request);
    if (jeton === null) return;
    const compteId = verifierJeton(jeton, cle, maintenant());
    if (compteId === null) return;
    const detail = await chargerCompte(db, compteId);
    if (detail === null) return;
    request.compte = { compteId: detail.compteId, acteurId: detail.acteurId, roles: detail.roles };
  });
}

/** preHandler: 401 without a valid session. */
export async function requireCompte(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  if (request.compte === null) {
    await reply.code(401).send({ erreur: 'non_autorise' });
  }
}

/** preHandler: 401 without a valid session, 403 when the caller holds none of `roles`. */
export function requireRole(...roles: Role[]) {
  return async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const compte = request.compte;
    if (compte === null) {
      await reply.code(401).send({ erreur: 'non_autorise' });
      return;
    }
    if (!roles.some((role) => compte.roles.includes(role))) {
      await reply.code(403).send({ erreur: 'interdit' });
    }
  };
}
