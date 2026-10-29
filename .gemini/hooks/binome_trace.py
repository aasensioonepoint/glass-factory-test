#!/usr/bin/env python3
"""SubagentStop — TRACE MECANIQUE DU BINOME DE CLOTURE, hors Claude Code.

T-00000589. Port du traceur Claude (`.claude/hooks/binome-trace.sh`), meme
contrat et meme format de trace.

TWIN VERBATIM (`.codex/hooks/` et `.gemini/hooks/`) servant CINQ hotes — Codex,
Kimi Code, GitHub Copilot, Gemini CLI, Antigravity — donc **nommer un hote ici
serait FAUX**. Les deux copies sont octet-pour-octet identiques, et un banc le
tient : toute correction s'applique aux DEUX. C'est la meme regle que le fichier
voisin `audit_gate.py` porte deja, et la premiere redaction de ce port l'avait
enfreinte — sa docstring enumerait trois hotes et renvoyait « son miroir » a
elle-meme, ce qui envoie le prochain qui debogue chercher un fichier inexistant.

CE QUE LE RELEVE A ETABLI, ET CE QU'IL N'A PAS ETABLI. Les quatre REGISTRES DU
KIT declarent l'evenement de fin de sous-agent — `SubagentStop`, `subagentStop`
pour Copilot — et y enregistraient deja `log_agent_usage.py`, qui lit le NOM de
la def sur ce meme evenement. Ce sont NOS fichiers : aucun hote n'a ete observe
emettant l'evenement. Il ne manquait donc pas la DECLARATION, il manquait le
TRACEUR — et la couverture exacte reste **1 mesure (Claude), le reste cable au
registre, evenement et nom du champ NON CONFIRMES cote hote**.

LES DEUX GRAPHIES, ET CE N'EST PAS DE LA COURTOISIE. `log_agent_usage.py` lit
`agentType` OU `agent_type` depuis toujours, parce que les hotes ne nomment pas
ce champ pareil. Le traceur Claude ne lisait que le snake_case : sur un hote en
camelCase il sortait 0 EN SILENCE — aucune trace, donc `tasks.py done` refusant
toute cloture, donc la sortie tracee comme seule issue. Une garde qu'on ne peut
franchir que par son echappatoire ne garde rien.

CE QU'IL NE FAIT PAS, ET NE FERA JAMAIS : lancer les critiques. AUCUN hook de ce
depot n'invoque de modele — le banc zero-LLM des hooks le prouve. Ce script
MESURE ce qui a tourne ; c'est `tasks.py` qui REFUSE.

(Ce banc est cite par son NOM et non par son CHEMIN, et ce n'est pas un detail :
son scanner SUIT les references de chemin trouvees dans un script de hook. Ecrire
son chemin ici le tirait dans son propre perimetre, ou il trouvait la liste des
motifs interdits que sa docstring enumere — un rouge instantane cause par une
simple mention. Mesure le 2026-09-13.)

BUDGET D'EXECUTION, BORNE PARCE QUE L'HOTE BORNE. Les quatre registres donnent
`timeout: 15` a cette entree. Ce script fait DEUX sous-processus, plus celui que
`_common` paie a l'import : d'ou `timeout=4` ici plutot que 5, pour rester sous
le plafond meme dans le pire cas. La doctrine est deja payee ailleurs — « le
budget du hook borne la sonde, l'hote tuerait le hook avant ».

ADVISORY, TOUJOURS `exit 0`. Un hook de fin de sous-agent qui echoue ferme
couterait un sous-agent ; le refus, lui, vit dans `tasks.py`, au seul endroit que
toutes les portes traversent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import ROOT

#: Vocabulaire CLOS, le MEME que `BINOME_CRITIQUES` dans `tasks.py` et que le
#: traceur Claude. Les ecrivains et le lecteur sont lies par un banc : un nom
#: accepte ici et refuse au board produirait une trace qui ne compte pour rien,
#: c'est-a-dire un faux vert.
CRITIQUES = ("critic-opus", "critic-fable", "critic-sonnet-max")


def principale(base: Path) -> Path:
    """La racine du depot PRINCIPAL, lue sur le disque sans git (memes controles que
    `racine_principale`, `tasks_requetes.py`) : `<base>/.git` FICHIER, jamais un lien
    symbolique -> son `gitdir`, dossier DIRECT de `<commun>/worktrees/`, dont le lien
    retour `<gitdir>/gitdir` designe `<base>/.git` -> le parent du `.git` commun.
    Sinon (`.git` dossier, absent, lien, illisible, pointeur forge ou lien retour
    perime) : `base` lui-meme, la ou `tasks.py` a pose focus et portee."""
    try:
        point = base / ".git"
        if point.is_symlink() or not point.is_file():
            return base
        ligne = point.read_text(encoding="utf-8").strip()
        if not ligne.startswith("gitdir:"):
            return base
        gitdir = Path(ligne[len("gitdir:"):].strip())
        gitdir = (gitdir if gitdir.is_absolute() else base / gitdir).resolve()
        commun = Path((gitdir / "commondir").read_text(encoding="utf-8").strip())
        commun = (commun if commun.is_absolute() else gitdir / commun).resolve()
        retour = Path((gitdir / "gitdir").read_text(encoding="utf-8").strip())
        retour = (retour if retour.is_absolute() else gitdir / retour).resolve()
        vrai = gitdir.parent == commun / "worktrees" and retour == point.resolve()
    except (OSError, RuntimeError, ValueError):
        return base
    return commun.parent if vrai and commun.name == ".git" and commun.parent.is_dir() else base


def portee_active(base: Path) -> tuple[dict | None, str | None]:
    """`(portee, None)` si `review-scope.json` est lisible et que son `focus` est celui
    de `focus.json` ; sinon `(None, motif)` — `aucune portee` ou `portee hors focus`."""
    local = principale(base) / ".agents" / "state" / "local"
    try:
        focus = json.loads((local / "focus.json").read_text(encoding="utf-8"))
        portee = json.loads((local / "review-scope.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "aucune portee"
    if not (isinstance(focus, dict) and isinstance(portee, dict)
            and isinstance(portee.get("focus"), str) and isinstance(portee.get("declared_at"), str)
            and isinstance(portee.get("members"), list) and isinstance(portee.get("consumed"), list)):
        return None, "aucune portee"
    if focus.get("task_id") != portee["focus"]:
        return None, "portee hors focus"
    return portee, None


def main() -> int:
    try:
        brut = sys.stdin.read()
    except Exception:
        return 0
    if not brut.strip():
        return 0
    try:
        charge = json.loads(brut)
    except (ValueError, TypeError):
        return 0
    if not isinstance(charge, dict):
        return 0

    agent = str(charge.get("agent_type") or charge.get("agentType") or "").strip()
    if agent not in CRITIQUES:
        return 0

    # LA RACINE VIENT DE `_common`, COMME POUR LES ONZE AUTRES HOOKS DE CE
    # DOSSIER, et c'est un correctif du binome. La premiere redaction resolvait
    # la racine elle-meme en consultant `CLAUDE_PROJECT_DIR` — variable que
    # `_common` ignore — et retombait sur `Path.cwd()` au lieu du KIT. Mesure :
    # avec `CLAUDE_PROJECT_DIR` exporte vers un autre arbre (le profil shell d'un
    # dev qui alterne les hotes), la trace partait dans le MAUVAIS arbre, donc
    # une revue reelle ne comptait pas et la cloture etait refusee sans que rien
    # ne relie la cause a l'effet. Deux hooks du meme dossier qui resolvent la
    # racine differemment sont un defaut en attente.
    tasks_py = ROOT / ".agents" / "bin" / "tasks.py"
    if not tasks_py.exists():
        return 0

    # `None` VEUT DIRE « PAS DE REPONSE » (T-00000845). La premiere redaction
    # rendait `""` sur exception, sur timeout, ET la stdout vide d'une commande
    # sortie non-zero ; l'appelant la completait en `"[]"`, donc un board
    # ILLISIBLE se lisait « aucune running » et le hook se taisait exactement
    # comme dans le cas nominal. rc != 0, timeout ou exception -> `None`.
    #
    # DECODAGE EXPLICITE EN UTF-8 (T-00000845, releve du binome). `tasks.py`
    # ecrit de l'UTF-8 (`ensure_ascii=False`) et le vrai board porte des
    # caracteres non ASCII. `text=True` sans `encoding` decode selon la LOCALE
    # — cp1252 sous Windows : `UnicodeDecodeError`, donc `None`, donc « board
    # illisible » A TORT et aucune trace apres une revue reelle.
    # `errors="replace"` : un octet invalide abime un libelle, pas le board.
    def run(*args: str) -> str | None:
        try:
            p = subprocess.run(
                args, cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=4,
            )
        except Exception:
            return None
        if p.returncode != 0:
            return None
        return p.stdout.strip()

    # LES TACHES VISEES SONT LES MEMBRES DE LA PORTEE DE REVUE (plus bas), jamais
    # chaque `running` : plusieurs `running` coexistent, et la revue de l'une ne
    # couvre pas l'autre.
    #
    # DEUX SILENCES QUI N'EN SONT PLUS UN (T-00000845). Aucune `running` sur un
    # board LU : on n'ecrit rien et on se tait — cas nominal, une trace sans
    # destinataire ne prouverait rien et polluerait. Board ILLISIBLE (`tasks.py
    # list` sorti non-zero, expire, injoignable, ou sortie qui n'est pas une
    # liste JSON) : on n'ecrit rien NON PLUS — le contrat d'ecriture de ce port
    # ne change pas, il n'a pas de nom reserve `_sans-slot` — mais on le dit sur
    # stderr — visibilite cote hote NON MESUREE en exit 0 —, parce qu'une tache
    # pouvait tourner et que sa revue vient de ne laisser aucune trace. Sans
    # cette ligne, « la tache n'etait pas running » et « le board n'a pas
    # repondu » se lisaient pareil : par un silence. Le `print` est lui-meme
    # protege : un stderr ferme ou mal encode ne doit pas faire planter un hook
    # advisory.
    # Pas de repli `or "[]"` : c'est lui qui changeait `None` en board vide ;
    # `tasks.py list --json` rend `[]` LUI-MEME sur un board vide.
    brut = run(sys.executable, str(tasks_py), "--root", str(ROOT), "list", "--json")
    try:
        if brut is None:
            raise ValueError("tasks.py list : rc non nul, expire ou injoignable")
        board = json.loads(brut)
        if not isinstance(board, list):
            raise ValueError("tasks.py list : JSON qui n'est pas une liste")
    except Exception as exc:
        try:
            print(
                f"binome_trace: board illisible ({exc}) -- aucune trace ecrite pour "
                f"{agent}, alors qu'une tache pouvait tourner",
                file=sys.stderr,
            )
        except Exception:
            pass
        return 0
    # LA PORTEE DE REVUE BORNE LA TRACE (T-01M5F728FGJ43QJX1RJKTWWKRB, S-01M5E50ABADJA72966YQF4J285).
    # Plusieurs `running` coexistent : tracer sur chacune ferait crediter A2 par la
    # revue de A1. On ne trace que sur les membres NON consommes et non clos de la
    # portee ACTIVE (`review-scope.json` du depot principal dont le `focus` est celui
    # de `focus.json`), relus contre le board, et chaque trace porte `portee` = son
    # `declared_at`. Sans portee active, rien n'est ecrit (ce port n'a pas de nom
    # reserve) ; une tache tourne pourtant : on le DIT sur stderr, avec le remede.
    lignes = [
        t for t in board
        if isinstance(t, dict) and isinstance(t.get("id"), str) and t["id"]
    ]
    portee, motif = portee_active(ROOT)
    cibles = [
        t["id"] for t in lignes
        if portee is not None and t.get("state") != "done"
        and t["id"] in portee["members"] and t["id"] not in portee["consumed"]
    ]
    if not cibles:
        if any(t.get("state") == "running" for t in lignes):
            try:
                print(
                    f"binome_trace: {motif or 'portee consommee'} -- aucune trace ecrite pour "
                    f"{agent} ; `tasks.py review-scope <T>...` avant le critique",
                    file=sys.stderr,
                )
            except Exception:
                pass
        return 0

    sha = run("git", "rev-parse", "--short", "HEAD") or "?"
    quand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dossier = ROOT / ".agents" / "state" / "local" / "binome"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0

    # UN FICHIER PAR CRITIQUE, et c'est un correctif paye sur Claude : la
    # doctrine lancait deux critiques EN PARALLELE avant S-00004500, et un
    # critique et son repli peuvent encore s'arreter dans la meme fenetre : deux
    # arrets lisaient tous deux l'etat vide et le second ecrasait le premier —
    # une seule entree, donc une cloture REFUSEE apres une revue reellement
    # faite. Rien ne lit avant d'ecrire : plus de course.
    for tid in cibles:
        try:
            (dossier / f"{tid}.{agent}.json").write_text(
                json.dumps({"sha": sha, "at": quand, "portee": portee["declared_at"]},
                           sort_keys=True), encoding="utf-8"
            )
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
