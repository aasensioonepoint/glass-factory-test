import { buildApp } from './app.ts';
import { createDb, DATA_DIR } from './db/client.ts';
import { migrate } from './db/migrate.ts';

const rawPort = process.env.PORT;
const port = rawPort === undefined ? 3000 : Number(rawPort);
if (rawPort !== undefined && (!/^\d+$/.test(rawPort) || port < 1 || port > 65535)) {
  console.error(`api: PORT invalide « ${rawPort} » — attendu un entier de 1 à 65535`);
  process.exit(1);
}
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
