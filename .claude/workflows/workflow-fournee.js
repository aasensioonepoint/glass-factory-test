export const meta = {
  name: 'workflow-fournee',
  description: 'Fournée de dev : devs en worktree sous le verdict de charge, fusions sérialisées au fil de l eau (contrôle de retour + SAST), exec-critic de chaque lot dès sa fusion, revue de sécurité du diff',
  whenToUse: 'Après `tasks.py fournee <T>` (Claude Code seul). Revue de clôture, porte et done restent à l orchestrateur.',
  phases: [
    { title: 'Contexte', detail: 'racine du dépôt dérivée par git, branches des grappes déjà présentes (présente ou illisible : aucun dev)' },
    { title: 'Dev', detail: 'vagues sous le verdict de charge du poste (charge_poste.py verdict), un agent par grappe, isolation worktree' },
    { title: 'Fusion', detail: 'tasks.py retour (contrôle de retour mécanique), merge --no-ff, SAST --at, tests ciblés — un à la fois' },
    { title: 'Exec', detail: 'exec-critic de chaque lot dès sa fusion, sous le verdict de charge' },
    { title: 'Sécurité', detail: 'security-code-review sur le diff de la fournée, SAST --since la base' },
  ],
}

// PORTÉE : Claude Code SEUL (outil Workflow, `isolation: 'worktree'`). Ailleurs, les lots se jouent en série
// sous COVERAGE DEGRADED (.agents/ref/PARALLELISME_HOTES.md). Ce fichier VOYAGE chez l'adoptant ; il ne cite
// aucun chemin propre à un poste, aucun chantier, aucun mandat local.
//
// ARGS (passés en JSON, jamais une chaîne) — tout est VALIDÉ avant le premier agent, sinon rien ne part :
// {
//   base: "<sha hexadécimal, 7 à 64>",            // BASE commune des devs (obligatoire ; SHA-1 ou SHA-256)
//   label: "F7",                                   // nom de la fournée (obligatoire)
//   repo: "/chemin/absolu",                        // FACULTATIF : s'il est donné, il doit égaler la racine dérivée
//   session: "https://claude.ai/code/session_…",   // FACULTATIF, passé par l'APPELANT (un script Workflow ne lit
//                                                  // pas sa session) : un lien https:// sans blanc ; ligne
//                                                  // Claude-Session des commits ; absente, la ligne est OMISE
//                                                  // et le journal le dit
//   borne: 1600,                                   // FACULTATIF : lignes au plus par fichier Python livré
//   max_devs: 6,                                   // FACULTATIF : plafond DUR de devs en vol, entier 1..12 (absent : 12) ;
//                                                  // le nombre qui part à chaque vague, c'est le verdict de charge qui le donne ;
//                                                  // un exec-critic en vol y prend une place et ATTEND une place
//                                                  // libre sous ce plafond (avec max_devs 1 la fournée devient série)
//   grappes: [ { id: "T-00001234", branche: "wt/T-00001234" (jamais un « - » initial), agentType: "dev-multi"|"dev-mono"|"frontend-fidelity",
//                taches: ["T-00001234", …], writeset: ["chemin", …],
//                (une tâche estampillée `direct` forme sa grappe SEULE : `tasks.py retour` refuse (c)
//                 sa fusion si la grappe nomme une autre tâche, et son `done` exige ce relevé, T-00001182)
//                consigne: "<le À FAIRE propre à la grappe ; toute clôture ``` ou ~~~ refermée par la MÊME marque>",
//                tests: "<FACULTATIF (décision S-01M5APP7E5) : `bash .agents/pyrun.sh -m pytest <fichiers>`,
//                        `python3 -m pytest <fichiers>` ou `pytest <fichiers>` ; options -q -x -v -s seules, jamais
//                        -c, -p, @fichier ni autre script ; chaque fichier un test_*.py ou *_test.py (::id admis)>",
//                bancs: "<items de la ligne du lot sous ## Tests, OBLIGATOIRE : chemins séparés par des virgules, ou aucun | <pourquoi>>" } ],
//   securite: "<consigne de priorité pour la revue de sécurité, optionnelle>",
//   plan: "docs/tasks/PLAN-T-….md",               // FACULTATIF : chemin RELATIF du plan (regex CHEMIN, sans « .. ») ;
//                                                  // donné, l'exec-critic de chaque lot y relit ses critères d'acceptation
//   exec_par_lot: true                             // FACULTATIF, booléen (absent : true) : un exec-critic par lot dès sa
//                                                  // fusion ; false = aucun exec-critic dans le workflow (comportement d'avant)
// }
// RETOUR : { arret: {statut, motif}|null, contexte, quota, charge, fusions: [...], refus: [...], securite }
// — chaque entrée de `fusions` porte `exec: {verdict, constats, rapport}` (null si exec_par_lot: false) ; un
// exec-critic mort ou muet rend `ABSENT — relancer exec-critic sur <merge_sha>`, jamais un rapport perdu ; un
// exec-critic qui ne peut pas trancher rend NO_GO, 1er constat `COVERAGE DEGRADED — …` ; chaque NO_GO est
// journalisé « EXEC NO_GO : <lot> ».
// — `arret` non null dit un ARRÊT AVANT TOUT DEV (args, contexte), même sans grappe lisible : un appel
// refusé ne passe jamais pour un succès vide. L'orchestrateur trace au journal, écrit la reprise, puis lance la
// revue de clôture (hors workflow, elle garde le regard inter-lots) avant la porte.
//
// CONTEXTE (avant tout dev) : UN agent dérive la racine par `git rev-parse --show-toplevel` et liste les
// branches des grappes déjà présentes (`git branch --list`). Agent mort, rc
// non nul, racine non absolue ou différente de `repo`, branches non lues ou une branche de grappe DÉJÀ présente
// (course interrompue : fusionner ou retirer avant de relancer) : AUCUN dev ne part (statut `contexte`). La session ne se dérive pas : l'APPELANT la passe dans `args.session`, sinon la
// ligne Claude-Session est omise et le journal le dit. Les devs tournent sur l'hôte : aucune route vers un
// modèle local n'existe plus (décision S-01M5PCD282N11RGE73BMQK7M70).
// HOOKS : aucun n'est garanti sur un `agent()` de Workflow — ni `bancs-mandat.sh`
// (`Agent|Task`), ni `safe-bash.sh` (`Bash`), ni `protect-paths.sh` (`Edit|Write`) : NON MESURÉ. D'où les
// contrôles AVANT tout agent ci-dessous, dont `jugeMandat`, qui rejoue la logique de `bancs-mandat.sh`.
//
// CAPACITÉS PERDUES en devenant voyageur, nommées : (1) le mandat local que chaque dev lisait sur le poste —
// la déf `dev-*` et ce prompt portent seuls les règles ; (2) l'avis non bloquant du modèle local sur le diff de
// fusion ; (3) le coauteur figé du pied de fusion — chaque agent suit la consigne d'attribution de son hôte ;
// (4) l'arrêt de quota là où `cadre-quota` n'est pas installé (outil du poste, absent du gabarit) : la vague
// part sous le seul verdict de charge, et le journal comme le retour le DISENT (`quota: NON MESURÉ`) ;
// (5) le démarrage du serveur du modèle local (LM Studio) avant la fusion, propre au poste ; depuis, plus
// aucun modèle local n'est proposé aux devs (décision S-01M5PCD282N11RGE73BMQK7M70) ; (6) les tests ciblés d'un adoptant NON Python
// (go test, npm test, mvn…) : `tests` n'admet qu'un pytest (décision S-01M5APP7E5) ; absent, la fournée ne joue
// que les BANCS des lots et la porte du projet couvre le reste ; (7) un chemin de write-set non ASCII ou à
// blanc : refusé, seuls [A-Za-z0-9_.@+/-] passent (0 tel chemin dans le kit).
// ISOLATION : chaque dev vérifie d'abord qu'il tourne dans un worktree LIÉ (`git rev-parse --git-dir` ≠
// `--git-common-dir`, chemins absolus) ; sinon il s'arrête (statut "stop") avant toute autre commande git.
// AGENT MORT : un agent de fusion mort rend la grappe DOUTEUSE (état inconnu : merge peut-être fait), et ses
// fichiers entrent dans la revue de sécurité ; une revue de sécurité morte rend un bloquant « REVUE DE
// SÉCURITÉ ABSENTE », jamais un rapport perdu.
// CONTRÔLES CONSERVÉS : `tasks.py retour` avant toute fusion, fusions sérialisées, SAST `--at HEAD` après
// chaque fusion (rendu `sast_ok` ; jamais bloquant : un SAST non propre est journalisé « SAST À RELIRE »),
// exec-critic de chaque lot dès SA fusion, au fil de l'eau, sans bloquer les devs ni les fusions suivantes
// (sur `git diff <merge>^1 <merge> -- <write-set>`, lecture seule ; EN PARALLÈLE de la revue de sécurité, tous relevés avant le retour),
// revue de sécurité du diff fusionné (sautée sans fusion) avec le SAST `--since <base>` de la fournée,
// verdict de charge du poste avant chaque vague.

const A = args

const DEVS = ['dev-mono', 'dev-multi', 'frontend-fidelity']
const ID = /^T-[0-9A-Za-z]+$/
const UNE_LIGNE = /^[^\r\n`]+$/
const SHA = /^[0-9a-f]{7,64}$/
const BRANCHE = /^\w[\w./-]*$/
const SESSION = /^https:\/\/[\w./-]+$/
// Tests ciblés, FACULTATIFS (décision S-01M5APP7E5 ; lancés par l'agent de fusion) : un pytest sur des FICHIERS
// de test, rien d'autre — ni -c, ni -p, ni @fichier, ni un autre script ; options -q -x -v -s seules. Un segment
// de chemin ouvre par un caractère de mot (un « . » devant admis) : ni « .. », ni « - », ni « @ » initial.
const SEGMENT = '\\.?\\w[\\w.@+-]*'
const FICHIER_TEST = `(?:${SEGMENT}/)*(?:test_[\\w.@+-]*|\\w[\\w.@+-]*_test)\\.py(?:::\\w[\\w.[\\]-]*)*`
const TESTS = new RegExp(`^(?:bash \\.agents/pyrun\\.sh -m pytest|python3? -m pytest|pytest)(?: -[qxvs]+)*(?: ${FICHIER_TEST})+$`)
const AUCUN = 'aucun | '

// La liste des bancs d'une grappe, telle qu'elle sera écrite dans la ligne `BANCS:` du dev, ou null si elle
// n'est pas lisible : OBLIGATOIRE, jamais complétée par un défaut (la liste du mandat est EXHAUSTIVE).
// `aucun | <pourquoi>` passe TEL QUEL, virgules comprises, comme au hook ; ailleurs, une virgule finale ou
// doublée ne fabrique pas d'élément vide et un doublon ne compte qu'une fois. La FORME est jugée ensuite
// par `jugeMandat` sur le mandat rendu.
function bancsDe(g) {
  if (typeof g.bancs !== 'string' || !/^[^\r\n]+$/.test(g.bancs.trim())) return null
  const valeur = g.bancs.trim()
  if (valeur.startsWith(AUCUN)) return valeur
  const items = [...new Set(valeur.split(',').map(item => item.trim()).filter(item => item !== ''))]
  return items.length ? items.join(', ') : null
}

// Un chemin de write-set entre dans des prompts et des commandes : [A-Za-z0-9_.@+/-] seuls (ni `$(`, ni `;`,
// ni apostrophe, ni blanc, ni non-ASCII — capacité perdue nommée en tête), relatif, sans « .. ».
const CHEMIN = /^[\w.@+/-]+$/
function chemins(v) {
  return Array.isArray(v) && v.length > 0 && v.every(p => typeof p === 'string' && CHEMIN.test(p)
    && !p.startsWith('/') && !p.split('/').includes('..'))
}

// PARITÉ AVEC LE HOOK `.claude/hooks/bancs-mandat.sh` : `jugeMandat` rejoue SA logique sur le mandat RENDU
// d'un dev — clôtures (``` ou ~~~ après des blancs, refermée par la MÊME marque seule), sortie
// `BANCS-SANS-BORNE:`, UNE ligne `BANCS: `, `aucun | <pourquoi>` de dix caractères au moins sans gabarit
// `<…>`, items de la liste fermée des noms de bancs —, à UNE exception nommée : l'existence de chaque banc
// sur disque, qu'un script Workflow ne peut pas lire ; le hook seul la juge. Rend null si le hook laisserait
// passer, sinon `<règle du hook> : <objet>`. Le banc .agents/evals/test_bancs_mandat_lanceurs.py rejoue le
// VRAI hook sur les mêmes mandats, et rougit au premier écart.
const BLANCS_PY = '[\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]'
const BLANCS_DEBUT = new RegExp(`^${BLANCS_PY}+`)
const BLANCS_BORDS = new RegExp(`^${BLANCS_PY}+|${BLANCS_PY}+$`, 'g')
const ITEM_BANC = /^[A-Za-z0-9._/-]+(::[A-Za-z0-9_][A-Za-z0-9_.[\]-]*)*$/
const NOM_BANC = /^(test_[^/]*\.py|[^/]*_test\.(?:py|go)|[^/]*\.(?:test|spec)\.[A-Za-z0-9]+|[^/]*_spec\.rb|[^/]*(?:Test|Tests|IT)\.(?:java|kt|cs))$/
const RUST = /^[^/]+\.rs$/
const GABARIT = /<[^>]*>/
const SANS_BORNE = /^BANCS-SANS-BORNE: ([^\n]{10,})$/u
const RAISON_MAX = 500
const gabarit = raison => GABARIT.test([...raison].slice(0, RAISON_MAX).join(''))

function jugeMandat(prompt) {
  const visibles = []
  let cloture = ''
  let ouverte = 0
  for (const [i, ligne] of prompt.split('\n').entries()) {
    const marque = [...ligne.replace(BLANCS_DEBUT, '')].slice(0, 3).join('')
    if ((marque === '```' || marque === '~~~') && marque === (cloture || marque)) {
      cloture = cloture ? '' : marque
      ouverte = i + 1
    } else if (!cloture) {
      visibles.push(ligne)
    }
  }
  if (cloture) return `cloture-ouverte : ligne-${ouverte}`
  const sansBorne = visibles.map(l => SANS_BORNE.exec(l)).filter(m => m).map(m => m[1])
  if (sansBorne.length && visibles.some(l => l.startsWith('BANCS: '))) return 'ambigu : BANCS-SANS-BORNE'
  if (sansBorne.length) return gabarit(sansBorne[0]) ? 'raison-gabarit : BANCS-SANS-BORNE' : null
  const lignes = visibles.filter(l => l.startsWith('BANCS: ')).map(l => l.slice('BANCS: '.length))
  if (lignes.length !== 1 || !lignes[0]) return `sans-liste : ${lignes.length} ligne(s) BANCS:`
  const valeur = lignes[0].replace(BLANCS_BORDS, '')
  if (valeur.startsWith(AUCUN) && [...valeur.slice(AUCUN.length)].length >= 10) {
    return gabarit(valeur.slice(AUCUN.length)) ? 'raison-gabarit : aucun' : null
  }
  for (const brut of valeur.split(',')) {
    const item = brut.replace(BLANCS_BORDS, '')
    if (item.includes('`') || !ITEM_BANC.test(item)) return `liste-ouverte : ${JSON.stringify(item)}`
    const segments = item.split('::')[0].split('/')
    if (segments.some(s => s === '' || s === '.' || s === '..')) return `liste-ouverte : ${JSON.stringify(item)}`
    const nom = segments[segments.length - 1]
    const rust = segments.length >= 2 && segments[segments.length - 2] === 'tests' && RUST.test(nom)
    if (!(NOM_BANC.test(nom) || rust)) return `pas-un-banc : ${JSON.stringify(item)}`
  }
  return null
}

// Toutes les fautes des ARGS, jamais la première seule : [] si la fournée peut partir.
function fautesArgs(a) {
  const f = []
  if (!a || typeof a !== 'object') return ['args absents ou non objet']
  if (typeof a.base !== 'string' || !SHA.test(a.base)) f.push('base : sha hexadécimal de 7 à 64 attendu')
  if (typeof a.label !== 'string' || !/^[\w.-]{1,40}$/.test(a.label)) f.push('label : 1 à 40 caractères [A-Za-z0-9_.-] attendus')
  if (a.repo !== undefined && (typeof a.repo !== 'string' || !UNE_LIGNE.test(a.repo)
    || !/^(\/|[A-Za-z]:[\\/])/.test(a.repo))) f.push('repo : chemin absolu sur une ligne attendu')
  if (a.session !== undefined && (typeof a.session !== 'string' || !SESSION.test(a.session))) {
    f.push('session : un lien https:// sans blanc attendu')
  }
  if (a.borne !== undefined && !(Number.isInteger(a.borne) && a.borne > 0)) f.push('borne : entier positif attendu')
  if (a.securite !== undefined && typeof a.securite !== 'string') f.push('securite : chaîne attendue')
  if (a.plan !== undefined && !chemins([a.plan])) f.push('plan : chemin relatif en [A-Za-z0-9_.@+/-], sans « .. », attendu')
  if (a.exec_par_lot !== undefined && typeof a.exec_par_lot !== 'boolean') f.push('exec_par_lot : booléen attendu')
  if (!Array.isArray(a.grappes) || a.grappes.length === 0) return [...f, 'grappes : liste non vide attendue']
  const vus = new Set()
  for (const [i, g] of a.grappes.entries()) {
    const n = g && typeof g.id === 'string' ? g.id : `grappe ${i}`
    if (!g || typeof g !== 'object') { f.push(`${n} : objet attendu`); continue }
    const avant = f.length
    if (typeof g.id !== 'string' || !ID.test(g.id)) f.push(`${n} : id T-<id> attendu`)
    if (typeof g.branche !== 'string' || !BRANCHE.test(g.branche) || g.branche.includes('..')) {
      f.push(`${n} : branche sans blanc, sans « - » initial ni « .. » attendue`)
    }
    for (const cle of ['id', 'branche']) {
      if (typeof g[cle] === 'string' && vus.has(cle + ':' + g[cle])) f.push(`${n} : ${cle} en double`)
      vus.add(cle + ':' + g[cle])
    }
    if (!DEVS.includes(g.agentType)) f.push(`${n} : agentType parmi ${DEVS.join(', ')}`)
    if (!Array.isArray(g.taches) || g.taches.length === 0 || !g.taches.every(t => typeof t === 'string' && ID.test(t))) {
      f.push(`${n} : taches = liste non vide de T-<id>`)
    }
    if (!chemins(g.writeset)) f.push(`${n} : writeset = liste non vide de chemins relatifs en [A-Za-z0-9_.@+/-], sans « .. »`)
    if (g.tests !== undefined && (typeof g.tests !== 'string' || !TESTS.test(g.tests))) {
      f.push(`${n} : tests FACULTATIF ; donné, un pytest sur des fichiers de test (bash .agents/pyrun.sh -m pytest, python3 -m pytest ou pytest), options -q -x -v -s seules, ni -c ni -p ni autre script`)
    }
    if (bancsDe(g) === null) f.push(`${n} : bancs OBLIGATOIRE — chemins séparés par des virgules sur une ligne, ou « aucun | <pourquoi> » seul`)
    if (typeof g.consigne !== 'string' || !g.consigne.trim()) f.push(`${n} : consigne non vide attendue`)
    // Grappe bien formée : son mandat RENDU passe au juge du hook, avant tout agent.
    const refus = f.length === avant ? jugeMandat(promptDev(g)) : null
    if (refus) f.push(`${n} : le hook bancs-mandat refuserait le mandat du dev (${refus})`)
    // Même juge sur le CADRE rendu du mandat de l'exec-critic (sha de merge et tip fictifs, hexadécimaux). La
    // consigne y est NEUTRE : c'est le même texte que dans le mandat du dev, déjà jugé ci-dessus, et aucun texte
    // du cadre qui la suit n'ouvre de clôture ni ne porte de ligne `BANCS:` — admise chez le dev, elle l'est ici.
    // Juger la consigne deux fois masquerait un juge du dev retiré (mutant `juge_non_appele` du banc de parité).
    const refusExec = f.length === avant && a.exec_par_lot !== false
      ? jugeMandat(promptExec({ ...g, consigne: 'consigne du lot, jugée au mandat du dev' },
        { merge_sha: '0000000' }, { head: '0000000' })) : null
    if (refusExec) f.push(`${n} : le hook bancs-mandat refuserait le mandat de l'exec-critic (${refusExec})`)
  }
  return f
}

// La racine dérivée par l'agent de contexte, ou un motif de refus.
function lireRacine(c, attendu) {
  if (!c) return { racine: null, motif: 'agent de contexte sans réponse' }
  if (c.rc_racine !== 0 || typeof c.racine !== 'string') return { racine: null, motif: `git rev-parse rc ${c.rc_racine}` }
  const r = c.racine.trim()
  if (!UNE_LIGNE.test(r) || !/^(\/|[A-Za-z]:[\\/])/.test(r)) return { racine: null, motif: `racine illisible ${JSON.stringify(r)}` }
  if (attendu !== undefined && r !== attendu) return { racine: null, motif: `racine dérivée ${r} ≠ repo ${attendu}` }
  return { racine: r, motif: '' }
}

const ECONOMIE = `ÉCONOMIE DE LA MACHINE (un EDR inspecte chaque fichier et chaque processus) : (1) un clone jetable par agent, réutilisé ; (2) git sparse-checkout quand la mesure ne touche qu'une partie du dépôt ; (3) un plafond de mesures en même temps PAR POSTE, que \`charge_poste.py verdict\` décide et calibre seul à chaque vague : ce workflow le lit avant chaque vague de devs (plus une fusion sérialisée) ; si toi-même tu lances des agents qui mesurent, \`bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <tes agents en vol>\` avant CHAQUE vague, au plus son PEUT_AJOUTER de plus (sans ligne PLAFOND= lisible, ou PEUT_AJOUTER qui n'est pas un entier ≥ 0 : cinq moins tes agents en vol, jamais la dernière valeur connue) — décisions pilote S-01M4Y10HZ6Y0TAXNNK0S1VRFC1, S-01M4Y2Q1QK4AGNCSPMQ7ES126Y, S-01M537VBGG5RVBCF3KHFV3JMN5, S-01M54B1KQ6SVNCA9ZSRPWHCCFP ; aucune porte pendant ces mesures. TMPDIR ≤ 80 caractères ; CADRE_STATE_DIR et AGENTS_EVENTS_DIR jetables ; CLAUDE_PROJECT_DIR non exporté. Sous isolation worktree : chemins littéraux, une commande git par appel, ou un script Python écrit avec Write puis lancé par \`bash .agents/pyrun.sh\`.`

const DEV_SCHEMA = {
  type: 'object',
  properties: {
    statut: { type: 'string', enum: ['livre', 'decision', 'plan', 'stop'] },
    branche: { type: 'string' },
    head: { type: 'string' },
    fichiers: { type: 'array', items: { type: 'string' } },
    lignes_py: { type: 'string' },
    temoins: { type: 'string' },
    defauts: { type: 'string' },
    question_pilote: { type: 'string' },
    rapport: { type: 'string' },
  },
  required: ['statut', 'branche', 'head', 'fichiers', 'temoins', 'rapport'],
}

const FUSION_SCHEMA = {
  type: 'object',
  properties: {
    fusionne: { type: 'boolean' },
    merge_sha: { type: 'string' },
    controles: { type: 'string' },
    sast: { type: 'string' },
    sast_ok: { type: 'boolean' },
    tests: { type: 'string' },
    motif_refus: { type: 'string' },
  },
  required: ['fusionne', 'controles', 'sast_ok'],
}

const SECU_SCHEMA = {
  type: 'object',
  properties: {
    bloquants: { type: 'array', items: { type: 'string' } },
    avis: { type: 'array', items: { type: 'string' } },
    couverture: { type: 'string' },
    rapport: { type: 'string' },
  },
  required: ['bloquants', 'avis', 'rapport'],
}

const EXEC_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['GO', 'GO_AVEC_RESERVES', 'NO_GO'] },
    constats: { type: 'array', items: { type: 'string' } },
    rapport: { type: 'string' },
  },
  required: ['verdict', 'rapport'],
}

const CONTEXTE_SCHEMA = {
  type: 'object',
  properties: {
    racine: { type: 'string' }, rc_racine: { type: 'number' },
    branches: { type: 'string' },
  },
  required: ['racine', 'rc_racine', 'branches'],
}

let RACINE = null
const piedSession = () => (A.session ? `\n   Claude-Session: ${A.session}` : '')

function promptDev(g) {
  return `Tu es le dev de ${g.taches.join(' puis ')} (fournée ${A.label}). Ta déf (${g.agentType}) porte tes règles ; ce prompt les complète.

Branche \`${g.branche}\`.${A.borne ? ` Borne : ${A.borne} lignes au plus par fichier Python livré.` : ''} Commits : suis la consigne d'attribution de ton hôte${A.session ? `, et termine chaque message par la ligne \`Claude-Session: ${A.session}\`` : ''}.

BASE = ${A.base} (étape 0, AVANT toute autre commande git : \`git rev-parse --path-format=absolute --git-dir --git-common-dir\` doit rendre DEUX lignes, deux chemins absolus DIFFÉRENTS — tu es dans un worktree LIÉ ; égales, une seule ligne ou un chemin relatif : statut "stop", rapport « isolation worktree absente », et AUCUNE autre commande git. Puis \`git switch -c ${g.branche}\`, \`git reset --keep ${A.base}\`, \`git rev-parse HEAD\` doit rendre la BASE).

Lis chaque tâche EN ENTIER (\`bash .agents/pyrun.sh .agents/bin/tasks.py list --task <T>\`, titre ET stage). Décision ouverte ou correction réelle sur 5 fichiers ou plus : ne code pas, statut "decision" ou "plan", avec la question formulée (contexte, options, conséquences).

WRITE-SET CLOS : ${g.writeset.join(', ')}. Rien d'autre ; s'il en faut un autre, statut "stop" et nomme-le.

BANCS: ${bancsDe(g)}

À FAIRE :
${g.consigne}

CHRONO DU LOT ${g.id} (journal local) : avant de coder, lance \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} begin\` (idempotent si le cycle est déjà ouvert), puis \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} estimate --etape dev\` et \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} step --etape dev --phase begin\`. Après ta tentative, réussite, arrêt ou échec, lance \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} step --etape dev --phase end\` et \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} show\` ; rends la durée et l'écart mesurables. Un rc non nul de chrono est nommé dans ton rapport, jamais bloquant pour ton travail. Ne relance pas un second début à la reprise.

${g.tests ? `Témoin : ${g.tests}.` : 'Témoin : aucun test ciblé donné par la grappe.'} Bancs : ceux de ta ligne \`BANCS:\`, et eux seuls (la porte joue le reste). Témoins ROUGES sur la base (ou sur un mutant), VERTS au tip, avec la ligne de sortie. La consigne ne porte jamais une seconde ligne \`BANCS:\`.

${ECONOMIE}

Rends ton rapport dans le champ "rapport", et remplis les champs structurés.`
}

function promptFusion(g, d) {
  return `Tu es l'agent de RETOUR et de FUSION de la grappe ${g.id} (fournée ${A.label}), dans le dépôt PRINCIPAL ${RACINE}. Tu es le SEUL à fusionner en ce moment.

Branche : ${g.branche} (tip annoncé ${d.head}). BASE : ${A.base}. Write-set déclaré : ${g.writeset.join(', ')}.

CHRONO DE FUSION du lot ${g.id} : avant le contrôle de retour, lance \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} estimate --etape fusion\` puis \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} step --etape fusion --phase begin\`. Après retour, merge et contrôles, même si l'un refuse ou échoue, lance \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} step --etape fusion --phase end\` puis \`bash .agents/pyrun.sh .agents/bin/tasks.py chrono ${g.id} show\`. Un rc non nul de chrono est nommé dans controles, sans bloquer la fusion ; l'exception d'écriture au journal ne couvre que ces appels chrono.

1. CONTRÔLE DE RETOUR MÉCANIQUE, dans UN appel séparé, AVANT toute fusion : \`bash .agents/pyrun.sh .agents/bin/tasks.py retour ${g.taches.join(' ')} --base ${A.base} --branche ${g.branche}\`. Il juge la base, les commits, le diff contre le write-set DÉCLARÉ, HEAD, le worktree, l'index, le doublon et (i), sur une tâche directe, son relevé antérieur — une branche de la tâche déjà entrée dans HEAD sans relevé admissible refuse, et ce refus se transmet aux relevés suivants —, et inscrit le relevé sur chaque tâche de la grappe. Recopie sa sortie ENTIÈRE dans controles. Son rc ≠ 0 : NE FUSIONNE PAS — fusionne=false, motif_refus = sa sortie (les causes et leurs remèdes y sont), AUCUNE fusion. Seul un rc 0 mène au point 2.
2. \`git merge --no-ff -q ${g.branche} -m "merge: ${g.taches.join(' + ')} — <résumé d'une ligne> (fournée ${A.label})"\`, avec un corps qui suit la consigne d'attribution de ton hôte${A.session ? ' et se termine par :' : ' (aucune ligne Claude-Session : la session n est pas connue).'}${piedSession()}
   Puis \`git worktree remove <chemin>\`, \`git branch -d ${g.branche}\`, et \`git branch -D worktree-<nom du dossier>\` SEULEMENT si le relevé du point 1 dit « doublon vierge, supprimable : worktree-<nom du dossier> » ; sinon ne la supprime pas.
3. SAST : \`bash .agents/security/semgrep-scan.sh --at HEAD\`. sast_ok=true seulement si la sortie dit « clean on the diff » ET que les cibles non inspectées (partial scope S/N) ne sont que des fichiers .md ou .json. Compte les .py et .sh du commit : s'il en manque un, ou si la sortie dit COVERAGE DEGRADED, sast_ok=false. Ne corrige rien.
4. ${g.tests ? `Tests ciblés : ${g.tests}. Rends sa dernière ligne dans tests.` : 'Tests ciblés : aucun test ciblé donné par la grappe (la porte du projet couvre le reste) ; tests = « non donnés ».'}
Interdits : verify.sh, push, --no-verify, rm d'un fichier suivi, toute écriture au board SAUF \`tasks.py retour\` (l'exception nommée : il inscrit le relevé), toute écriture au journal SAUF \`tasks.py chrono\` ci-dessus, toute écriture au ledger, toute édition de fichier.`
}

// L'exec-critic d'UN lot, lancé dès SA fusion (au fil de l'eau). Rien de ce que le dev a ÉCRIT n'entre dans ce
// prompt : seuls le sha du merge et le tip, contrôlés hexadécimaux, et les ARGS validés. La revue de clôture,
// hors workflow, garde le regard inter-lots.
function promptExec(g, f, d) {
  return `Tu es l'exec-critic du lot ${g.id} (${g.taches.join(' + ')}, fournée ${A.label}), dans le dépôt PRINCIPAL ${RACINE}. Tu produis la preuve et le verdict de CE lot seul ; la revue de clôture, après la fournée, juge l'ensemble.

Objet jugé, exact : \`git diff ${f.merge_sha}^1 ${f.merge_sha} -- ${g.writeset.join(' ')}\` (merge ${f.merge_sha}, tip du dev ${d.head}, BASE ${A.base}). D'autres lots fusionnent pendant que tu mesures : ne mesure JAMAIS dans le dépôt principal, mais dans un clone jetable extrait à ${f.merge_sha}.

BANCS: ${bancsDe(g)}
Critères d'acceptation du lot : ceux de sa consigne ci-dessous${A.plan ? `, et ceux du plan \`${A.plan}\` pour ce lot (lis-le à ${f.merge_sha})` : ''}. Rejoue CHAQUE critère par sa commande et recopie la ligne de verdict de sa sortie RÉELLE ; un critère sans commande exécutable, ou qui installe, écrit hors d'un répertoire temporaire ou atteint le réseau : ne le joue pas, dis-le. Quand c'est simple, mute : casse dans le clone la ligne qu'un témoin garde, montre-le rouge, puis restaure le fichier. Bancs : ceux de ta ligne \`BANCS:\`, et eux seuls (la porte joue le reste).

Consigne du lot :
${g.consigne}

${ECONOMIE}

LECTURE SEULE : aucune édition, aucun commit, aucun merge, aucune écriture au board, au journal ni au ledger, ni verify.sh, ni push. verdict = GO, GO_AVEC_RESERVES ou NO_GO (NO_GO pour un constat BLOQUANT seul : le lot livre faux, casse une garde ou un filet) ; constats = un par trouvaille, \`fichier:ligne\` et scénario ; rapport = les commandes jouées et leurs lignes de sortie. Si tu ne peux pas trancher : verdict NO_GO, 1er constat « COVERAGE DEGRADED — exec-critic indisponible : <quoi> ».`
}

// FILE PAR VAGUES, SOUS LE VERDICT DE CHARGE DU POSTE (T-01M4XZWZ9C0ZFVXN3MFSFY1G5V, lot W ; décisions pilote
// S-01M4Y10HZ6Y0TAXNNK0S1VRFC1, S-01M4Y2Q1QK4AGNCSPMQ7ES126Y, S-01M537VBGG5RVBCF3KHFV3JMN5 ; base à cinq :
// T-01M54B1SXM557Z86N1TXEJSRDE, S-01M54B1KQ6SVNCA9ZSRPWHCCFP). Le poste décide et calibre SEUL son plafond
// (contrat : .agents/ref/CHARGE_POSTE.md) ; ce script ne recalcule aucune de ses règles.
// Avant CHAQUE vague, UN agent de contrôle fait deux mesures : le quota du compte courant (cadre-quota
// --verdict, là où le poste l'a installé : à 90 %, sur seven_day OU five_hour, aucune grappe neuve ne part ; à
// 97 %, idem et le retour le dit — l'orchestrateur passe en régime d'atterrissage ; outil absent ou verdict
// INCONNU : COVERAGE DEGRADED dit à chaque vague, et le retour porte `quota: NON MESURÉ`), puis
// `charge_poste.py verdict --actifs <devs en vol> --attendre 540`, qu'il lance dans un appel Bash au paramètre
// `timeout: 600000` (le défaut coupe à 120 s).
// La vague part d'un seul geste : au plus min(PEUT_AJOUTER, place sous A.max_devs) grappes, A.max_devs étant
// un plafond DUR facultatif de devs en vol (1..12). Sortie illisible ou commande tuée (rc ≠ 0, aucune ligne
// PLAFOND= lisible, PEUT_AJOUTER négatif ou non entier) : max(0, 5 − devs en vol), jamais la dernière valeur
// connue, jamais cinq de plus par vague (C33, C45). Trois verdicts NULS PROBANTS de suite (sortie LISIBLE à
// PEUT_AJOUTER=0, donc une charge mesurée) : les grappes restantes rendent le statut `charge` ; chaque RETOUR de dev
// et chaque vague partie remettent ce compte à zéro. Un zéro de REPLI (sortie illisible ou contrôle mort, des
// devs en vol) ne compte JAMAIS : c'est l'outil qui est illisible, pas le poste qui est chargé — on attend un
// retour, sans relancer de contrôle, et le retour `verdict_illisible` le dit. Le statut `charge` est propre à ce
// lanceur (étape 8 du plan) : W diverge de K et P, qui n'en ont pas — divergence assumée. Les grappes parties vont
// au bout (fusion comprise). V1 : aucune redescente active — à la surcharge, aucun départ, les devs en vol finissent.
// EXEC-CRITIC : un agent qui MESURE, donc il compte UNE place — `actifs` (le `--actifs` du verdict, la place
// sous A.max_devs et le repli max(0, 5 − en vol)) compte les devs ET les exec-critics en vol ; son retour rend la
// place et remet le compte des nuls à zéro, comme un retour de dev.
// Banc : .agents/evals/test_charge_poste_fournee_kit.py, qui rejoue ce script sous node.
const DUR_MAX = 12
const ZEROS_MAX = 3
function plafondDur(v) {
  if (v === undefined || v === null) return DUR_MAX
  const n = Number(v)
  if (!Number.isInteger(n) || n < 1) {
    log(`max_devs ${JSON.stringify(v)} ignoré : entier 1..${DUR_MAX} attendu, plafond dur ${DUR_MAX}`)
    return DUR_MAX
  }
  return Math.min(n, DUR_MAX)
}
// La sortie de `verdict` (CHARGE_POSTE.md § 2) : l'entier PEUT_AJOUTER, ou null = ILLISIBLE.
function lirePeutAjouter(sortie, rc) {
  if (rc !== 0 || typeof sortie !== 'string') return null
  if (!/^[ \t]*PLAFOND=\d+\s/m.test(sortie)) return null
  const m = /^[ \t]*PEUT_AJOUTER=(\S*)/m.exec(sortie)
  if (!m || !/^\d+$/.test(m[1])) return null
  return Number(m[1])
}
function lireRedescente(sortie) {
  const m = typeof sortie === 'string' ? /DOIT_REDESCENDRE_A=(\d+)/.exec(sortie) : null
  return m ? Number(m[1]) : null
}
// Combien partent à CETTE vague : jamais au-delà du verdict, du plafond dur ni de la file.
function accordDeVague(peut, enVol, dur, restantes) {
  const brut = peut === null ? Math.max(0, 5 - enVol) : peut
  return Math.max(0, Math.min(brut, dur - enVol, restantes))
}
let actifs = 0
let zeros = 0
let illisibles = 0
let sansQuota = 0
let raisonQuota = ''
let stopQuota = null
let stopCharge = null
const attente = []
function signalerRetour() {
  actifs--
  zeros = 0
  for (const r of attente.splice(0)) r()
}
function attendreRetour() {
  return new Promise(r => attente.push(r))
}
const CONTROLE_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string' }, ligne: { type: 'string' },
    sortie_verdict: { type: 'string' }, rc_verdict: { type: 'number' },
  },
  required: ['verdict', 'sortie_verdict', 'rc_verdict'],
}
async function controler(vague, enVol) {
  let c = null
  try {
    c = await agent(
      `Deux mesures depuis ${RACINE}, rien d'autre ; rends les champs. (1) Si \`cadre-quota\` est sur le PATH (\`command -v cadre-quota\`) ou à \`~/.local/bin/cadre-quota\`, lance-le avec \`--verdict\` et rends le PREMIER mot de sa sortie dans verdict (OK, PAS-DE-NOUVELLE-FOURNEE, ATTERRIR ou INCONNU) et la ligne entière dans ligne ; s'il n'est à aucun des deux endroits, verdict = ABSENT et ligne = « cadre-quota absent du poste ». (2) Lance \`bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs ${enVol} --attendre 540\` dans UN appel Bash au paramètre \`timeout: 600000\` (l'attente monte à 540 s ; le défaut de Bash coupe à 120 s), puis recopie sa sortie standard ENTIÈRE, sans la résumer, dans sortie_verdict et son code de retour dans rc_verdict (commande tuée ou coupée : rc_verdict = -1). N'interprète pas ce verdict, ne lance rien d'autre.`,
      { label: `controle:vague-${vague}`, phase: 'Dev', schema: CONTROLE_SCHEMA },
    )
  } catch (e) {
    log(`contrôle de la vague ${vague} mort (${e && e.message ? e.message : e}) : quota inconnu, verdict illisible`)
  }
  if (c && (c.verdict === 'ATTERRIR' || c.verdict === 'PAS-DE-NOUVELLE-FOURNEE')) {
    stopQuota = c.ligne || c.verdict
    log(`QUOTA : ${stopQuota} — la vague ${vague} ne part pas`)
    return { ok: false, peut: 0, resume: stopQuota }
  }
  if (!c || c.verdict !== 'OK') {
    sansQuota++
    raisonQuota = c ? `${c.verdict}${c.ligne ? ' : ' + c.ligne : ''}` : 'contrôle sans réponse'
    log(`COVERAGE DEGRADED — quota non mesuré (${raisonQuota}) : la vague ${vague} part sous le seul verdict de charge, sans l'arrêt à 90 % ni à 97 %`)
  }
  const sortie = c ? c.sortie_verdict : null
  const peut = c ? lirePeutAjouter(sortie, c.rc_verdict) : null
  const redescente = lireRedescente(sortie)
  if (peut !== null && redescente !== null && redescente < enVol) {
    log(`COVERAGE DEGRADED — redescente active non livrée (V1) : à la surcharge, aucun départ ; les agents en vol finissent (DOIT_REDESCENDRE_A=${redescente}, ${enVol} en vol)`)
  }
  const resume = peut === null
    ? `verdict illisible (${c ? 'rc ' + c.rc_verdict : 'contrôle sans réponse'}) : max(0, 5 − ${enVol})`
    : `PEUT_AJOUTER=${peut}`
  return { ok: true, peut, resume }
}

// Fusions SÉRIALISÉES au fil de l'eau : chaque grappe fusionne dès que son dev rend, une à la fois.
let verrou = Promise.resolve()
const fusionner = (g, d) => {
  const tour = verrou.then(() => agent(promptFusion(g, d), {
    label: `fusion:${g.id}`, phase: 'Fusion', schema: FUSION_SCHEMA, agentType: 'general-purpose',
  }))
  verrou = tour.catch(() => null)
  return tour
}

const nonLancee = (g, statut, motif) => ({
  grappe: g && g.id ? g.id : '?', fusion: null,
  dev: { statut, branche: g && g.branche ? g.branche : '', head: '', fichiers: [], temoins: '', rapport: `non lancée : ${motif}` },
})

let arret = null
let contexte = 'non lu'
let DUR = DUR_MAX
let vague = 0
function rapport(resultats, securite) {
  const fusions = resultats.filter(r => r && r.fusion && r.fusion.fusionne)
  const refus = resultats.filter(r => !(r && r.fusion && r.fusion.fusionne))
  return {
    arret,
    contexte,
    quota: stopQuota ? `ARRÊT QUOTA : ${stopQuota} — régime d'atterrissage, aucune fournée neuve`
      : sansQuota ? `NON MESURÉ : ${sansQuota} vague(s) parties sans garde de quota (${raisonQuota}) — l'arrêt à 90 % / 97 % n'existe que là où cadre-quota est installé`
        : 'sous les seuils',
    charge: stopCharge ? `ARRÊT CHARGE : ${stopCharge} — relancer les grappes au statut charge quand le poste respire` : 'sous le verdict de charge',
    verdict_illisible: illisibles
      ? `OUTIL ILLISIBLE : ${illisibles} verdict(s) de charge sans sortie lisible (repli max(0, 5 − en vol)) — vérifier charge_poste.py et l'agent de contrôle ; ce n'est pas la charge du poste`
      : 'aucun',
    max_devs: DUR,
    vagues: vague,
    fusions: fusions.map(r => ({ grappe: r.grappe, merge: r.fusion.merge_sha, sast_ok: r.fusion.sast_ok, sast: r.fusion.sast, tests: r.fusion.tests, temoins: r.dev.temoins, defauts: r.dev.defauts || '', rapport: r.dev.rapport, exec: r.exec || null })),
    refus: refus.map(r => r ? ({ grappe: r.grappe, statut: r.dev ? r.dev.statut : null, question: r.dev ? (r.dev.question_pilote || '') : '', motif: r.fusion ? r.fusion.motif_refus : '', rapport: r.dev ? r.dev.rapport : '' }) : null),
    securite,
  }
}
function arretAvantDev(statut, motif) {
  log(`ARRÊT AVANT DEV (${statut}) : ${motif} — aucun dev ne part`)
  arret = { statut, motif }
  const grappes = A && Array.isArray(A.grappes) ? A.grappes : []
  return rapport(grappes.map(g => nonLancee(g, statut, motif)), null)
}

// VALIDATION : rien ne part, pas même le contexte, sur des ARGS fautifs.
const fautes = fautesArgs(A)
if (fautes.length) return arretAvantDev('args', fautes.join(' ; '))
DUR = plafondDur(A.max_devs)
if (!A.session) log('session absente des ARGS : ligne Claude-Session omise des commits de dev et de fusion')

// CONTEXTE : racine dérivée, branches des grappes lues. Aucune porte ne tourne pendant un workflow.
phase('Contexte')
let ctx = null
try {
  ctx = await agent(
    `Deux lectures, rien d'autre ; rends les champs. (1) \`git rev-parse --show-toplevel\` dans le répertoire courant : sa sortie standard exacte, sans retour final, dans racine, son code de retour dans rc_racine. (2) Depuis cette racine, \`git branch --list -- ${A.grappes.map(g => g.branche).join(' ')}\` : sa sortie standard ENTIÈRE dans branches (vide si aucune n'existe). Ne crée, ne supprime et ne lance rien d'autre.`,
    { label: 'contexte', phase: 'Contexte', schema: CONTEXTE_SCHEMA },
  )
} catch (e) {
  log(`agent de contexte mort (${e && e.message ? e.message : e})`)
}
const lu = lireRacine(ctx, A.repo)
if (lu.racine === null) {
  contexte = `ILLISIBLE : ${lu.motif}`
  return arretAvantDev('contexte', lu.motif)
}
RACINE = lu.racine
contexte = `racine ${RACINE} ; session ${A.session ? A.session : 'absente — ligne Claude-Session omise'}`
// REPRISE : une branche de grappe déjà présente est celle d'une course interrompue — `git switch -c` y
// échouerait et le dev improviserait. Rien ne part tant qu'elle n'est pas fusionnée ou retirée.
if (typeof ctx.branches !== 'string') return arretAvantDev('contexte', 'branches des grappes non lues')
if (ctx.branches.trim()) {
  const presentes = ctx.branches.trim().split(/\s+/).filter(b => !/^[*+]$/.test(b))
  return arretAvantDev('contexte', `branches déjà présentes : ${presentes.join(' ')} — fusionner ou retirer avant de relancer`)
}
log(`contexte : ${contexte}`)

// Un dev part : sa place se rend à SON retour (fusion non comprise : elle est sérialisée à part).
const enCours = []
function lancer(g) {
  actifs++
  enCours.push((async () => {
    let d = null
    try {
      d = await agent(promptDev(g), {
        label: `dev:${g.id}`, phase: 'Dev', schema: DEV_SCHEMA, isolation: 'worktree', agentType: g.agentType,
      })
    } catch (e) {
      log(`${g.id} : agent de dev mort (${e && e.message ? e.message : e})`)
    } finally {
      signalerRetour()
    }
    if (!d || d.statut !== 'livre') {
      log(`${g.id} : pas de fusion (statut ${d ? d.statut : 'null'})`)
      return { grappe: g.id, writeset: g.writeset, dev: d, fusion: null }
    }
    // Ce que le dev REND n'entre dans aucune commande : la branche doit être celle de la grappe, le tip un sha.
    const ecart = d.branche !== g.branche ? `branche rendue ${JSON.stringify(d.branche)} ≠ branche de la grappe ${g.branche}`
      : (typeof d.head !== 'string' || !SHA.test(d.head)) ? `tip rendu ${JSON.stringify(d.head)} : sha hexadécimal attendu` : ''
    if (ecart) {
      log(`${g.id} : pas de fusion — ${ecart}`)
      return { grappe: g.id, writeset: g.writeset, dev: d, fusion: { fusionne: false, controles: '', sast_ok: false, motif_refus: ecart } }
    }
    let f = null
    try {
      f = await fusionner(g, d)
    } catch (e) {
      log(`${g.id} : agent de fusion mort (${e && e.message ? e.message : e})`)
    }
    // Agent de fusion mort ou muet : le merge a PU se faire. La grappe est DOUTEUSE (fusionne: null), dite au
    // refus, et ses fichiers entrent dans la revue de sécurité.
    if (!f) {
      f = { fusionne: null, controles: '', sast_ok: false,
            motif_refus: `agent de fusion mort — état INCONNU : vérifier git log --merges ${A.base}..HEAD avant toute relance` }
    }
    // Ce que l'agent de fusion REND n'entre dans aucun prompt sans contrôle : le sha du merge doit être un sha.
    if (f.fusionne === true && (typeof f.merge_sha !== 'string' || !SHA.test(f.merge_sha))) {
      log(`${g.id} : merge_sha rendu ${JSON.stringify(f.merge_sha)} illisible — remplacé par ILLISIBLE ; relire git log --merges ${A.base}..HEAD`)
      f = { ...f, merge_sha: 'ILLISIBLE' }
    }
    const res = { grappe: g.id, writeset: g.writeset, dev: d, fusion: f, exec: null }
    // EXEC AU FIL DE L'EAU : le lot fusionné (sha lisible) part à son exec-critic SANS attendre — la boucle des
    // devs et des fusions continue ; le résultat est relevé avant le retour, la revue de sécurité tournant en parallèle.
    if (A.exec_par_lot !== false && f.fusionne === true) {
      if (SHA.test(f.merge_sha)) {
        execs.push(lancerExec(g, f, d).then(v => { res.exec = v }))
      } else {
        res.exec = { verdict: `ABSENT — merge_sha illisible, relancer exec-critic sur le merge de ${g.branche}`, constats: [], rapport: '' }
      }
    }
    return res
  })())
}

// Un exec-critic MESURE : il tient une place du verdict de charge (`actifs`), rendue à son retour.
const execs = []
async function lancerExec(g, f, d) {
  // Le dev a rendu sa place à son retour, avant la fusion : l'exec-critic en attend une sous le plafond dur.
  while (actifs >= DUR) await attendreRetour()
  actifs++
  let e = null
  try {
    e = await agent(promptExec(g, f, d), { label: 'exec:' + g.id, phase: 'Exec', schema: EXEC_SCHEMA, agentType: 'exec-critic' })
  } catch (err) {
    log(`${g.id} : exec-critic mort (${err && err.message ? err.message : err})`)
  } finally {
    signalerRetour()
  }
  if (!e || typeof e.verdict !== 'string') {
    return { verdict: `ABSENT — relancer exec-critic sur ${f.merge_sha}`, constats: [], rapport: '' }
  }
  const constats = Array.isArray(e.constats) ? e.constats.filter(c => typeof c === 'string') : []
  if (e.verdict === 'NO_GO') log(`EXEC NO_GO : ${g.id} — ${constats.join(' ; ') || 'constats non rendus'}`)
  return { verdict: e.verdict, constats, rapport: typeof e.rapport === 'string' ? e.rapport : '' }
}

phase('Dev')
const file = [...A.grappes]
while (file.length && !stopQuota) {
  // Plafond dur atteint : on attend un retour, AVANT toute mesure (un verdict ne peut rien y changer).
  if (actifs >= DUR) { await attendreRetour(); continue }
  vague++
  const avant = actifs
  const c = await controler(vague, avant)
  if (!c.ok) break
  // Une sortie illisible l'est, périmée ou non : elle se compte avant la remesure.
  if (c.peut === null) illisibles++
  // Un exec-critic parti PENDANT la mesure manque à son --actifs : ce PEUT_AJOUTER est périmé, on remesure
  // (ce tour ne compte pas parmi les verdicts nuls).
  if (actifs > avant) { log(`vague ${vague} : verdict périmé, remesure`); continue }
  const k = accordDeVague(c.peut, actifs, DUR, file.length)
  if (k === 0 && c.peut === null) {
    // Zéro de REPLI : max(0, 5 − en vol) = 0, donc au moins cinq devs en vol, dont un retour viendra.
    log(`vague ${vague} : verdict de charge ILLISIBLE (${c.resume}), ${actifs} en vol — l'outil, pas le poste : aucun départ, ce zéro ne compte pas, on attend un retour`)
    await attendreRetour()
    continue
  }
  if (k === 0) {
    zeros++
    log(`vague ${vague} : aucun départ, ${actifs} en vol (${c.resume}) — verdict nul ${zeros}/${ZEROS_MAX}`)
    if (zeros >= ZEROS_MAX) {
      stopCharge = `${ZEROS_MAX} verdicts nuls PROBANTS de suite, sans retour de dev ni d'exec-critic (dernier : ${c.resume})`
      log(`CHARGE : ${stopCharge} — ${file.length} grappe(s) ne partent pas`)
      break
    }
    continue
  }
  zeros = 0
  log(`vague ${vague} : ${k} grappe(s) de plus, ${actifs} en vol (${c.resume}, plafond dur ${DUR})`)
  for (const g of file.splice(0, k)) lancer(g)
}
const statutRestant = stopQuota ? 'quota' : 'charge'
const motifRestant = stopQuota || stopCharge
const resultats = [...await Promise.all(enCours), ...file.map(g => nonLancee(g, statutRestant, motifRestant))]

const fusions = resultats.filter(r => r && r.fusion && r.fusion.fusionne)
for (const r of resultats.filter(x => !fusions.includes(x))) {
  log(`NON FUSIONNÉE : ${r ? r.grappe : '?'} — ${r && r.fusion ? r.fusion.motif_refus : (r && r.dev ? r.dev.statut : 'agent mort')}`)
}
for (const r of fusions) if (!r.fusion.sast_ok) log(`SAST À RELIRE : ${r.grappe} — ${r.fusion.sast}`)

let securite = null
// Grappes DOUTEUSES : agent de fusion mort, merge peut-être fait — leur write-set entre dans la revue.
const douteuses = resultats.filter(r => r && r.fusion && r.fusion.fusionne === null)
if (fusions.length || douteuses.length) {
  phase('Sécurité')
  // Périmètre : les fichiers rendus par chaque dev, FILTRÉS par le write-set déclaré de sa grappe (rien d'autre
  // n'entre dans la commande) ; aucun fichier retenu : le write-set lui-même ; une grappe douteuse : son write-set.
  const fichiers = [...new Set([...fusions.flatMap(r => {
    const rendus = Array.isArray(r.dev.fichiers) ? r.dev.fichiers.filter(p => r.writeset.includes(p)) : []
    return rendus.length ? rendus : r.writeset
  }), ...douteuses.flatMap(r => r.writeset)])]
  const douteusesDites = douteuses.length ? ` ; DOUTEUSES (agent de fusion mort, merge peut-être fait) : ${douteuses.map(r => r.grappe).join(', ')}` : ''
  try {
    securite = await agent(
      `Revue de sécurité applicative du diff de la fournée ${A.label}, dépôt ${RACINE}. Périmètre exact : \`git diff ${A.base} HEAD -- ${fichiers.join(' ')}\` (fusions : ${fusions.map(r => r.fusion.merge_sha + ' ' + r.grappe).join(', ') || 'aucune sûre'}${douteusesDites}). ${A.securite || ''}
SAST de la fournée, exactement : \`bash .agents/security/semgrep-scan.sh --since ${A.base}\` (audit de tranche des fichiers changés sur ${A.base}...HEAD, jamais le mode par défaut du script, dont le périmètre n'est pas celui de la fournée).
Cherche : injection (subprocess avec shell, valeur re-parsée, eval), traversée de chemin, écriture ou suppression hors périmètre, secret, ReDoS, affaiblissement d'une garde. Lecture seule. bloquants = findings HIGH/CRITICAL (classe 1), avec fichier:ligne et scénario ; avis = MEDIUM/LOW ; couverture = ce que le SAST a réellement lu : la commande jouée, son rc, sa ligne de verdict (clean ou findings), les cibles non inspectées (partial scope) et toute ligne COVERAGE DEGRADED, recopiées.`,
      { label: 'securite', phase: 'Sécurité', schema: SECU_SCHEMA, agentType: 'security-code-review' },
    )
  } catch (e) {
    log(`revue de sécurité morte (${e && e.message ? e.message : e})`)
  }
  if (!securite) {
    securite = { bloquants: [`REVUE DE SÉCURITÉ ABSENTE — relancer security-code-review sur git diff ${A.base} HEAD`], avis: [], rapport: 'agent de sécurité mort ou muet' }
  }
} else {
  log('aucune fusion : revue de sécurité sautée')
}

// La revue de sécurité a tourné EN PARALLÈLE des exec-critics (AGENTS.md : exec-critic ∥ security gate) ;
// chaque exec lancé est poussé AVANT que son lot ne rende : la liste est complète, on la relève ici.
await Promise.all(execs)
return rapport(resultats, securite)
