"""LES POINTS D'ENTRÉE ADOPTANTS — `cadre tasks` délègue au moteur du board.

T-00000962 (BK-157), interface décidée par le pilote (S-01M4JPBTF82G4PW7DDDYRSVZC1,
analyse BK-156 § 6-7) : « même verbe, mêmes arguments, mêmes flux (refus et
usage sur stderr, résultat sur stdout), même code de sortie que `tasks.py
--root <racine du projet> <verbe> …` — la racine venant de la résolution de
`cadre`, et non plus de `--root` ou de `CLAUDE_PROJECT_DIR` ». Codes : `0`
succès, `1` réponse négative d'un contrôle (le moteur le pose : `retour`,
`replay-sync`, `commit-stores`/`commit-run-exports --exiger`, `cible-check`),
`2` erreur ou refus. `cadre ledger` et `cadre specs` (T-00000963) s'ajoutent à
`MOTEURS` sous les mêmes règles.

LE MOTEUR EST CELUI DU KIT, JAMAIS CELUI DE L'ADOPTANT. Le board appartient à
`tasks.py` et à ses dix-sept parties, que `cadre` n'importe jamais (voir
`cadre.init.FournisseurBoard`) : il est LANCÉ en sous-processus, par
`Executor`, ce que `check_no_inprocess_load` permet (sa borne 1). `moteur` le
cherche à deux endroits, dans cet ordre :
  1. EMBARQUÉ dans le paquet, `<pkg_root>/_moteur/tasks.py` : la wheel y copie
     en DONNÉES (force-include de `pyproject.toml`, T-00000962) la clôture de
     `tasks.py`, 23 fichiers de `.agents/bin/`. C'est le cas d'une installation
     par la wheel (`uv tool install`) chez un adoptant.
  2. Sinon l'ARBRE SOURCE du kit, `<kit>/.agents/bin/tasks.py`, où `<kit>` est
     trois crans au-dessus de `pkg_root()` sous `.agents/vendor/cadre`, deux
     dans l'ancienne disposition `src/` (`racine_du_kit`) — et
     seulement si `<kit>` porte le marqueur `.agents/IS_THE_KIT` (règle
     `strip:` de `.template-exclude` : une copie par `sync_template.py` ne le
     porte pas, une copie BRUTE du kit si). Un arbre sans marqueur n'est pas le
     kit : son `tasks.py`, peut-être celui d'un adoptant, n'est jamais exécuté.
  3. Ni l'un ni l'autre : refus en 2 (`MoteurIntrouvable`) qui nomme les DEUX
     chemins cherchés, sans rien lancer ni écrire.
Installé par `cadre init`, l'adoptant n'a aucun `.py` du kit dans son projet :
il n'y porte que ses stores. Reçu par la template, il garde
`.agents/bin/tasks.py`, qui pilote le même board : deux versions possibles du
moteur, bornées par `RECORD_FORMAT` (un format plus récent est refusé).

CE QUE LE MOTEUR EMBARQUÉ FAIT AUTREMENT CHEZ L'ADOPTANT, dit plutôt que
découvert — le moteur est un chemin de garde, il n'est pas réécrit ici :
  (a) ÉVÉNEMENTS. Le moteur cherche `events.py` sous `parents[2]` de son propre
      fichier (`replay_sync`, `_charger_events`) : embarqué, c'est le
      site-packages, `<purelib>/.agents/bin/events.py`. Aucun événement n'est
      donc émis chez l'adoptant, `AGENTS_EVENTS_DIR` posé ou non ; seul un
      `events.py` posé sous `<purelib>/.agents/bin/` serait exécuté, celui du
      projet JAMAIS.
  (b) MIROIR V3. `agentic_v3` n'est pas dans la wheel (T-00000887, décision
      S-00001586) : le miroir du board est perdu jusque-là. L'outbox de
      synchronisation est déversée hors du board au-delà de 200 intentions
      (`_deverser_sans_pont`, stderr « agentic_v3 absent de <purelib> »), et le
      remède qu'elle imprime — installer `agentic_v3` — est impossible d'ici là.
  (c) `commit-stores` et `commit-run-exports` restent offerts (décision pilote
      S-01M51E99DY03JJB6XZFK2JF57K, option 1) : ils lancent `bash <racine du
      projet>/.agents/bin/post-task-done-index.sh` — le script du dépôt
      ADOPTANT — et relaient sa DERNIÈRE ligne de sortie ; script absent ou
      muet : `failed`, code 0 ; aucun bash utilisable : `bash-introuvable`.
  (d) Des remèdes que le moteur imprime restent centrés sur le kit
      (`git checkout -- .agents/bin/…`, `specs.py add`, le `python3 -c` de
      `_remedy_line`) : ils ne s'appliquent pas tels quels chez l'adoptant.
  (e) EXPIRATION. La borne de 300 s de `LocalExecutor` tue le moteur, pas ses
      enfants : un `commit-stores` qui expire peut laisser le `bash` qu'il a
      lancé (`post-task-done-index.sh`) committer APRÈS le code 2, verrou du
      board déjà relâché. Relire `git log` avant de rejouer. Tuer le groupe de
      processus relève de `cadre.executor`, pas d'ici.

LA RACINE VIENT DE `cadre`. `project_root()` la résout (`$CADRE_PROJECT_ROOT`,
puis la racine git, puis l'ancêtre portant `.agents/`) ; elle est passée en
`--root` AVANT le verbe et en `CLAUDE_PROJECT_DIR` — le défaut de `--root` du
moteur (`tasks_cli`) ; dans la clôture embarquée, `plan_lots` et `specs` ne le
lisent que dans leur propre `main`, que le moteur n'appelle pas —, pour
qu'aucun canal ne vise un autre arbre que celui de `cadre`. Un `--root` — ou
une abréviation qu'argparse accepterait (`--ro`, `--r`) — placé EN TÊTE par
l'appelant l'emporterait dans le moteur (mesuré : le second `--root` gagne) :
il est refusé en 2 avant tout lancement. Après le verbe, le moteur le refuse
lui-même en 2 (mesuré) et `cadre` ne le juge pas. Le répertoire courant de
l'appelant est GARDÉ : un chemin relatif tapé par l'adoptant garde son sens.

LES CODES RESTENT DANS L'INTERFACE. Ceux du moteur, 0/1/2, passent tels quels,
avec ses deux flux recopiés octet pour octet. Tout autre code — expiration de
la borne de `LocalExecutor` (300 s), exécutable absent (127) ou refusé (126),
signal, code inconnu — devient 2 avec sa cause. Un traceback du moteur (une
exception non rattrapée sort en 1, que l'interface réserve à un contrôle
négatif) devient 2 : la trace interne est retirée, la ligne d'exception
gardée. Les refus propres à `cadre` (pas de racine, pas de moteur, `--root` en
tête, octet nul) sortent en 2 sur stderr, jamais en traceback. Sous Windows
hors mode UTF-8 (T-01M523WZN8WD6YB9RQJJD594ZE) : le moteur n'écrit en UTF-8
qu'après `parse_args` (`force_utf8_stdio`) ; ses erreurs d'argparse sortent
avant, dans l'encodage de ses flux. `deleguer` lui passe donc
`PYTHONIOENCODING=utf-8` — UTF-8 dès son premier octet —, `LocalExecutor`
décode en UTF-8 quel que soit l'encodage local, et `cadre` recopie en UTF-8
(`errors="replace"`, le geste `force_utf8_stdio` du moteur) : `--statusline`
(glyphe ⏸) sort en 0 et une erreur d'usage accentuée sort lisible, avec les
octets de `tasks.py` lancé en UTF-8 (lancé directement sur un pipe cp1252, il
garde ses erreurs d'argparse en cp1252). La variable passe aussi aux enfants
du moteur — `post-task-done-index.sh`, présent dans le kit seul, dont il lit
la dernière ligne en encodage local. Les refus propres à `cadre tasks`
sortent eux aussi en UTF-8 : `deleguer` reconfigure ses flux dès l'entrée.
PÉRIMÈTRE ÉTROIT, PAR DÉCISION : seul `cadre tasks` suit le moteur en UTF-8 ;
`cadre init`, `paths`, `config` et `lessons` restent dans l'encodage local.
MESURÉ par simulation (`PYTHONIOENCODING=cp1252`, `PYTHONUTF8=0`, encodage
local forcé à cp1252), pas sous Windows.

LE NOM RESTE RÉSERVÉ AU VERROU. `cadre tasks` est CÂBLÉE ici, comme `cadre
init` l'a été en partie, mais `tasks` reste dans `RESERVEES` de `cadre.cli` et
`reserve` dans `contract.lock.json` : la bascule réservé→public, la mineure et
la ligne de CHANGELOG appartiennent à T-00000797.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from cadre.executor import ExecutionRefusee, Executor, LocalExecutor, Resultat
from cadre.paths import CadrePathError, pkg_root, project_root
from cadre.workspace import Workspace

__all__ = ["MOTEURS", "MARQUEUR_DU_KIT", "DOSSIER_EMBARQUE", "CODES_DU_CONTRAT",
           "MoteurIntrouvable", "racine_du_kit", "moteur", "deleguer", "cadre_tasks"]

#: Commande `cadre` -> moteur qu'elle délègue, RELATIF à la racine du kit. Dans
#: la wheel, le même fichier vit sous `<pkg_root>/DOSSIER_EMBARQUE/<nom>`.
MOTEURS: dict[str, str] = {"tasks": ".agents/bin/tasks.py"}

#: Le fichier qui distingue l'arbre source du kit de tout autre arbre.
MARQUEUR_DU_KIT = ".agents/IS_THE_KIT"

#: Le dossier, sous la racine du paquet, où la wheel embarque le moteur.
DOSSIER_EMBARQUE = "_moteur"

#: Les codes que l'interface connaît (S-01M4JPBTF82G4PW7DDDYRSVZC1).
CODES_DU_CONTRAT = frozenset({0, 1, 2})

_OPTION_DE_RACINE = "--root"
_TETE_DE_TRACE = "Traceback (most recent call last):"


class MoteurIntrouvable(ValueError):
    """Le moteur délégué n'est pas là où le paquet le cherche, ou l'arbre qui le
    porte n'est pas le kit. Le message nomme le chemin cherché."""


def racine_du_kit(paquet: Path | None = None) -> Path:
    """La racine source du kit, depuis la racine du paquet (`paquet`, défaut
    `pkg_root()`) : `<kit>/.agents/vendor/cadre` -> `<kit>` (trois crans, quand
    le parent `vendor` est sous `.agents`), `<kit>/src/cadre` -> `<kit>` (deux
    crans, ancienne disposition). Hors disposition source (wheel installée), ce
    chemin ne porte pas le marqueur du kit ; le moteur y est cherché EMBARQUÉ
    d'abord (`moteur`)."""
    racine = pkg_root() if paquet is None else paquet
    parent = racine.parent
    if parent.name == "vendor" and parent.parent.name == ".agents":
        return parent.parent.parent
    return parent.parent


def moteur(commande: str, kit: Path | None = None, paquet: Path | None = None) -> Path:
    """Le chemin absolu du moteur de `commande`, ou `MoteurIntrouvable`.

    Ordre : (1) embarqué, `<paquet>/_moteur/<nom>` ; (2) arbre source du kit
    MARQUÉ, `<kit>/<MOTEURS[commande]>` ; (3) refus nommant les deux chemins.
    `paquet` (défaut `pkg_root()`) et `kit` (défaut `racine_du_kit()`) sont
    injectables (bancs). Toute E/S passe par `Workspace`."""
    relatif = MOTEURS[commande]
    embarque = f"{DOSSIER_EMBARQUE}/{Path(relatif).name}"
    livre = Workspace(pkg_root() if paquet is None else paquet)
    if livre.exists(embarque):
        return livre.resolve(embarque)
    atelier = Workspace(racine_du_kit() if kit is None else kit)
    marque = atelier.exists(MARQUEUR_DU_KIT)
    if marque and atelier.exists(relatif):
        return atelier.resolve(relatif)
    if marque:
        cause = f"{atelier.racine / relatif} absent"
    else:
        cause = (f"{atelier.racine} ne porte pas {MARQUEUR_DU_KIT}, ce n'est pas l'arbre "
                 f"source du kit : son {atelier.racine / relatif} n'est jamais exécuté")
    raise MoteurIntrouvable(
        f"moteur du board introuvable — ni embarqué dans le paquet "
        f"({livre.racine / embarque} absent), ni dans l'arbre source du kit ({cause}). "
        "Rien n'a été lancé.")


def _racine_detournee(argv: Sequence[str]) -> str | None:
    """Le jeton d'EN-TÊTE (avant le verbe) qui viserait l'option `--root` du
    moteur, abréviation comprise, ou None. Le premier jeton qui n'est pas une
    option est le verbe : au-delà, le moteur juge seul."""
    for jeton in argv:
        if jeton == "--" or not jeton.startswith("-"):
            return None
        nom = jeton.split("=", 1)[0]
        if len(nom) > 2 and _OPTION_DE_RACINE.startswith(nom):
            return jeton
    return None


def _dire(message: str) -> None:
    print(message, file=sys.stderr)


def _couper_la_trace(texte: str) -> tuple[str, str]:
    """(ce qui précède la trace, dernière ligne non vide = l'exception)."""
    lignes = texte.splitlines(keepends=True)
    debut = next((i for i, ligne in enumerate(lignes)
                  if ligne.rstrip() == _TETE_DE_TRACE), len(lignes))
    finale = next((ligne.strip() for ligne in reversed(lignes) if ligne.strip()), "")
    return "".join(lignes[:debut]), finale


def _flux_comme_le_moteur() -> None:
    """Les flux de `cadre` parlent la langue du moteur : UTF-8, `errors="replace"`.

    Le moteur écrit en UTF-8 dès son premier octet : `PYTHONIOENCODING=utf-8`,
    posé par `deleguer`, couvre ses erreurs d'argparse, qui sortent AVANT son
    propre `force_utf8_stdio()` (`tasks_stockage`) ; `LocalExecutor` le décode
    en UTF-8. Recopié tel quel sur un stdout cp1252 STRICT — un pipe sous
    Windows hors mode UTF-8 —, le glyphe ⏸ de `--statusline` levait
    `UnicodeEncodeError` hors de tout handler (mesuré : traceback, rc 1, le
    code réservé au contrôle négatif). Le même geste que le moteur rend les
    octets du moteur lancé en UTF-8. `getattr` : un flux redirigé
    (`io.StringIO` d'un banc) n'a pas de `reconfigure`, et n'a rien à encoder.
    `reconfigure` vaut pour TOUT le processus, pas pour ce seul appel : sous la
    CLI c'est sa dernière écriture ; un appelant en bibliothèque garde, après
    l'appel, des flux en UTF-8 `errors="replace"`."""
    for flux in (sys.stdout, sys.stderr):
        reconfigure = getattr(flux, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _restituer(nom: str, r: Resultat) -> int:
    """Recopie les deux flux du moteur et rend un code DE L'INTERFACE."""
    trace = any(ligne.rstrip() == _TETE_DE_TRACE for ligne in r.stderr.splitlines())
    sys.stdout.write(r.stdout)
    sys.stdout.flush()
    if r.code in CODES_DU_CONTRAT and not r.expire and not (trace and r.code != 0):
        sys.stderr.write(r.stderr)
        sys.stderr.flush()
        return r.code
    avant, exception = _couper_la_trace(r.stderr) if trace else (r.stderr, "")
    sys.stderr.write(avant)
    if avant and not avant.endswith("\n"):
        sys.stderr.write("\n")
    if r.expire:
        cause = "le moteur du board a dépassé sa borne et a été arrêté"
    elif trace:
        cause = (f"le moteur du board a levé une exception non rattrapée ({exception}) "
                 "— trace interne retirée")
    else:
        cause = f"le moteur du board a rendu le code {r.code}, hors de l'interface (0, 1, 2)"
    _dire(f"{nom} : {cause}. Son effet est à relire (`{nom} list`). Code rendu : 2.")
    return 2


def deleguer(commande: str, argv: Sequence[str], *, executeur: Executor | None = None,
             kit: Path | None = None, paquet: Path | None = None) -> int:
    """`cadre <commande> <argv…>` -> `<moteur> --root <racine> <argv…>`.

    `executeur`, `kit` et `paquet` sont injectables (bancs) ; par défaut
    `LocalExecutor`, `racine_du_kit()` et `pkg_root()`. Rend toujours 0, 1 ou
    2, jamais une exception."""
    # EN TÊTE, PAS DANS `_restituer` : les refus ci-dessous parlent la même
    # langue que le moteur qu'ils remplacent (mesuré : `refus\xe9` en cp1252 à
    # côté d'un `été` en UTF-8 quand l'appel ne couvrait que la recopie).
    _flux_comme_le_moteur()
    nom = f"cadre {commande}"
    args = [str(a) for a in argv]
    detourne = _racine_detournee(args)
    if detourne is not None:
        _dire(f"{nom} : `{detourne}` refusé — la racine du projet vient de cadre "
              "($CADRE_PROJECT_ROOT, sinon la racine git), jamais de --root. Rien "
              "n'a été lancé.")
        return 2
    try:
        racine = project_root()
        chemin = moteur(commande, kit, paquet)
    except (CadrePathError, MoteurIntrouvable, OSError) as exc:
        _dire(f"{nom} : {exc}")
        return 2
    lanceur = LocalExecutor() if executeur is None else executeur
    try:
        # CELUI QUI DÉCODE NOMME L'ENCODAGE. `LocalExecutor` décode en UTF-8 ;
        # le moteur n'écrit en UTF-8 qu'APRÈS `parse_args` (`force_utf8_stdio`),
        # et ses erreurs d'argparse sortaient dans l'encodage de ses flux —
        # mesuré : `--state été` rendu `�t�` sous un pipe cp1252.
        r = lanceur.run([sys.executable, str(chemin), "--root", str(racine), *args],
                        env={"CLAUDE_PROJECT_DIR": str(racine), "PYTHONIOENCODING": "utf-8"})
    except ExecutionRefusee as exc:
        _dire(f"{nom} : commande refusée avant lancement ({exc}). Rien n'a été lancé.")
        return 2
    return _restituer(nom, r)


def cadre_tasks(argv: Sequence[str], *, executeur: Executor | None = None,
                kit: Path | None = None, paquet: Path | None = None) -> int:
    """`cadre tasks …` : le board, par son moteur."""
    return deleguer("tasks", argv, executeur=executeur, kit=kit, paquet=paquet)
