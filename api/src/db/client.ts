import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { PGlite } from '@electric-sql/pglite';
import { drizzle, type PgliteDatabase } from 'drizzle-orm/pglite';

/**
 * Shared contract: the data lives at <repo>/data/pglite, resolved from this
 * file's location — never from process.cwd(), which is api/ under `npm -w api`.
 */
export const DATA_DIR = fileURLToPath(new URL('../../../data/pglite', import.meta.url));

export type Db = PgliteDatabase;

export interface DbHandle {
  client: PGlite;
  db: Db;
}

/** In-memory PGlite without argument, otherwise a persistent one in dataDir. */
export function createDb(dataDir?: string): DbHandle {
  let client: PGlite;
  if (dataDir === undefined) {
    client = new PGlite();
  } else {
    mkdirSync(dataDir, { recursive: true });
    client = new PGlite(dataDir);
  }
  return { client, db: drizzle({ client }) };
}
