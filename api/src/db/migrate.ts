import type { PGlite } from '@electric-sql/pglite';
import { migration0001 } from './migrations/0001_mcd_v0.ts';

export interface Migration {
  id: string;
  sql: string;
}

/** Ordered list: append only, never reorder or edit an applied entry. */
export const MIGRATIONS: readonly Migration[] = [migration0001];

/**
 * Home-made migrator (no drizzle-kit). The tracking table lives in the `meta`
 * schema, outside `public`, so it never counts among the business tables.
 * Each pending migration and its tracking row commit in ONE transaction, run
 * on the transaction handle: the outer client deadlocks inside the callback.
 */
export async function migrate(client: PGlite, migrations: readonly Migration[] = MIGRATIONS): Promise<string[]> {
  await client.exec(
    'CREATE SCHEMA IF NOT EXISTS meta; ' +
      'CREATE TABLE IF NOT EXISTS meta.migrations (id text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());',
  );
  const done = await client.query<{ id: string }>('SELECT id FROM meta.migrations');
  const applied = new Set(done.rows.map((row) => row.id));
  const ran: string[] = [];
  for (const migration of migrations) {
    if (applied.has(migration.id)) continue;
    await client.transaction(async (tx) => {
      await tx.exec(migration.sql);
      await tx.query('INSERT INTO meta.migrations (id) VALUES ($1)', [migration.id]);
    });
    ran.push(migration.id);
  }
  return ran;
}
