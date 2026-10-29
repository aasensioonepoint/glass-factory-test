import importlib.util
import os
import posixpath
import re
import stat
import sys
from pathlib import Path

from _common import (BIN, GATES, ROOT, deny, emit_event, lecture_copilot, paths_from_payload, read_payload,
                     tool_args)


PROTECTED_PREFIXES = (
    "src/legacy/",
    "generated/",
)

# `id_rsa` rejoint la liste (T-00000721) : c'était le seul jeton que Claude
# refusait et que les quatre hôtes Python laissaient passer — la divergence 6 du
# banc de parité. Les listes sont désormais ALIGNÉES, jeton pour jeton, avec le
# bras credential de `protect-paths.sh`.
SECRET_NAMES = (
    ".env",
    "credentials",
    "credential",
    "secret",
    "private-key",
    "private_key",
    "id_rsa",
)

SECRET_EXTENSIONS = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
)

# Exception scoped to the `.env` rules ONLY. A committed template carries the
# NAMES of the variables and never their values, and it is precisely the file an
# agent must update when it adds a configuration variable — so the four
# recognized template suffixes are editable. A template is recognized BY ITS
# SUFFIX, never by intent: `.env`, `.env.local`, `.env.production` and anything
# else stay blocked.
#
# ON THE RISK, stated rather than used as a reason to refuse: if a project puts
# real values in a `.env.example`, this exception makes them editable — but they
# were already committed, hence already leaked and already to be rotated. A path
# guard cannot rattrap that; the class-0 gitleaks gate is what detects it, and it
# still scans whatever content lands on disk here.
#
# Parity with .claude/hooks/protect-paths.sh's is_env_template() is what makes
# this a guard rather than a false sense of one — asserted by
# .agents/evals/test_protected_paths_extension.py across the four hosts.
ENV_TEMPLATE_SUFFIXES = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
)

# MCP configuration is human-audited (.agents/ref/MCP_REGISTRY.md), never
# agent-writable. Token-matched like SECRET_NAMES; the two host settings
# files are matched by exact suffix (PROTECTED_PREFIXES-style).
MCP_CONFIG_NAMES = ("mcp.json",)

MCP_CONFIG_PATHS = (
    ".codex/config.toml",
    ".gemini/settings.json",
    # Copilot CLI repo settings (alignement des hotes, L-D, H-29) : `disableAllHooks`
    # eteindrait TOUTES les gardes de ce hote. Lecture reelle du fichier par Copilot
    # NON MESUREE (doc) — protege par precaution, comme les deux autres reglages d'hote.
    ".github/copilot/settings.json",
)

MCP_DENY_REASON = (
    "BLOCKED by protected-path hook: MCP configuration is human-audited — "
    "see .agents/ref/MCP_REGISTRY.md; agents may not write it."
)

# The kickoff guard's ARMING FILE (T-00000243). It is the SWITCH of that guard,
# so it must never be agent-writable: a lock whose key sits in the prisoner's
# pocket is no lock. This is exactly why the arming lives in a PATH rather than
# in a board field — a `tasks.py unharden` would have travelled through Bash,
# which no path guard covers, and the constrained agent could have freed itself.
#
# MATCHED ON A CASE-FOLDED, SEPARATOR-FOLDED COPY, and that is load-bearing
# rather than tidy: this kit's declared development platform is Windows/NTFS,
# where `.agents\state\gates\KICKOFF_REQUIRED`,
# `.AGENTS/STATE/GATES/kickoff_required` and the canonical spelling all open ONE
# AND THE SAME file. Suffix match, PROTECTED_PREFIXES-style, never a substring:
# `docs/kickoff_required_notes.md` is a legitimate file and stays editable.
KICKOFF_ARMING_SUFFIX = ".agents/state/gates/kickoff_required"

KICKOFF_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this is the kickoff guard's arming file — "
    "only the pilot edits it, by hand (T-00000243). Agents may not arm or "
    "DISARM themselves."
)

# DEUX AUTRES MARQUEURS D'ARMEMENT, ET ILS N'ÉTAIENT PROTÉGÉS QUE SUR CLAUDE
# (T-00000604, relevé du binôme de clôture 2026-09-13). Mesure qui a ouvert la
# tâche : `git grep BINOME_REQUIRED` ne rendait RIEN dans `.codex/`, `.gemini/`,
# `.kimi-code/` ni `.github/` — trois occurrences, toutes côté Claude.
#
# POURQUOI C'EST LA FORME DE DÉFAUT LA PLUS CHÈRE : ces deux marqueurs ARMENT
# les refus, et là où le refus mord le plus fort il restait retirable d'un seul
# `Edit` — par l'agent que la garde contraint. Une garde qu'on peut désarmer
# d'un geste n'est pas une garde, c'est le sentiment d'en avoir une.
#
# CHACUNE A SA SORTIE LÉGITIME, et le refus la NOMME plutôt que de laisser
# chercher : `--sans-binome "<pourquoi>"` reste VISIBLE au board pour l'une,
# `AFFIRMATION_SANS_BINOME` est CONSOMMÉE UNE FOIS et JOURNALISÉE pour l'autre.
# Un refus sans issue nommée se contourne ; un refus qui nomme son issue tracée
# se respecte.
BINOME_ARMING_SUFFIX = ".agents/state/gates/binome_required"

BINOME_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the closing critical review (one critic, S-00004500) — "
    "only the pilot removes it, by hand (T-00000586). An agent's way out is "
    "`tasks.py done <id> --raison \"…\" --sans-binome \"<pourquoi>\"`, whose "
    "reason stays VISIBLE on the board."
)

AFFIRMATION_ARMING_SUFFIX = ".agents/state/gates/affirmation_required"

AFFIRMATION_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the refusal to END A TURN "
    "that wrote a durable affirmation without a double check — only the pilot "
    "removes it, by hand (T-00000602). THAT GUARD IS A CLAUDE CODE `Stop` HOOK "
    "AND DOES NOT RUN ON THIS HOST: there is nothing to escape here. Do NOT "
    "write `.agents/state/gates/AFFIRMATION_SANS_BINOME` from this host — the "
    "next Claude Code session would consume it and cross the guard without "
    "having asked."
)

PLAN_CHAIN_ARMING_SUFFIX = ".agents/state/gates/plan_chain_required"

# AND THIS ONE IS DIFFERENT FROM ITS NEIGHBOUR ABOVE, so the difference is
# written rather than left to be assumed. The affirmation guard is a Claude Code
# `Stop` hook and does NOT run here. The plan chain guard lives in
# `.agents/bin/tasks.py`, which EVERY host runs — so on this host it really does
# refuse, and the traced exit really is available. Telling an agent "there is
# nothing to escape here" would be false, and it would send it hunting for a
# workaround it does not need.
PLAN_CHAIN_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the PLAN CHAIN — only the "
    "pilot removes it, by hand (T-00000624). Unlike the affirmation guard, this "
    "one lives in `tasks.py` and DOES run on this host: `tasks.py start` refuses "
    "a task whose plan was not reviewed by at least ONE plan critic (S-00003871), "
    "with one "
    "plan traced by the host on SubagentStop. Your way out is "
    "`tasks.py start <id> --sans-chaine \"<why>\"`, whose reason stays VISIBLE "
    "on the board — never by disarming the guard."
)

PLAN_CIBLE_ARMING_SUFFIX = ".agents/state/gates/plan_cible_required"

# CINQUIÈME GARDE (T-00000654), et son commentaire dit la MÊME chose que le
# voisin du dessus, pour la MÊME raison : la garde de cible vit dans `tasks.py`
# ET `specs.py`, que TOUT hôte exécute — donc sur cet hôte elle refuse vraiment,
# et la sortie tracée existe vraiment. Dire à un agent « il n'y a rien à
# contourner ici » serait faux et l'enverrait chercher un contournement inutile.
PLAN_CIBLE_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the PLAN TARGET guard — only "
    "the pilot removes it, by hand (T-00000654). Like the plan chain guard, this "
    "one lives in `tasks.py`/`specs.py` and DOES run on this host: a `done`, a "
    "`start` that already carries an approval trace, or a `plan-critic` verdict "
    "is refused when the plan does not annotate every step with a target. Your "
    "way out is `--sans-cible \"<why>\"`, whose reason stays VISIBLE on the "
    "board — never by disarming the guard."
)

MESURE_ARMING_SUFFIX = ".agents/state/gates/mesure_required"

# SIXIÈME GARDE (T-00001128), entrée UN GESTE APRÈS son armement (f3d47430), par
# la passe de correction du binôme (S-00003956) — le trou que la leçon de
# `PLAN_CHAIN_REQUIRED` nomme. La garde vit dans `tasks.py`, que TOUT hôte
# exécute : sur cet hôte elle refuse vraiment, et la sortie tracée existe.
MESURE_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the MEASURE guard of "
    "`tasks.py new` — only the pilot removes it, by hand (T-00001128). Your way "
    "out is `--mesure \"<cmd> => <observed>\" --motif <M>` for a defect, or "
    "`--pas-un-defaut \"<why>\"` otherwise; the value stays VISIBLE on the "
    "board — never by disarming the guard."
)

CHRONO_ARMING_SUFFIX = ".agents/state/gates/chrono_required"

# SEPTIÈME GARDE (T-01M55Z3ZCS34CDR2EQN1CEBHR7), entrée DANS LE MÊME GESTE que sa
# graine — la leçon de `PLAN_CHAIN_REQUIRED`. La garde vit dans `specs.py`, que
# TOUT hôte exécute : sur cet hôte elle refuse vraiment, et la sortie tracée
# existe. Cet hôte ne rend pas d'agentId : le champ s'écrit à la main.
CHRONO_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the PLAN-TURN CHRONO guard "
    "of `specs.py add` — only the pilot removes it, by hand "
    "(T-01M55Z3ZCS34CDR2EQN1CEBHR7). It lives in `specs.py` and DOES run on "
    "this host: a `plan-critic …` loop verdict is refused without "
    "`chrono: planner=<duration>/<tokens> plan-critic=<duration>/<tokens>` in "
    "its text. Write that field by hand, or take the way out "
    "`--sans-chrono \"<why>\"`, whose reason joins the entry text, VISIBLE — "
    "never by disarming the guard."
)

# LES GRAINES DES TROIS GARDES DE PIPELINE (T-00001093, décision pilote
# S-00003693). `sync_template.py` écrit chaque graine vers
# `.agents/state/gates/<NOM>` sur la template : chaque adoptant naît armé de CES
# octets, donc les éditer est un geste du pilote. Mêmes rule ids que
# `protect-paths.sh` ; même méthode que les voisins : un suffixe replié.
SEED_BINOME_REQUIRED_SUFFIX = ".agents/adopter-seed/gates/binome_required"
SEED_PLAN_CHAIN_REQUIRED_SUFFIX = ".agents/adopter-seed/gates/plan_chain_required"
SEED_PLAN_CIBLE_REQUIRED_SUFFIX = ".agents/adopter-seed/gates/plan_cible_required"
# LA QUATRIÈME GRAINE (T-01M55Z3ZCS34CDR2EQN1CEBHR7), entrée DANS LE MÊME GESTE
# que la graine et que le suffixe de son marqueur armé (`CHRONO_ARMING_SUFFIX`).
SEED_CHRONO_REQUIRED_SUFFIX = ".agents/adopter-seed/gates/chrono_required"

SEED_DENY_REASON = (
    "BLOCKED by protected-path hook: this file is the SEED of a pipeline gate "
    "marker that the template sync writes into EVERY adopter (T-00001093) — "
    "only the pilot edits it, by hand. An adopter's own way out stays the "
    "traced exit of the guard (`--sans-binome`, `--sans-chaine`, "
    "`--sans-cible`, `--sans-chrono`), never an edit of the seed."
)

# SIXIÈME ET SEPTIÈME ENTRÉES (T-00000698, repli de T-00000706). La garde de
# branche par défaut (T-00000595) protège DEUX fichiers sur Claude
# (`protect-paths.sh:171,175`) : l'ARMEMENT et sa SORTIE tracée. Les jumeaux
# Python n'en portaient AUCUN — mesuré : un `apply_patch`/`write_file` qui
# désarmait le refus de pousser vers la branche par défaut, ou qui écrivait la
# sortie pilote-seule, n'était PAS refusé sur les quatre hôtes Python. Même
# méthode que les cinq voisins : un suffixe replié, jamais une sous-chaîne. Et
# contrairement aux gardes du dessus, celle-ci n'a AUCUNE sortie agent-écrivable,
# par conception : la sortie EST l'un des deux fichiers protégés.
PUSH_DEFAUT_ARMING_SUFFIX = ".agents/state/gates/push_defaut_protege"

PUSH_DEFAUT_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the refusal to push to the "
    "DEFAULT BRANCH — only the pilot removes it, by hand (T-00000595). That guard "
    "is a git pre-push hook: it runs wherever core.hooksPath points at .githooks/, "
    "on every host alike, and is inert where the marker is absent. There is NO "
    "agent-writable way out: an agent that wrote its own exit would grant itself "
    "the human review this guard exists to require."
)

PUSH_DEFAUT_SORTIE_SUFFIX = ".agents/state/gates/push_defaut_autorise"

PUSH_DEFAUT_SORTIE_DENY_REASON = (
    "BLOCKED by protected-path hook: this file is the traced exit of 'no merge to "
    "the default branch without human review' — the PILOT ALONE writes it, by hand "
    "(T-00000595). An agent that wrote it would grant itself the review it exists "
    "to require. There is NO agent-writable way out here."
)

# LES FICHIERS PILOTE-SEULS (T-00000723, T-00000750). Ce ne sont pas des
# marqueurs d'une garde de ce dépôt, mais leur ÉCRITURE par un agent vaut une
# élévation qu'il s'accorderait lui-même : l'allowlist de la nuit sans
# surveillance, le registre d'audit MCP, les permissions locales de Claude Code.
# Même méthode que les marqueurs : un suffixe replié.
# LES DEUX PREMIERS VIVENT SOUS `gates/`, donc ils rejoignent AUSSI la règle du
# nom de `safe_bash` (qui dérive ses noms de tout `*_SUFFIX` sous `gates/`) ;
# le dernier n'y entre pas. `AUDIT_LOG` reste écrivable (S-00002524).
NIGHT_HEADLESS_SUFFIX = ".agents/state/gates/night_headless.allow"

NIGHT_HEADLESS_DENY_REASON = (
    "BLOCKED by protected-path hook: this is the allowlist of the UNATTENDED night "
    "(`/night --headless`) — the pilot alone edits it (T-00000723). An agent that "
    "wrote it would choose the tools it runs with while nobody watches."
)

MCP_ALLOWLIST_SUFFIX = ".agents/state/gates/mcp_allowlist.md"

MCP_ALLOWLIST_DENY_REASON = (
    "BLOCKED by protected-path hook: this is the human MCP audit register — only "
    "the auditing human appends to it (T-00000723, .agents/ref/MCP_REGISTRY.md)."
)

CLAUDE_SETTINGS_LOCAL_SUFFIX = ".claude/settings.local.json"

CLAUDE_SETTINGS_LOCAL_DENY_REASON = (
    "BLOCKED by protected-path hook: `.claude/settings.local.json` carries the local "
    "permissions of Claude Code — the pilot alone edits it (T-00000750). An agent "
    "that wrote it would grant itself permissions."
)

# LE CODE DU KIT, ARMABLE (T-00000763 A). `KIT_CODE_PROTEGE` arme le refus
# d'écrire l'ensemble kit-code (`.agents/bin/kit_code_guard.py`), et
# `KIT_CODE_AUTORISE` porte les octrois du pilote. Les DEUX sont pilote-seuls,
# pour la même raison que la paire de la branche par défaut : un agent qui
# écrirait l'octroi s'accorderait l'exception que la garde réserve au pilote.
# LIVRÉ DÉSARMÉ ; `.gitignore` les tient hors de tout clone.
KIT_CODE_ARMING_SUFFIX = ".agents/state/gates/kit_code_protege"

KIT_CODE_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the kit-code guard — only the "
    "pilot sets or removes it, by hand (T-00000763)."
)

KIT_CODE_SORTIE_SUFFIX = ".agents/state/gates/kit_code_autorise"

KIT_CODE_SORTIE_DENY_REASON = (
    "BLOCKED by protected-path hook: this file carries the PILOT's grants to write "
    "kit code (T-00000763). An agent that wrote it would grant itself the "
    "exception. There is NO agent-writable way out here."
)

# LA CONFIG LINT/FORMAT EXISTANTE, ARMABLE (T-01M5C1AHZM41P9C3QH6X7PEQY1, calque de
# la paire kit-code). `CONFIG_QUALITE_PROTEGE` arme le refus de modifier une config
# lint/format EXISTANTE du projet (`.agents/bin/config_qualite_guard.py`) ; il est
# SUIVI par git et posé par le pilote, et l'adoptant le reçoit par sa GRAINE.
# `CONFIG_QUALITE_AUTORISE` porte les octrois du pilote, git-ignoré. Les TROIS sont
# pilote-seuls ; marqueur et octroi vivent sous `gates/`, donc `safe_bash` en dérive
# aussi le refus par le nom.
CONFIG_QUALITE_ARMING_SUFFIX = ".agents/state/gates/config_qualite_protege"

CONFIG_QUALITE_ARMING_DENY_REASON = (
    "BLOCKED by protected-path hook: this file arms the refusal to MODIFY an existing "
    "lint/format config — only the pilot sets or removes it, by hand "
    "(T-01M5C1AHZM41P9C3QH6X7PEQY1). Fix the code instead of weakening the config."
)

CONFIG_QUALITE_SORTIE_SUFFIX = ".agents/state/gates/config_qualite_autorise"

CONFIG_QUALITE_SORTIE_DENY_REASON = (
    "BLOCKED by protected-path hook: this file carries the PILOT's grants to modify an "
    "existing lint/format config (T-01M5C1AHZM41P9C3QH6X7PEQY1). An agent that wrote it "
    "would grant itself the exception. There is NO agent-writable way out here."
)

SEED_CONFIG_QUALITE_SUFFIX = ".agents/adopter-seed/gates/config_qualite_protege"

SEED_CONFIG_QUALITE_DENY_REASON = (
    "BLOCKED by protected-path hook: this file is the SEED of the lint/format config "
    "guard marker that the template sync writes into EVERY adopter "
    "(T-01M5C1AHZM41P9C3QH6X7PEQY1) — only the pilot edits it, by hand. An adopter's "
    "way out is a pilot grant in `.agents/state/gates/CONFIG_QUALITE_AUTORISE`, never "
    "an edit of the seed."
)

CONFIG_QUALITE_GUARD_UNREADABLE_REASON = (
    "BLOCKED by protected-path hook: CONFIG_QUALITE_PROTEGE is set but "
    "`.agents/bin/config_qualite_guard.py` cannot be loaded, so no write can be judged "
    "(T-01M5C1AHZM41P9C3QH6X7PEQY1). Remedy: restore that file (git checkout), or the "
    "pilot removes `.agents/state/gates/CONFIG_QUALITE_PROTEGE` by hand."
)

# LE REGISTRE D'EXCEPTIONS DE LA PORTE CLASS-0 (T-00000844). `.gitleaks.toml`
# est l'allowlist d'une porte NON LEVABLE : un Edit qui l'élargit exempte un
# secret, un Edit qui le corrompt éteignait la porte aux deux hooks. Pilote
# seul. Même suffixe replié que `protect-paths.sh` (`*.gitleaks.toml`), donc
# aussi `<x>.gitleaks.toml` et un sous-répertoire — la largeur de ses voisins.
# Hors `gates/` : il n'entre PAS dans la règle du nom de `safe_bash`.
GITLEAKS_ALLOWLIST_SUFFIX = ".gitleaks.toml"

GITLEAKS_ALLOWLIST_DENY_REASON = (
    "BLOCKED by protected-path hook: `.gitleaks.toml` is the exception register "
    "of the class-0 secrets gate, which is NOT waivable — the pilot alone edits "
    "it, by hand (T-00000844). A real secret is removed and rotated; a false "
    "positive is reported to the pilot, who decides whether to exempt it. There "
    "is NO agent-writable way out here."
)

# LE REGISTRE D'EXCEPTIONS DU SCANNER UNICODE (T-01M5CN9FM2MPY8Z00AS7FTXXWH),
# calque de `.gitleaks.toml` : une entrée y admet un caractère invisible ou bidi
# dans un texte d'instructions. Pilote seul. Même suffixe replié que
# `protect-paths.sh` ; hors `gates/`, donc hors de `arming_marker_names` :
# `safe_bash` refuse une redirection vers une cible NON CITÉE par ce suffixe (via
# `protected_reason`, jusque hors de la racine) ; une cible citée, ou le nom nu
# après un `cd`, passe — comme `.gitleaks.toml`. `cp`, `sed -i`, `tee`,
# `python -c` passent — ça empêche d'oublier, pas de tricher.
UNICODE_ALLOWLIST_SUFFIX = ".agents/security/unicode-allowlist.json"

UNICODE_ALLOWLIST_DENY_REASON = (
    "BLOCKED by protected-path hook: `.agents/security/unicode-allowlist.json` is "
    "the exception register of the Unicode scanner, reserved to the pilot "
    "(T-01M5CN9FM2MPY8Z00AS7FTXXWH): an entry is added through its traced "
    "decision (`specs.py add --kind decision`) and then by the pilot, by hand. "
    "An agent that wrote it would exempt an invisible character itself."
)

# LE JOURNAL DE SPECS (T-00000847, décision pilote). `SPECS.json` est
# append-only et ne s'écrit QUE par `specs.py` (Python, `save` atomique, jamais
# l'outil Edit/Write). Il porte les contrats `night-eligible` et le marqueur
# `night-delivered` que `/night` relit sans surveillance. Même suffixe replié
# que `protect-paths.sh`. Hors `gates/` : pas dans la règle du nom de `safe_bash`.
SPECS_JOURNAL_SUFFIX = ".agents/state/specs/specs.json"

SPECS_JOURNAL_DENY_REASON = (
    "BLOCKED by protected-path hook: `.agents/state/specs/SPECS.json` is the "
    "append-only specs journal — it is written only by `python .agents/bin/specs.py "
    "add` (T-00000847). An Edit/Write could erase a night-eligible contract or a "
    "night-delivered marker that /night re-reads unattended."
)

# SA FORME JOURNAL (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : `SPECS.jsonl`, append-only, même
# règle `specs-journal` ; la règle `SPECS.json` reste (monolithe de l'adoptant).
SPECS_JOURNAL_JSONL_SUFFIX = ".agents/state/specs/specs.jsonl"

SPECS_JOURNAL_JSONL_DENY_REASON = (
    "BLOCKED by protected-path hook: `.agents/state/specs/SPECS.jsonl` is the "
    "append-only specs journal (one entry per line) — it is written only by "
    "`python .agents/bin/specs.py add` (T-00000847, T-01M4KKMY43ZKCW1YD2Y8JX9MKH). "
    "An Edit/Write could erase a night-eligible contract or a night-delivered "
    "marker that /night re-reads unattended."
)

KIT_CODE_GUARD_UNREADABLE_REASON = (
    "BLOCKED by protected-path hook: KIT_CODE_PROTEGE is set but "
    "`.agents/bin/kit_code_guard.py` cannot be loaded, so no write can be judged "
    "(T-00000763). Remedy: restore that file (git checkout), or the pilot removes "
    "`.agents/state/gates/KIT_CODE_PROTEGE` by hand."
)


# ---------------------------------------------------------------------------
# Project-level extension (T-00000031). A consumer project can protect extra
# prefixes by listing them, one per line, in `.agents/protected-paths.local`
# (`#` comments and blank lines ignored). SHARED by all four hosts on purpose:
# a guard that only one host honours is not a guard, it is a false sense of
# one — the same doctrine that made the MCP path guards four-host.
#
# WHY THIS FILE, AND WHY IT IS EMPTY HERE: the pilot decision behind
# T-00000031 is that `.agents/bin/` must stay writable IN THE KIT (the kit
# maintains itself — every tool in that directory was written by an agent
# working in this repo) and become protected IN CONSUMER PROJECTS, where it
# is vendored code nobody should edit locally. So the mechanism ships from
# main and the CONTENT ships from the template branch, declared `own:` in
# `.template-exclude`: the file exists only there, and a project cloned from
# the template starts with `.agents/bin/` protected.
# ---------------------------------------------------------------------------

EXTRA_RELPATH = Path(".agents") / "protected-paths.local"


def _repo_root():
    """The project root, from THIS file's location: `.<host>/hooks/x.py` ->
    parents[2]. Deliberately not cwd (a hook runs from anywhere) and not an
    environment variable (this file serves two hosts, cf. L-006)."""
    return Path(__file__).resolve().parents[2]


def extra_prefixes():
    """Extra protected prefixes, or () when the file is absent/unreadable.
    Never raises: a guard that crashes on a malformed optional file fails
    OPEN, which is the one outcome a path guard must never have."""
    try:
        # errors="replace", and a broad except: a path guard that CRASHES on a
        # malformed optional file fails open, which is the one outcome it must
        # never have. Caught by this feature's own parity eval, which planted
        # non-UTF-8 bytes and found the guard exiting 1 instead of enforcing
        # its built-in rules.
        text = (_repo_root() / EXTRA_RELPATH).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ()
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.lower())
    return tuple(out)


def _nt_fold(p, dots=False):
    """LE PLI NTFS (T-00000722) : les orthographes qu'un volume NTFS/Win32 ouvre
    comme UN SEUL fichier — casse, `\\` pour `/`, un flux ADS (`x:y`,
    `x::$DATA`) coupé au premier `:` de chaque segment (le lecteur `c:` de tête
    gardé), et le point ou l'espace finaux de chaque segment, que Win32 retire.
    QUATRE COPIES du même corps, et c'est écrit plutôt que caché : `NT_FOLD`
    dans `protect-paths.sh`, cette fonction dans les deux jumeaux, `ntf` dans le
    snippet de `safe-bash.sh` — leur parité est tenue par un différentiel
    ÉNUMÉRÉ (`.agents/evals/test_protect_paths_hardening.py`), jamais par relecture.

    `dots` choisit la LECTURE d'un segment fait seulement de points et d'espaces
    (security-code-review à db1a65d9) : rognée par défaut (vidé), « points » si
    vrai (`..` pour au moins deux points, `.` pour un). Les deux sont jugées par
    `protected_reason` — aucune ne couvre l'autre."""
    segs = p.lower().replace(chr(92), "/").split("/")
    out = []
    for i, s in enumerate(segs):
        head = ""
        if i == 0 and len(s) >= 2 and s[1] == ":" and s[0].isalpha():
            head, s = s[:2], s[2:]          # lecteur x: de tête conservé
        s = s.split(":", 1)[0]              # flux ADS : x:y, x::$DATA
        if dots and "." in s and not s.strip(". "):
            s = ".." if s.count(".") >= 2 else "."   # lecture « points »
        elif s not in (".", ".."):
            s = s.rstrip(". ")              # point/espace finaux (Win32)
        out.append(head + s)
    return "/".join(out)


# LE POINT FIXE DES FORMES CANONIQUES (T-00000722 ; revue du lot T-00000721,
# HIGH « pli avant résolution »). La liste FIXE de candidats d'avant — minuscule,
# pli rogné, pli renormalisé, lecture « points » — n'était pas CLOSE : le chemin
# arrive résolu une fois (`_common.normalize_path`), et une forme obtenue par
# PLI pouvait encore porter un lien que rien ne résolvait —
# `ln -s <cible protégée> nom_neutre` puis `z/.../nom_neutre` : pass, mesuré.
# Même fermeture que `PP_FERMETURE` (protect-paths.sh), `fermer` (snippet de
# safe-bash.sh) et `canonical_forms` de `.agents/bin/kit_code_guard.py`.
FORMES_BORNE = 5

FORMES_INSTABLES_DENY_REASON = (
    "BLOCKED by protected-path hook: the canonical forms of this path (NTFS folds, "
    "lexical renormalisation, case fold, physical resolution) did not reach a fixed "
    "point within 5 rounds, so it cannot be judged — refused rather than judged in "
    "part (T-00000722). The usual cause is a chain of symbolic links whose targets "
    "carry dot segments: write the resolved path instead."
)


def _lecteurs(r):
    """Les orthographes Git Bash ↔ Win32 d'un chemin à lettre de lecteur
    (`C:/x` ↔ `/c/x`), la lettre dans ses deux casses : la racine arrive en
    `/c/…` (cygpath) quand `realpath` rend `C:/…` (security-code-review sur
    fdc7cd75, angle mort Windows ; même table que `_root_spellings` du kit).
    Ensemble vide pour tout autre chemin."""
    out = set()
    if len(r) >= 2 and r[1] == ":" and r[0].isalpha() and (len(r) == 2 or r[2] == "/"):
        out.update("/" + lettre + r[2:] for lettre in (r[0].lower(), r[0].upper()))
    if len(r) >= 2 and r[0] == "/" and r[1].isalpha() and (len(r) == 2 or r[2] == "/"):
        out.update(lettre + ":" + r[2:] for lettre in (r[1].lower(), r[1].upper()))
    return out


def _racines(root):
    """La racine sous ses orthographes — telle quelle, résolue, leurs formes à
    lettre de lecteur (`_lecteurs`), et chacune minusculisée et repliée NT —,
    les plus longues d'abord. Relativiser sur la seule orthographe exacte
    laissait la forme minusculisée d'un chemin absolu un tour en retard (racine
    sous `/var` → `/private/var` avec `T/`), et des fichiers ordinaires
    dépassaient la borne."""
    base = str(root).replace("\\", "/").rstrip("/")
    vues = {base, os.path.realpath(base).replace("\\", "/").rstrip("/")}
    for r in list(vues):
        vues |= _lecteurs(r)
    out = set()
    for r in vues:
        if r:
            out.update((r, r.lower(), _nt_fold(r)))
    return sorted(out, key=len, reverse=True)


def _relativiser(r, racines):
    """Fonction PURE : `r` (déjà résolu) rendu relatif à la racine quand il est
    sous l'une de ses orthographes (`.` pour la racine même), inchangé sinon."""
    for s in racines:
        if r == s:
            return "."
        if r.startswith(s + "/"):
            return r[len(s) + 1:]
    return r


def _physique(p, root, racines):
    """La résolution PHYSIQUE (`os.path.realpath` : `.`, `..`, liens, segment
    terminal inexistant toléré), relative à la racine quand elle est dessous
    (`_relativiser`), absolue sinon. Peut lever (octet nul) : l'appelant en
    fait un refus."""
    q = p.replace("\\", "/")
    if not os.path.isabs(q):
        q = os.path.join(str(root), q)
    return _relativiser(os.path.realpath(q).replace("\\", "/"), racines)


def canonical_forms(path, root=None):
    """`(formes, stable)` — l'ensemble COMPLET des formes canoniques de `path`,
    calculé comme un POINT FIXE et non comme une liste de passes : on part de
    {forme brute} ; à chaque tour, chaque forme ajoute sa casse repliée, ses
    deux plis NT (`_nt_fold`, rognée et « points », corps inchangé), sa
    renormalisation lexicale (`posixpath.normpath`) et sa résolution physique
    (`_physique`, relative à la racine). Arrêt quand l'ensemble ne grandit plus.

    BORNE : `FORMES_BORNE` = 5 tours ; la stabilité doit être CONSTATÉE au plus
    tard au 5e (un tour qui n'ajoute rien). POURQUOI 5 : un alias (point,
    espace, flux ADS, détour de points) d'un lien dont la cible porte un segment
    de points (`courte1 -> z/.../courte2`) ne se stabilise qu'au 5e — à 4, ce
    fichier ordinaire était refusé (exec-critic sur fdc7cd75, M2). Au-delà — ou
    si une résolution lève —, `stable` est faux et `protected_reason` REFUSE
    (fail-closed) : une CHAÎNE de tels liens n'avance que d'un maillon tous les
    deux tours. COÛT : au plus 5 × 5 opérations par forme, dont un `realpath`
    (un `lstat` par composant). LA MARGE, écrite ici et nulle part ailleurs,
    mesurée le 2026-09-27 : les 1 070 chemins suivis de ce dépôt, relatifs et
    absolus, au plus 3 tours — mais cet échantillon ne porte AUCUN lien
    symbolique (`git ls-files -s`, mode 120000 : 0), il ne mesure donc pas la
    résolution. Sur un arbre jetable AVEC liens (chaînes de 1 à 4 maillons vers
    un fichier ordinaire, cibles relatives et absolues à la casse d'origine,
    racine épelée telle quelle, en majuscules, en minuscules), au plus 4 tours,
    atteints par la racine en majuscules. DEUX CLASSES SANS MARGE, à 5 tours —
    la borne, stables mais sans un tour de reste : (1) les alias d'un lien dont
    la cible porte un segment de points (`courte1.`) ; (2) les alias (point,
    espace, flux ADS, `A/../…`) d'une chaîne dont les cibles sont ABSOLUES et
    épelées sous la racine en MAJUSCULES (`maj1.`, binôme de clôture). CES
    MESURES VALENT SUR UN FS INSENSIBLE À LA CASSE (macOS, par défaut) : sous
    Linux la racine en majuscules n'existe pas, et la classe (2) non plus.
    Tenu par `test_marge_de_la_borne` (inerte, donc sauté, là où la racine en
    majuscules n'existe pas)."""
    racine = ROOT if root is None else root
    racines = _racines(racine)
    formes = [path] if path else []
    vues = set(formes)
    for _tour in range(FORMES_BORNE):
        neuves = []
        for forme in formes:
            try:
                physique = _physique(forme, racine, racines)
            except (OSError, ValueError):
                return formes, False
            for g in (forme.lower(), _nt_fold(forme), _nt_fold(forme, True),
                      posixpath.normpath(forme), physique):
                if g and g not in vues:
                    vues.add(g)
                    neuves.append(g)
        if not neuves:
            return formes, True
        formes.extend(neuves)
    return formes, False


def protected_reason(path):
    """`(deny reason for the host, rule id for the audit trail)`.

    The rule id deliberately reuses .claude/hooks/protect-paths.sh's own
    vocabulary — the matched prefix itself, then `.env` / `credential-pattern` /
    `mcp-config` — so one denial reads identically whichever host produced it.

    DEUX CANDIDATS, UNE UNION DE REFUS (T-00000722) : la forme minusculisée,
    puis la forme repliée NT (`_nt_fold`). Le premier refus gagne ; une
    exemption vue sur un candidat ne lève JAMAIS le refus d'un autre (le
    gabarit `.env.example.` reste refusé sur sa forme minusculisée alors que son
    pli NT est un gabarit). Le pli ne remplace pas la forme minusculisée : il
    peut EFFACER le jeton qui refusait (`x/foo:MCP.JSON` replié vaut `x/foo`).

    ET UN TROISIÈME, le replié RENORMALISÉ (exec-critic, constat 1) : le pli peut
    faire naître un `..` — `z/..:s/KICKOFF_REQUIRED` replié vaut
    `z/../kickoff_required`, qu'aucun suffixe ne reconnaît, et
    `_common.normalize_path` l'a laissé passer puisque `..:s` est un nom
    ordinaire pour `Path.resolve`. `posixpath.normpath` (racine `/` gardée) le
    ramène à `kickoff_required`, jugé EN PLUS du replié.

    CES CANDIDATS SONT DÉSORMAIS L'ENSEMBLE ENTIER (T-00000722) : chaque forme
    de `canonical_forms(path)` — les quatre ci-dessus, la lecture « points »
    (security-code-review à db1a65d9 : `z/.. /KICKOFF_REQUIRED` vaut
    `kickoff_required`), la résolution physique de chaque forme pliée, et ainsi
    de suite jusqu'au point fixe — est jugée MINUSCULISÉE, puisque les règles de
    `_rule_hit` sont définies sur la forme minusculisée (le gabarit
    `x.env.EXAMPLE` reste un gabarit, sur les quatre hôtes). Union de
    refus ; un ensemble qui ne se stabilise pas dans la borne est un REFUS
    (`formes-instables`), jamais un jugement partiel.
    """
    formes, stable = canonical_forms(path)
    for candidate in dict.fromkeys(f.lower() for f in formes):
        reason, rule = _rule_hit(path, candidate)
        if reason:
            return reason, rule
    if not stable:
        return FORMES_INSTABLES_DENY_REASON, "formes-instables"
    return "", ""


def _rule_hit(path, lower):
    """Les règles, testées sur UN candidat (`lower`) tel qu'il est reçu ; les
    messages portent toujours le chemin BRUT (`path`)."""
    name = Path(lower).name
    env_template = name.endswith(ENV_TEMPLATE_SUFFIXES)
    for prefix in PROTECTED_PREFIXES + extra_prefixes():
        # The template exception is scoped to the `.env` RULE, whichever list
        # supplied it — including a project's own `.agents/protected-paths.local`.
        # The sh guard keys its exception on the matched pattern being `.env`, so
        # a project that writes `.env` into its local list keeps templates
        # editable there; without this line the Python hosts would deny what
        # Claude allows, i.e. exactly the silent per-host divergence this
        # exception exists to avoid (caught by this feature's own parity eval).
        # A project that really wants to re-block them lists a NARROWER pattern
        # (`.env.example`), which is not exempted here.
        if env_template and prefix == ".env":
            continue
        if lower.startswith(prefix):
            return f"BLOCKED by protected-path hook: {path} matches {prefix}.", prefix
    if (name == ".env" or name.startswith(".env.")) and not env_template:
        return f"BLOCKED by protected-path hook: {path} is an environment file.", ".env"
    # `.env` is ALSO a SECRET_NAMES token, matched as a substring: a template has
    # to be exempted here too, or the credential rule blocks what the rule above
    # just allowed.
    secret_tokens = tuple(t for t in SECRET_NAMES if not (env_template and t == ".env"))
    if any(token in lower for token in secret_tokens) or lower.endswith(SECRET_EXTENSIONS):
        return f"BLOCKED by protected-path hook: {path} looks credential-related.", "credential-pattern"
    if any(token in lower for token in MCP_CONFIG_NAMES) or any(
        lower.endswith(p) for p in MCP_CONFIG_PATHS
    ):
        return MCP_DENY_REASON, "mcp-config"
    # LES INTERNES GIT (T-00000763 B) : `.git/config` porte `core.hooksPath`,
    # `core.fsmonitor`, `alias.*` — une écriture qui arme une commande. TOUT
    # segment `.git`, pas seulement config/hooks/info : un sous-module
    # (`sub/.git/config`) et un gitfile (`sub/.git`) comptent. `.gitignore`,
    # `.github/` et `.gitleaks.toml` ne sont PAS des segments `.git`
    # (`.gitleaks.toml` est refusé par SA règle, `gitleaks-allowlist`, plus bas).
    if ".git" in lower.replace("\\", "/").split("/"):
        return (f"BLOCKED by protected-path hook: {path} is inside a `.git` directory — "
                "git internals (config, hooks, info) are never agent-written "
                "(T-00000763)."), "git-internals"
    # LE `\` → `/` EST UNE CEINTURE, pas la bretelle. Ma première rédaction le
    # présentait comme le garant de la casse NTFS : c'est FAUX et le binôme l'a
    # mesuré — `_common.normalize_path` a déjà converti les séparateurs avant que
    # ce chemin n'arrive ici, et retirer ce `.replace` laisse les 44 tests verts.
    # Il reste pour deux raisons qui, elles, tiennent : `protected_reason` est
    # aussi appelée par `safe_bash.judge_redirect`, et une fonction publique ne
    # doit pas dépendre du zèle de son appelant. Le garant de la casse est le
    # `.lower()` du candidat ; celui des ALIAS Win32 (point, espace, flux ADS
    # finaux) est le second candidat, `_nt_fold` (T-00000722).
    folded = lower.replace("\\", "/")
    for suffix, reason, rule in (
        (KICKOFF_ARMING_SUFFIX, KICKOFF_ARMING_DENY_REASON, "kickoff-arming"),
        (BINOME_ARMING_SUFFIX, BINOME_ARMING_DENY_REASON, "binome-arming"),
        (AFFIRMATION_ARMING_SUFFIX, AFFIRMATION_ARMING_DENY_REASON,
         "affirmation-arming"),
        (PLAN_CHAIN_ARMING_SUFFIX, PLAN_CHAIN_ARMING_DENY_REASON,
         "plan-chain-arming"),
        (PLAN_CIBLE_ARMING_SUFFIX, PLAN_CIBLE_ARMING_DENY_REASON,
         "plan-cible-arming"),
        (MESURE_ARMING_SUFFIX, MESURE_ARMING_DENY_REASON, "mesure-arming"),
        (CHRONO_ARMING_SUFFIX, CHRONO_ARMING_DENY_REASON, "chrono-arming"),
        (SEED_BINOME_REQUIRED_SUFFIX, SEED_DENY_REASON, "seed-binome-required"),
        (SEED_PLAN_CHAIN_REQUIRED_SUFFIX, SEED_DENY_REASON, "seed-plan-chain-required"),
        (SEED_PLAN_CIBLE_REQUIRED_SUFFIX, SEED_DENY_REASON, "seed-plan-cible-required"),
        (SEED_CHRONO_REQUIRED_SUFFIX, SEED_DENY_REASON, "seed-chrono-required"),
        # Les rule ids sont ceux de `protect-paths.sh:173,177` : un même refus se
        # lit à l'identique quel que soit l'hôte qui l'a produit (T-00000698).
        (PUSH_DEFAUT_ARMING_SUFFIX, PUSH_DEFAUT_ARMING_DENY_REASON,
         "push-defaut-arming"),
        (PUSH_DEFAUT_SORTIE_SUFFIX, PUSH_DEFAUT_SORTIE_DENY_REASON,
         "push-defaut-sortie"),
        # Pilote-seuls et code du kit (T-00000723, T-00000750, T-00000763) :
        # rule ids identiques à ceux de `protect-paths.sh`.
        (NIGHT_HEADLESS_SUFFIX, NIGHT_HEADLESS_DENY_REASON, "night-headless"),
        (MCP_ALLOWLIST_SUFFIX, MCP_ALLOWLIST_DENY_REASON, "mcp-allowlist"),
        (CLAUDE_SETTINGS_LOCAL_SUFFIX, CLAUDE_SETTINGS_LOCAL_DENY_REASON,
         "claude-settings-local"),
        (KIT_CODE_ARMING_SUFFIX, KIT_CODE_ARMING_DENY_REASON, "kit-code-arming"),
        (KIT_CODE_SORTIE_SUFFIX, KIT_CODE_SORTIE_DENY_REASON, "kit-code-sortie"),
        (CONFIG_QUALITE_ARMING_SUFFIX, CONFIG_QUALITE_ARMING_DENY_REASON,
         "config-qualite-arming"),
        (CONFIG_QUALITE_SORTIE_SUFFIX, CONFIG_QUALITE_SORTIE_DENY_REASON,
         "config-qualite-sortie"),
        (SEED_CONFIG_QUALITE_SUFFIX, SEED_CONFIG_QUALITE_DENY_REASON,
         "seed-config-qualite-protege"),
        (GITLEAKS_ALLOWLIST_SUFFIX, GITLEAKS_ALLOWLIST_DENY_REASON,
         "gitleaks-allowlist"),
        (UNICODE_ALLOWLIST_SUFFIX, UNICODE_ALLOWLIST_DENY_REASON,
         "unicode-allowlist"),
        (SPECS_JOURNAL_SUFFIX, SPECS_JOURNAL_DENY_REASON, "specs-journal"),
        (SPECS_JOURNAL_JSONL_SUFFIX, SPECS_JOURNAL_JSONL_DENY_REASON, "specs-journal"),
    ):
        if folded.endswith(suffix):
            return reason, rule
    return "", ""


def _load_kit_code_guard():
    """`.agents/bin/kit_code_guard.py`, chargé PARESSEUSEMENT et PAR CHEMIN
    EXPLICITE (`_common.BIN`) — jamais par nom : `_common.py` interdit l'import
    par nom pour `events.py`, parce qu'un homonyme sur `sys.path` gagnerait, et la
    même raison vaut ici. Paresseux : tant que le marqueur est absent, rien n'est
    chargé, et `protected_module.py` (qui importe ce module) n'en voit rien."""
    spec = importlib.util.spec_from_file_location("_kit_code_guard", BIN / "kit_code_guard.py")
    if spec is None or spec.loader is None:
        raise ImportError("kit_code_guard.py introuvable")
    module = importlib.util.module_from_spec(spec)
    # Enregistré AVANT l'exécution, comme `_common.py` le fait pour `events.py`
    # (L-00000142, `test_modload_registration.py`) : avec
    # `from __future__ import annotations`, `dataclasses` cherche le module de la
    # classe dans la table des modules chargés. Aucune dataclass ici aujourd'hui :
    # enregistrement préventif. Nom privé, recréé à chaque chargement.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Un module à moitié exécuté ne reste pas enregistré.
        sys.modules.pop(spec.name, None)
        raise
    return module


def _load_config_qualite_guard():
    """`.agents/bin/config_qualite_guard.py`, chargé PARESSEUSEMENT et PAR CHEMIN
    EXPLICITE (`_common.BIN`), jamais par nom — la raison de `_load_kit_code_guard`.
    Enregistré dans `sys.modules` AVANT l'exécution (L-00000142)."""
    spec = importlib.util.spec_from_file_location(
        "_config_qualite_guard", BIN / "config_qualite_guard.py")
    if spec is None or spec.loader is None:
        raise ImportError("config_qualite_guard.py introuvable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def raw_payload_paths(payload):
    """Les chemins de la charge tels qu'ÉCRITS, AVANT `normalize_path` — qui les résout,
    liens symboliques compris : le NOM d'un lien (`web/.eslintrc.json -> ../x.json`) et
    un lien pendant n'y survivent pas. Mêmes clés, même ordre et mêmes lignes
    `*** (Add|Update|Delete) File:` que `_common.paths_from_payload`, `\\` → `/`."""
    args = tool_args(payload)
    values = [args[key] for key in ("file_path", "filePath", "path", "target_file", "target", "filename")
              if key in args]
    for patch in (args.get("command"), args.get("patch"), args.get("input"), args.get("raw"),
                  payload.get("_raw")):
        if isinstance(patch, str):
            values.extend(m.group(1).strip() for m in
                          re.finditer(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, re.M))
    return list(dict.fromkeys(str(v).replace("\\", "/") for v in values if v))


def _feuille_est_lien(raw):
    """Le brut ne se juge seul que si sa FEUILLE est un lien symbolique : parents
    résolus, nom gardé. Un alias dans la racine (`/var` → `/private/var`, un lien vers
    la racine) n'est pas un lien de feuille — le résolu suffit, et le brut seul
    manquerait l'octroi. Une erreur de `lstat` le fait juger (fail-closed)."""
    try:
        p = raw if os.path.isabs(raw) else os.path.join(str(ROOT), raw)
        leaf = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
        return stat.S_ISLNK(os.lstat(leaf).st_mode)
    except (OSError, ValueError):
        return True


def config_qualite_verdict(paths, raw_paths=()):
    """La config lint/format EXISTANTE (T-01M5C1AHZM41P9C3QH6X7PEQY1), APRÈS les règles
    absolues et AVANT le code du kit : `None` quand le marqueur est absent (rien n'est
    chargé), sinon `("deny", raison, règle, chemin)` ou
    `("warn", "", "config-qualite-octroi", [chemins])`. Marqueur présent et module
    absent, cassé, qui lève ou sort : REFUS nommé, jamais un accord par défaut. La
    règle vit ICI, jamais dans `protected_reason` (que `safe_bash` appelle aussi).
    `raw_paths` : les chemins BRUTS (`raw_payload_paths`), chacun jugé seul en plus des
    formes résolues quand sa feuille est un lien (`_feuille_est_lien`) — le nom écrit
    d'un lien est une config, sa cible peut ne pas l'être."""
    try:
        if not (GATES / "CONFIG_QUALITE_PROTEGE").is_file():
            return None
    except OSError:
        pass
    if not paths:
        return None
    try:
        module = _load_config_qualite_guard()
        granted = []
        # Le résolu, puis l'ensemble de ses formes canoniques : l'existence se juge en
        # UNION sur toutes. Puis chaque brut qui en diffère et dont la feuille est un
        # lien, SEUL : une union entre deux chemins d'un patch refuserait la création de
        # l'un sur l'existence de l'autre.
        jobs = [(path, (path, *canonical_forms(path)[0])) for path in paths]
        jobs += [(raw, (raw,)) for raw in raw_paths if raw not in paths and _feuille_est_lien(raw)]
        for path, forms in jobs:
            reason, rule, grant = module.config_qualite_reason(tuple(dict.fromkeys(forms)), ROOT)
            if reason:
                return ("deny", reason, rule, path)
            if grant:
                granted.append(path)
    except (Exception, SystemExit):
        return ("deny", CONFIG_QUALITE_GUARD_UNREADABLE_REASON, "config-qualite-illisible", paths[0])
    if granted:
        return ("warn", "", "config-qualite-octroi", granted)
    return None


def kit_code_verdict(paths):
    """Le code du kit (T-00000763 A), APRÈS les règles absolues : `None` quand le
    marqueur est absent (le régime de référence, livré), sinon
    `("deny", raison, règle, chemin)` ou `("warn", "", "kit-code-octroi", [chemins])`.
    Marqueur présent et module illisible — absent, cassé, qui lève — : REFUS
    nommé, jamais un accord par défaut."""
    try:
        if not (GATES / "KIT_CODE_PROTEGE").is_file():
            return None
    except OSError:
        pass
    if not paths:
        return None
    try:
        module = _load_kit_code_guard()
        granted = []
        for path in paths:
            # L'ENSEMBLE, pas trois orthographes (T-00000722) : la garde le
            # referme encore elle-même, octroi seulement si chaque forme de
            # l'ensemble tombant dans le code du kit est couverte. LE DRAPEAU
            # `stable` EST IGNORÉ ICI, et c'est voulu (security-code-review sur
            # fdc7cd75, S2) : `main` n'appelle ce verdict qu'après
            # `protected_reason`, qui a déjà REFUSÉ tout chemin dont l'ensemble
            # est instable ; et `kit_code_reason` referme l'ensemble reçu et
            # refuse lui-même `formes-instables` s'il ne se stabilise pas.
            reason, rule, grant = module.kit_code_reason(
                tuple(canonical_forms(path)[0]), ROOT)
            if reason:
                return ("deny", reason, rule, path)
            if grant:
                granted.append(path)
    except (Exception, SystemExit):
        return ("deny", KIT_CODE_GUARD_UNREADABLE_REASON, "kit-code-guard-illisible", paths[0])
    if granted:
        return ("warn", "", "kit-code-octroi", granted)
    return None


def main():
    payload = read_payload()
    # Une LECTURE LOCALE identifiée positivement sous Copilot sort ici, avant
    # toute E/S propre au garde (le `git rev-parse` d'import de `_common.ROOT`
    # a déjà tourné ; T-01M4RWC6VHHN479J2A9RRY1BE3) ; partout ailleurs, inerte.
    if lecture_copilot(payload):
        return
    paths = paths_from_payload(payload)
    for path in paths:
        reason, rule = protected_reason(path)
        if reason:
            deny(reason)
            # hook.deny{guard,rule,path} — same kind, same fields, same order
            # (host first, then the event) as the Claude homologue. `path` is a
            # bounded, already-normalized repo-relative path from
            # paths_from_payload, and events.py caps this field at 300 chars for
            # this kind. The deny REASON is never sent: it is prose, and prose
            # does not belong in a machine-read audit line.
            emit_event("hook.deny", guard="protect-paths", rule=rule, path=path)
            return
    # La config lint/format EXISTANTE, puis le code du kit : son octroi ne lève que
    # CE refus-ci, et le code du kit juge encore le même chemin.
    verdict = config_qualite_verdict(paths, raw_payload_paths(payload))
    if verdict is not None and verdict[0] == "deny":
        _, reason, rule, path = verdict
        deny(reason)
        emit_event("hook.deny", guard="protect-paths", rule=rule, path=path)
        return
    if verdict is not None:
        for path in verdict[3]:
            emit_event("hook.warn", guard="protect-paths", rule="config-qualite-octroi", path=path)
    # Le code du kit vient APRÈS : un octroi ne lève que CE refus-ci, jamais un
    # `.env`, un credential, un marqueur ou un interne git jugés ci-dessus.
    verdict = kit_code_verdict(paths)
    if verdict is None:
        return
    if verdict[0] == "deny":
        _, reason, rule, path = verdict
        deny(reason)
        emit_event("hook.deny", guard="protect-paths", rule=rule, path=path)
        return
    for path in verdict[3]:
        emit_event("hook.warn", guard="protect-paths", rule="kit-code-octroi", path=path)


if __name__ == "__main__":
    main()
