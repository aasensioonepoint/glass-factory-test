// Témoin de bout en bout du socle, joué sur la racine fusionnée (après `npm ci`) :
// `npm test` des workspaces, `npm run build`, puis l'API réelle lancée sur un port
// libre et interrogée sur /api/health, qui doit rendre {"status":"ok","tables":49}.
// Sort en 0 si tout passe, sinon avec le code de l'étape qui a échoué, nommée sur stderr.
//
// Usage : `node scripts/smoke.mjs` depuis la racine. Sans shell : npm est lancé par
// son CLI JS (npm_execpath, sinon celui livré à côté de node).
// L'API est arrêtée comme dans dev.mjs : sous win32 `taskkill /T /F`, dont on attend
// l'`exit` avant de sortir (sinon un node.exe orphelin garde le port, constat C8).
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const isWin = process.platform === "win32";
const PORT = Number(process.env.SMOKE_PORT ?? 3917);
const EXPECTED_TABLES = 49;
const HEALTH_TIMEOUT_MS = 90_000;

const npmCli =
  process.env.npm_execpath ?? join(dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js");

function fail(step, message) {
  process.stderr.write(`smoke : ÉCHEC ${step} — ${message}\n`);
  process.exit(1);
}

function run(step, args) {
  return new Promise((resolve) => {
    process.stdout.write(`smoke : ${step}…\n`);
    const child = spawn(process.execPath, [npmCli, ...args], { cwd: ROOT, stdio: "inherit" });
    child.on("error", (err) => fail(step, err.message));
    child.on("exit", (code) => (code === 0 ? resolve() : fail(step, `code ${code}`)));
  });
}

function stop(child) {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.pid === undefined) return resolve();
    if (isWin) {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
      killer.on("exit", () => resolve());
      killer.on("error", () => resolve());
    } else {
      child.on("exit", () => resolve());
      child.kill("SIGTERM");
    }
  });
}

async function health() {
  const url = `http://127.0.0.1:${PORT}/api/health`;
  const server = spawn(process.execPath, ["src/server.ts"], {
    cwd: join(ROOT, "api"),
    env: { ...process.env, PORT: String(PORT) },
    stdio: ["ignore", "inherit", "inherit"],
  });
  let exited = null;
  server.on("exit", (code) => (exited = code));
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  try {
    while (Date.now() < deadline) {
      if (exited !== null) throw new Error(`l'API est sortie (code ${exited}) avant de répondre`);
      try {
        const res = await fetch(url);
        const body = await res.json();
        if (res.status !== 200 || body.status !== "ok" || body.tables !== EXPECTED_TABLES) {
          throw new Error(`réponse inattendue ${res.status} ${JSON.stringify(body)}`);
        }
        process.stdout.write(`smoke : ${url} => ${JSON.stringify(body)}\n`);
        return;
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("réponse inattendue")) throw err;
        await new Promise((r) => setTimeout(r, 500));
      }
    }
    throw new Error(`aucune réponse en ${HEALTH_TIMEOUT_MS / 1000} s`);
  } finally {
    await stop(server);
  }
}

if (!existsSync(npmCli)) fail("préalable", `CLI npm introuvable : ${npmCli}`);
if (!existsSync(join(ROOT, "node_modules"))) fail("préalable", "node_modules absent : lancer `npm ci` d'abord");

await run("npm test", ["test"]);
await run("npm run build", ["run", "build"]);
try {
  await health();
} catch (err) {
  fail("/api/health", err instanceof Error ? err.message : String(err));
}
process.stdout.write("smoke : OK\n");
