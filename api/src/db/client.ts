import { closeSync, mkdirSync, openSync, readFileSync, rmSync, writeSync } from 'node:fs';
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
  /** Releases the exclusive lock on the data dir; no-op in memory. */
  release: () => void;
}

/** Windows (EDR, indexer) can briefly hold the lock file: EPERM/EBUSY are retried. */
const LOCK_RM = { force: true, maxRetries: 5, retryDelay: 100 } as const;

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return (err as NodeJS.ErrnoException).code === 'EPERM';
  }
}

/**
 * PGlite does not lock its data dir: a second process on the same dir silently
 * erases the first one's writes. Exclusive lock file `${dataDir}.lock` holding the
 * owner's PID; a lock whose owner is dead is reclaimed once.
 */
function acquireLock(dataDir: string): () => void {
  const lockPath = `${dataDir}.lock`;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let fd: number;
    try {
      fd = openSync(lockPath, 'wx');
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== 'EEXIST') throw err;
      let owner = Number.NaN;
      try {
        owner = Number.parseInt(readFileSync(lockPath, 'utf8').trim(), 10);
      } catch {
        // Unreadable or vanished lock: treated as stale.
      }
      if (Number.isInteger(owner) && owner > 0 && isAlive(owner)) {
        throw new Error(`${dataDir} déjà ouvert par le processus ${owner} : arrêter l'autre API d'abord`);
      }
      rmSync(lockPath, LOCK_RM);
      continue;
    }
    writeSync(fd, String(process.pid));
    closeSync(fd);
    let released = false;
    const release = (): void => {
      if (released) return;
      released = true;
      rmSync(lockPath, LOCK_RM);
    };
    process.once('exit', release);
    return release;
  }
  throw new Error(`${dataDir} : verrou ${lockPath} impossible à prendre`);
}

/** In-memory PGlite without argument, otherwise a persistent one in dataDir. */
export function createDb(dataDir?: string): DbHandle {
  let client: PGlite;
  let release: () => void = () => {};
  if (dataDir === undefined) {
    client = new PGlite();
  } else {
    mkdirSync(dataDir, { recursive: true });
    release = acquireLock(dataDir);
    try {
      client = new PGlite(dataDir);
    } catch (err) {
      release();
      throw err;
    }
  }
  return { client, db: drizzle({ client }), release };
}
