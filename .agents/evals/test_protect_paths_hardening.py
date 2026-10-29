"""Durcissement de protect-paths — T-00000721, T-00000722, T-00000723, T-00000750, T-00000763.

LE PLAN FAIT FOI : `docs/tasks/T-00000721-plan.md` (rév. 5). Ce banc porte ses
deux tables « Relevé BASE → POST » dans la colonne POST, ligne pour ligne, et il
a été LANCÉ AU SHA DE DÉPART (9582d114) avant toute édition des gardes : l'ensemble
rouge y était EXACTEMENT l'ensemble des lignes BASE≠POST (plus les témoins neufs
qui n'ont pas de BASE — le pli, les six lignes `Edit(./…)`, le mode sans python).
Un banc qui n'a jamais été rouge ne prouve pas qu'il sait l'être.

CE QU'IL EXERCE, ET COMMENT. Chaque ligne pilote les VRAIES gardes, copiées dans
un projet jetable (`mkdtemp` + `git init` — `_common.project_root` résout par
`git rev-parse`, donc les jumeaux s'ancrent sur la fixture et jamais sur ce
dépôt), nourries par STDIN comme leur hôte les nourrit :

  claude -> .claude/hooks/protect-paths.sh / safe-bash.sh   (refus = exit 2)
  codex  -> .codex/hooks/protect_paths.py / safe_bash.py    (refus = corps
  gemini -> .gemini/hooks/protect_paths.py / safe_bash.py    permissionDecision)

La RÈGLE du refus se lit dans l'événement canal A (`hook.deny{rule}`), jamais
dans la prose du message : c'est le vocabulaire commun aux hôtes. D'où la copie
de `redaction.py` dans la fixture, pris au paquet `cadre` que `vendor_paths`
résout (vendor d'abord) et posé à l'ancien lieu `src/cadre/ledger/` ET au neuf
`.agents/vendor/cadre/ledger/` — `events.py` le charge PAR CHEMIN (parents[2]),
et sans lui chaque ligne est NEUTRALISÉE en
`{"redaction_unavailable": true}` : la règle devient illisible et tout le banc
rougit pour une raison qui n'est pas la sienne (mesuré au premier rejeu).
Ne retire pas cette copie.

« Relatif = absolu sous la racine » (plan, en-tête de table) : chaque chemin
relatif est rejoué une seconde fois préfixé de la racine de la fixture, sur les
trois hôtes, et doit rendre le même verdict.

Les marqueurs (`KIT_CODE_PROTEGE`, `KIT_CODE_AUTORISE`) sont posés par
`Path.write_text` DANS la fixture : une redirection shell vers eux serait
refusée par la garde même que ce banc teste, et le dépôt est livré DÉSARMÉ.

CE QUE CE BANC NE PROUVE PAS : que Windows/NTFS ouvre bien le même fichier pour
chaque orthographe repliée (plateforme non disponible ici — le pli est une
MODÉLISATION de Win32, épinglée par le différentiel énuméré) ; les noms courts
8.3 (`KICKOF~1`) et `C:foo` relatif au lecteur restent des résidus écrits.
"""
from __future__ import annotations

import ast
import concurrent.futures
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="pas de bash — l'hôte Claude n'est pas exerçable")

COPIED = (
    ".claude/hooks/protect-paths.sh",
    ".claude/hooks/emit-event.sh",
    ".claude/hooks/safe-bash.sh",
    ".codex/hooks/_common.py",
    ".codex/hooks/protect_paths.py",
    ".codex/hooks/safe_bash.py",
    ".codex/hooks/safe_bash_git.py",
    ".codex/hooks/safe_bash_hooks.py",
    ".gemini/hooks/_common.py",
    ".gemini/hooks/protect_paths.py",
    ".gemini/hooks/safe_bash.py",
    ".gemini/hooks/safe_bash_git.py",
    ".gemini/hooks/safe_bash_hooks.py",
    ".agents/bin/events.py",
    ".agents/bin/kit_code_guard.py",
    # Voir la docstring : sans lui, la règle de chaque refus est illisible.
    "src/cadre/ledger/redaction.py",
    ".agents/vendor/cadre/ledger/redaction.py",
)

# `cadre` résolu par vendor_paths chargé PAR CHEMIN (S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VP = importlib.util.spec_from_file_location("_pph_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VP is not None and _SPEC_VP.loader is not None
_VP = sys.modules[_SPEC_VP.name] = importlib.util.module_from_spec(_SPEC_VP)
_SPEC_VP.loader.exec_module(_VP)
_PAQUET_CADRE = _VP.dossier_paquet(ROOT, "cadre")


def _source(rel: str) -> Path:
    """La source d'une entrée de COPIED : `redaction.py` vient du paquet résolu,
    quel que soit le lieu où la fixture le pose ; le reste, de `ROOT / rel`."""
    if rel.endswith("cadre/ledger/redaction.py") and _PAQUET_CADRE is not None:
        return _PAQUET_CADRE / "ledger" / "redaction.py"
    return ROOT / rel

G = ".agents/state/gates/"
A = "PUSH_DEFAUT_AUTORISE"
PY_HOSTS = (".codex", ".gemini")

# ---------------------------------------------------------------------------
# Les projets jetables, un par configuration de marqueurs.
# ---------------------------------------------------------------------------
PROJETS = {
    # `lnksrc -> src` : la case {résolu} × {points} de la clause de redirection.
    "base": {"links": {"lnksrc": "src"}},
    "ext": {"extension": "Vendor/"},
    # Motif local à antislash : seul refus propre à la passe BRUTE de Claude.
    "extbs": {"extension": "a\\B\\"},
    "kitoff": {},
    "kiton": {"marker": True},
    "oct": {"marker": True, "octroi": ".claude/hooks/ T-00000721 2099-01-01T00:00Z\n"},
    "octfile": {"marker": True, "octroi": ".claude/hooks/x.sh T-00000721 2099-01-01T00:00Z\n"},
    "octpast": {"marker": True, "octroi": ".claude/hooks/ T-00000721 2020-01-01T00:00Z\n"},
    "octbad": {"marker": True, "octroi": ".claude/hooks/ T-721 demain\n"},
    "octdot": {"marker": True, "octroi": ". T-00000721 2099-01-01T00:00Z\n"},
    "octclaude": {"marker": True, "octroi": ".claude/ T-00000721 2099-01-01T00:00Z\n"},
    "octbin": {"marker": True, "octroi": ".agents/bin/ T-00000721 2099-01-01T00:00Z\n"},
    "noguard": {"marker": True, "drop_guard": True},
    "broken": {"marker": True, "broken_guard": True},
    # Liens symboliques vers un dossier protégé (revue de sécurité, finding 1/2).
    "lien": {"links": {"lnk": ".agents/state/gates"}},
    "kitlien": {"marker": True, "links": {"lnkhooks": ".claude/hooks", "lnkdocs": "docs",
                                          "lnksub": "docs/sub"}},
}

# ---------------------------------------------------------------------------
# TABLE « Edit », colonne POST. (id, projet, chemin, attendu claude, attendu py)
# claude : "0" | "2/<règle>" | "0+warn" ; py : "0" | "<règle>" | "0+warn".
# `<ROOT>` est remplacé par la racine de la fixture.
# ---------------------------------------------------------------------------
PS = "push-defaut-sortie"
KA = "kickoff-arming"
MCP = "mcp-config"
CRED = "credential-pattern"
GIT = "git-internals"
KIT = "kit-code"

EDIT_ROWS = [
    # -- pli NTFS (T-00000722)
    ("autorise", "base", G + A, "2/" + PS, PS),
    ("autorise-point", "base", G + A + ".", "2/" + PS, PS),
    ("autorise-espace", "base", G + A + " ", "2/" + PS, PS),
    ("autorise-ads", "base", G + A + "::$DATA", "2/" + PS, PS),
    ("kickoff-point", "base", G + "KICKOFF_REQUIRED.", "2/" + KA, KA),
    ("kickoff-segment-point", "base", ".agents./state/gates/KICKOFF_REQUIRED", "2/" + KA, KA),
    ("kickoff-lecteur", "base", "C:\\r\\.agents\\state\\gates\\KICKOFF_REQUIRED.", "2/" + KA, KA),
    ("kickoff-antislash-casse", "base", ".AGENTS\\STATE\\GATES\\KICKOFF_REQUIRED", "2/" + KA, KA),
    ("pem-point", "base", "key.pem.", "2/" + CRED, CRED),
    ("mcp-point", "base", ".mcp.json.", "2/" + MCP, MCP),
    ("codex-antislash", "base", ".codex\\config.toml", "2/" + MCP, MCP),
    ("gemini-antislash", "base", ".gemini\\settings.json", "2/" + MCP, MCP),
    ("codex-casse", "base", ".CODEX/config.toml", "2/" + MCP, MCP),
    ("gemini-casse", "base", ".Gemini/Settings.json", "2/" + MCP, MCP),
    ("mcp-casse", "base", ".MCP.json", "2/" + MCP, MCP),
    ("mcp-flux", "base", "x/foo:MCP.JSON", "2/" + MCP, MCP),
    # -- fichiers pilote-seuls (T-00000723, T-00000750) et marqueurs kit-code
    ("night-headless", "base", G + "NIGHT_HEADLESS.allow", "2/night-headless", "night-headless"),
    ("mcp-allowlist", "base", G + "MCP_ALLOWLIST.md", "2/mcp-allowlist", "mcp-allowlist"),
    ("settings-local", "base", ".claude/settings.local.json", "2/claude-settings-local", "claude-settings-local"),
    # Le marqueur de la route de dev locale, retirée (T-01M5PCCHMWXTRCM5QJT8J5KNEH) :
    # plus rien ne le lit, plus rien ne le protège — un Edit passe sur les trois copies.
    ("marqueur-route-retiree", "base", ".agents/state/local/" "DEV_" "ROUTE", "0", "0"),
    ("kit-arming", "base", G + "KIT_CODE_PROTEGE", "2/kit-code-arming", "kit-code-arming"),
    ("kit-sortie", "base", G + "KIT_CODE_AUTORISE", "2/kit-code-sortie", "kit-code-sortie"),
    ("audit-log-epingle", "base", G + "AUDIT_LOG", "0", "0"),  # S-00002524
    # -- internes git (T-00000763 B)
    ("git-config", "base", ".git/config", "2/" + GIT, GIT),
    ("git-hook", "base", ".git/hooks/pre-commit", "2/" + GIT, GIT),
    ("git-exclude", "base", ".git/info/exclude", "2/" + GIT, GIT),
    ("git-sous-module", "base", "sub/.git/config", "2/" + GIT, GIT),
    ("git-casse", "base", ".GIT/config", "2/" + GIT, GIT),
    ("gitignore", "base", ".gitignore", "0", "0"),
    ("workflow", "base", ".github/workflows/ci.yml", "0", "0"),
    # Le registre d'exceptions de la porte class-0, pilote seul (T-00000844) —
    # « 0 » jusque-là : un Edit d'agent le corrompait et éteignait la porte.
    ("gitleaks", "base", ".gitleaks.toml", "2/gitleaks-allowlist", "gitleaks-allowlist"),
    ("gitleaks-casse", "base", ".GitLeaks.TOML", "2/gitleaks-allowlist", "gitleaks-allowlist"),
    ("gitleaks-point", "base", ".gitleaks.toml.", "2/gitleaks-allowlist", "gitleaks-allowlist"),
    ("gitleaks-notes", "base", "docs/gitleaks-notes.md", "0", "0"),
    # Le journal de specs, écrit par `specs.py` seul (T-00000847) — « 0 »
    # jusque-là : un Edit d'agent pouvait effacer un marqueur night-delivered.
    ("specs-journal", "base", ".agents/state/specs/SPECS.json", "2/specs-journal", "specs-journal"),
    ("specs-journal-casse", "base", ".AGENTS/State/Specs/specs.JSON", "2/specs-journal", "specs-journal"),
    ("specs-journal-point", "base", ".agents/state/specs/SPECS.json.", "2/specs-journal", "specs-journal"),
    ("specs-vue", "base", ".agents/state/local/SPECS.md", "0", "0"),
    ("specs-ailleurs", "base", "docs/SPECS.json", "0", "0"),
    # Sa forme JOURNAL (T-01M4KKMY43ZKCW1YD2Y8JX9MKH, H1) : même règle, trois hôtes — « 0 » à la BASE.
    ("specs-jsonl", "base", ".agents/state/specs/SPECS.jsonl", "2/specs-journal", "specs-journal"),
    ("specs-jsonl-casse", "base", ".AGENTS/State/Specs/specs.JSONL", "2/specs-journal", "specs-journal"),
    ("specs-jsonl-point", "base", ".agents/state/specs/SPECS.jsonl.", "2/specs-journal", "specs-journal"),
    ("specs-jsonl-ailleurs", "base", "docs/SPECS.jsonl", "0", "0"),
    ("docs", "base", "docs/x.md", "0", "0"),
    ("readme", "base", "README.md", "0", "0"),
    ("readme-point", "base", "README.md.", "0", "0"),
    ("codex-agent", "base", ".codex/agents/foo.toml", "0", "0"),
    # -- jetons credential (T-00000721)
    ("id-rsa", "base", "id_rsa", "2/" + CRED, CRED),
    ("id-rsa-flux", "base", "x/notes.md:id_rsa", "2/" + CRED, CRED),
    ("server-key", "base", "server.key", "2/" + CRED, CRED),
    ("server-key-lecteur", "base", "x:server.key", "2/" + CRED, CRED),
    ("secrets-rotation", "base", "docs/SecretsRotation.md", "2/" + CRED, CRED),
    ("secret-flux-casse", "base", "docs/a:SECRET.md", "2/" + CRED, CRED),
    ("credential-singulier", "base", "a.credential.txt", "2/" + CRED, CRED),
    ("pem-casse", "base", "k.PEM", "2/" + CRED, CRED),
    ("secret-flux", "base", "docs/a:secret.md", "2/" + CRED, CRED),
    ("credentials", "base", "foo.credentials.json", "2/" + CRED, CRED),
    ("envrc", "base", ".envrc", "2/.env", CRED),  # ids différents, verdict identique (préexistant)
    # -- liste BLOCKED_PATTERNS jugée par candidat (L-013 intacte)
    ("legacy-casse", "base", "SRC/LEGACY/x.ts", "2/src/legacy/", "src/legacy/"),
    ("generated-casse", "base", "GENERATED/x", "2/generated/", "generated/"),
    ("env-local-casse", "base", ".ENV.LOCAL", "2/.env", ".env"),
    ("env-example-casse", "base", ".ENV.EXAMPLE", "0", "0"),
    ("env-example", "base", ".env.example", "0", "0"),
    ("env-example-imbrique", "base", "apps/web/.env.example", "0", "0"),
    ("dotenv-example", "base", "dotenv.example", "0", "0"),
    ("env-example-point", "base", ".env.example.", "2/.env", ".env"),
    ("env-example-bak", "base", ".env.example.bak", "2/.env", ".env"),
    # Gabarit reconnu sans casse sur les quatre hôtes (décision
    # S-01M5X79JTGRSSTB872R4YBPVMF, qui remplace S-01M5SZJE11).
    ("x-env-example-casse", "base", "x.env.EXAMPLE", "0", "0"),
    ("env-sample-casse", "base", ".env.Sample", "0", "0"),
    ("env-example-imbrique-casse", "base", "app/.env.Example", "0", "0"),
    ("env-example-bak-casse", "base", ".env.Example.bak", "2/.env", ".env"),
    ("ext-majuscule", "ext", "Vendor/x.py", "2/Vendor/", "vendor/"),
    ("ext-minuscule", "ext", "vendor/x.py", "2/vendor/", "vendor/"),
    # Divergence antislash, épinglée pour que la passe brute garde un témoin
    # rouge : Claude refuse le candidat brut (par la liste minusculisée `a\b\`),
    # jumeaux : motif à antislash INERTE (même `a\B\x.py` admis, mesuré) — trou
    # ouvert, T-01M5YSEVJF72H3HJSBHCGG6HNK.
    ("ext-antislash-brut", "extbs", "a\\b\\x.py", "2/a\\b\\", "0"),
    # -- code du kit (T-00000763 A) — désarmé
    ("kit-off-hook", "kitoff", ".claude/hooks/x.sh", "0", "0"),
    ("kit-off-bin", "kitoff", ".agents/bin/tasks.py", "0", "0"),
    # -- armé, sans octroi
    ("kit-hook", "kiton", ".claude/hooks/x.sh", "2/" + KIT, KIT),
    ("kit-bin", "kiton", ".agents/bin/tasks.py", "2/" + KIT, KIT),
    ("kit-verify", "kiton", "core-scripts/verify.sh", "2/" + KIT, KIT),
    ("kit-casse", "kiton", ".CLAUDE/HOOKS/x.sh", "2/" + KIT, KIT),
    ("kit-segment-point", "kiton", ".claude/hooks./x.sh", "2/" + KIT, KIT),
    ("kit-absolu", "kiton", "<ROOT>/.claude/hooks/x.sh", "2/" + KIT, KIT),
    # Segments `..` et `.` : les jumeaux les résolvent (`normalize_path`), Claude
    # passe le chemin tel quel — mesuré, ces trois-là rendaient 0 sur Claude
    # avant que `kit_code_guard._relative` ne normalise la clé.
    ("kit-dotdot", "kiton", "a/../.claude/hooks/x.sh", "2/" + KIT, KIT),
    ("kit-dotdot-absolu", "kiton", "<ROOT>/.claude/../.claude/hooks/x.sh", "2/" + KIT, KIT),
    ("kit-point-segment", "kiton", ".claude/./hooks/x.sh", "2/" + KIT, KIT),
    ("kit-readme", "kiton", "README.md", "0", "0"),
    ("kit-core-other", "kiton", "core-scripts/other.py", "0", "0"),
    ("kit-evals", "kiton", ".agents/evals/x.py", "0", "0"),
    ("kit-v3", "kiton", "agentic_v3/x.py", "0", "0"),
    ("kit-hors-racine", "kiton", "/tmp/y/.claude/hooks/x.sh", "0", "0"),
    # -- armé + octroi
    ("oct-hook", "oct", ".claude/hooks/x.sh", "0+warn", "0+warn"),
    ("oct-bin", "oct", ".agents/bin/tasks.py", "2/" + KIT, KIT),
    ("octfile-exact", "octfile", ".claude/hooks/x.sh", "0+warn", "0+warn"),
    ("octfile-sous-chaine", "octfile", ".claude/hooks/x.sh.bak", "2/" + KIT, KIT),
    ("octpast-hook", "octpast", ".claude/hooks/x.sh", "2/" + KIT, KIT),
    ("octbad-hook", "octbad", ".claude/hooks/x.sh", "2/" + KIT, KIT),
    ("octdot-hook", "octdot", ".claude/hooks/x.sh", "2/" + KIT, KIT),
    ("octclaude-hook", "octclaude", ".claude/hooks/x.sh", "2/" + KIT, KIT),
    ("octbin-env", "octbin", ".agents/bin/.env", "2/.env", ".env"),
    ("noguard-readme", "noguard", "README.md", "2/kit-code-guard-illisible", "kit-code-guard-illisible"),
    ("broken-readme", "broken", "README.md", "2/kit-code-guard-illisible", "kit-code-guard-illisible"),
    # -- le chemin RÉSOLU (revue de sécurité, finding 1, class 1) : `.`, `..` et
    # liens symboliques. Les jumeaux résolvent (`normalize_path` →
    # `Path.resolve`) ; Claude jugeait le texte brut, et TOUS les bras de
    # `juger()` se contournaient par `x/../<cible>` ou par un lien — mesuré, rc 0
    # dès 9582d114. Quatrième candidat `$FILE_RP` (realpath, relatif à la racine
    # résolue). Contrôle : un fichier ordinaire reste écrivable.
    ("rp-kickoff", "base", G + "z/../KICKOFF_REQUIRED", "2/" + KA, KA),
    ("rp-binome", "base", G + "z/../BINOME_REQUIRED", "2/binome-arming", "binome-arming"),
    ("rp-kit-sortie", "base", G + "z/../KIT_CODE_AUTORISE", "2/kit-code-sortie", "kit-code-sortie"),
    ("rp-night", "base", G + "z/../NIGHT_HEADLESS.allow", "2/night-headless", "night-headless"),
    ("rp-legacy", "base", "src/x/../legacy/y.ts", "2/src/legacy/", "src/legacy/"),
    ("rp-lien", "lien", "lnk/KICKOFF_REQUIRED", "2/" + KA, KA),
    # LA MATRICE {brut, résolu} × {rogné, points, LC/ADS} sur le chemin RÉSOLU
    # (security-code-review sur 14fc95b5, HIGH 2) : la lecture « points » n'était
    # appliquée qu'au chemin BRUT. Mesuré avant correctif : les deux premières
    # lignes rendaient 0 sur Claude (les jumeaux, qui résolvent puis plient,
    # refusaient déjà). Les suivantes ferment les autres cases de la matrice.
    ("rpnd-lien-espace", "lien", "lnk/z/.. /KICKOFF_REQUIRED", "2/" + KA, KA),
    ("rpnd-lien-triple", "lien", "lnk/z/.../BINOME_REQUIRED", "2/binome-arming", "binome-arming"),
    ("rpnr-lien-espace", "lien", "lnk/.. /KICKOFF_REQUIRED", "2/" + KA, KA),
    ("rpnr-lien-triple", "lien", "lnk/.../KICKOFF_REQUIRED", "2/" + KA, KA),
    ("rpnn-lien-flux", "lien", "lnk/z/..:s/KICKOFF_REQUIRED", "2/" + KA, KA),
    ("rpnt-lien-ads", "lien", "lnk/KICKOFF_REQUIRED::$DATA", "2/" + KA, KA),
    ("rpnt-lien-point", "lien", "lnk/KICKOFF_REQUIRED.", "2/" + KA, KA),
    ("rp-lien-controle", "lien", "lnk/z/.. /docs/y.md", "0", "0"),
    ("rp-controle", "base", "docs/x/../y.md", "0", "0"),
    # -- le `..` NÉ DU PLI NT (exec-critic, constat 1) : sous le modèle NT du kit
    # `..:s` vaut `..`, mais `realpath` et `Path.resolve` y voient un nom
    # ordinaire — seule une renormalisation lexicale APRÈS le pli le résout.
    # Mesuré à 604db568 : rc 0 sur Claude, pass sur les deux jumeaux.
    ("nn-kickoff", "base", G + "z/..:s/KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nn-binome", "base", G + "z/..:s/BINOME_REQUIRED", "2/binome-arming", "binome-arming"),
    ("nn-night", "base", G + "z/..:s/NIGHT_HEADLESS.allow", "2/night-headless", "night-headless"),
    ("nn-legacy", "base", "src/x/..:s/legacy/y.ts", "2/src/legacy/", "src/legacy/"),
    ("nn-controle", "base", "x/..:s/docs/y.md", "0", "0"),
    # -- le segment FAIT DE POINTS ET D'ESPACES (security-code-review à db1a65d9,
    # classe T-722) : `rstrip(". ")` VIDAIT `.. ` au lieu d'y lire `..`, donc
    # `z/.. /KICKOFF_REQUIRED` valait `z/kickoff_required` — 0 sur les trois
    # hôtes. Seconde LECTURE du pli (« points ») : un tel segment vaut `..` s'il
    # porte au moins deux points, `.` sinon ; normalisée, jugée EN PLUS de la
    # lecture « rognée » d'origine (union de refus). La tabulation n'est PAS
    # rognée par Win32 (caractère interdit dans un nom : l'écriture échoue) :
    # `..\t` reste un nom, épinglé à 0.
    ("nd-kickoff", "base", G + "z/.. /KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nd-binome", "base", G + "z/.. /BINOME_REQUIRED", "2/binome-arming", "binome-arming"),
    ("nd-night", "base", G + "z/.. /NIGHT_HEADLESS.allow", "2/night-headless", "night-headless"),
    ("nd-triple", "base", G + "z/.../KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nd-quadruple-espace", "base", G + "z/.... /KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nd-ads", "base", G + "z/.. ::$DATA/KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nd-legacy", "base", "src/x/.. /legacy/y.ts", "2/src/legacy/", "src/legacy/"),
    ("nd-tete", "base", ".. /.agents/state/gates/KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nd-tab-epingle", "base", G + "z/..\t/KICKOFF_REQUIRED", "0", "0"),
    ("nd-controle", "base", "x/.. /docs/y.md", "0", "0"),
    ("nd-kit", "kiton", "x/.. /.claude/hooks/y.sh", "2/" + KIT, KIT),
    # La lecture ROGNÉE renormalisée, seule à refuser ceux-ci (la lecture points
    # y lit `gates/../kickoff_required`) : sans ces lignes, retirer le candidat
    # « replié renormalisé » des jumeaux survivait (M29py, mesuré).
    ("nr-rogne-espace", "base", G + ".. /KICKOFF_REQUIRED", "2/" + KA, KA),
    ("nr-rogne-triple", "base", G + ".../KICKOFF_REQUIRED", "2/" + KA, KA),
    # -- et la garde kit-code (finding 2) : un lien vers un préfixe de l'ensemble
    # est refusé, un lien vers un dossier HORS ensemble reste écrivable.
    ("kit-lien", "kitlien", "lnkhooks/x.sh", "2/" + KIT, KIT),
    ("kit-lien-hors", "kitlien", "lnkdocs/x.md", "0", "0"),
    ("kit-lien-points", "kitlien", "lnkdocs/.. /.claude/hooks/x.sh", "2/" + KIT, KIT),
    # Un `..` APRÈS un lien (exec-critic, constat 2) : la forme LEXICALE
    # (Win32 résout `..` avant le lien) vaut `.claude/hooks/x.sh`, la forme
    # PHYSIQUE (POSIX) vaut `docs/.claude/hooks/x.sh`. Refusé à 6503c35b,
    # accepté à 604db568 quand `realpath` a REMPLACÉ la forme lexicale au lieu de
    # s'y ajouter. Les deux formes sont jugées, union de refus.
    # DIVERGENCE ÉPINGLÉE (résidu écrit) : les jumeaux reçoivent de
    # `_common.normalize_path` un chemin DÉJÀ résolu physiquement
    # (`docs/.claude/hooks/x.sh`) — la forme lexicale ne leur parvient jamais, et
    # `_common.py` est hors du write-set du lot. La fermer rougira cette ligne.
    ("kit-lien-dotdot", "kitlien", "lnksub/../.claude/hooks/x.sh", "2/" + KIT, "0"),
]

# La ligne ignorée est COMPTÉE et sa cause NOMMÉE dans le refus (plan, étape 6).
IGNORED_CAUSE = {"octpast": "échue", "octbad": "malformée", "octdot": "hors ensemble",
                 "octclaude": "hors ensemble"}

# ---------------------------------------------------------------------------
# TABLE « Redirection », colonne POST. <d> = mkdtemp HORS de la fixture.
# (id, cible sous <d>, attendu claude rc, attendu judge_redirect py, attendu hook py)
# ---------------------------------------------------------------------------
REDIR_ROWS = [
    ("autorise", G + A, 2, "protected", "deny"),
    ("autorise-point", G + A + ".", 2, "protected", "deny"),
    ("night-headless", G + "NIGHT_HEADLESS.allow", 2, "protected", "deny"),
    ("mcp-allowlist", G + "MCP_ALLOWLIST.md", 2, "protected", "deny"),
    ("kit-sortie", G + "KIT_CODE_AUTORISE", 2, "protected", "deny"),
    # Le NOM NU (hors `gates/`) : refusé par la règle du nom, qui vit dans `main`
    # et non dans `judge_redirect` — donc `pass` pour la fonction, `deny` pour le hook.
    ("night-headless-nu", "NIGHT_HEADLESS.allow", 2, "pass", "deny"),
    ("mcp-allowlist-nu", "MCP_ALLOWLIST.md", 2, "pass", "deny"),
    ("kit-sortie-nu", "KIT_CODE_AUTORISE", 2, "pass", "deny"),
    ("audit-log-epingle", "AUDIT_LOG", 0, "pass", "pass"),
    ("audit-log-gates-epingle", G + "AUDIT_LOG", 0, "pass", "pass"),
    ("git-config", ".git/config", 2, "protected", "deny"),
    ("settings-local", ".claude/settings.local.json", 2, "protected", "deny"),
    ("gitleaks", ".gitleaks.toml", 2, "protected", "deny"),  # T-00000844
    ("specs-journal", ".agents/state/specs/SPECS.json", 2, "protected", "deny"),  # T-00000847
    # Hors `gates/` : PAS dans la règle du nom — le nom nu passe (témoin).
    ("specs-journal-nu", "SPECS.json", 0, "pass", "pass"),  # T-00000847
    ("id-rsa", "id_rsa", 2, "protected", "deny"),
    ("server-key", "server.key", 2, "protected", "deny"),
    ("envrc", ".envrc", 2, "protected", "deny"),
    ("server-key-flux", "x:server.key", 2, "protected", "deny"),
    ("environment-dir", "x.environment/f", 2, "protected", "deny"),
    ("codex-config", ".codex/config.toml", 2, "protected", "deny"),
    ("copilot-settings", ".github/copilot/settings.json", 2, "protected", "deny"),  # alignement L-D (H-29)
    ("secrets-rotation", "docs/SecretsRotation.md", 2, "protected", "deny"),
    # Les témoins de la passe NT de la CLAUSE DE CHEMIN (M8). Sur un marqueur,
    # la règle du nom refuse aussi (`autorise-point` reste rouge sans `ntf` dans
    # `protected()` : mesuré, le mutant survivait) ; ces deux cibles ne sont PAS
    # des marqueurs, donc seule la passe NT de `protected()` les refuse.
    ("pem-point", "key.pem.", 2, "protected", "deny"),
    ("mcp-point", "x/.mcp.json.", 2, "protected", "deny"),
    # Le `..` né du pli (constat 1), hors dépôt. Sur un marqueur la règle du nom
    # refuse déjà le HOOK ; la colonne `judge_redirect` est celle que le
    # correctif retourne.
    ("nn-kickoff", G + "z/..:s/KICKOFF_REQUIRED", 2, "protected", "deny"),
    ("nn-binome", G + "z/..:s/BINOME_REQUIRED", 2, "protected", "deny"),
    ("nn-night", G + "z/..:s/NIGHT_HEADLESS.allow", 2, "protected", "deny"),
    # Le segment de points (lecture « points »). Un espace couperait le mot de
    # la commande : les formes sans espace portent la redirection.
    ("nd-triple", G + "z/.../KICKOFF_REQUIRED", 2, "protected", "deny"),
    ("nd-triple-binome", G + "z/.../BINOME_REQUIRED", 2, "protected", "deny"),
    ("nr-rogne-triple", G + ".../KICKOFF_REQUIRED", 2, "protected", "deny"),
]

# Règle du nom : (id, commande avec {d}, attendu claude rc, attendu hook py)
NAME_ROWS = [
    ("cd-gates-point", "cd {d}/" + G + " && printf y > " + A + ".", 2, "deny"),
    ("cite-ads", "printf y > '{d}/" + A + "::$DATA'", 2, "deny"),
    ("cd-night-minuscule", "cd {d} && printf y > night_headless.allow", 2, "deny"),
    ("cd-kit-arming", "cd {d} && printf y > KIT_CODE_PROTEGE", 2, "deny"),
    ("cd-settings-local", "cd {d} && printf y > settings.local.json", 0, "pass"),  # hors famille
    # La clause de redirection RÉSOUT déjà (`normalize` → `Path.resolve`) :
    # témoins posés pour qu'un retour au texte brut rougisse (finding 1).
    ("rp-redir-kickoff", "printf y > .agents/state/gates/z/../KICKOFF_REQUIRED", 2, "deny"),
    ("rp-redir-legacy", "printf y > src/x/../legacy/y.ts", 2, "deny"),
    ("rp-redir-controle", "printf y > docs/x/../y.md", 0, "pass"),
    # Le `..` né du pli, dans le dépôt, sur une cible qui n'est PAS un marqueur :
    # seule la clause de chemin peut la refuser (constat 1).
    ("nn-redir-legacy", "printf y > src/x/..:s/legacy/y.ts", 2, "deny"),
    ("nn-redir-controle", "printf y > x/..:s/docs/y.md", 0, "pass"),
    ("nd-redir-legacy", "printf y > src/x/.../legacy/y.ts", 2, "deny"),
    ("nd-redir-legacy-4", "printf y > src/x/..../legacy/y.ts", 2, "deny"),
    ("nd-redir-controle", "printf y > x/.../docs/y.md", 0, "pass"),
    # Seule la lecture ROGNÉE renormalisée refuse celle-ci (`src/legacy/y.ts`) ;
    # la lecture points y lit `legacy/y.ts`. Sans elle, retirer ce candidat de
    # `protected()` survivait (M29sb, mesuré) : sur un marqueur, la règle du nom
    # masque la clause de chemin.
    ("nr-redir-legacy", "printf y > src/.../legacy/y.ts", 2, "deny"),
    # {résolu} × {points} côté redirection : `normalize` résout le lien, puis
    # `protected()` juge ses quatre lectures — mesuré sain à 0b83d3b8, épinglé.
    ("rpnd-redir-legacy", "printf y > lnksrc/x/.../legacy/y.ts", 2, "deny"),
    ("rpnd-redir-legacy-4", "printf y > lnksrc/x/..../legacy/y.ts", 2, "deny"),
    ("rpnd-redir-controle", "printf y > lnksrc/x/.../z/y.md", 0, "pass"),
]

# Les six lignes `permissions.deny` (plan, étape 4 et 6).
DENY_LINES = (
    "Edit(./.agents/state/gates/NIGHT_HEADLESS.allow)",
    "Edit(./.agents/state/gates/MCP_ALLOWLIST.md)",
    "Edit(./.claude/settings.local.json)",
    "Edit(./.agents/state/gates/KIT_CODE_PROTEGE)",
    "Edit(./.agents/state/gates/KIT_CODE_AUTORISE)",
    "Edit(./.gitleaks.toml)",  # T-00000844
    "Edit(./.agents/state/specs/SPECS.json)",  # T-00000847
    "Edit(./.agents/state/specs/SPECS.jsonl)",  # T-01M4KKMY43ZKCW1YD2Y8JX9MKH (H1)
    "Edit(./.github/copilot/settings.json)",  # alignement des hôtes, L-D (H-29)
)

# Le différentiel ÉNUMÉRÉ des quatre copies du pli (R7, R8) : chaque entrée porte
# sa sortie ATTENDUE en clair — une parité seule resterait verte si la même faute
# frappait les quatre copies (retirer la branche lettre de lecteur partout).
NT_CASES = (
    ("C:\\r\\.agents\\state\\gates\\KICKOFF_REQUIRED.", "c:/r/.agents/state/gates/kickoff_required"),
    ("C:\\Users\\USER\\id_rsa", "c:/users/user/id_rsa"),
    ("c:foo", "c:foo"),
    ("C:", "c:"),
    (".agents./state/gates/KICKOFF_REQUIRED", ".agents/state/gates/kickoff_required"),
    (G + A + ".", ".agents/state/gates/push_defaut_autorise"),
    (G + A + " ", ".agents/state/gates/push_defaut_autorise"),
    (G + A + "::$DATA", ".agents/state/gates/push_defaut_autorise"),
    ("x/foo:MCP.JSON", "x/foo"),
    ("docs/a:SECRET.md", "docs/a"),
    ("x:server.key", "x:server.key"),
    ("x/notes.md:id_rsa", "x/notes.md"),
    ("a/.../b", "a//b"),
    ("a/../b/./c", "a/../b/./c"),
    ("key.pem.", "key.pem"),
    (".mcp.json. . .", ".mcp.json"),
    (".codex\\config.toml", ".codex/config.toml"),
    ("/Abs/Path/To/File.TXT", "/abs/path/to/file.txt"),
    ("sub/.GIT./config", "sub/.git/config"),
    ("\\\\Server\\Share\\x", "//server/share/x"),
    (".env.example.", ".env.example"),
    ("", ""),
    # La lecture « rognée » d'un segment de points et d'espaces : VIDÉ.
    (".. /x", "/x"),
    ("a/.... /b", "a//b"),
    ("a/.. ::$DATA/b", "a//b"),
    ("a/..\t/b", "a/..\t/b"),
)

# La lecture « points » (`dots=True`) : un segment fait SEULEMENT de points et
# d'espaces vaut `..` s'il porte au moins deux points, `.` s'il en porte un ;
# tout autre segment est plié comme dans la lecture rognée.
NT_DOTS_CASES = (
    (G + "z/.. /KICKOFF_REQUIRED", ".agents/state/gates/z/../kickoff_required"),
    (".. /x", "../x"),
    ("a/.../b", "a/../b"),
    ("a/.... /b", "a/../b"),
    ("a/.. ::$DATA/b", "a/../b"),
    ("a/. ./b", "a/../b"),
    ("a/ ../b", "a/../b"),
    ("a/. /b", "a/./b"),
    ("a/  /b", "a//b"),
    ("a/..\t/b", "a/..\t/b"),
    ("a/../b/./c", "a/../b/./c"),
    (G + A + ".", ".agents/state/gates/push_defaut_autorise"),
    ("C:\\r\\.. \\x", "c:/r/../x"),
    ("", ""),
)


# ---------------------------------------------------------------------------
# Le banc : fixtures et exécuteurs.
# ---------------------------------------------------------------------------
class Banc:
    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="t721-"))
        self.env = {
            **os.environ,
            "CADRE_STATE_DIR": str(self.tmp / "cadre-state"),
            "CADRE_PROJECT_ROOT": str(self.tmp / "cadre-root"),
        }
        self._n = 0
        self.projets = {k: self._projet(k, **v) for k, v in PROJETS.items()}
        self.dehors = Path(tempfile.mkdtemp(prefix="t721-d-", dir=str(self.tmp)))
        (self.dehors / G).mkdir(parents=True)

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _projet(self, name, extension=None, marker=False, octroi=None,
                drop_guard=False, broken_guard=False, links=None) -> Path:
        root = self.tmp / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for link, target in (links or {}).items():
            (root / target).mkdir(parents=True, exist_ok=True)
            os.symlink(target, root / link)
        for rel in COPIED:
            src = _source(rel)
            if not src.exists() or (drop_guard and rel.endswith("kit_code_guard.py")):
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
        if broken_guard:
            guard = root / ".agents" / "bin" / "kit_code_guard.py"
            guard.parent.mkdir(parents=True, exist_ok=True)
            guard.write_text("raise SystemExit(1)\n", encoding="utf-8")
        if extension:
            (root / ".agents").mkdir(exist_ok=True)
            (root / ".agents" / "protected-paths.local").write_text(extension + "\n", encoding="utf-8")
        gates = root / ".agents" / "state" / "gates"
        if marker:
            gates.mkdir(parents=True, exist_ok=True)
            (gates / "KIT_CODE_PROTEGE").write_text("", encoding="utf-8")
        if octroi is not None:
            gates.mkdir(parents=True, exist_ok=True)
            (gates / "KIT_CODE_AUTORISE").write_text(octroi, encoding="utf-8")
        return root

    def _events(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="ev-", dir=str(self.tmp)))
        return d

    @staticmethod
    def _rules(evdir: Path, kind: str) -> list:
        out = []
        for f in sorted(evdir.rglob("*.jsonl")):
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("kind") == kind:
                    out.append((o.get("data") or {}).get("rule"))
        return out

    def edit_claude(self, root: Path, path: str, path_env: str | None = None,
                    extra_env: dict | None = None):
        ev = self._events()
        env = {**self.env, "CLAUDE_PROJECT_DIR": str(root), "AGENTS_EVENTS_DIR": str(ev)}
        if path_env is not None:
            env["PATH"] = path_env
        if extra_env:
            env.update(extra_env)
        p = subprocess.run([BASH, str(root / ".claude/hooks/protect-paths.sh")],
                           input=json.dumps({"tool_input": {"file_path": path}}),
                           capture_output=True, text=True, env=env, timeout=60)
        deny = self._rules(ev, "hook.deny")
        warn = self._rules(ev, "hook.warn")
        if p.returncode == 0:
            verdict = "0+warn" if warn else "0"
        else:
            verdict = f"{p.returncode}/{deny[-1] if deny else '?'}"
        return verdict, p.stderr

    def edit_py(self, root: Path, host: str, path: str):
        ev = self._events()
        env = {**self.env, "AGENTS_EVENTS_DIR": str(ev)}
        if host == ".codex":
            env["AGENTS_HOOK_HOST"] = "codex"
        p = subprocess.run([sys.executable, "-B", str(root / host / "hooks/protect_paths.py")],
                           input=json.dumps({"tool_input": {"file_path": path}}),
                           capture_output=True, text=True, env=env, cwd=str(root), timeout=60)
        if p.returncode != 0:
            return f"CRASH{p.returncode}", p.stderr
        deny = self._rules(ev, "hook.deny")
        warn = self._rules(ev, "hook.warn")
        if '"deny"' in p.stdout:
            # La raison est dans un corps JSON (`ensure_ascii` échappe les
            # accents) : on la DÉCODE avant d'y chercher un mot.
            try:
                reason = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
            except (ValueError, KeyError, TypeError):
                reason = p.stdout
            return (deny[-1] if deny else "?"), reason
        return ("0+warn" if warn else "0"), p.stdout

    def redir_claude(self, root: Path, cmd: str) -> int:
        ev = self._events()
        env = {**self.env, "CLAUDE_PROJECT_DIR": str(root), "AGENTS_EVENTS_DIR": str(ev)}
        p = subprocess.run([BASH, str(root / ".claude/hooks/safe-bash.sh")],
                           input=json.dumps({"tool_input": {"command": cmd}}),
                           capture_output=True, text=True, env=env, cwd=str(root), timeout=60)
        return p.returncode

    def redir_py_hook(self, root: Path, host: str, cmd: str) -> str:
        ev = self._events()
        env = {**self.env, "AGENTS_EVENTS_DIR": str(ev)}
        p = subprocess.run([sys.executable, "-B", str(root / host / "hooks/safe_bash.py")],
                           input=json.dumps({"tool_input": {"command": cmd}}),
                           capture_output=True, text=True, env=env, cwd=str(root), timeout=60)
        if p.returncode != 0:
            return f"CRASH{p.returncode}"
        return "deny" if '"deny"' in p.stdout else "pass"

    def judge_redirect(self, root: Path, host: str, target: str) -> str:
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import safe_bash; "
                "print(safe_bash.judge_redirect(sys.argv[2])[0])")
        p = subprocess.run([sys.executable, "-B", "-c", code, str(root / host / "hooks"), target],
                           capture_output=True, text=True, cwd=str(root), env=self.env, timeout=60)
        return p.stdout.strip() or f"ERR {p.stderr.strip()[-200:]}"


def _variants(root: Path, path: str) -> list:
    if "<ROOT>" in path:
        return [("abs", path.replace("<ROOT>", str(root)))]
    if path.startswith("/"):
        return [("rel", path)]
    return [("rel", path), ("abs", f"{root}/{path}")]


@pytest.fixture(scope="module")
def banc():
    b = Banc()
    try:
        yield b
    finally:
        b.close()


@pytest.fixture(scope="module")
def edit_results(banc):
    """Toutes les lignes « Edit » calculées une fois, en parallèle (sous-processus
    indépendants ; le banc n'a aucune mesure de temps)."""
    jobs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for rid, projet, path, _c, _p in EDIT_ROWS:
            root = banc.projets[projet]
            for tag, v in _variants(root, path):
                jobs[(rid, tag, "claude")] = ex.submit(banc.edit_claude, root, v)
                for host in PY_HOSTS:
                    jobs[(rid, tag, host)] = ex.submit(banc.edit_py, root, host, v)
        return {k: f.result() for k, f in jobs.items()}


@pytest.mark.parametrize("rid,projet,path,exp_c,exp_p", EDIT_ROWS, ids=[r[0] for r in EDIT_ROWS])
def test_table_edit_colonne_post(edit_results, banc, rid, projet, path, exp_c, exp_p):
    root = banc.projets[projet]
    got = {}
    for tag, _v in _variants(root, path):
        got[f"claude/{tag}"] = edit_results[(rid, tag, "claude")][0]
        for host in PY_HOSTS:
            got[f"{host}/{tag}"] = edit_results[(rid, tag, host)][0]
    want = {k: (exp_c if k.startswith("claude") else exp_p) for k in got}
    assert got == want, f"{path!r} ({projet})"
    cause = IGNORED_CAUSE.get(projet)
    if cause:
        for tag, _v in _variants(root, path):
            text = edit_results[(rid, tag, "claude")][1]
            assert "ignor" in text and cause in text, f"claude/{tag}: la ligne ignorée n'est pas comptée ({text!r})"
            for host in PY_HOSTS:
                text = edit_results[(rid, tag, host)][1]
                assert "ignor" in text and cause in text, f"{host}/{tag}: la ligne ignorée n'est pas comptée"


@pytest.mark.parametrize("rid,target,exp_c,exp_j,exp_h", REDIR_ROWS, ids=[r[0] for r in REDIR_ROWS])
def test_table_redirection_colonne_post(banc, rid, target, exp_c, exp_j, exp_h):
    root = banc.projets["base"]
    full = f"{banc.dehors}/{target}"
    cmd = f"printf y > {full}"
    got = {"claude": banc.redir_claude(root, cmd)}
    for host in PY_HOSTS:
        got[f"{host}/judge"] = banc.judge_redirect(root, host, full)
        got[f"{host}/hook"] = banc.redir_py_hook(root, host, cmd)
    want = {"claude": exp_c}
    for host in PY_HOSTS:
        want[f"{host}/judge"] = exp_j
        want[f"{host}/hook"] = exp_h
    assert got == want, target


@pytest.mark.parametrize("rid,cmd,exp_c,exp_h", NAME_ROWS, ids=[r[0] for r in NAME_ROWS])
def test_regle_du_nom_colonne_post(banc, rid, cmd, exp_c, exp_h):
    root = banc.projets["base"]
    cmd = cmd.format(d=banc.dehors)
    got = {"claude": banc.redir_claude(root, cmd)}
    for host in PY_HOSTS:
        got[host] = banc.redir_py_hook(root, host, cmd)
    want = {"claude": exp_c, **{h: exp_h for h in PY_HOSTS}}
    assert got == want, cmd


# ---------------------------------------------------------------------------
# Sans python (Claude seul) : shims `python3`/`python`/`py` exit 127 en tête de
# PATH — la technique de safe-bash.test.sh (j). Trois bras.
# ---------------------------------------------------------------------------
def _sans_python_path(banc) -> str:
    stub = banc.tmp / "stub-127"
    if not stub.exists():
        stub.mkdir()
        for c in ("python3", "python", "py"):
            s = stub / c
            s.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
            s.chmod(s.stat().st_mode | stat.S_IEXEC)
    return f"{stub}{os.pathsep}{os.environ.get('PATH', '')}"


def test_sans_python_arme_refuse_tout(banc):
    verdict, err = banc.edit_claude(banc.projets["kiton"], "README.md", path_env=_sans_python_path(banc))
    assert verdict.startswith("2/"), (verdict, err)
    assert "KIT_CODE_PROTEGE" in err, err
    assert err.count("PYTHON 3 NOT FOUND") == 1, "le diagnostic historique doit rester unique"


def test_sans_python_desarme_laisse_passer(banc):
    verdict, err = banc.edit_claude(banc.projets["kitoff"], "README.md", path_env=_sans_python_path(banc))
    assert verdict == "0", (verdict, err)


def test_lecture_rognee_ne_depend_pas_de_l_environnement(banc):
    """security-code-review sur 14fc95b5, HIGH 1 : `NT_FOLD` lit `NT_DOTS` dans
    l'environnement, et seuls les appels de la lecture « points » l'épinglaient.
    Mesuré avant correctif, `NT_DOTS=1` AMBIANT : les chemins que seule la
    lecture rognée refuse rendaient 0 — la lecture rognée devenait une seconde
    lecture « points ». Chaque appel épingle désormais sa lecture ; `NT_DOTS=1`
    injecté dans l'environnement du banc ne change aucun verdict."""
    got = {}
    for projet, path in (("base", G + ".. /KICKOFF_REQUIRED"),
                         ("base", G + ".../KICKOFF_REQUIRED"),
                         ("base", G + "z/.. /KICKOFF_REQUIRED"),
                         ("lien", "lnk/.. /KICKOFF_REQUIRED"),
                         ("lien", "lnk/z/.. /KICKOFF_REQUIRED"),
                         ("base", "x/.. /docs/y.md")):
        for amb in ("1", ""):
            got[(path, amb)] = banc.edit_claude(banc.projets[projet], path,
                                                extra_env={"NT_DOTS": amb})[0]
    want = {k: ("0" if k[0] == "x/.. /docs/y.md" else "2/" + KA) for k in got}
    assert got == want, got


def test_python_arme_readme_passe(banc):
    verdict, err = banc.edit_claude(banc.projets["kiton"], "README.md")
    assert verdict == "0", (verdict, err)


def test_traceback_de_la_fermeture_citee(banc):
    """Binôme de clôture sur 119f81e5 : `2>/dev/null` jetait la traceback de la
    fermeture, et le refus `formes-illisibles` ne disait pas POURQUOI. Fermeture
    cassée (`BORNE = 5)`) : le refus cite la DERNIÈRE ligne de python, capturée
    au rejeu dans la seule branche de refus (un `mktemp` coûtait +10 à +13 ms
    sur chaque Edit)."""
    root = _pf_projet(banc, "pf-traceback")
    hook = root / ".claude" / "hooks" / "protect-paths.sh"
    texte = hook.read_text(encoding="utf-8")
    assert texte.count("\nBORNE = 5\n") == 1
    hook.write_text(texte.replace("\nBORNE = 5\n", "\nBORNE = 5)\n"), encoding="utf-8")
    verdict, err = banc.edit_claude(root, "docs/x.md")
    assert verdict == "2/formes-illisibles", (verdict, err)
    assert "python : SyntaxError" in err, err


def _charge_claude(banc, root: Path, charge: str, extra_env: dict | None = None) -> str:
    """Le hook Claude nourri d'une charge BRUTE (texte arbitraire), verdict comme `edit_claude`."""
    ev = banc._events()
    env = {**banc.env, "CLAUDE_PROJECT_DIR": str(root), "AGENTS_EVENTS_DIR": str(ev), **(extra_env or {})}
    p = subprocess.run([BASH, str(root / ".claude/hooks/protect-paths.sh")], input=charge.encode("utf-8"),
                       capture_output=True, env=env, timeout=60)
    deny = banc._rules(ev, "hook.deny")
    return "0" if p.returncode == 0 else f"{p.returncode}/{deny[-1] if deny else '?'}"


def test_extraction_de_la_charge_en_octets(banc):
    """Binôme de clôture sur 119f81e5 : l'extraction de `$FILE` lisait `sys.stdin`
    et écrivait par `print` — sous `PYTHONIOENCODING=ascii`, `docs/é/.env` faisait
    lever `print`, `$FILE` restait vide et le hook sortait 0 en silence (mesuré).
    Lue et écrite en octets, et une extraction en ÉCHEC (python présent) est un
    refus nommé `charge-illisible`. Deux régimes gardés : charge sans `file_path`
    (dont `NotebookEdit`, qui écrit par `notebook_path`) → 0, inchangé ; python
    ABSENT → `test_sans_python_*`. Sur 376 charges réelles et synthétisées
    (Edit, Write, MultiEdit, NotebookEdit), 0 sur-refus mesuré le 2026-09-27."""
    root = banc.projets["base"]
    ascii_ = {"PYTHONIOENCODING": "ascii"}
    got = {
        "é-env-ascii": _charge_claude(banc, root, json.dumps({"tool_input": {"file_path": "docs/é/.env"}}), ascii_),
        "é-env": _charge_claude(banc, root, json.dumps({"tool_input": {"file_path": "docs/é/.env"}})),
        "é-md-ascii": _charge_claude(banc, root, json.dumps({"tool_input": {"file_path": "docs/é/x.md"}}), ascii_),
        "pas-du-json": _charge_claude(banc, root, "pas du json"),
        "tool-input-liste": _charge_claude(banc, root, '{"tool_input": [1]}'),
        "sans-file-path": _charge_claude(banc, root, '{"tool_name": "Edit", "tool_input": {}}'),
        "notebook": _charge_claude(banc, root, json.dumps(
            {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "docs/n.ipynb", "new_source": "x"}})),
    }
    assert got == {"é-env-ascii": "2/.env", "é-env": "2/.env", "é-md-ascii": "0",
                   "pas-du-json": "2/charge-illisible", "tool-input-liste": "2/charge-illisible",
                   "sans-file-path": "0", "notebook": "0"}, got


# ---------------------------------------------------------------------------
# R1 : la fermeture en ÉCHEC (python PRÉSENT, programme planté) — shim
# `python3` qui refuse tout programme portant le pli (`def f(p`). Brut et LC
# restent jugés par bash et gardent le nom de leur règle ; TOUT le reste est
# REFUSÉ `formes-illisibles` (binôme de clôture sur ae45e199, F1 : « ensemble
# sauté » laissait passer `z/../<marqueur>` et l'alias Win32, rc 0 mesuré).
# Python ABSENT est un autre régime, épinglé par `test_sans_python_*`.
# ---------------------------------------------------------------------------
def test_file_nt_vide_brut_et_lc_restent_juges(banc):
    stub = banc.tmp / "stub-ntfail"
    stub.mkdir(exist_ok=True)
    real = sys.executable
    shim = stub / "python3"
    shim.write_text(
        f"#!{real}\n"
        "import os, sys\n"
        "if len(sys.argv) > 2 and sys.argv[1] == '-c' and 'def f(p' in sys.argv[2]:\n"
        "    sys.exit(1)\n"
        f"os.execv({real!r}, [{real!r}] + sys.argv[1:])\n",
        encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    path_env = f"{stub}{os.pathsep}{os.environ.get('PATH', '')}"
    root = banc.projets["base"]
    got = {p: banc.edit_claude(root, p, path_env=path_env)[0]
           for p in ("docs/a:SECRET.md", "x.env.EXAMPLE", ".codex\\config.toml", G + A + ".",
                     G + "z/../KICKOFF_REQUIRED", "docs/x.md")}
    got["a\\b\\x.py"] = banc.edit_claude(banc.projets["extbs"], "a\\b\\x.py", path_env=path_env)[0]
    assert got == {
        "a\\b\\x.py": "2/a\\b\\",  # passe BRUTE seule
        "docs/a:SECRET.md": "2/" + CRED,       # passe LC
        "x.env.EXAMPLE": "2/formes-illisibles",  # gabarit sans casse : seule la fermeture refuse
        ".codex\\config.toml": "2/" + MCP,     # passe LC (antislash replié)
        # L'ANCIEN TROU ÉPINGLÉ, FERMÉ (fail-closed) : l'alias Win32 du marqueur,
        # le `..` physique, et même un fichier ordinaire — la fermeture n'a rien lu.
        G + A + ".": "2/formes-illisibles",
        G + "z/../KICKOFF_REQUIRED": "2/formes-illisibles",
        "docs/x.md": "2/formes-illisibles",
    }, got


# ---------------------------------------------------------------------------
# kit_code_guard.py SEUL, par sa CLI, un seul candidat brut (finding 2) : la
# garde ne doit pas dépendre du zèle de son appelant pour résoudre un lien.
# L'octroi est comparé sur la forme RÉSOLUE — un octroi `lnkhooks/` est hors
# ensemble, un octroi `.claude/hooks/` couvre `lnkhooks/x.sh`.
# ---------------------------------------------------------------------------
def _kit_cli(root: Path, candidate: str, env: dict) -> int:
    guard = ROOT / ".agents" / "bin" / "kit_code_guard.py"
    return subprocess.run([sys.executable, "-B", str(guard), "--root", str(root), "--", candidate],
                          capture_output=True, text=True, env=env, cwd=str(root)).returncode


def test_kit_code_guard_resout_les_liens(banc):
    root = banc.tmp / "kitcli"
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".agents" / "state" / "gates").mkdir(parents=True)
    os.symlink(".claude/hooks", root / "lnkhooks")
    os.symlink("docs", root / "lnkdocs")
    got = {c: _kit_cli(root, c, banc.env) for c in ("lnkhooks/x.sh", "lnkdocs/x.md", f"{root}/lnkhooks/x.sh")}
    grant = root / ".agents" / "state" / "gates" / "KIT_CODE_AUTORISE"
    grant.write_text(".claude/hooks/ T-00000763 2099-01-01T00:00Z\n", encoding="utf-8")
    got["octroi-resolu"] = _kit_cli(root, "lnkhooks/x.sh", banc.env)
    grant.write_text("lnkhooks/ T-00000763 2099-01-01T00:00Z\n", encoding="utf-8")
    got["octroi-sur-le-lien"] = _kit_cli(root, "lnkhooks/x.sh", banc.env)
    grant.unlink()
    # UN APPELANT PARTIEL (exec-critic sur fdc7cd75, M1) : la garde ne reçoit que
    # la forme BRUTE, et un pli y révèle un lien (`z/.../lnkhooks`, `lnkhooks.`).
    # Seul `canonical_forms` du kit — pli PUIS résolution — les ramène à
    # `.claude/hooks/x.sh` : son mutant « return candidates, True » rendait 0
    # ici et laissait toute la suite verte. Contrôle : le même détour vers `docs/`.
    (root / "z").mkdir()
    for c in ("z/.../lnkhooks/x.sh", "z/..:s/lnkhooks/x.sh", "lnkhooks./x.sh", "z/.../lnkdocs/x.md"):
        got[f"partiel {c}"] = _kit_cli(root, c, banc.env)
    # Un `..` que le PLI fait naître (`..:s` est un flux ADS de `..` sous le
    # modèle NT) : `realpath` y voit un nom ordinaire, seule la renormalisation
    # APRÈS le pli le résout. Contrôle : le même détour vers `docs/` reste à 0.
    got["pli-dotdot"] = _kit_cli(root, "x/..:s/.claude/hooks/y.sh", banc.env)
    got["pli-dotdot-hors"] = _kit_cli(root, "x/..:s/docs/y.md", banc.env)
    # LES DEUX FORMES (exec-critic, constat 2). `lnksub -> docs/sub` : un `..`
    # après le lien vaut `.claude/hooks/x.sh` LEXICALEMENT, `docs/.claude/…`
    # PHYSIQUEMENT — la forme lexicale suffit à refuser. `.agents/bin/lnkhs ->
    # ../../.claude/hooks/sub` : `.agents/bin/lnkhs/../y.sh` vaut
    # `.agents/bin/y.sh` lexicalement et `.claude/hooks/y.sh` physiquement, deux
    # formes DANS l'ensemble — un octroi ne vaut que s'il couvre les deux.
    (root / "docs" / "sub").mkdir()
    os.symlink("docs/sub", root / "lnksub")
    (root / ".agents" / "bin").mkdir(parents=True)
    (root / ".claude" / "hooks" / "sub").mkdir()
    os.symlink("../../.claude/hooks/sub", root / ".agents" / "bin" / "lnkhs")
    got["lexical-seule"] = _kit_cli(root, "lnksub/../.claude/hooks/x.sh", banc.env)
    got["deux-formes-sans-octroi"] = _kit_cli(root, ".agents/bin/lnkhs/../y.sh", banc.env)
    for nom, lignes in (("octroi-lexical-seul", ".agents/bin/"),
                        ("octroi-physique-seul", ".claude/hooks/"),
                        ("octroi-les-deux", ".agents/bin/\n.claude/hooks/")):
        grant.write_text("".join(f"{g} T-00000763 2099-01-01T00:00Z\n" for g in lignes.split("\n")),
                         encoding="utf-8")
        got[nom] = _kit_cli(root, ".agents/bin/lnkhs/../y.sh", banc.env)
    grant.write_text(".claude/hooks/ T-00000763 2099-01-01T00:00Z\n", encoding="utf-8")
    got["octroi-lexical-couvert"] = _kit_cli(root, "lnksub/../.claude/hooks/x.sh", banc.env)
    assert got == {"lnkhooks/x.sh": 2, "lnkdocs/x.md": 0, f"{root}/lnkhooks/x.sh": 2,
                   "octroi-resolu": 3, "octroi-sur-le-lien": 2,
                   "partiel z/.../lnkhooks/x.sh": 2, "partiel z/..:s/lnkhooks/x.sh": 2,
                   "partiel lnkhooks./x.sh": 2, "partiel z/.../lnkdocs/x.md": 0,
                   "pli-dotdot": 2, "pli-dotdot-hors": 0,
                   "lexical-seule": 2, "deux-formes-sans-octroi": 2,
                   "octroi-lexical-seul": 2, "octroi-physique-seul": 2, "octroi-les-deux": 3,
                   "octroi-lexical-couvert": 3}, got


# ---------------------------------------------------------------------------
# Les six lignes `permissions.deny`.
# ---------------------------------------------------------------------------
def test_six_lignes_edit_deny():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    missing = [line for line in DENY_LINES if line not in deny]
    assert missing == [], missing


# ---------------------------------------------------------------------------
# T-00001090 : le frère safe_bash_git.py est aussi OBLIGATOIRE que _common.py.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("host", PY_HOSTS)
def test_import_du_frere_git_direct_sans_repli(host):
    """Un repli (try/except ImportError) autour de l'import du frère ouvrirait toute la garde git
    en silence quand le frère manque : `git reset --hard` passerait (mutant E4, mesuré). Exactement
    UN `from safe_bash_git import …`, enfant DIRECT du module, avec ses noms EXACTS (les étages 0.5 et 1 y
    vivent depuis T-01M5D6XV3J ; T-01M5C1AF6GB3ZRX5QF9SF6R80Y y ajoute `hooks_refusal` et
    `BRANCH_FORCE_REASON`) ; aucun sous un try."""
    tree = ast.parse((ROOT / host / "hooks" / "safe_bash.py").read_text(encoding="utf-8"))
    essais = (ast.Try, getattr(ast, "TryStar", ast.Try))

    def du_frere(node):
        return isinstance(node, ast.ImportFrom) and node.module == "safe_bash_git"

    directs = [n for n in tree.body if du_frere(n)]
    assert len(directs) == 1 and len([n for n in ast.walk(tree) if du_frere(n)]) == 1, directs
    assert {a.name for a in directs[0].names} == {"BRANCH_FORCE_REASON", "ENVELOPES", "_ANSI_UNREAD",
                                                  "_EXPANSION_MARK", "_GIT_GLOBAL_VALUE", "_long_option",
                                                  "alias_assignment", "expand_braces", "hooks_refusal",
                                                  "judge_git", "quoted_spans", "read_ansi", "strip_heredoc_bodies"}
    sous_essai = [n for t in ast.walk(tree) if isinstance(t, essais) for n in ast.walk(t) if du_frere(n)]
    assert sous_essai == [], sous_essai


# ---------------------------------------------------------------------------
# Le différentiel des QUATRE copies du pli : `NT_FOLD` (protect-paths.sh),
# `_nt_fold` ×2 (protect_paths.py), `ntf` (snippet de safe-bash.sh).
# ---------------------------------------------------------------------------
def _nt_fold_sh() -> str:
    text = (ROOT / ".claude" / "hooks" / "protect-paths.sh").read_text(encoding="utf-8")
    m = re.search(r"^NT_FOLD='(.*?)'$", text, re.M | re.S)
    assert m, "NT_FOLD absent de protect-paths.sh"
    return m.group(1)


def _ntf_safe_bash():
    text = (ROOT / ".claude" / "hooks" / "safe-bash.sh").read_text(encoding="utf-8")
    m = re.search(r"^def ntf\(p, dots=False\):\n(?:(?:    .*)?\n)+", text, re.M)
    assert m, "ntf(p, dots=False) absent du snippet de safe-bash.sh"
    ns: dict = {}
    exec(m.group(0), ns)  # noqa: S102 — texte du dépôt, extrait pour le différentiel
    return ns["ntf"]


def _nt_fold_py(host: str, cases, dots: bool):
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import protect_paths as p; "
            "d = sys.argv[2] == '1'; "
            "print(json.dumps([p._nt_fold(x, d) for x in json.loads(sys.stdin.read())]))")
    r = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / host / "hooks"), "1" if dots else "0"],
                       input=json.dumps([c for c, _ in cases]), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _nt_fold_kit(cases, dots: bool):
    code = ("import sys, json, importlib.util; "
            "s = importlib.util.spec_from_file_location('_kcg', sys.argv[1]); "
            "m = importlib.util.module_from_spec(s); sys.modules['_kcg'] = m; s.loader.exec_module(m); "
            "d = sys.argv[2] == '1'; "
            "print(json.dumps([m.nt_fold(x, d) for x in json.loads(sys.stdin.read())]))")
    r = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / ".agents" / "bin" / "kit_code_guard.py"),
                        "1" if dots else "0"],
                       input=json.dumps([c for c, _ in cases]), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("dots", [False, True], ids=["lecture-rognee", "lecture-points"])
def test_differentiel_enumere_des_plis(dots):
    """Les CINQ copies du pli — `NT_FOLD` (sh, `NT_DOTS=1` pour la lecture
    points), `ntf` (safe-bash), `_nt_fold` ×2, `nt_fold` de kit_code_guard —
    rendent la sortie ATTENDUE en clair, pour les deux lectures."""
    cases = NT_DOTS_CASES if dots else NT_CASES
    programme = _nt_fold_sh()
    assert "'" not in programme, "le programme NT_FOLD ne doit porter aucune apostrophe"
    env = {**os.environ, "NT_DOTS": "1" if dots else ""}
    sh = []
    for entree, _ in cases:
        r = subprocess.run([sys.executable, "-c", programme], input=entree.encode("utf-8"),
                           capture_output=True, env=env)
        assert r.returncode == 0, r.stderr
        sh.append(r.stdout.decode("utf-8"))
    ntf = _ntf_safe_bash()
    copies = {
        "protect-paths.sh NT_FOLD": sh,
        "safe-bash.sh ntf": [ntf(e, dots) for e, _ in cases],
        ".codex _nt_fold": _nt_fold_py(".codex", cases, dots),
        ".gemini _nt_fold": _nt_fold_py(".gemini", cases, dots),
        "kit_code_guard nt_fold": _nt_fold_kit(cases, dots),
    }
    for nom, sortie in copies.items():
        ecarts = [(e, o, w) for (e, w), o in zip(cases, sortie) if o != w]
        assert ecarts == [], f"{nom} : {ecarts}"
    assert len(cases) >= (20 if not dots else 12)


# ---------------------------------------------------------------------------
# LE POINT FIXE DES FORMES CANONIQUES (T-00000722 ; revue du lot T-00000721,
# HIGH « pli avant résolution »). La liste FIXE des formes jugées — brute,
# minuscule, pliée rognée/points, renormalisée, résolue — n'était pas CLOSE :
# une forme obtenue par PLI pouvait encore porter un lien symbolique que rien ne
# résolvait, la résolution physique n'étant appliquée qu'à la forme brute.
# `ln -s <cible protégée> nom_neutre` puis `Edit z/.../nom_neutre` : rc 0 sur
# les trois hôtes. Chaque garde calcule désormais l'ensemble COMPLET par point
# fixe borné (5 tours, refus nommé `formes-instables` au-delà).
#
# LE BANC EST GÉNÉRÉ, JAMAIS ÉCRIT À LA MAIN : 6 cibles × {lien vers le
# fichier, lien vers son dossier} × {aucun, 1, 2 jetons}, où un jeton est un
# DÉTOUR `z/<points|espaces|ADS>` posé AVANT ou APRÈS le lien, ou un SUFFIXE
# (point, espace, flux ADS) posé SUR le nom du lien — l'alias Win32 du lien
# lui-même. Les paires de k=2 tournent sur les jetons (j, j+1 mod n). Chaque
# forme désigne la cible sous le modèle NT du kit (lecture « points » : le
# détour vaut l'identité, le suffixe est rogné) ; son TÉMOIN est la même forme
# vers un fichier ordinaire (`tem*` → `docs/n<i>/`), et doit passer.
# Edit : relatif ET absolu, trois hôtes. Redirection : même générateur, jetons
# qu'un mot de shell NU peut porter (ni espace, ni `$`) — une cible citée est
# invisible à la clause de chemin par construction (T-00000720), hors banc.
# ---------------------------------------------------------------------------
PF_CIBLES = (
    (G + "KICKOFF_REQUIRED", KA),
    (G + "BINOME_REQUIRED", "binome-arming"),
    (G + "NIGHT_HEADLESS.allow", "night-headless"),
    (".claude/settings.local.json", "claude-settings-local"),
    (".git/config", GIT),
    ("src/legacy/y.ts", "src/legacy/"),
)
PF_DETOURS = ("...", ".. ", "..:s", ".. ::$DATA")
PF_SUFFIXES = (".", " ", "::$DATA", ". .")
PF_DETOURS_REDIR = ("...", "..:s", "....")
PF_SUFFIXES_REDIR = (".", "..", ":s")
PF_K1 = ("avant", "apres", "sur")
PF_K2 = (("avant", "avant"), ("avant", "apres"), ("apres", "apres"),
         ("avant", "sur"), ("sur", "apres"))
PF_CHAINE = 6  # maillons de la chaîne témoin de la borne
PF_INSTABLE = "formes-instables"
# Le témoin de la borne : `chaine1` (six liens) doit être REFUSÉ `formes-instables` ;
# `courte1` et ses ALIAS (exec-critic sur fdc7cd75, M2) visent un fichier
# ordinaire et doivent PASSER — les alias ne se stabilisent qu'au 5e tour, donc
# une borne à 4 les faux-refusait. La redirection ne porte que les formes sans espace.
PF_BORNE = ("chaine1", "courte1", "courte1.", "COURTE1 ", "z/.../courte1")


def _pf_chemin(lien, base, plan, jetons, detours, suffixes):
    avant, apres, suffixe = [], [], ""
    for place, j in zip(plan, jetons):
        if place == "avant":
            avant.append("z/" + detours[j])
        elif place == "apres":
            apres.append("z/" + detours[j])
        else:
            suffixe = suffixes[j]
    return "/".join(avant + [lien + suffixe] + apres + ([base] if base else []))


def _pf_cas(detours, suffixes):
    """[(id, forme vers la cible, forme témoin, règle attendue)], déterministe."""
    n = len(detours)
    paires = [(j, (j + 1) % n) for j in range(n)]
    plans = ([((), ())] + [((p,), (j,)) for p in PF_K1 for j in range(n)]
             + [(pp, pr) for pp in PF_K2 for pr in paires])
    cas = []
    for i, (cible, regle) in enumerate(PF_CIBLES):
        nom = cible.rsplit("/", 1)[-1]
        for g in ("f", "d"):
            base_c, base_t = (nom, "note.md") if g == "d" else ("", "")
            for plan, jetons in plans:
                cid = f"{i}{g}-{'+'.join(plan) or 'nu'}-{''.join(map(str, jetons))}"
                cas.append((cid,
                            _pf_chemin(f"lien{g}{i}", base_c, plan, jetons, detours, suffixes),
                            _pf_chemin(f"tem{g}{i}", base_t, plan, jetons, detours, suffixes),
                            regle))
    return cas


PF_EDIT = _pf_cas(PF_DETOURS, PF_SUFFIXES)
PF_REDIR = _pf_cas(PF_DETOURS_REDIR, PF_SUFFIXES_REDIR)
# La garde kit-code REÇOIT l'ensemble : un détour ou un suffixe devant un lien
# vers `.claude/hooks` (armé) — refusé sans octroi, octroyé sous `.claude/hooks/`.
PF_KIT = (tuple(("z/" + t + "/lnkhooks/x.sh", "z/" + t + "/lnkdocs/x.md") for t in PF_DETOURS)
          + tuple(("lnkhooks" + s + "/x.sh", "lnkdocs" + s + "/x.md") for s in PF_SUFFIXES))


def _pf_projet(banc, nom, marker=False, octroi=None) -> Path:
    root = banc.tmp / nom
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel in COPIED:
        src = _source(rel)
        if src.exists():
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
    (root / "z").mkdir()
    gates = root / ".agents" / "state" / "gates"
    if marker:
        gates.mkdir(parents=True, exist_ok=True)
        (gates / "KIT_CODE_PROTEGE").write_text("", encoding="utf-8")
    if octroi is not None:
        (gates / "KIT_CODE_AUTORISE").write_text(octroi, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def pf(banc):
    """Tous les verdicts du banc du point fixe, calculés une fois, en parallèle."""
    return TestPointFixeFormes.calculer(banc)


class TestPointFixeFormes:
    """Toute forme qui désigne une cible protégée — après pli NTFS OU résolution
    de lien, dans n'importe quel ordre — est refusée sur les trois hôtes, en Edit
    et en redirection ; la même forme vers un fichier ordinaire passe ; une forme
    dont l'ensemble ne se stabilise pas en 5 tours est refusée, nommée."""

    @staticmethod
    def calculer(banc):
        root = _pf_projet(banc, "pointfixe")
        for i, (cible, _regle) in enumerate(PF_CIBLES):
            dossier = cible.rsplit("/", 1)[0]
            if not cible.startswith(".git/"):
                (root / dossier).mkdir(parents=True, exist_ok=True)
                (root / cible).write_text("", encoding="utf-8")
            (root / "docs" / f"n{i}").mkdir(parents=True)
            (root / "docs" / f"n{i}" / "note.md").write_text("", encoding="utf-8")
            os.symlink(cible, root / f"lienf{i}")
            os.symlink(dossier, root / f"liend{i}")
            os.symlink(f"docs/n{i}/note.md", root / f"temf{i}")
            os.symlink(f"docs/n{i}", root / f"temd{i}")
        # La chaîne qui ne se stabilise pas : chaque maillon vise `z/.../<suivant>`,
        # et seul un pli PUIS une résolution avancent d'un maillon (deux tours).
        for k in range(1, PF_CHAINE):
            os.symlink(f"z/.../chaine{k + 1}", root / f"chaine{k}")
        os.symlink("docs/n0/note.md", root / f"chaine{PF_CHAINE}")
        # Son témoin court : un seul maillon, stable dans la borne, doit passer.
        os.symlink("z/.../courte2", root / "courte1")
        os.symlink("docs/n0/note.md", root / "courte2")
        # UNE CHAÎNE DE QUATRE LIENS vers un fichier ordinaire, un dossier par
        # maillon, atteinte par un chemin absolu dont la RACINE est en majuscules
        # (binôme de clôture sur ae45e199, F4 : l'échantillon « chemins suivis »
        # ne portait aucun lien). Mesuré : 4 tours sur 5 sur un FS insensible à
        # la casse (macOS) ; sous Linux la racine en majuscules n'existe pas et ce
        # chemin ne désigne rien — il passe alors par absence. Doit passer.
        for lien, cible in (("quatre1", "A/quatre2"), ("A/quatre2", "../B/quatre3"),
                            ("B/quatre3", "../C/quatre4"), ("C/quatre4", "../docs/n0/note.md")):
            (root / lien).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(cible, root / lien)
        maj = f"{str(root).upper()}/quatre1"
        kits = {}
        for nom, octroi in (("pfkit", None), ("pfkitoct", ".claude/hooks/ T-00000722 2099-01-01T00:00Z\n")):
            kr = _pf_projet(banc, nom, marker=True, octroi=octroi)
            (kr / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
            (kr / "docs").mkdir()
            os.symlink(".claude/hooks", kr / "lnkhooks")
            os.symlink("docs", kr / "lnkdocs")
            kits[nom] = kr
        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            def edit(r, key, chemin):
                for tag, v in _variants(r, chemin):
                    jobs[key + (tag, "claude")] = ex.submit(banc.edit_claude, r, v)
                    for host in PY_HOSTS:
                        jobs[key + (tag, host)] = ex.submit(banc.edit_py, r, host, v)

            def redir(r, key, chemin):
                cmd = "printf y > " + chemin
                jobs[key + ("claude",)] = ex.submit(banc.redir_claude, r, cmd)
                for host in PY_HOSTS:
                    jobs[key + (host,)] = ex.submit(banc.redir_py_hook, r, host, cmd)

            for cid, cible, temoin, _regle in PF_EDIT:
                edit(root, ("edit", cid, "cible"), cible)
                edit(root, ("edit", cid, "temoin"), temoin)
            for cid, cible, temoin, _regle in PF_REDIR:
                redir(root, ("redir", cid, "cible"), cible)
                redir(root, ("redir", cid, "temoin"), temoin)
            for chemin in PF_BORNE:
                edit(root, ("borne", chemin), chemin)
                if " " not in chemin:
                    redir(root, ("borne-redir", chemin), chemin)
            jobs[("borne-maj", "claude")] = ex.submit(banc.edit_claude, root, maj)
            for host in PY_HOSTS:
                jobs[("borne-maj", host)] = ex.submit(banc.edit_py, root, host, maj)
            redir(root, ("borne-maj-redir",), maj)
            for k, (cible, temoin) in enumerate(PF_KIT):
                for nom, kr in kits.items():
                    edit(kr, (nom, k, "cible"), cible)
                    edit(kr, (nom, k, "temoin"), temoin)
            return {k: f.result() for k, f in jobs.items()}

    @staticmethod
    def _ecarts_edit(pf, cas, quoi, attendu):
        ecarts = []
        for cid, _cible, _temoin, regle in cas:
            for tag in ("rel", "abs"):
                for host in ("claude",) + PY_HOSTS:
                    got = pf[("edit", cid, quoi, tag, host)][0]
                    if got != attendu(regle, host):
                        ecarts.append(f"{cid}/{tag}/{host}={got}")
        return ecarts

    @staticmethod
    def _ecarts_redir(pf, quoi, rc, py):
        ecarts = []
        for cid, _cible, _temoin, _regle in PF_REDIR:
            got = {"claude": pf[("redir", cid, quoi, "claude")],
                   **{h: pf[("redir", cid, quoi, h)] for h in PY_HOSTS}}
            want = {"claude": rc, **{h: py for h in PY_HOSTS}}
            ecarts += [f"{cid}/{h}={got[h]}" for h in got if got[h] != want[h]]
        return ecarts

    def test_decompte_du_produit(self):
        assert (len(PF_EDIT), len(PF_REDIR), len(PF_KIT)) == (396, 300, 8)
        assert len({c for c, *_ in PF_EDIT}) == len(PF_EDIT)
        assert len({c for c, *_ in PF_REDIR}) == len(PF_REDIR)

    def test_edit_forme_vers_la_cible_refusee(self, pf):
        ecarts = self._ecarts_edit(pf, PF_EDIT, "cible",
                                   lambda regle, host: ("2/" + regle) if host == "claude" else regle)
        assert ecarts == [], f"{len(ecarts)} écart(s) : {ecarts}"

    def test_edit_temoin_passe(self, pf):
        ecarts = self._ecarts_edit(pf, PF_EDIT, "temoin", lambda _regle, _host: "0")
        assert ecarts == [], f"{len(ecarts)} écart(s) : {ecarts}"

    def test_redirection_forme_vers_la_cible_refusee(self, pf):
        ecarts = self._ecarts_redir(pf, "cible", 2, "deny")
        assert ecarts == [], f"{len(ecarts)} écart(s) : {ecarts}"

    def test_redirection_temoin_passe(self, pf):
        ecarts = self._ecarts_redir(pf, "temoin", 0, "pass")
        assert ecarts == [], f"{len(ecarts)} écart(s) : {ecarts}"

    def test_borne_atteinte_refus_nomme(self, pf):
        got = {}
        for chemin in PF_BORNE:
            for tag in ("rel", "abs"):
                for host in ("claude",) + PY_HOSTS:
                    got[(chemin, tag, host)] = pf[("borne", chemin, tag, host)][0]
            if " " in chemin:
                continue
            for host in ("claude",) + PY_HOSTS:
                got[(chemin, "redir", host)] = pf[("borne-redir", chemin, host)]
        # La chaîne de quatre liens, racine en MAJUSCULES : un fichier ordinaire (F4).
        for host in ("claude",) + PY_HOSTS:
            got[("quatre1-racine-maj", "abs", host)] = pf[("borne-maj", host)][0]
            got[("quatre1-racine-maj", "redir", host)] = pf[("borne-maj-redir", host)]
        want = {}
        for (chemin, tag, host) in got:
            if tag == "redir":
                refus = 2 if host == "claude" else "deny"
                passe = 0 if host == "claude" else "pass"
            else:
                refus = ("2/" + PF_INSTABLE) if host == "claude" else PF_INSTABLE
                passe = "0"
            want[(chemin, tag, host)] = refus if chemin == "chaine1" else passe
        assert got == want

    def test_derniere_ligne_de_nt_fold(self, banc):
        """exec-critic sur fdc7cd75, m3, MESURÉ : la dernière ligne de `NT_FOLD`
        SUPPRIMÉE, rien n'est coupé et la fermeture reste juste ; MODIFIÉE sans
        plus porter `$PP_COUPE`, elle s'exécute et consomme STDIN — la fermeture
        rendait alors `OK` sans aucune forme. État `VIDE` : refus nommé."""
        texte = (ROOT / ".claude" / "hooks" / "protect-paths.sh").read_text(encoding="utf-8")
        ligne = re.search(r"^sys\.stdout\.buffer\.write\(f\(.*'$", texte, re.M)
        assert ligne, "dernière ligne de NT_FOLD introuvable"
        modifiee = (ligne.group(0).replace("sys.stdout.buffer.write(", "sys.stdout.write(", 1)
                    .replace('.encode("utf-8", "surrogateescape"))' + "'", ")'"))
        got = {}
        for nom, remplacement in (("supprimee", "'"), ("modifiee", modifiee)):
            root = _pf_projet(banc, f"pfnt-{nom}")
            hook = root / ".claude" / "hooks" / "protect-paths.sh"
            hook.write_text(texte.replace(ligne.group(0), remplacement, 1), encoding="utf-8")
            for chemin in ("docs/x.md", G + "z/.../KICKOFF_REQUIRED"):
                got[(nom, chemin)] = banc.edit_claude(root, chemin)[0]
        assert got == {("supprimee", "docs/x.md"): "0",
                       ("supprimee", G + "z/.../KICKOFF_REQUIRED"): "2/" + KA,
                       ("modifiee", "docs/x.md"): "2/formes-illisibles",
                       ("modifiee", G + "z/.../KICKOFF_REQUIRED"): "2/formes-illisibles"}, got

    def test_kit_code_recoit_l_ensemble(self, pf):
        ecarts = []
        for k in range(len(PF_KIT)):
            for nom, quoi, attendu_c, attendu_p in (("pfkit", "cible", "2/" + KIT, KIT),
                                                    ("pfkit", "temoin", "0", "0"),
                                                    ("pfkitoct", "cible", "0+warn", "0+warn"),
                                                    ("pfkitoct", "temoin", "0", "0")):
                for tag in ("rel", "abs"):
                    for host in ("claude",) + PY_HOSTS:
                        got = pf[(nom, k, quoi, tag, host)][0]
                        want = attendu_c if host == "claude" else attendu_p
                        if got != want:
                            ecarts.append(f"{nom}/{k}/{quoi}/{tag}/{host}={got}")
        assert ecarts == [], f"{len(ecarts)} écart(s) : {ecarts}"


# ---------------------------------------------------------------------------
# LES ORTHOGRAPHES WINDOWS DE LA RACINE (security-code-review sur fdc7cd75,
# angle mort Windows). Sous Git Bash la racine arrive en `/c/…` (cygpath) quand
# `realpath` rend `C:/…` : sans les formes à lettre de lecteur, un chemin sous
# la racine restait ABSOLU (règles de préfixe aveugles, un tour de retard sur la
# borne). Test UNITAIRE PUR de `relativiser` — aucun système de fichiers
# Windows, les racines choisies n'existent pas ici — sur les QUATRE copies. Le
# runtime Windows, lui, reste NON mesuré.
# ---------------------------------------------------------------------------
RELATIVISER_CAS = (
    ("/c/Users/user", "C:/Users/user/docs/x.md", "docs/x.md"),
    ("/c/Users/user", "c:/users/user/.agents/state/gates/kickoff_required",
     ".agents/state/gates/kickoff_required"),
    ("/c/Users/user", "C:/Users/user", "."),
    ("C:/Users/user", "/c/Users/user/src/legacy/y.ts", "src/legacy/y.ts"),
    ("C:\\Users\\user", "C:/Users/user/src/legacy/y.ts", "src/legacy/y.ts"),
    ("/c/Users/user", "D:/autre/x", "D:/autre/x"),
    ("/c/Users/user", "C:/Users/users/x", "C:/Users/users/x"),
    ("/cdrom/r", "c:drom/r/x", "c:drom/r/x"),
    ("/Users/user/p", "/Users/user/p/docs/x", "docs/x"),
)


def _relativiser_sh():
    texte = (ROOT / ".claude" / "hooks" / "protect-paths.sh").read_text(encoding="utf-8")
    nt = _nt_fold_sh()
    m = re.search(r"^PP_FERMETURE='(.*?)'$", texte, re.M | re.S)
    assert m, "PP_FERMETURE absent de protect-paths.sh"
    ns: dict = {}
    # noqa: S102 — texte du dépôt : le pli de NT_FOLD puis les définitions de la fermeture.
    exec(nt[:nt.index("sys.stdout.buffer.write")] + m.group(1)[:m.group(1).index("\nbrut = ")], ns)
    return lambda root, r: ns["relativiser"](r, ns["racines"](root))


def _relativiser_safe_bash():
    texte = (ROOT / ".claude" / "hooks" / "safe-bash.sh").read_text(encoding="utf-8")
    ns: dict = {"os": os, "ntf": _ntf_safe_bash()}
    for nom in ("lecteurs(r)", "racines(root)", "relativiser(r, rs)"):
        m = re.search(r"^def " + re.escape(nom) + r":\n(?:(?:    .*)?\n)+", texte, re.M)
        assert m, f"def {nom} absent du snippet de safe-bash.sh"
        exec(m.group(0), ns)  # noqa: S102 — texte du dépôt
    return lambda root, r: ns["relativiser"](r, ns["racines"](root))


def _relativiser_py(host: str):
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import protect_paths as p; "
            "print(json.dumps([p._relativiser(r, p._racines(root)) for root, r in json.loads(sys.stdin.read())]))")
    r = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / host / "hooks")],
                       input=json.dumps([[a, b] for a, b, _ in RELATIVISER_CAS]),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _relativiser_kit():
    """Le kit (binôme de clôture sur ae45e199, F2) : `_root_spellings` n'y
    ajoutait la lettre de lecteur que dans UNE casse (`c:` depuis `/c/`), donc
    `C:/Users/user/…` sous la racine `/c/Users/user` restait absolu."""
    s = importlib.util.spec_from_file_location("_kcg_rel", ROOT / ".agents" / "bin" / "kit_code_guard.py")
    m = importlib.util.module_from_spec(s)
    sys.modules[s.name] = m
    s.loader.exec_module(m)
    return lambda root, r: m._relativiser(r, m._root_spellings(root))


def test_relativiser_orthographes_windows():
    sh, sb, kit = _relativiser_sh(), _relativiser_safe_bash(), _relativiser_kit()
    copies = {
        "protect-paths.sh": [sh(root, r) for root, r, _ in RELATIVISER_CAS],
        "safe-bash.sh": [sb(root, r) for root, r, _ in RELATIVISER_CAS],
        ".codex": _relativiser_py(".codex"),
        ".gemini": _relativiser_py(".gemini"),
        "kit_code_guard": [kit(root, r) for root, r, _ in RELATIVISER_CAS],
    }
    for nom, sortie in copies.items():
        ecarts = [(root, r, o, w) for (root, r, w), o in zip(RELATIVISER_CAS, sortie) if o != w]
        assert ecarts == [], f"{nom} : {ecarts}"


# ---------------------------------------------------------------------------
# LA MARGE DE LA BORNE, AFFIRMÉE (binôme de clôture, second tour : critic-fable
# mesurait 5 = la borne, critic-opus 3, sur deux arbres différents — les deux
# rejoués, les deux vrais sous leurs conditions). Pour chaque forme, la borne
# MINIMALE à laquelle `canonical_forms` (code réel du jumeau `.codex`, identique
# octet pour octet à `.gemini`) est stable, en entrée brute (le hook sh) et
# normalisée (les hôtes Python). DEUX CLASSES SANS MARGE, mesurées à 5 : les
# formes d'un lien dont la cible porte un segment de points (`courte1`, ses
# alias, et `courte1` même sous la racine en majuscules), et les alias d'une
# chaîne dont les cibles sont ABSOLUES et épelées sous la racine en MAJUSCULES
# (`maj1.`). Tout le reste : au plus 4, un tour de marge. Une opération qui
# ajouterait un tour ferait rougir ce test AVANT de faire refuser un fichier
# ordinaire. INERTE SOUS LINUX (FS sensible à la casse : la racine en majuscules
# n'existe pas) — sauté, et c'est dit.
# ---------------------------------------------------------------------------
MARGE_CODE = (
    "import json, sys\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\n"
    "import protect_paths as pp, _common\nroot = sys.argv[2]\nborne = pp.FORMES_BORNE\n"
    "def tours(p):\n    for k in range(1, 13):\n        pp.FORMES_BORNE = k\n"
    "        if pp.canonical_forms(p, root)[1]:\n            return k\n    return None\n"
    "_common.ROOT = Path(root).resolve()\n"
    "print(json.dumps({'borne': borne, 'tours': [[tours(p), tours(_common.normalize_path(p))]"
    " for p in json.loads(sys.stdin.read())]}))\n")
MARGE_SANS = ("maj1.", "A/../maj1 ", "maj1::$DATA", "courte1", "courte1.", "COURTE1 ", "z/.../courte1")
MARGE_AVEC = ("maj1", "z/../maj1", "rel1", "rel1.", "A/../rel1 ")


def test_marge_de_la_borne(banc):
    root = banc.tmp / "Marge-Borne" / "Projet"
    root.mkdir(parents=True)
    if not os.path.exists(str(root).upper()):
        pytest.skip("FS sensible à la casse : la racine en majuscules n'existe pas — témoin inerte ici")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for d in ("A", "B", "z", "docs"):
        (root / d).mkdir()
    (root / "docs" / "note.md").write_text("", encoding="utf-8")
    maj = str(root).upper()
    for lien, cible in (("maj1", f"{maj}/A/maj2"), ("A/maj2", f"{maj}/B/maj3"), ("B/maj3", f"{maj}/docs/note.md"),
                        ("rel1", "A/rel2"), ("A/rel2", "../docs/note.md"),
                        ("courte1", "z/.../courte2"), ("courte2", "docs/note.md")):
        os.symlink(cible, root / lien)
    chemins = {}
    for groupe, formes in (("sans", MARGE_SANS), ("avec", MARGE_AVEC)):
        for rel in formes:
            for variante in (rel, f"{root}/{rel}", f"{maj}/{rel}", f"{str(root).lower()}/{rel}"):
                chemins[variante] = groupe
    r = subprocess.run([sys.executable, "-B", "-c", MARGE_CODE, str(ROOT / ".codex" / "hooks"), str(root)],
                       input=json.dumps(list(chemins)), capture_output=True, text=True, env=banc.env, timeout=120)
    assert r.returncode == 0, r.stderr
    sortie = json.loads(r.stdout)
    borne = sortie["borne"]
    mesures = {groupe: [] for groupe in ("sans", "avec")}
    for (chemin, groupe), (brut, norm) in zip(chemins.items(), sortie["tours"]):
        assert brut is not None and norm is not None, f"instable : {chemin!r}"
        mesures[groupe] += [brut, norm]
    assert (borne, max(mesures["sans"]), max(mesures["avec"])) == (5, 5, 4), (borne, mesures)
