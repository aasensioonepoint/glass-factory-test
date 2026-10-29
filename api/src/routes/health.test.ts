import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { buildApp } from '../app.ts';
import { createDb, DATA_DIR, type DbHandle } from '../db/client.ts';
import { migrate } from '../db/migrate.ts';

let handle: DbHandle | undefined;

afterEach(async () => {
  await handle?.client.close();
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
});

describe('DATA_DIR', () => {
  it('is <repo>/data/pglite resolved from client.ts, never from the cwd', () => {
    const clientUrl = new URL('../db/client.ts', import.meta.url);
    expect(DATA_DIR).toBe(fileURLToPath(new URL('../../../data/pglite', clientUrl)));
    expect(DATA_DIR.replaceAll('\\', '/').endsWith('api/data/pglite')).toBe(false);
    // Positive control: two levels up from DATA_DIR is the repo root, which holds schema/.
    expect(existsSync(join(DATA_DIR, '..', '..', 'schema', 'graffard_racing_mcd_v0.sql'))).toBe(true);
  });
});
