import { buildApp } from './app.ts';
import { createDb, DATA_DIR } from './db/client.ts';
import { migrate } from './db/migrate.ts';

const port = Number(process.env.PORT ?? 3000);
const host = '127.0.0.1';

const { client, db } = createDb(DATA_DIR);
await migrate(client);

const app = buildApp({ db });

async function shutdown(): Promise<void> {
  await app.close();
  await client.close();
  process.exit(0);
}
process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

await app.listen({ port, host });
console.log(`api listening on http://${host}:${port}`);
