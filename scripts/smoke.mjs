// Témoin de bout en bout du socle, joué sur la racine fusionnée (après `npm ci`) :
// `npm test` des workspaces, `npm run build`, puis l'API réelle lancée sur un port
// libre et interrogée sur /api/health, qui doit rendre {"status":"ok","tables":49}.
// Sort en 0 si tout passe, sinon en 1, l'étape et sa cause nommées sur stderr.
//
// Usage : `node scripts/smoke.mjs` depuis la racine. Sans shell : npm est lancé par
// son CLI JS (npm_execpath, sinon celui livré à côté de node).
// L'API est arrêtée comme dans dev.mjs : sous win32 `taskkill /T /F`, dont on attend
// l'`exit` avant de sortir (sinon un node.exe orphelin garde le port, constat C8).
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const isWin = process.platform === "win32";
const PORT = Number(process.env.SMOKE_PORT ?? 3917);
const EXPECTED_TABLES = 49;
const HEALTH_TIMEOUT_MS = 90_000;
// Chemin absolu : aucune résolution par PATH (comme dev.mjs).
const TASKKILL = join(process.env.SystemRoot ?? "C:\\Windows", "System32", "taskkill.exe");

const npmCli =
  process.env.npm_execpath ??
  join(dirname(process.execPath), ...(isWin ? [] : ["..", "lib"]), "node_modules", "npm", "bin", "npm-cli.js");

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

// Résout true si l'API est arrêtée (taskkill code 0, ou 128 : déjà sortie), false sinon.
function stop(child) {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null || child.pid === undefined) return resolve(true);
    if (isWin) {
      const killer = spawn(TASKKILL, ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
      killer.on("exit", (code) => resolve(code === 0 || code === 128));
      killer.on("error", (err) => {
        process.stderr.write(`smoke : taskkill — ${err.message}\n`);
        resolve(false);
      });
    } else {
      child.on("exit", () => resolve(true));
      child.kill("SIGTERM");
    }
  });
}

function portFree(port) {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.once("error", () => resolve(false));
    probe.once("listening", () => probe.close(() => resolve(true)));
    probe.listen(port, "127.0.0.1");
  });
}

// Rend true si l'API a bien été arrêtée ; lève si /api/health n'a pas répondu comme attendu.
async function health() {
  const url = `http://127.0.0.1:${PORT}/api/health`;
  const server = spawn(process.execPath, ["src/server.ts"], {
    cwd: join(ROOT, "api"),
    env: { ...process.env, PORT: String(PORT) },
    stdio: ["ignore", "inherit", "inherit"],
  });
  let exited = null;
  server.on("exit", (code, signal) => (exited = code ?? signal));
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  const probe = async () => {
    while (Date.now() < deadline) {
      if (exited !== null) throw new Error(`l'API est sortie (code ${exited}) avant de répondre`);
      try {
        const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
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
  };
  // Aucun throw dans un finally : l'arrêt est toujours attendu, son verdict toujours rendu.
  let failure = null;
  try {
    await probe();
  } catch (err) {
    failure = err;
  }
  const stopped = await stop(server);
  if (failure !== null) {
    if (!stopped) process.stderr.write(`smoke : l'API (pid ${server.pid}) n'a pas pu être arrêtée\n`);
    throw failure;
  }
  return stopped;
}

if (!existsSync(npmCli)) fail("préalable", `CLI npm introuvable : ${npmCli}`);
if (!existsSync(join(ROOT, "node_modules"))) fail("préalable", "node_modules absent : lancer `npm ci` d'abord");
if (!(await portFree(PORT))) fail("préalable", `port ${PORT} occupé sur 127.0.0.1 : libérer le port ou poser SMOKE_PORT`);

await run("npm test", ["test"]);
await run("npm run build", ["run", "build"]);
let stopped = false;
try {
  stopped = await health();
} catch (err) {
  fail("/api/health", err instanceof Error ? err.message : String(err));
}
if (!stopped) fail("arrêt de l'API", `taskkill n'a pas arrêté l'API : le port ${PORT} peut rester tenu`);
process.stdout.write("smoke : OK\n");
