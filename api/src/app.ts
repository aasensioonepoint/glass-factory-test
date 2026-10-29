import Fastify, { type FastifyInstance } from 'fastify';
import type { Db } from './db/client.ts';
import { registerAuth } from './auth/session.ts';
import { registerChevaux } from './routes/chevaux.ts';
import { registerHealth } from './routes/health.ts';
import { registerSession } from './routes/session.ts';

export interface AppDeps {
  db: Db;
  /** Clock in epoch milliseconds, shared by auth and the dated routes; tests freeze it. */
  maintenant?: () => number;
}

/** Builds the HTTP app around an injected database: tests pass an in-memory one. */
export function buildApp({ db, maintenant }: AppDeps): FastifyInstance {
  const app = Fastify({ logger: false });
  // Auth first: its hook and decorators serve every route registered after it.
  registerAuth(app, db, { maintenant });
  registerHealth(app, db);
  registerSession(app, db);
  registerChevaux(app, db, { maintenant });
  return app;
}
