import { buildApp } from './app.ts';
import { cleDeSignature } from './auth/session.ts';
import { createDb, DATA_DIR } from './db/client.ts';
import { migrate } from './db/migrate.ts';
import { jour, jourDesDonnees, seed } from './db/seed.ts';

const rawPort = process.env.PORT;
const port = rawPort === undefined ? 3000 : Number(rawPort);
if (rawPort !== undefined && (!/^\d+$/.test(rawPort) || port < 1 || port > 65535)) {
  console.error(`api: PORT invalide « ${rawPort} » — attendu un entier de 1 à 65535`);
  process.exit(1);
}
const host = '127.0.0.1';

// Validate the signing key BEFORE opening the database: a bad key must not leave a seeded base behind.
try {
  cleDeSignature();
} catch (err) {
  console.error(`api: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
}
if (!process.env.GRAFFARD_CLE_SIGNATURE) {
  console.warn('api: clé de signature aléatoire — jetons perdus au redémarrage');
}

let handle: ReturnType<typeof createDb>;
try {
  handle = createDb(DATA_DIR);
} catch (err) {
  console.error(`api: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
}
const { client, db, release } = handle;
await migrate(client);
// Fictional demo data, inserted only while table `compte` is empty (seed checks it).
if (await seed(client)) {
  console.log('api: données de démonstration fictives insérées');
} else {
  const d = await jourDesDonnees(client);
  if (d !== null && d !== jour(new Date())) {
    console.warn(
      `api: données de démonstration datées du ${d} — affectations et soins périmés ; arrêter l'API et supprimer data/pglite`,
    );
  }
}

const app = buildApp({ db });

async function shutdown(): Promise<void> {
  await app.close();
  await client.close();
  release();
  process.exit(0);
}
process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

await app.listen({ port, host });
console.log(`api listening on http://${host}:${port}`);
