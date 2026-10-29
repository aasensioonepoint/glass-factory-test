import Fastify, { type FastifyInstance } from 'fastify';
import type { Db } from './db/client.ts';
import { registerHealth } from './routes/health.ts';

export interface AppDeps {
  db: Db;
}

/** Builds the HTTP app around an injected database: tests pass an in-memory one. */
export function buildApp({ db }: AppDeps): FastifyInstance {
  const app = Fastify({ logger: false });
  registerHealth(app, db);
  return app;
}
