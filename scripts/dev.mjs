// Lance `npm run dev` des workspaces api et web côte à côte, stdio hérité, sans shell.
// Un enfant qui sort, ou SIGINT/SIGTERM reçu, arrête l'autre ; dev.mjs sort avec le
// code du PREMIER enfant sorti.
//
// Sous win32, l'arrêt passe par `taskkill /T /F` (l'arbre entier : npm puis node), et
// dev.mjs n'attend PAS seulement le spawn de taskkill : il attend son `exit` (ou son
// `error`). Sortir dans le même tick laisse un node.exe orphelin qui garde :3000/:5173
// (constat C8, mesuré). Ailleurs, `kill("SIGTERM")` puis attente de la sortie de l'enfant.
import { spawn } from "node:child_process";
import path from "node:path";

const WORKSPACES = ["api", "web"];
const isWin = process.platform === "win32";
// Chemin absolu : aucune résolution par PATH (un taskkill.exe planté dans le cwd ou le PATH).
const TASKKILL = path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "taskkill.exe");
const npmCli = process.env.npm_execpath;

if (!npmCli) {
  process.stderr.write("dev.mjs : lancer par « npm run dev »\n");
  process.exit(1);
}
if (process.env.PORT !== undefined && process.env.PORT !== "3000") {
  process.stderr.write(`dev.mjs : PORT=${process.env.PORT} refusé — le proxy Vite vise 127.0.0.1:3000\n`);
  process.exit(1);
}

const children = [];
const ended = new Set();
let firstCode = null;
let stopping = false;
let pendingKills = 0;

const isAlive = (child) => !ended.has(child);

function maybeExit() {
  if (!stopping || pendingKills > 0) return;
  if (!isWin && children.some(isAlive)) return;
  process.exit(firstCode ?? 1);
}

function stopChild(child) {
  if (!isAlive(child) || child.pid === undefined) return;
  if (isWin) {
    pendingKills += 1;
    let settled = false;
    const settle = () => {
      if (settled) return;
      settled = true;
      pendingKills -= 1;
      maybeExit();
    };
    const killer = spawn(TASKKILL, ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    killer.on("exit", (code) => {
      if (code !== 0 && code !== 128) {
        process.stderr.write(`dev.mjs : taskkill ${child.pid} code ${code} — ports peut-être tenus\n`);
      }
      settle();
    });
    killer.on("error", (err) => {
      process.stderr.write(`dev.mjs : ${err.message}\n`);
      settle();
    });
  } else {
    child.kill("SIGTERM");
  }
}

function stopAll() {
  if (stopping) return;
  stopping = true;
  for (const child of children) stopChild(child);
  maybeExit();
}

function onChildEnd(code) {
  if (firstCode === null) firstCode = typeof code === "number" ? code : 1;
  if (stopping) {
    maybeExit();
    return;
  }
  stopAll();
}

for (const ws of WORKSPACES) {
  const child = spawn(process.execPath, [npmCli, "run", "dev", "-w", ws], { stdio: "inherit" });
  const end = (code) => {
    if (ended.has(child)) return;
    ended.add(child);
    onChildEnd(code);
  };
  child.on("exit", (code) => end(code));
  child.on("error", (err) => {
    process.stderr.write(`dev.mjs : ${ws} — ${err.message}\n`);
    end(1);
  });
  children.push(child);
}

process.on("SIGINT", stopAll);
process.on("SIGTERM", stopAll);
