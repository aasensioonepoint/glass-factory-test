import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { buildApp } from '../app.ts';
import { createDb, DATA_DIR, type DbHandle } from '../db/client.ts';
import { migrate } from '../db/migrate.ts';

let handle: DbHandle | undefined;

afterEach(async () => {
  await handle?.client.close();
  handle?.release();
  handle = undefined;
});

async function health(h: DbHandle): Promise<{ statusCode: number; body: unknown }> {
  const app = buildApp({ db: h.db });
  try {
    const res = await app.inject({ method: 'GET', url: '/api/health' });
    return { statusCode: res.statusCode, body: res.json() };
  } finally {
    await app.close();
  }
}

describe('GET /api/health', () => {
  it('reports 0 tables before migrate', async () => {
    handle = createDb();
    const res = await health(handle);
    expect(res.statusCode).toBe(200);
    expect(res.body).toEqual({ status: 'ok', tables: 0 });
  });

  it('reports the 49 MCD V0 tables after migrate', async () => {
    handle = createDb();
    await migrate(handle.client);
    const res = await health(handle);
    expect(res.statusCode).toBe(200);
    expect(res.body).toEqual({ status: 'ok', tables: 49 });
  });

  it('is idempotent: a second migrate applies nothing and keeps 49 tables', async () => {
    handle = createDb();
    expect(await migrate(handle.client)).toEqual(['0001_mcd_v0']);
    expect(await migrate(handle.client)).toEqual([]);
    const res = await health(handle);
    expect(res.body).toEqual({ status: 'ok', tables: 49 });
    const tracked = await handle.client.query<{ id: string }>('SELECT id FROM meta.migrations');
    expect(tracked.rows).toEqual([{ id: '0001_mcd_v0' }]);
  });

  it('is atomic: SQL that succeeds but a tracking insert that fails leaves no table and no row', async () => {
    handle = createDb();
    // The SQL itself succeeds; its last statement makes the tracking INSERT that follows fail
    // (a NOT VALID check still applies to new rows). Only one transaction around SQL + INSERT
    // can roll the CREATE TABLE back.
    const poisoned = {
      id: '9999_atomicity_probe',
      sql:
        'CREATE TABLE public.atomicity_probe (id int); ' +
        'ALTER TABLE meta.migrations ADD CONSTRAINT refuse_all CHECK (false) NOT VALID;',
    };
    await expect(migrate(handle.client, [poisoned])).rejects.toThrow();
    const res = await health(handle);
    expect(res.body).toEqual({ status: 'ok', tables: 0 });
    const tracked = await handle.client.query<{ id: string }>('SELECT id FROM meta.migrations');
    expect(tracked.rows).toEqual([]);
  });
});

describe('createDb on disk', () => {
  it('locks its data dir: a second open of the same dir is refused, then allowed once released', async () => {
    const dir = join(mkdtempSync(join(tmpdir(), 'gr-')), 'pglite');
    handle = createDb(dir);
    expect(existsSync(`${dir}.lock`)).toBe(true);
    expect(() => createDb(dir)).toThrow(/déjà ouvert/);
    await handle.client.close();
    handle.release();
    expect(existsSync(`${dir}.lock`)).toBe(false);
    handle = createDb(dir);
  });
});

describe('DATA_DIR', () => {
  it('is <repo>/data/pglite resolved from client.ts, never from the cwd', () => {
    const clientUrl = new URL('../db/client.ts', import.meta.url);
    expect(DATA_DIR).toBe(fileURLToPath(new URL('../../../data/pglite', clientUrl)));
    // Outside the api/ workspace, bounded on path segments (a checkout folder named *api stays fine).
    const apiDir = fileURLToPath(new URL('../../', import.meta.url));
    expect(relative(apiDir, DATA_DIR).startsWith('..')).toBe(true);
    // Positive control: two levels up from DATA_DIR is the repo root, which holds schema/.
    expect(existsSync(join(DATA_DIR, '..', '..', 'schema', 'graffard_racing_mcd_v0.sql'))).toBe(true);
  });
});
