# tasks_gardes.py — PARTIE de `tasks.py` (T-00000788) : les GARDES — chaîne de
# plan, cible de plan, dépendances de plan, binôme de clôture (ses
# constantes `BINOME_*` restent dans la façade). Exécutée dans l'espace de noms
# de `tasks` par `_charger_parties()`, jamais importée seule.

from __future__ import annotations

# ---------------------------------------------------------------------------
# LA CHAÎNE DE PLAN (T-00000624) — L'AUTRE BOUT DU MÊME CONTRAT
# ---------------------------------------------------------------------------
# `T-00000586` a rendu mécanique la CLÔTURE : des critiques tracés par l'hôte
# (`BINOME_MIN`, UN depuis S-00004500), et `done` refuse sans eux. L'OUVERTURE — `planner` → `plan-critic` → porte
# humaine — restait tenue par la seule mémoire de l'orchestrateur, c'est-à-dire
# exactement l'état que le binôme de clôture a quitté.
#
# *** TROIS TUPLES SÉPARÉS, ET AUCUN NE DOIT FUSIONNER AVEC `BINOME_CRITIQUES`.***
# Fusionner ferait accepter UN critique de PLAN comme revue de CLÔTURE : la
# garde la plus lourde du dépôt franchie par un plan jamais relu APRÈS
# implémentation. Les traces vivent d'ailleurs dans un dossier SÉPARÉ
# (`plan/` et non `binome/`), pour que la confusion soit impossible et pas
# seulement interdite — `plan-critic-sonnet-max` contient la sous-chaîne
# `critic`, et ce dépôt a déjà mesuré qu'un `startswith` trop large suffisait à
# satisfaire une garde avec un fichier posé à la main.
#
# *** UN CRITIQUE DE PLAN, UN PLAN (décision pilote S-00003871, 2026-10-03). ***
# `plan-critic` est LE critique et `planner` LE planner. Jusqu'à S-00003871 la
# garde exigeait DEUX critiques.
#
# POURQUOI LES TUPLES GARDENT DEUX NOMS (décision pilote S-01M4TZZ13Y,
# 2026-10-13 : la planification se fait sur Opus seul). `planner-sonnet` et
# `plan-critic-sonnet-max` sont DÉBRANCHÉS, pas supprimés : l'orchestrateur ne
# les invoque plus et le refus ne les propose plus en remède, mais une trace
# fraîche de l'un d'eux (moins de `PLAN_TRACE_TTL_HEURES`, 24 h) reste ACCEPTÉE
# — une chaîne lancée avant la décision finit sans être refusée. Retirer un nom
# d'ici est un retrait, soumis à la règle des deux passes.
PLAN_REVIEWERS = ("plan-critic", "plan-critic-sonnet-max")
PLAN_PLANNERS = ("planner", "planner-sonnet")
PLAN_GATE = Path(".agents") / "state" / "gates" / "PLAN_CHAIN_REQUIRED"
PLAN_TRACES = Path(".agents") / "state" / "local" / "plan"
PLAN_JOURNAL = Path(".agents") / "state" / "local" / "plan-chain-consommations.log"


_PLAN_CIBLE_MOD: Any = None


def plan_cible_module() -> Any:
    """Charge `plan_cible` (module FRÈRE, stdlib seule) SANS l'importer en tête.

    `plan_cible` ne dépend de RIEN de `tasks` — c'est l'isolation D6 : il reçoit
    le `data` du board et relit `SPECS.json` lui-même, il ne prend jamais
    `board_lock`. Un import paresseux évite donc de coupler le chargement du
    board à celui du verrou de cible, et l'import est robuste que `tasks.py` soit
    lancé comme SCRIPT (le dossier `bin/` est déjà `sys.path[0]`) ou chargé par
    `spec_from_file_location` (les bancs, où il ne l'est pas) : on ajoute le
    dossier de CE fichier avant l'import.
    """
    global _PLAN_CIBLE_MOD
    if _PLAN_CIBLE_MOD is None:
        bin_dir = str(Path(__file__).resolve().parent)
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        try:
            import plan_cible as _pc
        except ModuleNotFoundError:
            # MODULE FRÈRE ABSENT = GARDE INERTE, jamais une trace (mesuré le
            # 2026-09-18 : `run-recap.test.sh` copie `tasks*.py` sans ce module dans un dépôt
            # jetable puis appelle `start` — la porte rougissait sur un traceback,
            # pas sur une propriété). Même polarité que le marqueur absent : pas de
            # mécanisme, pas de contrainte. BORNE écrite : sur CE dépôt le module
            # est livré à côté de `tasks.py`, donc ce chemin ne désarme rien ici ;
            # il protège les harnais et les copies partielles.
            return None

        _PLAN_CIBLE_MOD = _pc
    return _PLAN_CIBLE_MOD


_CIBLE_MARQUEUR_REL = Path(".agents") / "state" / "gates" / "PLAN_CIBLE_REQUIRED"

_REFUS_CIBLE_INEXPLOITABLE = (
    "TASKS: refus de {geste} — garde de cible ARMÉE mais INEXPLOITABLE. Le "
    "marqueur `.agents/state/gates/PLAN_CIBLE_REQUIRED` est présent, mais "
    "`.agents/bin/plan_cible.py` est ABSENT : la contrainte est déclarée et "
    "rien ne peut la vérifier.\n"
    "Remède : `git checkout -- .agents/bin/plan_cible.py` (le module est suivi), "
    "ou retire le marqueur si le désarmement est voulu — un désarmement est un "
    "geste, pas un effet de bord.\n"
    "Sortie tracée : `--sans-cible \"<pourquoi>\"`, visible au board."
)


def cible_inexploitable(root: str | os.PathLike[str]) -> bool:
    """ARMÉE MAIS INEXPLOITABLE : le marqueur est là, `plan_cible.py` ne l'est pas.

    C'EST UN REFUS, PAS UN DÉSARMEMENT (revue de clôture T-00000654, C3/T6). Le
    premier état livré traitait « module absent » comme « garde inerte » PARTOUT,
    et ouvrait une échappatoire à DEUX gestes, mesurée par le binôme : un
    `git rm .agents/bin/plan_cible.py` — que `safe-bash` ne refuse pas, son
    `decide_git()` ne connaissant que `clean`/`restore`/`checkout` — suffisait à
    rendre `start` et `done` muets, SANS même écrire la marque `[SANS CIBLE]` qui
    aurait laissé une trace au board. La contrainte disparaissait sans un octet.

    ET `safe-bash` NE SERA PAS ÉLARGI — décision pilote du 2026-09-18, tracée
    `S-00001569` : `git rm` sur un fichier suivi reste AUTORISÉ, la mesure
    touchant les cinq hôtes pour une famille où des gestes légitimes existent.
    Ce refus-ci est donc le SEUL filet, et il ne fait pas ce qu'on pourrait lui
    prêter : il n'empêche pas le fichier de PARTIR, il empêche que son départ
    rende la garde MUETTE. Dit plutôt que découvert.

    La borne « module absent = inerte » reste VRAIE là où elle a été mesurée et
    où elle sert — un harnais qui copie `tasks*.py` sans ce module dans un dépôt jetable
    (`run-recap.test.sh`) n'a pas de marqueur : rien n'y est armé, donc rien n'y
    est refusé. Ce que ce test ajoute, c'est que les deux faits doivent CONCORDER
    : pas de marqueur ET pas de module = inerte ; marqueur SANS module = refus.
    Le marqueur se teste par le SYSTÈME DE FICHIERS et non par le module, sans
    quoi la question se répondrait par l'objet même qui manque.
    """
    if plan_cible_module() is not None:
        return False
    return (Path(root) / _CIBLE_MARQUEUR_REL).exists()


def cible_marqueur_present(root: str | os.PathLike[str]) -> bool:
    """Vrai si le marqueur PLAN_CIBLE_REQUIRED est ARMÉ (présent), même malformé.

    DÉCISION ORCHESTRATEUR (T-00000654) : la marque `[SANS CIBLE : …]` ne
    s'écrit au board QUE si le marqueur existe. Sans ce test, un adoptant
    DÉSARMÉ (marqueur absent) verrait la marque sur chaque clôture `--sans-cible`
    passant par le pont V3 ou le tableau de bord — une dérogation affichée là où
    aucune contrainte n'est armée. Un marqueur MALFORMÉ compte comme PRÉSENT : le
    chantier est bien sous contrainte, seule sa lecture a échoué, et la garde de
    cible elle-même refusera fail-closed sur le chemin sans `--sans-cible`.
    """
    _pc = plan_cible_module()
    if _pc is None:
        # MODULE ABSENT : on répond par le SYSTÈME DE FICHIERS et non par `False`
        # (revue de clôture T-00000654, C3bis). Répondre `False` faisait taire la
        # marque `[SANS CIBLE : …]` exactement dans le cas où elle est la plus
        # nécessaire — une garde armée que plus rien n'exécute.
        return (Path(root) / _CIBLE_MARQUEUR_REL).exists()
    try:
        return _pc.lire_marqueur(root) is not None
    except _pc.CibleError:
        return True


_PLAN_DEPENDS_MOD: Any = None


def plan_depends_module(lecture: bool = False) -> Any:
    """Charge `plan_depends` (frère, T-00000765) SANS l'importer en tête — copie de `plan_cible_module`. Absent ⇒
    `None` : inerte sans marqueur, refus sinon. `lecture=True` (aide, depends-show) : CASSÉ ⇒ `None` aussi."""
    global _PLAN_DEPENDS_MOD
    if _PLAN_DEPENDS_MOD is None:
        bin_dir = str(Path(__file__).resolve().parent)
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        try:
            import plan_depends as _pd
        except (Exception if lecture else ModuleNotFoundError):  # une LECTURE ne plante jamais (exec-critic T-765)
            return None
        _PLAN_DEPENDS_MOD = _pd
    return _PLAN_DEPENDS_MOD


# Deux refus décidés ICI (un module absent ne peut pas se refuser lui-même) ; « absent » couvre son import (opus T4).
_DEPENDS_ABSENT = "`.agents/bin/plan_depends.py` ou son import `plan_cible.py` est ABSENT"
_DEPENDS_REMEDE = "Remède : `git checkout -- .agents/bin/plan_depends.py .agents/bin/plan_cible.py`"
_REFUS_DEPENDS_INEXPLOITABLE = (
    "TASKS: refus de {geste} — garde des dépendances de plan ARMÉE mais INEXPLOITABLE : `PLAN_CIBLE_REQUIRED` est "
    f"présent, {_DEPENDS_ABSENT}. Rien n'est écrit : un module retiré ne rouvre pas l'effacement d'un ORDRE "
    f"PILOTE.\n{_DEPENDS_REMEDE}, ou retire le marqueur.")
_REFUS_DEPENDS_VERBE_SANS_MODULE = (
    "TASKS: refus de {geste} — verbe T-00000765 sans comportement d'avant sur lequel "
    f"retomber, et {_DEPENDS_ABSENT}.\n{_DEPENDS_REMEDE}.")


def plan_chain_trace(root: str | os.PathLike[str]) -> dict[str, dict[str, Any]]:
    """Les defs de plan QUI ONT RÉELLEMENT TOURNÉ, par nom.

    Écrit par l'HÔTE sur `SubagentStop` (`.agents/bin/plan_trace.py`), jamais
    par l'agent qui se relirait lui-même.

    PAS D'IDENTIFIANT DE TÂCHE, et c'est mesuré plutôt que choisi : au moment où
    ces defs tournent la tâche n'est pas encore `running` — la chaîne PRÉCÈDE
    `start` —, et viser la `running` du moment attribuerait les verdicts d'une
    tâche à une AUTRE. Sur ce dépôt le chantier T-012 tourne en permanence et
    aurait tout absorbé. L'attribution est donc portée par la CONSOMMATION :
    une chaîne de verdicts autorise exactement UN `start`, et c'est journalisé.
    """
    vus: dict[str, dict[str, Any]] = {}
    d = Path(normalize_root(root)) / PLAN_TRACES
    for nom in PLAN_REVIEWERS + PLAN_PLANNERS:
        try:
            charge = json.loads((d / f"{nom}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # UNE CHARGE INCOMPLÈTE N'EST PAS UNE PREUVE. `isinstance(charge, dict)`
        # seul acceptait `{}` : trois fichiers vides suffisaient à franchir la
        # garde, et le journal de consommation écrivait alors `plan-critic@?`,
        # c'est-à-dire une ligne d'attribution qui ne nomme rien. Mesuré par le
        # binôme de clôture sur `ffa66b0`.
        if isinstance(charge, dict) and charge.get("at") and charge.get("sha"):
            vus[nom] = charge
    return vus


# LES TRACES PÉRIMENT, et c'est un défaut que `T-00000592` a dû corriger APRÈS
# COUP sur le binôme de clôture : sans péremption, UNE chaîne couvre tous les
# démarrages à venir. Mesuré sur ce dépôt le 2026-09-15 — une chaîne complète
# datée de la veille, à deux SHA de distance, attendait d'autoriser le prochain
# `start`.
#
# POURQUOI UNE DURÉE ET NON L'ANCRAGE `VERIFY_STAMP` DU BINÔME : la chaîne de
# plan PRÉCÈDE toute porte, donc il n'existe aucun verdict vert auquel l'ancrer.
# 24 h est un DÉFAUT, pas une mesure — le pilote peut le trancher autrement, et
# c'est ici la seule valeur à changer.
PLAN_TRACE_TTL_HEURES = 24

# BORNE D'ÂGE DE L'EMPRUNT SANS BORNE DE PORTE (T-00000846, décision pilote du
# 2026-09-30). Sans deux verts `frozen` distincts dans `VERIFY_STAMP.log` (tout
# clone neuf : le journal est git-ignoré), `cycle_precedent` rend None et
# l'emprunt ne périmait JAMAIS (fail-open, critic-fable sur T-00000840). Il faut
# désormais `BINOME_MIN` critique(s) distinct(s) (UN depuis S-00004500) dont
# l'`at` a moins de ce nombre d'heures.
# CONSTANTE SEULE, comme `PLAN_TRACE_TTL_HEURES` et le `12 * 3600` de la garde
# jumelle : aucun précédent de surcharge par l'environnement dans le kit.
EMPRUNT_SANS_BORNE_TTL_HEURES = 24
#: L'avance d'horloge TOLÉRÉE sur l'`at` d'une trace empruntée (T-00000846).
EMPRUNT_AVANCE_TOLEREE = timedelta(minutes=5)


def _date_trace_brute(at: object) -> datetime | None:
    """`at` au format STRICT des traceurs (`%Y-%m-%dT%H:%M:%SZ`), en UTC, ou None.
    Ne juge PAS le futur : c'est `_date_trace`."""
    try:
        return datetime.strptime(str(at), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _date_trace(at: object) -> datetime | None:
    """`at` DATABLE en UTC, ou None : absent, malformé ou futur. On tolère 5 min
    d'avance — recul NTP, horloge WSL/VM ; au-delà, un `at` futur rendrait
    l'emprunt frais pour toujours, le défaut même que T-00000846 ferme."""
    quand = _date_trace_brute(at)
    if quand is None or quand > datetime.now(timezone.utc) + EMPRUNT_AVANCE_TOLEREE:
        return None
    return quand


def plan_chain_perimees(vus: dict[str, dict[str, Any]]) -> list[str]:
    """Les noms dont la trace est trop vieille — retirés de `vus` EN PLACE.

    Comparaison sur la chaîne ISO, qui est lexicographiquement ordonnée tant que
    le format est celui que le traceur écrit (`%Y-%m-%dT%H:%M:%SZ`, UTC, longueur
    fixe). Une charge dont `at` n'a pas cette forme est traitée comme PÉRIMÉE, et
    non comme valide : le sens sûr de l'erreur.
    """
    limite = (datetime.now(timezone.utc)
              - timedelta(hours=PLAN_TRACE_TTL_HEURES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    perimees = sorted(n for n, c in vus.items() if str(c.get("at") or "") < limite)
    for nom in perimees:
        vus.pop(nom)
    return perimees


def plan_chain_refusal(root: str | os.PathLike[str], tid: str) -> str | None:
    """Le refus, ou `None`. ARMÉ PAR LA PRÉSENCE du marqueur, absent du kit ; la
    sync template le SÈME chez l'adoptant, qui naît donc ARMÉ (sortie tracée).

    CE QU'ELLE PROUVE, ET IL FAUT LE LIRE AVANT DE S'EN SERVIR : que les defs
    ont TOURNÉ. Jamais que leur travail était bon, jamais que le verdict final
    était GO — `SubagentStop` porte le NOM de la def, pas son verdict, et
    l'entrée `kind=verdict` de SPECS est saisie par l'orchestrateur, donc
    auto-déclarative. Ça empêche d'OUBLIER, pas de TRICHER.
    """
    racine = Path(normalize_root(root))
    if not (racine / PLAN_GATE).exists():
        return None
    vus = plan_chain_trace(root)
    perimees = plan_chain_perimees(vus)
    # LE RÔLE DÉCLARÉ EST CROISÉ AVEC LE NOM DE FICHIER, sinon `role` est un champ
    # écrit et jamais lu — c'est-à-dire une garantie apparente que rien ne tient.
    # Relevé par le binôme : le banc posait `"role": "x"` sans que rien ne bronche.
    relecteurs = sorted(n for n, c in vus.items()
                        if n in PLAN_REVIEWERS and c.get("role") == "reviewer")
    planners = sorted(n for n, c in vus.items()
                      if n in PLAN_PLANNERS and c.get("role") == "planner")
    if relecteurs and planners:
        return None
    manque = []
    if perimees:
        manque.append(
            f"trace(s) PÉRIMÉE(S), ignorée(s) : {', '.join(perimees)} — une trace "
            f"de plus de {PLAN_TRACE_TTL_HEURES} h ne couvre plus un démarrage, "
            f"sinon UNE chaîne couvrirait tous les démarrages à venir"
        )
    if not relecteurs:
        manque.append(
            f"aucun critique de plan tracé (attendu : `{PLAN_REVIEWERS[0]}`)"
        )
    if not planners:
        manque.append("aucun plan tracé (attendu : `planner`)")
    detail = "".join(f"  - {m}\n" for m in manque)
    return (
        f"TASKS: refus de démarrer {tid} — la chaîne de plan n'est pas tracée.\n"
        f"{detail}"
        f"L'exigence : UN critique de plan (décision pilote S-00003871) et UN "
        f"plan. Planification sur Opus seul (décision pilote S-01M4TZZ13Y) : "
        f"au NO_GO, `planner` reprend son plan avec les constats du critique ; "
        f"`plan-critic` indisponible = COVERAGE DEGRADED, verdict absent.\n"
        f"Remède : fais tourner la chaîne — `planner`, puis `plan-critic` sur le "
        f"plan. La trace est écrite par l'hôte, tu n'as rien à poser.\n"
        f"Petite tâche ({MAX_FICHIERS_DIRECT} fichiers ou moins, sans garde, sans "
        f"décision ni sécurité ouverte) : la voie directe — `tasks.py direct {tid}` "
        f"la VÉRIFIE par code et l'estampille, puis `start` passe sans chaîne.\n"
        f"Sortie tracée si la tâche ne mérite pas la chaîne (coquille, renommage, "
        f"ticket caduc) ou si `plan-critic` est indisponible (quota ; motif "
        f"`plan-critic indisponible — COVERAGE DEGRADED, verdict absent`) : "
        f"`tasks.py start {tid} --sans-chaine \"<pourquoi>\"`. "
        f"La raison reste VISIBLE au board : l'exception se voit, l'oubli ne "
        f"passe plus."
    )


def consume_plan_chain(root: str | os.PathLike[str], tid: str) -> None:
    """CONSOMME les traces — journalisées D'ABORD, effacées ENSUITE.

    C'est ce qui porte l'attribution que la trace elle-même ne porte pas : une
    chaîne de verdicts autorise EXACTEMENT UN démarrage. Sans consommation, le
    premier plan d'un chantier aurait couvert tous ses `start` indéfiniment —
    c'est le défaut que `T-00000592` a dû corriger après coup sur le binôme de
    clôture, et qu'on ferme ici dès le premier jour.

    FAIL-CLOSED SUR LE JOURNAL, même forme que la sortie de `pre-push` : si on
    ne peut pas écrire la ligne, on n'efface RIEN et on lève. Une consommation
    muette est précisément ce qui rend une dérogation réutilisable sans trace.
    """
    racine = Path(normalize_root(root))
    vus = plan_chain_trace(root)
    if not vus:
        return
    ligne = "\t".join([
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tid,
        ",".join(f"{n}@{c.get('sha', '?')}" for n, c in sorted(vus.items())),
    ])
    journal = racine / PLAN_JOURNAL
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as fh:
            fh.write(ligne + "\n")
    except OSError as exc:
        raise BoardError(
            f"TASKS: refus de démarrer {tid} — la chaîne de plan est tracée mais "
            f"le journal de consommation n'a pas pu être écrit ({exc}). On "
            f"n'efface rien : une consommation muette rendrait la même chaîne de "
            f"verdicts réutilisable indéfiniment. Répare "
            f"`{PLAN_JOURNAL}` puis recommence."
        ) from exc
    # *** ON N'EFFACE QUE CE QU'ON A JOURNALISÉ. ***
    # Le traceur écrit HORS du verrou du board (`plan_trace.py` tourne sur
    # `SubagentStop`, pas sous `board_lock`), et une def de la chaîne peut s'arrêter
    # PENDANT un `start` : une trace NEUVE peut donc apparaître entre la
    # lecture de `vus` et cet effacement, et serait détruite sans jamais figurer
    # dans la ligne de journal — c'est-à-dire une chaîne payée puis perdue.
    #
    # LA SÉMANTIQUE EST EXPLICITE, parce que la critique de plan a eu raison de
    # la réclamer : une trace RÉÉCRITE n'est PAS un manque. Elle est laissée en
    # place et le démarrage continue — elle appartient à la chaîne SUIVANTE, et
    # la détruire coûterait un cycle complet. Seule une trace qu'on ne peut pas
    # effacer est un manque, parce que celle-là resterait consommable une
    # seconde fois.
    #
    # CE QUE ÇA NE FERME PAS, dit plutôt que découvert : relire-puis-effacer
    # reste un TOCTOU. La fenêtre passe de « toute la durée du démarrage » à
    # « entre le `read_text` et l'`unlink` », elle ne disparaît pas. La fermer
    # vraiment demanderait que le traceur prenne le verrou du board, ce qu'un
    # hook `SubagentStop` advisory ne peut pas faire sans risquer de bloquer un
    # sous-agent.
    manques = []
    for nom in vus:
        chemin = racine / PLAN_TRACES / f"{nom}.json"
        try:
            if json.loads(chemin.read_text(encoding="utf-8")) != vus[nom]:
                continue
            chemin.unlink()
        except (OSError, ValueError) as exc:
            manques.append(f"{nom} ({exc})")
    if manques:
        raise BoardError(
            f"TASKS: {tid} — la chaîne de plan a été journalisée mais des traces "
            f"n'ont pas pu être effacées : {', '.join(manques)}. Elles resteraient "
            f"consommables une seconde fois. Retire-les à la main avant de "
            f"redémarrer quoi que ce soit."
        )


def binome_trace(root: str | os.PathLike[str], tid: str) -> dict[str, Any]:
    """Les critiques QUI ONT RÉELLEMENT TOURNÉ sur cette tâche, et sur quel SHA.

    La trace est écrite sur `SubagentStop` par le traceur de l'hôte —
    `.claude/hooks/binome-trace.sh`, ou son jumeau verbatim
    `.codex/hooks/binome_trace.py` / `.gemini/hooks/binome_trace.py` pour les
    cinq autres —, à partir du champ `agent_type` (ou `agentType`, les hôtes ne
    le nomment pas pareil) que la charge porte — donc par le HÔTE, pas par
    l'agent qui se relit lui-même. Un fichier absent, illisible ou d'une
    autre forme est ignoré : cette fonction ne juge pas, elle relève.

    UN FICHIER PAR CRITIQUE, ET C'EST UN CORRECTIF DU BINÔME DE CLÔTURE. La
    première version tenait un seul fichier par tâche, lu-modifié-réécrit à
    chaque passage. La règle actuelle (S-00004500) est UN critique de clôture,
    repli en série (`critic-fable`, puis `critic-sonnet-max`) ; mais un critique
    et son repli peuvent encore s'arrêter dans la même fenêtre, qui lisaient
    l'état vide, et le second écrasait le premier — une seule entrée perdue.
    Le mécanisme aurait échoué sur le cas qu'il existe pour servir. Ici chaque critique écrit
    SON fichier : plus aucune lecture-modification-écriture, donc plus de
    course, et un fichier tronqué ne coûte que sa propre entrée."""
    d = Path(normalize_root(root)) / BINOME_TRACES
    vus: dict[str, Any] = {}
    for nom in BINOME_CRITIQUES:
        try:
            vus[nom] = json.loads((d / f"{tid}.{nom}.json").read_text(encoding="utf-8"))
        except Exception:
            continue
    return vus


def purge_binome_trace(root: str | os.PathLike[str], tid: str) -> list[str]:
    """Périme la preuve de revue d'une tâche, et DIT ce qu'elle a retiré.

    Deux appelants : `reopen` (qui ignore le retour) et le verbe `binome-purge`
    (T-00000842), qui l'imprime. Ce second appelant existe parce que le parcours
    du matin de `/night` doit purger les traces DIRECTES d'une tâche livrée la
    nuit — `binome_preuve` ne les périme jamais — et que le `rm` qu'il
    prescrivait est refusé par `safe-bash.sh` (« outside »). Rend les noms des
    critiques dont la trace a été retirée, dans l'ordre de `BINOME_CRITIQUES`."""
    d = Path(normalize_root(root)) / BINOME_TRACES
    retires: list[str] = []
    echecs: list[str] = []
    for nom in BINOME_CRITIQUES:
        chemin = d / f"{tid}.{nom}.json"
        try:
            chemin.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            # ABSENT ET INEFFAÇABLE NE SE CONFONDENT PAS (revue T-00000842) : une
            # trace qu'on n'a pas pu retirer reste une preuve DIRECTE au `done` —
            # mesuré, `chmod 555` sur le dossier : « aucune trace », rc 0, puis
            # `done` passait sans le binôme du matin. Même règle que les traces
            # de plan plus haut : on REFUSE plutôt que de laisser consommable.
            echecs.append(f"{chemin.name} ({exc})")
            continue
        retires.append(nom)
    if echecs:
        raise BoardError(
            f"TASKS: {tid} — traces de binôme NON effacées : {', '.join(echecs)}"
            + (f" (effacées : {', '.join(retires)})" if retires else "")
            + ". Elles resteraient une preuve DIRECTE au `done`. Rends le dossier "
            "inscriptible puis rejoue `tasks.py binome-purge`."
        )
    return retires


def cycle_precedent(root: str | os.PathLike[str]) -> str | None:
    """L'`at` de l'AVANT-DERNIER verdict vert, ou None si on ne peut pas mesurer.

    LA BORNE QUI FAIT EXPIRER UN EMPRUNT (T-00000592). Le tampon seul ne dit que
    le dernier cycle ; il ne permet donc pas de distinguer une revue tombée dans
    le cycle COURANT d'une revue vieille de trois jours. `verify.sh` tient
    désormais un historique append-only des verdicts verts, et l'avant-dernière
    ligne est exactement la frontière cherchée : une trace postérieure à elle
    appartient au cycle courant.

    POURQUOI PAS LE SHA DU TAMPON COURANT, qui semblait l'évidence et que le
    ticket recommandait : le binôme passe AVANT la porte, donc la trace naît
    TOUJOURS avec le sha précédent. Mesuré à la clôture de `T-00000591` — trace
    `@ e5beb66` pendant que le tampon portait `97ab48d`. Cette règle-là aurait
    refusé le cas NOMINAL, et les aurait refusés TOUS.

    NONE VEUT DIRE « PAS MESURABLE », JAMAIS « PÉRIMÉ » : un dépôt neuf, un
    historique absent ou un premier cycle n'ont pas d'avant-dernière ligne. On
    ne refuse jamais sur une mesure de PORTE qu'on n'a pas pu faire. Sur None,
    `done` retombe depuis T-00000846 (décision pilote du 2026-09-30) sur la
    borne d'ÂGE `EMPRUNT_SANS_BORNE_TTL_HEURES` (24 h) : avant, il n'appliquait
    AUCUNE fenêtre et un emprunt n'expirait jamais — fail-open sur tout clone
    neuf. La garde jumelle, elle, retombe sur 12 h : les deux ont désormais une
    fenêtre sur None, mais PAS LA MÊME durée — divergence qui reste CONNUE.

    UN JOURNAL ILLISIBLE N'EST PAS TRAITÉ ICI, ET C'EST ÉCRIT PLUTÔT QUE CORRIGÉ
    (décision pilote par défaut du 23/09, critic-opus T5, mesuré) : un octet non
    UTF-8 (0xFF) lève `UnicodeDecodeError`, donc un traceback au `done` ; un
    problème de DROITS est un `OSError`, donc None MUET — l'emprunt retombe
    alors sur la borne d'âge de 24 h (T-00000846), sans que rien ne dise que
    la borne de porte a été perdue.

    UNE JUMELLE RECOPIE CETTE DÉFINITION (S-00001884, D1 = A) :
    `.claude/hooks/affirmation-guard.sh::_verts_frozen`. Toute modification ici
    se reporte là-bas ; `.agents/evals/test_affirmation_guard_fenetre.py::
    PariteJumellesTests` fait lire le MÊME journal aux deux et rougit si leurs
    bornes divergent."""
    chemin = Path(normalize_root(root)) / ".agents" / "state" / "local" / "VERIFY_STAMP.log"
    try:
        lignes = [l for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return None
    # DEUX FILTRES, ET LES DEUX SONT DES CORRECTIFS DU BINÔME DE CLÔTURE, qui
    # les a mesurés indépendamment l'un de l'autre.
    #
    # (1) UN VERDICT `live` NE BORNE RIEN. La forme nue de `verify.sh` mesure
    #     l'arbre VIVANT et écrit `mode=live` ; `.githooks/pre-push` la REFUSE
    #     au push. La laisser déplacer la borne périmerait une revue valide sur
    #     un verdict qui ne vaut rien — mesuré : binôme 11:00, forme nue 11:30,
    #     `--at` 12:00, et la clôture était refusée.
    #
    # (2) DEUX VERTS SUR LE MÊME SHA SONT UN SEUL CYCLE. Rejouer une porte —
    #     après un flake, ou parce que le hook post-`done` a commité l'état —
    #     comptait pour deux cycles et périmait la revue du lot qu'on ferme.
    #     C'est exactement le cas que `test_le_LOT_legitime_passe_ENTIER`
    #     prétendait couvrir, et qui devenait faux hors du banc.
    cycles: list[tuple[str, str]] = []
    for ligne in lignes:
        champs = dict(c.split("=", 1) for c in ligne.split("\t") if "=" in c)
        if champs.get("mode", "").strip() != "frozen":
            continue
        at = champs.get("at", "").strip()
        sha = champs.get("sha", "").strip()
        if not at or at == "unknown":
            continue
        if cycles and cycles[-1][1] == sha:
            continue  # même sha = même cycle ; on garde la PREMIÈRE borne
        cycles.append((at, sha))
    if len(cycles) < 2:
        return None
    return cycles[-2][0]


# ---------------------------------------------------------------------------
# LA PORTÉE DE REVUE BORNE LA PREUVE (T-01M5F728FGJ43QJX1RJKTWWKRB, lot C de
# T-01M5DBFPWCXH54VW0VMN8HWRX7 ; S-01M5E50ABADJA72966YQF4J285). Plusieurs `running`
# coexistent : la revue de A1 ne crédite plus A2. Le traceur n'écrit que sur les
# membres NON consommés de la portée ACTIVE (`review-scope.json` dont le focus est
# celui de `focus.json`) et ESTAMPILLE la trace de son `declared_at` ; sans portée,
# `_sans-slot`, qui ne crédite personne. Ce lecteur tient l'autre moitié : une trace
# estampillée ne vaut que sous la portée active qui couvre l'emprunteur, au même
# `declared_at` et datée à ou après lui — une nouvelle déclaration invalide donc les
# anciennes traces. Une trace NON estampillée (traceur d'avant ce code, ou posée à la
# main) ne garde l'ancien régime que SANS `focus.json` au clone ; focus présent, elle
# ne crédite que sous une portée qui couvre la tâche, et doit alors, elle aussi, suivre
# la déclaration — sur chaque jambe : propre, livraison, portée et groupe. Ça empêche
# d'OUBLIER, pas de TRICHER.
# ---------------------------------------------------------------------------
def portee_active(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    """La portée de revue ACTIVE du clone, ou None : absente, illisible, hors forme, ou
    HORS FOCUS (son `focus` n'est plus celui de `focus.json`, absent compris) — jamais
    une portée devinée."""
    try:
        portee, focus = lire_portee(root), lire_focus(root)
    except BoardError:
        return None
    if portee is None or focus is None or focus["task_id"] != portee["focus"]:
        return None
    return portee


def portee_couvre(portee: dict[str, Any] | None, tid: str) -> bool:
    """`tid` est-il un membre NON consommé de `portee` ?"""
    return portee is not None and tid in portee["members"] and tid not in portee["consumed"]


def _declaree_a(portee: dict[str, Any]) -> datetime | None:
    """`declared_at` (à la milliseconde) TRONQUÉ à la seconde, l'unité de l'`at` des traceurs :
    un critique arrêté dans la seconde de la déclaration la suit. Illisible : None."""
    try:
        return datetime.strptime(str(portee["declared_at"])[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError, KeyError):
        return None


def binome_creditables(traces: dict[str, Any], tid: str, portee: dict[str, Any] | None,
                       focus: bool = False, propre: bool = False) -> dict[str, Any]:
    """Les traces de `traces` qui CRÉDITENT `tid` sous `portee` (`portee_active`). Estampillée
    (`portee` = un `declared_at`) : seulement si `portee` couvre `tid` au MÊME `declared_at`.
    NON estampillée (ancien traceur, qui écrivait sur CHAQUE `running`, ou posée à la main) :
    dès qu'un focus existe au clone (`focus`), seulement sous une portée qui couvre `tid` ;
    sans focus (clone d'avant ce code), l'ancien régime — elle passe telle quelle. Sous une
    portée qui couvre `tid`, une trace DATÉE avant la déclaration est écartée ; un `at`
    illisible l'est aussi sur la trace PROPRE (`propre` : rien d'autre ne la date, donc rien
    ne prouve qu'elle suit la déclaration), et passe sur un emprunt à la jambe de fraîcheur,
    qui l'écarte : sans borne de porte, refus qui le NOMME (« sans date lisible ») ; sous la
    borne de porte, seuls les `at` lisibles et non futurs (`_date_trace`) datent la plus
    récente, et une trace qui n'en a aucun ne passe jamais pour fraîche."""
    couvre = portee_couvre(portee, tid)
    borne = _declaree_a(portee) if couvre and portee is not None else None
    retenues: dict[str, Any] = {}
    for nom, trace in traces.items():
        estampille = trace.get("portee") if isinstance(trace, dict) else None
        if estampille is not None and not (couvre and portee is not None
                                           and estampille == portee["declared_at"]):
            continue
        if estampille is None and not couvre and focus:
            continue
        if couvre:
            quand = _date_trace_brute(trace.get("at") if isinstance(trace, dict) else None)
            if borne is None or (quand is None and propre) or (quand is not None and quand < borne):
                continue
        retenues[nom] = trace
    return retenues


def binome_remede_portee(root: str | os.PathLike[str], tid: str) -> str:
    """FOCUS PRÉSENT, PORTÉE QUI NE COUVRE PAS `tid` (absente, hors focus, consommée) : le
    refus NOMME `review-scope`. Sans `focus.json`, `""` : `remede_focus_absent` le dit. Une portée
    qui couvre ENCORE `tid` mais dont le focus a changé (F1 de la clôture) : le remède nomme D'ABORD
    `tasks.py focus <son focus>`, qui la rétablit sans nouveau critique — re-déclarer l'invaliderait."""
    if not chemin_focus(root).exists():
        return ""
    try:
        focus = lire_focus(root)
    except BoardError:
        focus = None
    if focus is not None and portee_couvre(portee_active(root), tid):
        return ""
    try:
        brute = lire_portee(root)
    except BoardError:
        brute = None
    fid = focus["task_id"] if focus is not None else "<T running>"
    membres = fid if fid == tid else f"{fid} {tid}"
    if focus is not None and brute is not None and brute["focus"] != fid and portee_couvre(brute, tid):
        return (f"PORTÉE DE REVUE : la portée du {brute['declared_at']} couvre {tid}, mais son focus "
                f"{brute['focus']} n'est plus celui du clone ({fid}). REMÈDE SANS NOUVEAU CRITIQUE : "
                f"`tasks.py focus {brute['focus']}` (s'il tourne encore), puis rejoue `done` ; sinon "
                f"`tasks.py review-scope {membres} [<T>…]` PUIS le critique de clôture.\n")
    return (f"PORTÉE DE REVUE : aucune portée active ne couvre {tid} (focus {fid}) — le traceur "
            f"n'écrit que sur les membres de la portée déclarée. REMÈDE : `tasks.py review-scope "
            f"{membres} [<T>…]` (liste explicite des tâches revues), PUIS le critique de clôture.\n")


def binome_preuve(
    root: str | os.PathLike[str], tid: str, data: dict[str, Any] | None = None
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    """La preuve de revue qui couvre cette tâche, et la tâche QUI LA PORTE.

    LA TRACE S'ÉCRIT SUR CE QUI TOURNE, ET CE N'EST PAS TOUJOURS CE QU'ON FERME.
    Correctif du binôme de clôture, sur un défaut qui rendait la garde
    DÉCORATIVE dans le modèle de travail réel de ce dépôt : le hook crédite les
    tâches `running`, mais un chantier au mandat d'écriture armé garde UNE tâche
    au slot `running` et ferme ses sous-tâches depuis `pending` (règle 1bis).
    Aucune sous-tâche n'avait donc jamais de trace : toutes les clôtures
    tombaient sur le refus, et la seule issue restante était la dérogation. Une
    garde qu'on ne peut franchir que par son échappatoire n'est pas une garde.

    ON ACCEPTE DONC LA PREUVE D'UN SLOT `running` LIÉ À LA TÂCHE — jadis par le
    chantier, depuis T-01M5F728FGJ43QJX1RJKTWWKRB par la PORTÉE DE REVUE déclarée ou
    le GROUPE parallèle déclaré (plus bas) : le binôme a relu le travail fait SOUS ce
    slot. C'est aussi ce qui se passe en fait — une revue couvre le lot, pas un ticket.

    CE QUE ÇA COÛTE, ET C'EST DIT PLUTÔT QUE DÉCOUVERT : un seul binôme peut
    alors couvrir PLUSIEURS sous-tâches fermées sous le même slot. C'est fidèle
    à la pratique, mais ça affaiblit le « par tâche ». La contrepartie est que
    l'emprunt est ÉCRIT au board, dans le motif de clôture : on voit toujours
    que la preuve venait d'ailleurs, et de où.

    Une tâche hors de toute portée active et de tout groupe n'emprunte rien : sans
    quoi la revue de A1 créditerait A2, `running` du même chantier.

    LA LIVRAISON, ENTRE LES DEUX (T-01M4WTYSCE, S-01M4X6K3JRR90VVWR4AFHT983G) :
    propres → livraison → slot. Une tâche qui porte une livraison (`livraison_de`)
    emprunte la trace d'un AUTRE membre au dict identique, tout état, datée à ou
    après la borne (`livraison_borne` : la déclaration et chaque relevé `--vers` d'un
    membre) et fraîche par la règle du slot (`binome_livraison`). Sinon le slot reste
    essayé, MAIS SOUS LA MÊME BORNE : un relevé postérieur à la revue la rend
    caduque pour TOUT emprunt (choix du dev, plus strict que « → slot » nu : sans lui
    le slot `running` de la même portée ou du même groupe ressusciterait la revue caduque ; et c'est ce qui
    rend la provenance exacte, `livraison_preteuse`). Les traces PROPRES ne sont PAS
    bornées par l'âge (la doctrine : `binome_preuve` ne périme jamais une trace directe ;
    seule la portée les borne, `binome_creditables`) : sous
    une voie où chaque membre tourne à l'arrêt du critique, la caducité d'un relevé
    postérieur reste de PROSE. Échec : le constat de la livraison remplace celui du
    slot (`binome_refusal` le route en premier). Une livraison n'emprunte rien d'une
    tâche hors de ses membres que par le slot.

    BORNÉE PAR LA PORTÉE DE REVUE (T-01M5F728FGJ43QJX1RJKTWWKRB) : chaque trace passe par
    `binome_creditables` — propre, d'un membre de livraison ou d'un slot. Le slot n'est
    plus celui du CHANTIER : c'est un `running` de la MÊME portée active (les deux membres,
    `tid` non consommé) ou du MÊME groupe parallèle déclaré (trace valable pour son
    porteur) ; la fraîcheur (borne de porte, 24 h) reste celle du slot."""
    portee, focus = portee_active(root), chemin_focus(root).exists()
    vus = binome_creditables(binome_trace(root, tid), tid, portee, focus, propre=True)
    if len(vus) >= BINOME_MIN:
        return vus, tid, None
    try:
        data = data if data is not None else load(root)
        moi = find(data, tid)
    except Exception:
        return vus, tid, None
    constat_livraison: dict[str, Any] | None = None
    if livraison_de(moi) is not None:
        pretee = binome_livraison(root, moi, data, cycle_precedent(root), portee)
        if isinstance(pretee, tuple):
            return pretee[0], pretee[1], None
        constat_livraison = pretee
    couverte, groupe = portee_couvre(portee, tid), parallel_group_of(moi)
    if not (couverte or groupe):
        return vus, tid, constat_livraison
    borne = cycle_precedent(root)
    perime_vu: dict[str, Any] | None = None
    for autre in data["tasks"]:
        if autre["id"] == tid or autre.get("state") != "running":
            continue
        meme_portee = couverte and autre["id"] in portee["members"]
        if meme_portee or (groupe and parallel_group_of(autre) == groupe):
            empruntee = binome_creditables(binome_trace(root, autre["id"]),
                                           tid if meme_portee else autre["id"], portee, focus)
            if constat_livraison is not None:
                # LA BORNE DE LA LIVRAISON VAUT POUR LE SLOT (voir la docstring) ; un slot
                # écarté par elle est NOMMÉ au refus, comme un membre.
                bornee = {n: v for n, v in empruntee.items()
                          if livraison_apres(v, constat_livraison["borne_livraison"])}
                if empruntee and len(bornee) < BINOME_MIN:
                    constat_livraison["avant"].append(f"{autre['id']} (slot)")
                empruntee = bornee
            if len(empruntee) >= BINOME_MIN:
                # L'EMPRUNT EXPIRE AVEC SON CYCLE (T-00000592). Sans cette borne,
                # la preuve ne se périmait QUE par `reopen` : dès qu'un chantier
                # avait son premier binôme tracé, toute sous-tâche se fermait sur
                # lui, indéfiniment, avec au board une mention qui avait
                # l'apparence d'une revue. Une garde qui semble mordre et ne mord
                # plus après son premier passage est PIRE qu'une garde absente.
                #
                # LE LOT LÉGITIME PASSE ENTIER, et c'était la contrainte : deux
                # sous-tâches fermées sous la MÊME porte partagent le même cycle,
                # donc la même trace les couvre toutes les deux. Ce qui tombe,
                # c'est la trace d'un cycle PASSÉ.
                if borne is None:
                    # PAS DE BORNE DE PORTE — clone neuf, moins de deux verts
                    # `frozen`, journal absent ou refusé en lecture (un octet non
                    # UTF-8 y lève encore un traceback) : la BORNE D'ÂGE prend le
                    # relais (T-00000846) ; avant, l'emprunt ne périmait JAMAIS.
                    # SUR `at`, PAS SUR LE MTIME : `at` est écrit par le traceur
                    # de l'hôte, c'est la date que le board imprime et que la
                    # branche à borne compare ; le mtime est RÉÉCRIT par une
                    # copie, une restauration ou un `touch`. Pas de repli mtime.
                    # `BINOME_MIN` CRITIQUES DISTINCTS FRAIS (S-00004500 : un) :
                    # une trace de plus de 24 h ne compte pas, même à côté d'une fraîche.
                    limite = datetime.now(timezone.utc) - timedelta(
                        hours=EMPRUNT_SANS_BORNE_TTL_HEURES)
                    dates = {n: _date_trace((v or {}).get("at")) for n, v in empruntee.items()}
                    frais = {n: empruntee[n] for n, q in dates.items() if q and q > limite}
                    if len(frais) >= BINOME_MIN:
                        return frais, autre["id"], None
                    if perime_vu is None:
                        # TROIS CAUSES, toutes rangées, jamais seulement la
                        # première : illisible, futur (au-delà de la tolérance),
                        # plus vieux que la borne d'âge.
                        futurs = sorted(n for n, q in dates.items()
                                        if q is None and _date_trace_brute(
                                            (empruntee[n] or {}).get("at")) is not None)
                        illisibles = sorted(n for n, q in dates.items()
                                            if q is None and n not in futurs)
                        vieux = sorted(n for n, q in dates.items() if q and q <= limite)
                        # CHAQUE CRITIQUE PORTE SON ÉTAT sur la ligne « Trace du
                        # slot » : la phrase pilote de la cause d'âge seule ne
                        # nomme personne, c'est cette ligne qui départage.
                        def etat(n: str) -> str:
                            if n in futurs:
                                return "future"
                            if n in illisibles:
                                return "illisible"
                            return "périmée" if n in vieux else "fraîche"
                        perime_vu = {
                            "porteur": autre["id"],
                            "borne": None,
                            "at": ", ".join(
                                f"{n} @ {(empruntee[n] or {}).get('at') or '(sans date)'}"
                                f" ({etat(n)})"
                                for n in sorted(empruntee)),
                            "illisibles": illisibles,
                            "futurs": futurs,
                            "vieux": vieux,
                        }
                    continue
                # SEULS LES `at` DATABLES COMPTENT (C-K1) : comparées en CHAÎNES, « zzzz »
                # ou « 2099-… » dépassaient toute borne et passaient pour fraîches.
                recent = max((v.get("at") for v in empruntee.values() if isinstance(v, dict)
                              and _date_trace(v.get("at")) is not None), default="")
                if not recent or recent <= borne:
                    # UNE TRACE SANS `at` NE SE PÉRIME PAS TOUTE SEULE : sans le
                    # `not recent`, une trace malformée rendait `""`, qui n'est
                    # jamais `<= borne`, donc elle passait pour éternellement
                    # fraîche. Fail-closed sur une trace qu'on ne sait pas dater.
                    #
                    # ET ON NE REND PAS AU PREMIER PÉRIMÉ : un AUTRE slot `running`
                    # de la même portée ou du même groupe déclaré
                    # peut porter une trace fraîche. Rendre ici laisserait
                    # l'ORDRE DU BOARD décider du verdict.
                    if perime_vu is None:
                        perime_vu = {
                            "porteur": autre["id"], "at": recent or "(sans date)",
                            "borne": borne,
                        }
                    continue
                return empruntee, autre["id"], None
    return vus, tid, constat_livraison if constat_livraison is not None else perime_vu


def binome_refusal(
    root: str | os.PathLike[str],
    tid: str,
    preuve: tuple[dict[str, Any], str, dict[str, Any] | None] | None = None,
) -> str | None:
    """Le refus de clore sans revue critique, ou None.

    `preuve` : le résultat de `binome_preuve` DÉJÀ CALCULÉ par l'appelant
    (T-00000846). `set_state` le calcule UNE fois et le passe ici puis à la
    mention au board : deux calculs à deux instants différents franchissaient
    le refus à 24 h pile puis rendaient une mention VIDE. Sans lui, la preuve
    est calculée ici, comme avant.

    POURQUOI CETTE GARDE EXISTE. « Aucune tâche n'est marquée terminée sans une
    revue critique » est la règle la plus lourde du dépôt, et
    la seule que RIEN ne tenait : `.agents/skills/task-board/SKILL.md` l'écrivait
    lui-même — « le refus est DOCTRINAL et non mécanique ». Une règle tenue par
    la mémoire d'un orchestrateur est une règle qu'on oublie, et le pilote devait
    la réclamer à chaque clôture (demande du 2026-09-13).

    ELLE VIT ICI ET NON DANS `argparse`, exactement comme la garde du motif
    au-dessus, et pour la même raison mesurée : la CLI n'est pas le seul chemin
    vers `done` — le pont V3 et le tableau de bord ferment aussi. Une exigence
    posée au parseur seul laisserait deux portes ouvertes, et une règle qu'on
    contourne par une autre porte n'est pas une règle.

    `BINOME_MIN` CRITIQUES DISTINCTS — UN depuis la décision pilote S-00004500
    (T-00001226), qui a ABANDONNÉ l'indépendance de deux modèles pour toute
    clôture : un critique seul porte l'union des angles A et B ; la paire de
    T-00000586 et la passe de correction de T-00001222 sont retirées. Le
    nombre vit en UN point de la façade, doublé textuellement dans le hook
    `affirmation-guard.sh` ; le vocabulaire est clos et DOUBLÉ dans le hook qui
    écrit ; des bancs lient les deux listes et les deux nombres.

    Que la revue ait vu l'état COURANT des fichiers de reprise de lot, CE N'EST PAS
    ICI : c'est `binome_reprise_refusal` (`tasks_etats.py`), appelée juste après.

    CE QUE ÇA NE PROUVE PAS, dit plutôt que découvert : que la revue était BONNE,
    ni qu'elle portait sur l'état final — le binôme passe AVANT la porte par
    décision pilote, donc les corrections lui succèdent et le SHA relu n'est pas
    celui de la clôture. Le refus imprime donc les SHA relus, pour qu'un lecteur
    voie lui-même une trace périmée. Et ça empêche d'OUBLIER, pas de TRICHER : la
    trace est un fichier d'état qu'un agent déterminé peut écrire."""
    racine = Path(normalize_root(root))
    if not (racine / BINOME_GATE).exists():
        return None
    vus, _porteur, perime = preuve if preuve is not None else binome_preuve(root, tid)
    if len(vus) >= BINOME_MIN:
        return None
    presents = ", ".join(
        f"{nom} @ {info.get('sha', '?')}" for nom, info in sorted(vus.items())
    ) or "aucun"
    if perime is not None and perime.get("livraison"):
        # LA LIVRAISON D'ABORD (T-01M4WTYSCE) : la tâche en porte une, son constat dit pourquoi
        # aucun membre ne prête la revue — jamais la phrase du slot, qui enverrait au chantier.
        # Focus présent sans portée qui couvre `tid` : le remède `review-scope` suit (C-K2).
        remede = binome_remede_portee(root, tid)
        return livraison_refus(tid, perime) + (f"\n{remede.rstrip()}" if remede else "")
    if perime is not None and perime.get("borne") is None:
        # LA BORNE D'ÂGE (T-00000846) : pas de borne de porte mesurable, et moins
        # de `BINOME_MIN` critique(s) distinct(s) daté(s) de moins de 24 h sur le slot.
        # Le refus distingue « trop vieille », « pas datable » et « datée dans
        # le futur », et les NOMME TOUTES : taire la seconde cause ferait
        # relancer un binôme qui retomberait sur elle.
        causes: list[str] = []
        if perime.get("illisibles"):
            causes.append(
                f"trace sans date lisible (`at` absent ou malformé pour "
                f"{', '.join(perime['illisibles'])})"
            )
        if perime.get("futurs"):
            causes.append(
                f"trace datée dans le FUTUR pour {', '.join(perime['futurs'])} "
                "(horloge décalée ?)"
            )
        # Seule, la cause d'âge garde la phrase EXACTE de la décision pilote
        # (les noms et dates suivent sur la ligne « Trace du slot ») ; mêlée à
        # d'autres causes, elle nomme ses critiques pour qu'on les départage.
        if perime.get("vieux") or not causes:
            causes.append(
                f"trace de plus de {EMPRUNT_SANS_BORNE_TTL_HEURES} h"
                + (f" pour {', '.join(perime['vieux'])}"
                   if perime.get("vieux") and causes else "")
            )
        cause = "et " + " ; ".join(causes) + " — relance le binôme"
        return (
            f"clore {tid} exige la REVUE CRITIQUE — preuve empruntée "
            f"PÉRIMÉE : pas deux portes vertes frozen dans VERIFY_STAMP.log, "
            f"{cause}.\n"
            f"Trace du slot `{perime['porteur']}` : {perime['at']}.\n"
            "POURQUOI CE REFUS EXISTE : sans historique de portes (clone neuf, "
            "moins de deux verdicts `frozen` distincts), l'emprunt ne périmait "
            "JAMAIS — la première revue d'un chantier couvrait toutes ses "
            f"sous-tâches pour toujours. Faute de borne de porte, la borne est "
            f"l'âge : {BINOME_MIN} critique(s) distinct(s) daté(s) de moins de "
            f"{EMPRUNT_SANS_BORNE_TTL_HEURES} h.\n"
            "REMÈDE : relance `critic-opus` (repli `critic-fable`, puis "
            "`critic-sonnet-max` à effort maximal) sur le travail que tu fermes, "
            "corrige ses constats, puis referme. Deux portes `verify.sh --at` "
            "vertes rendent ensuite la borne de porte à l'emprunt.\n"
            f"SORTIE TRACÉE si rien n'est à relire : `tasks.py done {tid} "
            f"--raison \"<pourquoi>\" --sans-binome \"<pourquoi pas de revue>\"`."
        )
    if perime is not None:
        # LE REFUS NOMME LA CONDITION MANQUANTE, jamais un « non » nu : sans
        # cette branche, un emprunt périmé se lisait « 0 critique tracé » et
        # envoyait relancer un critique qu'on venait peut-être de lancer.
        return (
            f"clore {tid} exige la REVUE CRITIQUE, et la preuve empruntée est "
            f"PÉRIMÉE : la trace du slot `{perime['porteur']}` date de "
            f"{perime['at']}, donc d'AVANT la porte verte précédente "
            f"({perime['borne']}). Elle appartient à un cycle passé.\n"
            "POURQUOI CE REFUS EXISTE : sans lui, la première revue d'un "
            "chantier couvrait toutes ses sous-tâches indéfiniment, et le board "
            "affichait « binôme relevé sur … » pour des clôtures que personne "
            "n'avait relues.\n"
            "CE QUI EST TOUJOURS PERMIS : plusieurs sous-tâches fermées sous la "
            "MÊME porte partagent le même cycle, donc la même revue les couvre "
            "toutes. Ce qui tombe, c'est la trace d'un cycle passé.\n"
            "REMÈDE : relance `critic-opus` (repli `critic-fable`, puis "
            "`critic-sonnet-max` à effort maximal) sur le travail que tu fermes, "
            "corrige ses constats, puis referme.\n"
            f"SORTIE TRACÉE si rien n'est à relire : `tasks.py done {tid} "
            f"--raison \"<pourquoi>\" --sans-binome \"<pourquoi pas de revue>\"`."
        )
    return (
        f"clore {tid} exige la REVUE CRITIQUE, et elle n'a pas eu lieu : "
        f"{len(vus)} critique(s) tracé(s) — {presents} ; il en faut {BINOME_MIN}.\n"
        f"LA TRACE S'ÉCRIT SUR LES MEMBRES DE LA PORTÉE DE REVUE déclarée "
        f"(`tasks.py review-scope`, focus compris) ; hors d'elle, {tid} n'emprunte "
        f"que la trace d'un `running` de son groupe parallèle déclaré — vérifie "
        f"`tasks.py list --task {tid}`.\n"
        f"{binome_remede_portee(root, tid)}"
        "La règle (S-00004500) : UN critique de clôture, qui porte seul l'union "
        "des angles A et B — `critic-opus`, repli `critic-fable` puis "
        "`critic-sonnet-max` à effort maximal —, et sa place est AVANT la porte.\n"
        "La trace n'est pas déclarative : elle est écrite par l'hôte quand un "
        "sous-agent critique s'arrête. Lance-le, corrige ses constats, puis "
        "referme.\n"
        f"SORTIE TRACÉE si cette tâche n'a rien à faire relire — un doublon, un "
        f"ticket caduc, une décision sans code : "
        f"`tasks.py done {tid} --raison \"<pourquoi>\" --sans-binome \"<pourquoi "
        f"pas de revue>\"`. La raison reste sur le board, donc l'exception se "
        f"voit ; l'oubli, lui, ne passe plus."
    )


# ---------------------------------------------------------------------------
# LA LIVRAISON DÉCLARÉE (T-01M4WTYSCEYHC6KZF2DC1PXBRN, décision pilote
# S-01M4X6K3JRR90VVWR4AFHT983G : un verbe dédié). Plusieurs tâches livrées par UNE
# branche d'intégration L (leurs lots fusionnés dans L, puis L dans la cible) :
# `tasks.py livraison <T…> --branche <L>` pose le MÊME dict sur chacune. Trois
# lecteurs : la revue de clôture (`binome_preuve` → `binome_livraison` : un membre
# porte la trace, les autres l'empruntent), `retour --vers <L>` (contrôle (v)) et le
# `done` d'une directe relevée `--vers` (R-v). Ça empêche d'OUBLIER, pas de TRICHER :
# le dict est déclaratif, comme le relevé.
# ---------------------------------------------------------------------------

#: Le format de `livraison.le` : celui de `retour.le` et de l'`at` des traces, à la
#: seconde — une date seule rendrait « trace antérieure à la déclaration » invérifiable
#: dans la journée.
LIVRAISON_FORMAT_LE = "%Y-%m-%dT%H:%M:%SZ"
LIVRAISON_PREFIXE_REF = "refs/heads/"


def livraison_de(task: dict[str, Any]) -> dict[str, Any] | None:
    """La livraison DÉCLARÉE de `task`, ou None (absente ou malformée).

    CONTRAT FIGÉ (lu par `binome_livraison`, le contrôle (v) de `retour --vers`, la
    cause (R-v) du `done`, et par T-01M4WTYRE5) : `task["livraison"]` =
    {"branche": nom de branche locale SANS `refs/heads/`, "taches": ids résolus par
    `find`, dans l'ordre de la déclaration, sans doublon, "le": ISO UTC à la seconde
    (`LIVRAISON_FORMAT_LE`)}. Le MÊME dict sur chaque tâche nommée ; une
    re-déclaration le REMPLACE sur les tâches nommées (le dit), `--retirer` ôte la
    clé, `reopen` et le `start` depuis `done` l'ôtent (la clôture annulée emporte sa
    revue). Hors `SYNC_SNAPSHOT_FIELDS` : la projection V3 ne la voit pas, un revert
    du code laisse au board une clé INERTE. Malformé (un champ absent, d'un autre
    type, une date illisible) se lit comme absent : aucun lecteur ne l'emprunte."""
    liv = task.get("livraison")
    if not isinstance(liv, dict):
        return None
    branche, taches, le = liv.get("branche"), liv.get("taches"), liv.get("le")
    if not (isinstance(branche, str) and branche and isinstance(taches, list) and taches
            and all(isinstance(t, str) for t in taches) and _date_trace_brute(le) is not None):
        return None
    return liv


def livraison_membres(data: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    """Les MEMBRES de la livraison de `task`, `task` compris : les tâches que son dict
    nomme ET qui portent un dict IDENTIQUE (branche, tâches et date), tout état. Une
    tâche re-déclarée ailleurs n'est plus membre ; un id disparu du board est ignoré.
    Vide si `task` ne porte pas de livraison lisible."""
    liv = livraison_de(task)
    if liv is None:
        return []
    par_id = {t.get("id"): t for t in data["tasks"] if isinstance(t, dict)}
    return [par_id[t] for t in dict.fromkeys(liv["taches"])
            if t in par_id and livraison_de(par_id[t]) == liv]


def livraison_borne(task: dict[str, Any], membres: list[dict[str, Any]]) -> tuple[datetime, str | None, str]:
    """LA BORNE DE LA REVUE D'UNE LIVRAISON : `(borne, par, quand)`. `borne` = le plus
    tardif de la déclaration (`livraison.le`) et du `retour.le` de chaque membre relevé
    `--vers` cette branche ; `par` = l'id du membre dont le relevé la pose (None = la
    déclaration) ; `quand` = sa date, telle qu'écrite. Un relevé `--vers` à la date
    illisible rend une borne INFINIE (fail-closed : aucune trace ne la passe), DITE."""
    liv = livraison_de(task) or {}
    borne = _date_trace_brute(liv.get("le")) or datetime.max.replace(tzinfo=timezone.utc)
    par, quand = None, str(liv.get("le"))
    for membre in membres:
        releve = membre.get("retour")
        if not (isinstance(releve, dict) and releve.get("vers") == liv.get("branche")):
            continue
        date_releve = _date_trace_brute(releve.get("le")) or datetime.max.replace(tzinfo=timezone.utc)
        if date_releve > borne or (date_releve == borne and par is None):
            borne, par = date_releve, membre["id"]
            quand = str(releve.get("le")) if date_releve.year < 9999 else "date illisible"
    return borne, par, quand


def livraison_apres(trace: Any, borne: datetime) -> bool:
    """La trace `trace` (le JSON du traceur) est-elle datée À ou APRÈS `borne` ?"""
    quand = _date_trace_brute(trace.get("at") if isinstance(trace, dict) else None)
    return quand is not None and quand >= borne


def livraison_fraiches(retenues: dict[str, Any], porte: str | None) -> dict[str, Any]:
    """Les traces `retenues` FRAÎCHES — LA MÊME RÈGLE que l'emprunt au slot de
    `binome_preuve`, qu'elle recopie sans la factoriser (dette nommée) : sous une borne
    de porte (`cycle_precedent`), toutes si la plus récente lui est postérieure, aucune
    sinon ; sans elle, celles datées de moins de `EMPRUNT_SANS_BORNE_TTL_HEURES` (une
    date future ou illisible ne compte pas). Identique, pour que la provenance d'un
    emprunt reste exacte : ce que le slot rend n'a pas pu passer la livraison."""
    if porte is not None:
        recent = max((v.get("at") for v in retenues.values() if isinstance(v, dict)
                      and _date_trace(v.get("at")) is not None), default="")
        return retenues if recent and recent > porte else {}
    limite = datetime.now(timezone.utc) - timedelta(hours=EMPRUNT_SANS_BORNE_TTL_HEURES)
    out = {}
    for nom, trace in retenues.items():
        quand = _date_trace(trace.get("at") if isinstance(trace, dict) else None)
        if quand and quand > limite:
            out[nom] = trace
    return out


def binome_livraison(root: str | os.PathLike[str], task: dict[str, Any], data: dict[str, Any],
                     porte: str | None, portee: dict[str, Any] | None = None
                     ) -> tuple[dict[str, Any], str] | dict[str, Any]:
    """LA REVUE PRÊTÉE PAR LA LIVRAISON de `task` (qui en porte une, lisible) : `(traces,
    porteur)` si un AUTRE membre (dict identique, TOUT ÉTAT — un membre déjà clos prête
    encore) porte au moins `BINOME_MIN` critique(s) datés à ou après la borne
    (`livraison_borne`) ET frais (`livraison_fraiches`, `porte` = `cycle_precedent`) ;
    sinon le constat, un dict que `binome_refusal` route avant toute autre forme :
    {"livraison", "borne_livraison", "quand", "par", "avant" (membres dont TOUTES les
    traces précèdent la borne), "cycle" (premier membre aux traces datées mais
    périmées : porteur, at), "porte", "membres"}. Membres parcourus dans l'ordre de la
    déclaration : le premier prêteur valable rend, l'ordre du board ne décide rien."""
    liv = livraison_de(task) or {}
    membres = livraison_membres(data, task)
    borne, par, quand = livraison_borne(task, membres)
    avant: list[str] = []
    cycle: dict[str, Any] | None = None
    for membre in membres:
        if membre["id"] == task["id"]:
            continue
        # LA PORTÉE D'ABORD (T-01M5F728FGJ43QJX1RJKTWWKRB) : la trace d'un membre crédite
        # `task` sous la règle de `binome_creditables`, jamais au-delà.
        traces = binome_creditables(binome_trace(root, membre["id"]), task["id"], portee,
                                    chemin_focus(root).exists())
        retenues = {n: v for n, v in traces.items() if livraison_apres(v, borne)}
        if len(retenues) < BINOME_MIN:
            if traces:
                avant.append(membre["id"])
            continue
        fraiches = livraison_fraiches(retenues, porte)
        if len(fraiches) >= BINOME_MIN:
            return fraiches, membre["id"]
        if cycle is None:
            cycle = {"porteur": membre["id"], "at": ", ".join(
                f"{n} @ {(v.get('at') if isinstance(v, dict) else None) or '(sans date)'}"
                for n, v in sorted(retenues.items()))}
    return {"livraison": liv.get("branche"), "borne_livraison": borne, "quand": quand, "par": par,
            "avant": avant, "cycle": cycle, "porte": porte, "membres": [m["id"] for m in membres]}


def livraison_preteuse(data: dict[str, Any] | None, tid: str, porteur: str) -> str | None:
    """La branche de la livraison par laquelle `tid` a emprunté la preuve de `porteur`,
    ou None (preuve propre, emprunt au slot, board illisible). EXACT parce que
    `binome_preuve` filtre l'emprunt au slot d'une tâche livrée par la même borne et la
    même fraîcheur : un membre au dict identique qui les passe est rendu par la
    livraison, jamais par le slot."""
    if data is None or porteur == tid:
        return None
    try:
        moi = find(data, tid)
    except BoardError:
        return None
    if any(m["id"] == porteur for m in livraison_membres(data, moi)):
        return (livraison_de(moi) or {}).get("branche")
    return None


def livraison_refus(tid: str, constat: dict[str, Any]) -> str:
    """Le refus de clore une tâche LIVRÉE dont aucun membre ne prête la revue — TOUTES
    les causes, puis le remède et la sortie tracée. Rien d'un id du kit : il voyage."""
    branche = retour_lisible(str(constat.get("livraison")))
    causes: list[str] = []
    if constat.get("avant") and constat.get("par"):
        causes.append(f"un relevé de {constat['par']} postérieur à la revue ({constat['quand']}) — relance le "
                      f"critique ; les corrections se commitent sur {branche}, sans relevé "
                      f"(trace(s) antérieure(s) sur {', '.join(constat['avant'])})")
    elif constat.get("avant"):
        causes.append(f"la trace de {', '.join(constat['avant'])} précède la déclaration de la livraison "
                      f"({constat['quand']})")
    if constat.get("cycle"):
        perime = constat["cycle"]
        causes.append(f"la trace de `{perime['porteur']}` ({perime['at']}) est PÉRIMÉE : "
                      + (f"antérieure à la porte verte précédente ({constat['porte']})" if constat.get("porte")
                         else f"plus de {EMPRUNT_SANS_BORNE_TTL_HEURES} h, ou datée dans le futur"))
    if not causes:
        causes.append(f"aucun membre ne porte de trace postérieure au dernier relevé ({constat['quand']}) — "
                      f"un membre `running` à l'arrêt du critique")
    return (
        f"clore {tid} exige la REVUE CRITIQUE, et la livraison `{branche}` ne la prête pas : "
        + " ; ".join(causes) + ".\n"
        f"Membres (dict identique) : {', '.join(constat.get('membres') or []) or 'aucun'}.\n"
        "POURQUOI : une revue de la livraison couvre ses membres si l'un d'eux porte une trace datée après "
        "la déclaration ET après le dernier relevé `--vers` d'un membre — un relevé postérieur fait entrer "
        "du code que la revue n'a pas lu.\n"
        "REMÈDE : un membre `running` à l'arrêt du critique de clôture (`critic-opus`, repli `critic-fable`, "
        "puis `critic-sonnet-max` à effort maximal), qui relit la pointe de la livraison ; corrige ses "
        "constats sur la branche, sans nouveau relevé ; puis referme.\n"
        f"SORTIE TRACÉE si rien n'est à relire : `tasks.py done {tid} --raison \"<pourquoi>\" "
        f"--sans-binome \"<pourquoi pas de revue>\"`."
    )


def livraison_branche_refus(branche: str) -> list[str]:
    """Les causes qui rendent `branche` inadmissible comme nom de livraison (vide,
    option, espace, caractère de contrôle) ; vide = admissible."""
    causes = []
    if not branche:
        causes.append("--branche vide")
    if branche.startswith("-"):
        causes.append(f"--branche « {retour_lisible(branche)} » commence par « - » (lue comme une option par git)")
    if any(c.isspace() for c in branche):
        causes.append(f"--branche « {retour_lisible(branche)} » porte un espace")
    if any(not c.isprintable() and not c.isspace() for c in branche):
        causes.append(f"--branche « {retour_lisible(branche)} » porte un caractère de contrôle")
    return causes


def livraison_declarer(root: str, tids: list[str], branche: str, retirer: bool = False) -> str:
    """Le verbe `livraison` : pose (ou, `retirer`, ôte) la livraison `branche` sur
    CHAQUE tâche nommée, sous `board_lock` → `save`. Ids résolus par `find` EXACT ;
    TOUTES les causes de refus sont rendues ensemble (id inconnu — `unknown task id:
    <tid>` —, tâche close, branche inadmissible, et sous `retirer` une tâche qui porte
    une AUTRE livraison), `BoardError` (rc 2), rien n'est écrit. Une re-déclaration
    REMPLACE le dict et le DIT, en nommant les tâches de l'ancienne livraison qui
    gardent l'ancien dict (elles ne prêtent plus aux nommées)."""
    nom = branche[len(LIVRAISON_PREFIXE_REF):] if branche.startswith(LIVRAISON_PREFIXE_REF) else branche
    with board_lock(root):
        data = load(root)
        causes: list[str] = []
        taches: list[dict[str, Any]] = []
        for tid in dict.fromkeys(tids):
            try:
                tache = find(data, tid)
            except BoardError as exc:
                causes.append(str(exc))
                continue
            if tache.get("state") == "done":
                causes.append(f"{tache['id']} est close (done) : une livraison ne se déclare que sur une tâche ouverte")
            porte = tache.get("livraison")
            if retirer and isinstance(porte, dict) and porte.get("branche") != nom:
                causes.append(f"{tache['id']} porte une autre livraison que {retour_lisible(nom)} : "
                              f"`--retirer` n'ôte que la livraison nommée")
            taches.append(tache)
        causes += livraison_branche_refus(nom)
        if causes:
            raise BoardError(f"refus de {'retirer' if retirer else 'déclarer'} la livraison — {len(causes)} cause(s) :\n"
                             + "".join(f"  - {c}\n" for c in causes) + "Rien n'a été écrit.")
        today = date.today().isoformat()
        lignes: list[str] = []
        dict_neuf = {"branche": nom, "taches": [t["id"] for t in taches],
                     "le": datetime.now(timezone.utc).strftime(LIVRAISON_FORMAT_LE)}
        anciens: dict[str, dict[str, Any]] = {}
        ecrites = 0
        for tache in taches:
            before = copy.deepcopy(tache)
            ancien = tache.get("livraison")
            if retirer:
                if "livraison" not in tache:
                    lignes.append(f"TASKS: {tache['id']} ne porte aucune livraison — rien à retirer")
                    continue
                tache.pop("livraison")
                lignes.append(f"TASKS: {tache['id']} livraison {nom} retirée")
            else:
                if isinstance(ancien, dict):
                    anciens[tache["id"]] = ancien
                    lignes.append(f"TASKS: {tache['id']} livraison REMPLACÉE : "
                                  f"{retour_lisible(str(ancien.get('branche')))} @ {ancien.get('le')} → {nom}")
                tache["livraison"] = copy.deepcopy(dict_neuf)
            tache["updated"] = today
            enqueue_sync_intent(data, tache["id"], before, tache)
            ecrites += 1
        if not retirer:
            lignes.insert(0, f"TASKS: livraison {nom} déclarée sur {', '.join(dict_neuf['taches'])} "
                             f"(le {dict_neuf['le']})")
            nommees = set(dict_neuf["taches"])
            for ancien in anciens.values():
                restes = [t["id"] for t in data["tasks"] if t.get("id") not in nommees
                          and t.get("livraison") == ancien]
                if restes:
                    lignes.append(f"TASKS: {', '.join(restes)} garde(nt) l'ancienne livraison "
                                  f"{retour_lisible(str(ancien.get('branche')))} @ {ancien.get('le')} — "
                                  f"dict différent : plus de prêt de revue avec les tâches nommées")
        if ecrites:
            save(root, data)
    return "\n".join(lignes)
