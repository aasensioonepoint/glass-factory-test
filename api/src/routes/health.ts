import type { FastifyInstance } from 'fastify';
import { sql } from 'drizzle-orm';
import type { Db } from '../db/client.ts';

const healthResponse = {
  200: {
    type: 'object',
    properties: {
      status: { type: 'string', enum: ['ok'] },
      tables: { type: 'integer' },
    },
    required: ['status', 'tables'],
    additionalProperties: false,
  },
} as const;

/** GET /api/health: liveness plus the count of business tables in `public`. */
export function registerHealth(app: FastifyInstance, db: Db): void {
  app.get('/api/health', { schema: { response: healthResponse } }, async () => {
    const result = await db.execute<{ n: number }>(
      sql`SELECT count(*)::int AS n FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'`,
    );
    return { status: 'ok' as const, tables: result.rows[0]?.n ?? 0 };
  });
}
