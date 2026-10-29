# tasks_etats.py — PARTIE de `tasks.py` (T-00000788) : les TRANSITIONS d'état —
# `set_state` (start, done et leurs gardes), `stage_task`, `stage_running_task`.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations

# LES FICHIERS QUE LA REVUE DE `done` DOIT AVOIR VUS DANS LEUR ÉTAT COURANT
# (T-00001064, S-00003393) : les motifs `REPRISES` de `affirmation-guard.sh`, plus
# `PLAN-ETAT.md`. JUMELLE TEXTUELLE de ce tuple-là, sans factorisation (le hook
# est un heredoc) : un banc de PARITÉ les lie (`test_binome_guard.py`, B12). PAS
# `PLAN-ETAT-DETAIL.md` : historique écrit par presque chaque tâche, il est gardé
# par l'affirmation-guard seule (borne écrite).
REPRISES_BINOME = (
    "docs/interne/chantier/lots/*",
    "docs/interne/chantier/reprises/prompt_de_reprise_et_planification.md",
    "docs/tasks/LOT-*-REPRISE.md",
    "PLAN-ETAT.md",
)


def reprise_changee_depuis(root: str, sha: Any, delai: float = 5) -> tuple[str, Any]:
    """Les fichiers surveillés (`REPRISES_BINOME`) changés depuis `sha`, ou pourquoi
    on ne le sait pas. Rend `("ok", [chemins])`, `("inerte", cause)` ou
    `("non-mesuré", cause)`, par des tests dans CET ordre :
      (a) HORS GIT = PAS DE `.git` À LA RACINE, RIEN D'AUTRE — un fait de fichier,
          jamais un code de sortie : un git en panne, un propriétaire douteux, un
          git absent ne produisent JAMAIS `inerte` ;
      (b) aucun fichier surveillé PRÉSENT (système de fichiers, pas git) → ok [] :
          un adoptant sans ces fichiers n'est pas touché, même si git est cassé ;
      (c) `sha` absent ou non hexadécimal → non-mesuré ;
      (d) git, environnement purgé de toute redirection (`GIT_DIR`…), de toute
          config désignée par l'environnement (`GIT_CONFIG_GLOBAL`/`_SYSTEM`/
          `_PARAMETERS`/`_COUNT`/`_KEY_*`/`_VALUE_*`), de `GIT_EXEC_PATH`, de
          `GIT_NO_REPLACE_OBJECTS` et des modes de pathspec (`GIT_*_PATHSPECS`) ;
          la config globale lue est alors celle de `HOME`/`XDG_CONFIG_HOME`.
          `LC_ALL=C`, sortie en octets décodée UTF-8. Appels :
          `rev-parse --show-toplevel` (rc ≠ 0, ou un toplevel qui n'est pas la
          racine par `samefile` → non-mesuré : un `.git` vide sous un dépôt
          englobant ferait lire l'AUTRE dépôt),
          `rev-parse --disambiguate=<sha>` puis `cat-file -t` de CHAQUE objet
          listé (le sha est lu en PRÉFIXE d'objet, jamais en nom : une ref
          homonyme ne passe pas devant ; zéro ou plusieurs COMMITS de ce
          préfixe → non-mesuré), `diff -z --no-renames <sha plein>` et
          `ls-files -z --others` (ignores personnels neutralisés), TOUJOURS
          restreints au pathspec (sans lui, `diff` réécrit `.git/index`). Tout
          rc ≠ 0, toute exception, tout délai (`delai` s par appel) → non-mesuré,
          la cause nommée : jamais une exception à travers le verrou du board.
    BORNES : le `sha` est HEAD à l'ARRÊT du critique (`binome-trace.sh`) — un
    commit fait pendant la revue compte « vu » : la jambe prouve qu'un critique
    s'est ARRÊTÉ sur cet état, jamais qu'il l'a LU (empêche d'oublier, pas de
    tricher) ; un dépôt à `GIT_DIR` externe est lu hors git ; un fichier
    SURVEILLÉ au stat sali fait prendre `index.lock` quelques ms (un `git
    commit` concurrent peut échouer et se rejoue)."""
    import fnmatch
    import os
    import re
    import subprocess

    racine = os.path.abspath(normalize_root(root))
    if not os.path.lexists(os.path.join(racine, ".git")):
        return ("inerte", "pas de .git à la racine")
    spec = sorted({(p.split("*", 1)[0].rsplit("/", 1)[0] if "*" in p else p) or "."
                   for p in REPRISES_BINOME})

    def surveille(chemin: str) -> bool:
        return any(fnmatch.fnmatchcase(chemin, m) for m in REPRISES_BINOME)

    def present() -> bool:
        for s in spec:
            p = os.path.join(racine, s)
            if os.path.isfile(p) and surveille(s):
                return True
            for dossier, _sous, fichiers in os.walk(p):
                for f in fichiers:
                    rel = os.path.relpath(os.path.join(dossier, f), racine)
                    if surveille(rel.replace(os.sep, "/")):
                        return True
        return False

    if not present():
        return ("ok", [])
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9A-Fa-f]{4,40}", sha):
        return ("non-mesuré", f"sha tracé illisible ({sha!r})")
    redirections = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                    "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                    "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
                    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_NO_REPLACE_OBJECTS",
                    "GIT_EXEC_PATH", "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS",
                    "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS")
    env = {k: v for k, v in os.environ.items() if k not in redirections
           and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env["LC_ALL"] = "C"

    def git(verbe: str, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=racine, env=env, capture_output=True,
                           timeout=delai, check=False)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "surrogateescape").strip().splitlines()
            raise RuntimeError(f"{verbe} en échec (rc {r.returncode} : "
                               f"{err[0] if err else 'stderr vide'})")
        return r.stdout.decode("utf-8", "surrogateescape")

    try:
        haut = git("rev-parse", "rev-parse", "--show-toplevel").strip()
        if not os.path.samefile(haut, racine):
            return ("non-mesuré", f"toplevel git {haut} différent de la racine {racine}")
        # Le sha tracé est COURT (`rev-parse --short`) : lu comme un NOM, une ref
        # homonyme (un tag `268742c`) passerait devant l'objet. Il est résolu en
        # PRÉFIXE d'objet, filtré aux commits, et seul le sha PLEIN atteint `diff`.
        objets = git("rev-parse", "rev-parse", f"--disambiguate={sha}").split()
        commits = [o for o in objets
                   if git("cat-file", "cat-file", "-t", o).strip() == "commit"]
        if len(commits) != 1:
            return ("non-mesuré", f"sha tracé {sha} : {len(commits)} commit(s) de ce préfixe")
        sha = commits[0]
        changes = git("diff", "-c", "core.quotePath=false", "diff", "-z", "--name-only",
                      "--no-renames", sha, "--", *spec).split("\0")
        neufs = git("ls-files", "-c", "core.excludesFile=" + os.devnull, "ls-files", "-z",
                    "--others", "--exclude-standard", "--", *spec).split("\0")
    except RuntimeError as exc:
        return ("non-mesuré", str(exc))
    except Exception as exc:
        return ("non-mesuré", f"{type(exc).__name__} : {exc}")
    return ("ok", sorted({c for c in changes + neufs if c and surveille(c)}))


def binome_reprise_refusal(root: str, tid: str, preuve: Any,
                           data: dict[str, Any] | None = None, exige: int = BINOME_MIN) -> str | None:
    """Le refus de clore quand la preuve RETENUE par `binome_preuve` (`preuve` :
    traces propres ou slot emprunté — jamais une relecture de `binome_trace`) n'a
    pas `exige` critique(s) « à jour » sur les fichiers de reprise et `PLAN-ETAT.md`
    (T-00001064, S-00003393). Appelée par `set_state` APRÈS `binome_refusal`, sous
    `BINOME_REQUIRED` et hors `--sans-binome`. `exige` vaut `BINOME_MIN` (UN depuis
    S-00004500, T-00001226), par défaut comme à l'appel de `set_state`.
    INERTE sans `BINOME_REQUIRED` (`preuve` None) ; `vus` vide → None (branche
    morte en production : la garde d'origine exige déjà `BINOME_MIN` traces). INERTE ET
    MUETTE hors git (pas de `.git` à la racine) : rien n'est écrit au board — un
    adoptant sans la convention ne doit pas lire une mention propre au kit.
    Dans un dépôt git, NON MESURABLE N'EST PAS « PASSE » : c'est un refus qui
    nomme la cause. PORTÉE : `lots/` et le prompt vivant n'existent que dans le
    kit ; `docs/tasks/LOT-*-REPRISE.md` (`keep:`) et `PLAN-ETAT.md` (convention
    d'adoptant) VOYAGENT — la jambe mord chez qui arme `BINOME_REQUIRED` ET tient
    un de ces fichiers à la racine d'un dépôt git. BORNE : un projet
    sous-répertoire d'un dépôt (monorepo) n'a pas de `.git` à sa racine — la
    jambe y est INERTE et MUETTE (mesuré). EXEMPT STRUCTURELLEMENT : le pont V3
    ferme sous `sans_binome=`. Le verrou du board est TENU pendant les appels
    git : pire cas (4 + k) appels × 5 s × 3 critiques, k le nombre d'objets
    qui partagent le préfixe tracé (1 en pratique pour 7 hex : ≈ 75 s), borne
    nommée, non fermée."""
    if preuve is None:
        return None
    vus, porteur, _perime = preuve
    if not vus:
        return None
    lignes, a_jour, fichiers, non_mesure = [], [], set(), False
    for nom in sorted(vus):
        # Une trace est du JSON quelconque (`binome_trace` relève, ne juge pas) :
        # non-dict → sha None → refus NOMMÉ par (c), jamais un traceback sous le verrou.
        t = vus[nom]
        sha = t.get("sha") if isinstance(t, dict) else None
        issue, detail = reprise_changee_depuis(root, sha)
        if issue == "inerte":
            return None
        if issue == "ok" and not detail:
            a_jour.append(nom)
            classe = "à jour"
        elif issue == "ok":
            fichiers.update(detail)
            classe = "périmé : " + ", ".join(detail)
        else:
            non_mesure = True
            classe = f"[REPRISE NON MESURÉE : {detail}]"
        lignes.append(f"  - {nom} @ {sha} — {classe}")
    if len(a_jour) >= exige:
        return None
    purge = ""
    if porteur == tid and data is not None:
        try:
            chantier = chantier_of(find(data, tid))
            slot = [t["id"] for t in data["tasks"] if t["id"] != tid and chantier
                    and t.get("state") == "running" and chantier_of(t) == chantier
                    and len(binome_trace(root, t["id"])) >= BINOME_MIN]
        except Exception:
            slot = []
        if slot:
            purge = (f"La preuve PROPRE de {tid} masque celle du slot `{slot[0]}` : "
                     f"`tasks.py binome-purge {tid}` retire la preuve propre périmée, "
                     "la preuve du slot est alors relue.\n")
    emprunt = f", preuve empruntée au slot `{porteur}`" if porteur != tid else ""
    branche_liv = livraison_preteuse(data, tid, porteur)  # T-01M4WTYSCE : l'emprunt à un membre se nomme
    if branche_liv:
        emprunt = f", preuve empruntée à `{porteur}` (livraison `{branche_liv}`)"
    return (
        f"clore {tid} exige {exige} critique(s) qui ont vu "
        "l'état COURANT des fichiers de reprise "
        f"de lot et de `PLAN-ETAT.md` ; {len(a_jour)} critique(s) à jour sur "
        f"{len(vus)}" + emprunt
        + " :\n" + "\n".join(lignes) + "\n"
        + (f"Fichiers changés depuis la revue : {', '.join(sorted(fichiers))}.\n"
           if fichiers else "")
        + "POURQUOI : l'état du chantier vit dans ces fichiers (S-00003374) ; une revue "
        "tracée AVANT leur dernière écriture ne les a pas relus (S-00003393). Le `sha` "
        "d'une trace est HEAD à l'arrêt du critique : cette garde empêche d'oublier, "
        "pas de tricher.\n"
        "REMÈDE, dans l'ordre : commite les écritures du lot sur la reprise et "
        "`PLAN-ETAT.md` ; relance `critic-opus` (repli `critic-fable`, puis "
        "`critic-sonnet-max`) APRÈS ce commit ; corrige ses constats (un correctif "
        "qui réécrit un fichier surveillé appelle UNE revue bis) ; puis la porte, puis "
        "les `done` ; la reprise se range APRÈS le dernier `done` du lot.\n"
        + ("NON MESURÉ : rends le dépôt lisible par git (la cause est nommée), puis "
           "relance — pas de passer la garde.\n" if non_mesure else "")
        + purge
        + "La sortie `--sans-binome` garde ses trois motifs prévus (doublon, ticket "
        "caduc, décision sans code) ; l'employer pour franchir CE refus n'entre dans "
        "AUCUN des trois : c'est une décision du pilote."
    )


#: LA MARQUE DE CHAÎNE (T-00001177) : une seule forme, au `start`, au `done`, à la reprise.
_MARQUE_CHAINE = "[SANS CHAÎNE DE PLAN : {}]"
_MARQUE_CHAINE_RE = r"\[SANS CHAÎNE DE PLAN : ([^\]]*)\]"


def avec_marque_chaine(stage: str | None, raison: str) -> str:
    """`stage` suivi de la marque de chaîne, JAMAIS DOUBLÉE (A-3, S-00004149) : un
    `--stage` ou un `--raison` qui la porte déjà la garde une fois. `stage` vide ou
    `None` (`--stage` est facultatif sur `start`) rend la marque seule."""
    m = _MARQUE_CHAINE.format(raison)
    if stage in (None, ""):
        return m
    return stage if m in stage else f"{stage} {m}"


def efface_derogation_chaine(task: dict[str, Any]) -> None:
    """LA DÉROGATION DE CHAÎNE DIT L'ÉTAT, PAS L'HISTOIRE (S-00004157, « T-1177 : a »).

    Retire le champ `sans_chaine` ET sa marque du stage en vol. Appelée par le
    `start` qui PAIE la chaîne (B-3) et par le `start` depuis `done` (A-1). Le stage
    AUSSI, parce que `start` sans `--stage` le garde : la marque restée là serait
    REPRISE au `done` par la jambe du board antérieur (A-8), et la dérogation
    effacée reviendrait. L'histoire reste au journal V3."""
    raison = task.pop("sans_chaine", None)
    stage = avant = task.get("stage") or ""
    if raison:
        exacte = _MARQUE_CHAINE.format(raison)
        stage = stage.replace(f" {exacte}", "").replace(exacte, "")
    stage = re.sub(" ?" + _MARQUE_CHAINE_RE, "", stage)
    if stage != avant:
        task["stage"] = stage.strip()
        task.pop("stage_actor", None)  # stage réécrit sans acteur : l'ancien ne le signe plus


def poser_acteur_stage(task: dict[str, Any], acteur: dict[str, Any] | None) -> None:
    """LE STAGE ET SON AUTEUR VONT ENSEMBLE (T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot A). Chaque
    réécriture de ``stage`` écrit ``stage_actor`` — une COPIE de l'acteur passé — ou le RETIRE
    quand l'appelant n'en donne pas (``None`` : API historiques, pont V3 avant son lot). Un stage
    PRÉSERVÉ (``stage_kept``) ne passe pas par ici et garde le sien : jamais un
    acteur périmé à côté d'un stage qu'il n'a pas écrit. Forme :
    ``{"auteur": {"nom": str|None, "email": str|None}, "copie": str|None}`` (``acteur_courant``)."""
    if acteur is None:
        task.pop("stage_actor", None)
    else:
        task["stage_actor"] = copy.deepcopy(acteur)


def remede_focus_absent(root: str, task: dict[str, Any]) -> str:
    """LE REMÈDE DE L'ADOPTANT MIS À JOUR (C39, T-01M5F7286N1EYGXAXA5244X86B) : un ``done``
    refusé faute de critique, sans ``focus.json`` au clone, NOMME ``focus`` puis
    ``review-scope`` — le board d'avant ce code ne porte aucun focus. Focus présent : ``""``."""
    if chemin_focus(root).exists():
        return ""
    cible = task["id"] if task.get("state") == "running" else "<T running>"
    membres = cible if cible == task["id"] else f"{cible} {task['id']}"
    return (f" — REMÈDE (aucun focus au clone, {FOCUS_NOM} absent) : `tasks.py focus {cible}`, puis "
            f"`tasks.py review-scope {membres} [<T>…]` (liste explicite des tâches revues) avant le "
            f"critique de clôture")


RAISON_REPRISE_PLAFOND = 200


def raison_reprise_propre(raison: str) -> str:
    """La raison de reprise ÉCRITE au stage : caractères de contrôle et de format retirés, espaces
    resserrés, caviardée (`cadre.ledger.redaction`, le caviardage de l'acteur) PUIS plafonnée à
    `RAISON_REPRISE_PLAFOND`. Rédaction introuvable ou raison vide une fois nettoyée : refus, aucun
    transfert (échec fermé)."""
    import unicodedata

    nette = " ".join("".join(c if unicodedata.category(c)[0] != "C" else " " for c in raison).split())
    rediger = getattr(_acteur_module_cadre("cadre.ledger.redaction", ("ledger", "redaction.py")), "rediger", None)
    if rediger is None:
        raise BoardError("REVENDICATION : raison de reprise non écrite, rédaction indisponible — aucune reprise")
    nette = rediger(nette)
    if len(nette) > RAISON_REPRISE_PLAFOND:
        nette = nette[:RAISON_REPRISE_PLAFOND] + ACTEUR_MARQUE
    if not nette.strip():
        raise BoardError("REVENDICATION : raison de reprise vide une fois nettoyée — aucune reprise")
    return nette


def set_state(
    root: str,
    tid: str,
    state: str,
    stage: str | None = None,
    sans_binome: str = "",
    sans_chaine: str = "",
    sans_cible: str = "",
    sans_dependances: str = "",
    retour_premesure: dict[str, Any] | None = None,
    acteur: dict[str, Any] | None = None,
    preuve_reprise: dict[str, Any] | None = None,
    propriete_attendue: dict[str, Any] | None = None,
) -> str:
    """Transition one task. Several running tasks are legitimate, grouped or not, and
    ``start`` demotes nobody (T-01M5F7286N1EYGXAXA5244X86B). ``sans_dependances``
    (T-00000765) skips the plan's ``ARÊTE:`` leg VISIBLY (``plan_depends``).
    ``retour_premesure`` (T-00001182) is the dispatch's OUT-OF-LOCK measure of
    the merge (``tasks_retour.retour_premesure``): this function runs no git and
    no extra ``load`` outside its lock; without it, a direct task crossing an
    armed guard is refused at ``done`` (« non pré-mesuré »). Under an armed
    ``BINOME_REQUIRED``, ``done`` needs ``BINOME_MIN`` distinct closing critics
    (ONE since S-00004500, T-00001226, which retired the one-critic pass flag).

    ``done`` ALSO RELEASES (T-00000182). Every task ``blocked`` with
    ``blocked_on == tid`` returns to ``pending`` in the SAME lock and the SAME
    save — a release that needed a second command would be a release nobody
    runs. Each one is announced on its own line AFTER the unchanged first line:
    ``TASKS: <tid> → done`` is a consumer contract (hooks match on it), so the
    releases are added below it, never folded into it.

    ``blocked_on`` NEVER SURVIVES AN EXIT FROM ``blocked``, whichever door the
    task leaves by — ``start``, ``done``, or ``set_state`` to ``pending``. A link left behind on a task later re-blocked for an unrelated reason
    would make the OLD blocker's closure release it, which is the one failure
    mode a machine link must not have.

    THE UPSTREAM LEG (S-01M4Z5VMP5E9YN8T6EMDTBAF0T): every ``start`` whose source
    is not ``running`` (pending, blocked OR done) is judged by
    ``jambe_amont_start`` — an open upstream, a cycle, an unreadable journal or a
    plan older than an upstream closure refuses it, unless ``sans_dependances``.
    ``done`` stamps ``done_at`` on ENTRY; every exit from ``done`` erases
    ``done_at``, ``lancee_sous`` and ``lancee_le``; a passing ``start`` writes
    ``lancee_sous``, and ``lancee_le`` (the launch instant) when that trace changes.
    A ``sans_dependances`` reason that is blank once stripped is refused, before the lock.

    ``acteur`` (T-01M5DBFK3XKKM2VHQM5RE4TP6K) is RESOLVED BY THE CALLER, out of the lock —
    this function runs no git for it. ``start_actor`` is the DURABLE owner
    (S-01M5HH8QMC4E7SYN4K6AP2SMKE): written on entry into ``running`` only when the task has no
    owner and ``acteur`` has an author, kept across cycles (an actor-less start keeps it too), and
    replaced only by a ``preuve_reprise`` checked under the lock against ``propriete_attendue``. Every rewrite of ``stage`` writes ``stage_actor`` or removes it
    (``poser_acteur_stage``); a preserved stage keeps its actor.
    """
    if sans_dependances and not sans_dependances.strip():
        raise BoardError(REFUS_SANS_DEPENDANCES_VIDE.format(
            geste=f"{'démarrer' if state == 'running' else 'passer'} {tid}", raison=sans_dependances))
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        if state == "running" and propriete_attendue is not None:
            if task.get("start_actor") != propriete_attendue.get("ancien") and task.get("start_actor") != acteur:
                raise BoardError(f"REVENDICATION: propriété de {tid} changée depuis le précontrôle")
            ancien_auteur = _rev_auteur(task.get("start_actor"))
            if ancien_auteur is not None and ancien_auteur != _rev_auteur(acteur) and preuve_reprise is None:
                raise BoardError(f"REVENDICATION: {tid} appartient à un autre pilote")
        if preuve_reprise is not None:
            if state != "running" or preuve_reprise.get("nouveau") != acteur:
                raise BoardError(f"REVENDICATION: preuve de reprise invalide pour {tid}")
            if task.get("start_actor") != preuve_reprise.get("ancien"):
                if task.get("start_actor") != acteur:
                    raise BoardError(f"REVENDICATION: propriété de {tid} changée depuis le précontrôle")
                preuve_reprise = None  # le rejeu V3 a déjà posé ce même pilote
        # Nettoyée AVANT toute jambe qui écrit : un refus ici ne laisse rien derrière lui.
        raison_reprise = (raison_reprise_propre(str(preuve_reprise.get("raison", "")))
                          if preuve_reprise is not None and preuve_reprise.get("manuel") else "")
        today = date.today().isoformat()
        released: list[tuple[dict[str, Any], dict[str, Any]]] = []
        lignes_dep: list[str] = []
        lignes_amont: list[str] = []  # la jambe d'amont DIT (reprise, dérogation, avis) après la 1re ligne
        marque_dep: str | None = None
        marque_dir = ""  # `[DIRECT SANS PLAN : …]` (T-00001178), posée par la jambe qui a franchi une garde armée
        # Chargé SEULEMENT si une jambe peut mordre (opus T5) : un frère cassé ne fait pas planter un dépôt désarmé.
        _pd = plan_depends_module() if state in ("running", "done") and (sans_dependances or cible_marqueur_present(root)) else None

        if state == "running":
            # LA CIBLE DE PLAN, AVANT LA CHAÎNE (T-00000654). Greffée ICI, AVANT
            # le bloc chaîne et sa consommation (:2300 et suivantes), pour qu'un
            # refus de cible ne consomme RIEN : sans cet ordre, une chaîne serait
            # consommée puis le `start` refusé, et la même paire de verdicts
            # deviendrait irrécupérable. La jambe `start` n'exige la cible que si
            # une trace d'approbation existe DÉJÀ (R1 seule) — sans elle, elle
            # PASSE, la cible mordant au `done`. `plan_cible` reçoit le `data` du
            # board et relit `SPECS.json` lui-même : il ne reprend jamais le
            # verrou déjà tenu ici (isolation D6).
            if not sans_cible and cible_inexploitable(root):
                raise BoardError(_REFUS_CIBLE_INEXPLOITABLE.format(geste="démarrer"))
            if not sans_cible and plan_cible_module() is not None:
                _pc = plan_cible_module()
                try:
                    refus_cible = _pc.refus_au_start(root, tid, data)
                except (_pc.CibleError, OSError, ValueError) as exc:  # ⊃ UnicodeDecodeError (plan non UTF-8)
                    # OSError EN PLUS de CibleError (À CORRIGER 2) : `_registre_pour`
                    # lève désormais `CibleError` nommée sur une spec absente, mais
                    # on capte aussi tout `OSError` résiduel pour ne jamais laisser
                    # un traceback échapper à la garde. La RACINE est retirée du message
                    # (avis de sécurité S-01M5072DQ863DE4RKPMKE9K4G1, W26), le remède reste.
                    raise BoardError(str(exc).replace(os.path.abspath(normalize_root(root)) + os.sep, "")) from exc
                if refus_cible:
                    raise BoardError(refus_cible)

            # L'AMONT D'ABORD (S-01M4Z5VMP5E9YN8T6EMDTBAF0T) : TOUT `start` dont la source n'est pas
            # `running` — pending, blocked ET done — est jugé ICI, après la cible, AVANT les arêtes et
            # la chaîne (un refus ne consomme rien), HORS de la condition `_pd` (la jambe mord sur un
            # dépôt désarmé). Depuis `done`, le cycle clos est effacé AVANT le jugement : gardé, son
            # `lancee_sous` ferait reprendre un plan périmé en REPRISE_DITE. `running` → `running`
            # (le second `start` d'une tâche en vol) n'est pas jugé. Le `start` qui passe inscrit
            # `lancee_sous` = la trace élue, quand `plan_cible` la lit (sinon rien, sans refus).
            if before["state"] == "done":
                effacer_cycle_clos(task)
            if before["state"] != "running":
                lignes_amont, sid_amont = jambe_amont_start(root, tid, data, sans_dependances)
            else:
                sid_amont = sid_elue_ou_rien(root, tid)
            if sid_amont:
                # `lancee_le` : l'instant du LANCEMENT sous cette trace, posé quand elle CHANGE (comparé après
                # l'effacement du cycle clos, avant l'affectation) ; une reprise sous la même trace le garde.
                # ÉCART DIT : le texte de S-01M50AKX95G écrit « à tout start » ; c'est le patch C6 (posé quand
                # la trace CHANGE) qui fait foi — réécrit à chaque relance, il élargirait la reprise.
                if before["state"] != "running" and task.get("lancee_sous") != sid_amont:
                    task["lancee_le"] = horodatage_done()
                task["lancee_sous"] = sid_amont

            # ARÊTES DU PLAN (T-765), après la cible, AVANT la chaîne ; `--sans-cible` passe module absent (task-board).
            if _pd is None and sans_dependances:
                raise BoardError(_REFUS_DEPENDS_VERBE_SANS_MODULE.format(geste="démarrer avec --sans-dependances"))
            if _pd is None and not sans_cible and cible_marqueur_present(root):
                raise BoardError(_REFUS_DEPENDS_INEXPLOITABLE.format(geste="démarrer"))
            if _pd is not None:
                refus_dep, lignes_dep, marque_dep = _pd.jambe_start(
                    root, tid, data, sans_dependances=sans_dependances)
                if refus_dep:
                    raise BoardError(refus_dep)
            # LA MARQUE D'UN `start --sans-dependances` est celle de la jambe d'amont (arête + amont),
            # posée QUEL QUE SOIT le marqueur : elle remplace l'ancienne marque d'arête, armée seule.
            if sans_dependances:
                marque_dep = MARQUE_SANS_DEPENDANCES.format(sans_dependances)

            # LA CHAÎNE DE PLAN, AVANT TOUTE MUTATION (T-00000624). Le refus mord
            # ICI, sur `start`, et non sur l'édition : la chaîne tourne pendant
            # que la tâche est `pending`, donc une garde par écriture serait
            # INERTE au moment où elle devrait mordre — et elle créerait une
            # circularité, le plan étant lui-même un fichier qu'il faudrait
            # écrire. `start` est le seul geste que la chaîne traverse à coup sûr.
            #
            # *** LE MARQUEUR SE TESTE ICI, ET PAS SEULEMENT DANS LE REFUS. ***
            # Défaut MESURÉ par les DEUX critiques de clôture sur `ffa66b0`, et
            # il rendait FAUSSE la phrase « la garde voyage INERTE » écrite dans
            # `AGENTS.md` : `plan_chain_refusal` testait `PLAN_GATE`, pas
            # `consume_plan_chain`. Marqueur ABSENT, le refus rendait `None` et
            # la consommation tournait quand même — donc chez un adoptant qui
            # n'a rien armé, chaque `start` effaçait des traces ET écrivait un
            # journal, et **refusait** le démarrage si ce journal n'était pas
            # écrivable (la consommation est fail-closed). Une garde livrée
            # désarmée qui refuse quand même est pire qu'une garde absente.
            #
            # *** UNE CHAÎNE PAR TÂCHE, PAS PAR `start`. *** Second défaut mesuré :
            # ce dépôt appelle `start` PLUSIEURS FOIS sur la même tâche et sur le
            # même plan. Trois cas réels, tous cassés par la version précédente :
            # un groupe parallèle DÉCLARÉ, dont la disjonction vient du shard
            # split d'UN plan ; la reprise d'une tâche sortie de `running`, qui
            # est l'étape 5 de `/kickoff` ; et le pool
            # `/planning`. Le drapeau vit sur la TÂCHE, donc il survit à la
            # sortie de `running` et voyage avec le board — et il ferme du même geste
            # le mutant « n'exiger la chaîne que depuis `pending` », qu'un
            # critique a joué vert sur 17 témoins.
            # *** L'EMPRUNT DE GROUPE EST VISIBLE, JAMAIS SILENCIEUX. ***
            # La disjonction d'un groupe parallèle vient du shard split d'UN plan,
            # donc UNE chaîne couvre légitimement le groupe. Mais
            # `declare_parallel_group` dit lui-même, dans sa docstring, qu'il est
            # « A GUARD OF COHERENCE, NOT OF SECURITY » : rien n'empêche de
            # déclarer un groupe bidon à côté d'une tâche déjà dédouanée pour
            # démarrer gratuitement. Relevé par la critique de plan, et la
            # première rédaction aggravait le cas en posant le drapeau sur la
            # tâche empruntante — qui héritait alors du dédouanement À VIE.
            #
            # DEUX CORRECTIONS, et la seconde est celle qui compte : le drapeau
            # n'est posé QUE sur la tâche dont la chaîne a réellement été
            # consommée ; et l'emprunt s'ÉCRIT au board. Même forme que l'emprunt
            # de binôme (`[binôme relevé sur T-…]`), et pour la même raison — le
            # taire ferait lire « cette tâche a eu son plan relu », quand le vrai
            # fait est « le groupe sous lequel elle tourne l'a eu ». Le pilote
            # voit alors le groupe bidon dans le champ que `list --task` rend.
            racine_chaine = Path(normalize_root(root))
            chaine_armee = (racine_chaine / PLAN_GATE).exists()
            # LA VOIE DIRECTE (T-00001178, S-00004114) : une tâche ESTAMPILLÉE par
            # `tasks.py direct` franchit la chaîne ARMÉE sans la consommer, et
            # `refus_direct` est REJOUÉ avec l'instantané — AVANT l'emprunt de
            # groupe (R5-5 : l'emprunt n'en dispense jamais) et avant toute
            # consommation. Refus : `BoardError` qui liste les causes, jamais une
            # bascule silencieuse vers la chaîne. Marqueur absent : rien n'est lu.
            directe = not sans_chaine and chaine_armee and "direct" in task
            if directe:
                marque_dir = direct_jambe_start(root, tid, task, today)
                # UNE SEULE MARQUE, L'ÉTAT (S-00004175 (1)) : la chaîne franchie par
                # la jambe directe efface la dérogation, comme la chaîne payée (B-3).
                efface_derogation_chaine(task)
            # LA MARQUE DIRECTE DIT CE `start` (F2 du binôme) : non franchi par la
            # jambe directe, il retire `chaine_franchie` — jamais héritée d'un cycle clos.
            if not directe and isinstance(task.get("direct"), dict):
                task["direct"].pop("chaine_franchie", None)
            groupe_chaine = parallel_group_of(task)
            emprunt_groupe = ""
            if bool(groupe_chaine) and not directe:
                porteurs = sorted(
                    autre["id"] for autre in data["tasks"]
                    if autre["state"] == "running"
                    and autre["id"] != tid
                    and parallel_group_of(autre) == groupe_chaine
                    and autre.get("plan_chain_consumed")
                )
                # LA FOURNÉE (`tasks_fournee.py`) : le PARENT paie la chaîne à son nom,
                # il n'emprunte jamais (sinon il l'emprunterait à une tâche étrangère
                # du groupe et ses lots après lui) ; un LOT nomme son parent quand il
                # est parmi les porteurs, sinon le premier porteur, comme avant.
                lien_lot = task.get("fournee") if isinstance(task.get("fournee"), dict) else {}
                if porteurs and "lots" not in lien_lot:
                    emprunt_groupe = lien_lot.get("parent") if lien_lot.get("parent") in porteurs else porteurs[0]
            if (
                not sans_chaine
                and chaine_armee
                and not task.get("plan_chain_consumed")
                and not emprunt_groupe
                and not directe
            ):
                refus_plan = plan_chain_refusal(root, tid)
                if refus_plan:
                    raise BoardError(refus_plan)
                # LA CONSOMMATION PRÉCÈDE LE `save`, ET C'EST LE SENS SÛR DE
                # L'ERREUR : si une étape ultérieure échoue, les traces sont
                # perdues et il faut rejouer la chaîne — coûteux mais fermé.
                consume_plan_chain(root, tid)
                # LE DRAPEAU NE SE POSE QUE LÀ : sur la tâche qui a réellement
                # payé la chaîne. Une empruntante ne l'hérite pas, donc son
                # prochain `start` hors groupe la redemandera. ET LA DÉROGATION
                # TOMBE LÀ (B-3, S-00004157) : la chaîne payée, le board dit l'état
                # final — la marque disparaît, l'histoire reste au journal V3.
                task["plan_chain_consumed"] = True
                efface_derogation_chaine(task)

            # UN `start` DEPUIS `done` REPART SANS DÉROGATION HÉRITÉE (A-1, S-00004157) :
            # elle couvrait le cycle clos ; un `--sans-chaine` de CE `start` la repose plus bas.
            if before["state"] == "done":
                efface_derogation_chaine(task)
            # ET SANS RELEVÉ HÉRITÉ (T-00001182), comme `reopen` : resté, il admettrait le `done`
            # de ce cycle sur la fusion du cycle clos (forme de T-624, mesurée au dev).
            if before["state"] == "done":
                task.pop("retour", None)
            # NI LIVRAISON HÉRITÉE (T-01M4WTYSCE), comme `reopen` : la clôture annulée emporte sa revue.
            if before["state"] == "done":
                task.pop("livraison", None)

            # `start` NE RÉTROGRADE PLUS PERSONNE (T-01M5F7286N1EYGXAXA5244X86B, décision
            # pilote S-01M5DBTHMEAEXGD93Q284GJPJE). Il rétrogradait toute running hors du
            # groupe de la tâche démarrée : sur deux postes, ou deux sessions d'un clone,
            # le `start` de l'un sortait la tâche de l'autre. Les autres running gardent
            # état, stage, acteur et groupe ; seule une sortie EXPLICITE de `running`
            # vers `pending` ou `blocked` (`block`, `set_state`) inscrit `lancee_sous`. Le focus
            # du clone, lui, passe à la tâche démarrée (`poser_focus`, depuis `main`).
            # CAPACITÉ PERDUE, DITE (F2 de la clôture) : le `start` ne prouve plus la disjonction ;
            # une running HORS du groupe de la tâche qui recouvre son write-set est un AVIS, jamais
            # un refus (refuser serait une décision pilote) — `parallel` refusera de les grouper.
            for autre in data["tasks"]:
                if autre["id"] == tid or autre["state"] != "running" or not writeset_of(task):
                    continue
                if groupe_chaine and parallel_group_of(autre) == groupe_chaine:
                    continue
                paire = writeset_paths_overlap(writeset_of(task), writeset_of(autre))
                if paire is not None:
                    lignes_dep = [*lignes_dep, (
                        f"TASKS: AVIS — {tid} (`{paire[0]}`) recouvre la running {autre['id']} (`{paire[1]}`), "
                        f"hors de tout groupe prouvé : sérialise-les ; `tasks.py parallel` refusera de les grouper")]

        # LA CLÔTURE DIT POURQUOI, ET C'EST STRUCTUREL PLUTÔT QUE CLI. La garde
        # vit ICI et non dans `argparse` parce que la CLI n'est pas le seul
        # chemin vers `done` : le pont V3 (`board_bridge.py`) et le tableau de
        # bord ferment aussi des tâches. Une exigence posée au parseur seul
        # aurait laissé deux portes ouvertes, et une règle qu'on peut contourner
        # par une autre porte n'est pas une règle.
        #
        # POURQUOI EXIGER UN MOTIF. `done` était le seul verbe terminal sans
        # explication : le board affirmait « c'est fini » sans jamais dire au nom
        # de quoi. Mesuré le 2026-09-12 sur T-00000560 et T-00000561, deux
        # clôtures dont on a dû reconstituer la justification a posteriori,
        # contre le dépôt, pour découvrir qu'elle n'existait pas.
        if state == "done" and not (stage or "").strip():
            raise BoardError(
                f"clore {tid} exige un motif : `tasks.py done {tid} --raison \"<pourquoi>\"`. "
                "Une clôture sans motif est une affirmation que personne ne peut "
                "vérifier plus tard — et c'est en la reconstituant contre le dépôt "
                "qu'on découvre, parfois, qu'elle était fausse."
            )
        emprunt = ""
        if state == "done" and not sans_binome:
            # UN SEUL CALCUL DE PREUVE, pour le refus ET pour la mention
            # (T-00000846). Deux appels à `binome_preuve` lisaient l'horloge à
            # deux instants : à 24 h pile d'une trace empruntée, le refus était
            # franchi puis la mention calculée VIDE — un emprunt clos sans que
            # le board le dise. Gate absente : rien à calculer, rien à écrire.
            armee = (Path(normalize_root(root)) / BINOME_GATE).exists()
            # UN SEUL NOMBRE, CELUI DE LA FAÇADE (S-00004500) : la jambe reprise
            # exige autant de critiques à jour que `binome_refusal` de traces.
            exige = BINOME_MIN
            preuve = binome_preuve(root, tid, data) if armee else None
            refus = binome_refusal(root, tid, preuve) or binome_reprise_refusal(
                root, tid, preuve, data, exige=exige)
            if refus:
                raise BoardError(refus + remede_focus_absent(root, task))
            # L'EMPRUNT SE VOIT AU BOARD, sinon il n'a pas eu lieu pour le
            # lecteur. Une preuve portée par le slot `running` du chantier reste
            # une preuve indirecte : la taire ferait lire « cette tâche a été
            # relue », quand le vrai fait est « le lot fermé sous ce slot l'a
            # été ». Le champ que `list --task` rend en entier est le seul
            # endroit où ça survit à la session.
            if preuve is not None:
                _vus, porteur, _perime = preuve
                if _vus and porteur != tid:
                    # L'EMPRUNT PORTE SON ÂGE — et depuis `T-00000592` il EXPIRE.
                    # Une trace antérieure à l'AVANT-DERNIER verdict vert est
                    # refusée par `binome_refusal`, avec un refus qui nomme
                    # l'expiration ; sans deux verts frozen, c'est une trace de
                    # plus de 24 h (T-00000846). La rédaction précédente disait « une
                    # faiblesse que la garde ne ferme pas encore » et « tant que
                    # l'arbitrage n'est pas rendu » : il l'est, trente lignes
                    # plus haut, et un commentaire qui nie une garantie tenue
                    # fait qu'on ne s'y fie pas.
                    # CE QUI RESTE ÉCRIT ICI EST LE COÛT ASSUMÉ : un binôme
                    # couvre tout le lot fermé sous la MÊME porte. Le board dit
                    # donc quand la revue a eu lieu et sur quel SHA, pour qu'un
                    # lecteur voie le PÉRIMÈTRE du lot.
                    quand = sorted(
                        (v or {}).get("at", "?") for v in _vus.values()
                    )[-1]
                    shas = sorted({(v or {}).get("sha", "?") for v in _vus.values()})
                    emprunt = f" [binôme relevé sur {porteur} @ {'/'.join(shas)}, {quand}]"
                    # LA LIVRAISON SE NOMME (T-01M4WTYSCE) : la preuve vient d'un MEMBRE, pas du slot.
                    branche_liv = livraison_preteuse(data, tid, porteur)
                    if branche_liv:
                        emprunt = (f" [binôme de la livraison {branche_liv} relevé sur {porteur} @ "
                                   f"{'/'.join(shas)}, {quand}]")
        # LA CIBLE DE PLAN AU `done` (T-00000654), APRÈS le binôme. Même isolation
        # que la jambe `start` : `plan_cible` reçoit le `data` du board et relit
        # `SPECS.json` LUI-MÊME, il ne reprend JAMAIS le `board_lock` tenu ici
        # (D6) — un ré-emprunt du verrou interbloquerait jusqu'au timeout, ce que
        # `cli_done_arme_sous_processus` éprouve en sous-processus réel. La
        # résolution D8 est R1 (dernière trace `plan approuvé` propre de la tâche,
        # empreinte recalculée identique) puis R2 (slot `running` du même chantier
        # dont le plan NOMME la tâche) ; sans plan approuvé, c'est un refus
        # fail-closed dont `evaluer_done` NOMME la cause (aucune trace, empreinte
        # divergente citant les deux sha, plan non enrôlant citant la ligne 1).
        emprunt_cible = ""
        if state == "done" and not sans_cible and cible_inexploitable(root):
            raise BoardError(_REFUS_CIBLE_INEXPLOITABLE.format(geste="clore"))
        if state == "done" and not sans_cible and plan_cible_module() is not None:
            _pc = plan_cible_module()
            try:
                # LA VOIE DIRECTE AU `done` (T-00001178) : sous cible ARMÉE, SANS plan
                # résolu (R3) et estampillée, `refus_direct` rejoué sur le titre et le
                # stage STOCKÉS remplace `evaluer_done` ; un plan résolu (R1/R2) est
                # TOUJOURS contrôlé ; un refus direct rend le refus R3 plus ses causes.
                refus_cible, note_cible, marque_dir = direct_jambe_done(root, tid, task, data, _pc)
            except (_pc.CibleError, OSError, ValueError) as exc:  # ⊃ UnicodeDecodeError (plan non UTF-8)
                # OSError EN PLUS de CibleError (À CORRIGER 2) : spec du marqueur
                # absente du disque → `_registre_pour` lève `CibleError`, et tout
                # `OSError` résiduel est capté ici plutôt que de tracer. La RACINE est
                # retirée, même forme que la jambe `start` (S-01M5072DQ863DE4RKPMKE9K4G1).
                raise BoardError(str(exc).replace(os.path.abspath(normalize_root(root)) + os.sep, "")) from exc
            if refus_cible:
                raise BoardError(refus_cible)
            # L'EMPRUNT SE VOIT AU BOARD, exactement comme celui du binôme : une
            # cible relevée sur le slot `running` d'un AUTRE est une preuve
            # INDIRECTE. La taire ferait lire « cette tâche portait sa cible »,
            # quand le vrai fait est « le slot sous lequel elle tourne la
            # portait ». Le champ que `list --task` rend en entier est le seul
            # endroit où l'emprunt survit à la session.
            emprunt_cible = note_cible
        # ARÊTES AU `done` (T-765) : sous `sans_cible` (pont V3) la jambe DIT, module absent compris (marque, opus T3).
        if state == "done" and _pd is None and sans_dependances:
            raise BoardError(_REFUS_DEPENDS_VERBE_SANS_MODULE.format(geste="clore avec --sans-dependances"))
        if state == "done" and _pd is None and cible_marqueur_present(root):
            if not sans_cible:
                raise BoardError(_REFUS_DEPENDS_INEXPLOITABLE.format(geste="clore"))
            marque_dep = "[SANS DÉPENDANCES : plan_depends absent, relevé sous --sans-cible]"
        if state == "done" and _pd is not None:
            refus_dep, lignes_dep, marque_dep = _pd.jambe_done(
                root, tid, data, sans_dependances=sans_dependances, sans_cible=sans_cible)
            if refus_dep:
                raise BoardError(refus_dep)
        # L'EPIC DU PLAN AU `done` (T-00001043), JUSTE APRÈS les arêtes, sur le `data`
        # pris SOUS ce verrou : même régime (`_arme_pour_tache`), même plan (R1 puis R2).
        # Sous `sans_cible` (pont V3) elle se tait, et `[SANS CIBLE : …]` ci-dessous le dit.
        if state == "done" and not sans_cible:
            refus_epic = refus_epic_au_done(root, tid, data)
            if refus_epic:
                raise BoardError(refus_epic)
        if state == "done" and sans_binome:
            # LA DÉROGATION S'AJOUTE AU MOTIF, ELLE NE LE REMPLACE PAS — et sa
            # place ICI, après les deux gardes, est un correctif du binôme de
            # clôture. Composée dans la CLI, elle rendait `stage` non vide AVANT
            # que la garde du motif le teste : `done --raison "" --sans-binome
            # "doublon"` passait alors avec rc=0, rouvrant la garde du
            # 2026-09-12 dont toute la raison d'être est qu'une clôture dise au
            # nom de quoi. Mesuré par le binôme, pas raisonné.
            #
            # ELLE VIT DANS `set_state` POUR LA RAISON HABITUELLE : la CLI n'est
            # pas le seul chemin vers `done`. Le pont V3 et le tableau de bord
            # passent aussi `sans_binome`, et leur dérogation doit être VISIBLE
            # au board comme celle d'un humain.
            stage = f"{stage} [SANS BINÔME : {sans_binome}]"
        if state == "done" and sans_cible and cible_marqueur_present(root):
            # MÊME FORME que la dérogation du binôme au `done` : la raison
            # s'AJOUTE au motif, elle ne le remplace pas. Elle vit dans
            # `set_state` parce que la CLI n'est pas le seul chemin vers `done` —
            # le pont V3 et le tableau de bord passent aussi `sans_cible`, et leur
            # dérogation doit être VISIBLE au board comme celle d'un humain.
            # GARDÉE PAR LA PRÉSENCE DU MARQUEUR (décision orchestrateur) : sur un
            # dépôt DÉSARMÉ, une dérogation de cible n'a pas lieu d'être — la
            # marquer y ferait lire une contrainte qui n'existe pas.
            stage = f"{stage} [SANS CIBLE : {sans_cible}]"
        # LA DÉROGATION DE CHAÎNE SE RELIT AU `done` (T-00001177, S-00004106),
        # MÊME FORME qu'au `start`, à côté du binôme et de la cible. Mesuré :
        # `done --raison renommé` rendait « renommé [SANS BINÔME …] [SANS
        # CIBLE …] » sans elle, quand la doc promet la raison VISIBLE au board.
        # Non gardée par `PLAN_GATE` : la marque du `start` ne l'est pas.
        raison_chaine = (task.get("sans_chaine") or "") if state == "done" else ""
        if state == "done" and not raison_chaine and not task.get("plan_chain_consumed"):
            # BOARD ANTÉRIEUR À T-1177 (A-8, S-00004149) : son `start --sans-chaine`
            # n'écrivait que la marque au stage, pas le champ ; elle est REPRISE du
            # stage d'avant le `done`. JAMAIS sur une chaîne payée (B-3) : le board
            # ne dit pas si la dérogation précède ou suit ce paiement, ce cas garde
            # le comportement d'avant (pas de marque). Les effacements de
            # `efface_derogation_chaine` vident aussi le stage : rien à reprendre.
            reprises = re.findall(_MARQUE_CHAINE_RE, before.get("stage") or "")
            if reprises:
                raison_chaine = task["sans_chaine"] = reprises[-1]
        if raison_chaine:
            stage = avec_marque_chaine(stage, raison_chaine)
        if state == "running" and sans_chaine:
            # MÊME FORME, MÊME RAISON que la dérogation du binôme : l'exception
            # se VOIT au board, sinon elle n'a pas eu lieu pour le lecteur. Et
            # elle vit dans `set_state` et non dans la CLI, parce que la CLI
            # n'est pas le seul chemin vers `running`.
            #
            # ELLE EST AGENT-ÉCRIVABLE, décision pilote du 2026-09-14, et le
            # raisonnement doit survivre ici : cette garde mord sur CHAQUE tâche,
            # y compris une coquille ou un renommage. Une garde sans échappatoire
            # praticable est désarmée dans la semaine — ce dépôt l'a mesuré deux
            # fois. On ferme donc l'OUBLI, pas la TRICHE, et la raison visible au
            # board est ce qui rend la triche coûteuse plutôt qu'impossible.
            #
            # `--stage` EST FACULTATIF SUR `start`, contrairement au `--raison`
            # de `done` : sans ce test le board affichait le littéral `None`
            # collé à la dérogation (mesuré sur banc). Une dérogation illisible
            # est une dérogation qu'on ne relit pas.
            stage = avec_marque_chaine(stage, sans_chaine)
            # LA RAISON VIT AUSSI SUR LA TÂCHE (T-00001177) : `done` remplace ce
            # `stage` par son `--raison`, et sans ce champ la dérogation sortait
            # du board à la clôture. `done` la relit, `reopen` l'efface, un second
            # `--sans-chaine` la REMPLACE (A-2), la chaîne payée l'efface (B-3).
            task["sans_chaine"] = sans_chaine
        if state == "running" and sans_cible and cible_marqueur_present(root):
            # MÊME FORME, MÊME RAISON que la dérogation de chaîne : l'exception
            # se VOIT au board, sinon elle n'a pas eu lieu pour le lecteur. Elle
            # est agent-écrivable et vit dans `set_state`, pas dans la CLI, parce
            # que la CLI n'est pas le seul chemin vers `running`. Le test
            # `stage in (None, "")` évite d'afficher le littéral `None` collé à
            # la dérogation quand `--stage` est omis. GARDÉE PAR LA PRÉSENCE DU
            # MARQUEUR (décision orchestrateur) : pas de marque sur un dépôt
            # désarmé, comme au `done`.
            marque = f"[SANS CIBLE : {sans_cible}]"
            stage = marque if stage in (None, "") else f"{stage} {marque}"
        if marque_dep:  # `[SANS DÉPENDANCES : …]`, forme de `[SANS CIBLE]`, gardée par la jambe
            stage = marque_dep if stage in (None, "") else f"{stage} {marque_dep}"
        if state == "done" and not marque_dir:
            marque_dir = direct_marque_franchie(task)  # la chaîne franchie au `start` SURVIT au `done`
        # LA JAMBE RETOUR (T-00001182, S-00004192 voie (a)) : la directe qui franchit une garde armée
        # exige le relevé ok de sa branche fusionnée `--no-ff` et un verdict de sécurité après lui ;
        # la fusion se lit sur `retour_premesure`, mesurée HORS verrou par le dispatch `done`.
        if state == "done" and marque_dir and not sans_cible:
            releve = task.get("retour")
            borne = releve.get("specs_borne") if isinstance(releve, dict) and releve.get("verdict") == "ok" else None
            causes_secu, note_secu = retour_refus_securite(root, tid, task, data, borne)
            causes_retour = retour_refus_done(root, tid, task, data, retour_premesure) + causes_secu
            if causes_retour:
                raise BoardError(retour_message_refus(tid, causes_retour))
            if note_secu:
                marque_dir = f"{marque_dir} {note_secu}"
        if state == "done" and marque_dir and sans_cible:
            # C1 (S-00004199) : la jambe retour sautée se DIT. Sous cible armée aussi (binôme c4f3
            # F4) : `[SANS CIBLE]` dit la cible sautée, `[SANS RELEVÉ]` la jambe retour — deux marques.
            marque_dir = f"{marque_dir} [SANS RELEVÉ : {sans_cible}]"
        if marque_dir:  # `[DIRECT SANS PLAN : …]`, même forme, posée là où une garde armée a été franchie
            stage = marque_dir if stage in (None, "") else f"{stage} {marque_dir}"
        if state == "running" and emprunt_groupe:
            # L'EMPRUNT S'ÉCRIT, sinon il n'a pas eu lieu pour le lecteur. Un
            # groupe parallèle prouve la COHÉRENCE des writesets, jamais qu'un
            # plan commun existe — donc le pilote doit voir de QUI cette tâche
            # tient son dédouanement, et juger si le groupe était réel.
            emprunt = f"[chaîne de plan empruntée au groupe, portée par {emprunt_groupe}]"
            stage = emprunt if stage in (None, "") else f"{stage} {emprunt}"
        if state == "done" and emprunt:
            stage = f"{stage}{emprunt}"
        if state == "done" and emprunt_cible:
            # La note de `plan_cible` n'a pas d'espace de tête (contrairement à
            # `emprunt` du binôme), on en pose un ici.
            stage = f"{stage} {emprunt_cible}"
        # LE CYCLE D'AMONT (S-01M4Z5VMP5E9YN8T6EMDTBAF0T) : `done_at` à l'ENTRÉE dans `done` seulement
        # (un `done` rejoué ne le réécrit pas) ; toute sortie de `done` efface le cycle clos — vers
        # `running` c'est fait AVANT le jugement, plus haut, et le refaire ici effacerait le
        # `lancee_sous` que ce `start` vient d'inscrire (mesuré, W16b) ; une sortie de `running`
        # vers pending ou blocked inscrit `lancee_sous` s'il manque. Ces deux branches servent les
        # appelants de `set_state` à `pending`/`blocked` (API de STATES ; test_tasks.py:2020) — W24.
        if state == "done" and before["state"] != "done":
            task["done_at"] = horodatage_done()
        if before["state"] == "done" and state not in ("done", "running"):
            effacer_cycle_clos(task)
        if before["state"] == "running" and state in ("pending", "blocked"):
            inscrire_lancee_sous(root, task)
        if state == "running" and before["state"] != "running":
            # LE PROPRIÉTAIRE DURABLE : posé à la 1re prise avec un auteur, gardé d'un cycle à l'autre ;
            # seule une reprise prouvée le remplace.
            if _rev_auteur(task.get("start_actor")) is None and _rev_auteur(acteur) is not None:
                task["start_actor"] = copy.deepcopy(acteur)
            elif preuve_reprise is not None:
                task["start_actor"] = copy.deepcopy(acteur)
        elif state == "running" and preuve_reprise is not None:
            # Tous les refus du démarrage sont déjà passés ; propriété et intention
            # Jira sont écrites dans le même save, sous ce verrou.
            task["start_actor"] = copy.deepcopy(acteur)
        if state == "running" and preuve_reprise is not None and preuve_reprise.get("manuel"):
            # LA REPRISE LEVÉE GARDÉE AU BOARD (S-01M5HH8QMC) : les prises étrangères `{auteur, transition}`
            # que CETTE reprise a levées ; seule la même prise, encore poussée, devient un avis ensuite.
            # Durable comme `start_actor` : une nouvelle reprise la remplace, un nouveau cycle de l'ancien
            # pilote porte une autre transition et refuse toujours.
            levees = preuve_reprise.get("levees")
            if isinstance(levees, list) and levees:
                task["reprise_levee"] = copy.deepcopy(levees)
            else:
                task.pop("reprise_levee", None)
            marque_reprise = f"[REPRISE : {raison_reprise}]"
            courant_stage = task.get("stage") if stage is None else stage
            stage = marque_reprise if not courant_stage else f"{courant_stage} {marque_reprise}"
        task["state"] = state
        if stage is not None:
            task["stage"] = stage
            poser_acteur_stage(task, acteur)
        elif before["state"] == "blocked" and state != "blocked":
            # SORTIR DE `blocked` N'EMPORTE JAMAIS SON MOTIF, et cette ligne
            # répare une régression que T-00000577 venait d'introduire.
            # `stage` porte deux choses SELON L'ÉTAT : l'étape EN VOL quand la
            # tâche tourne, le MOTIF quand elle est bloquée. Faire de `None` un
            # « ne touche pas » est juste quand la tâche quitte `running` ; c'est
            # faux quand elle quitte `blocked`, parce que cela PROMEUT un motif
            # d'attente en étape de pipeline. Les trois autres sorties de
            # `blocked` l'effacent déjà (`unblock`, la libération au `done` d'un
            # bloqueur, et `done` qui l'écrase par sa raison) : `start` était la
            # quatrième et avait cessé de le faire.
            # Mesuré le 2026-09-13 : une tâche bloquée sur « attente decision
            # pilote » ressortait `running` en portant ce motif comme étape, et
            # la statusline affichait « ▶ T-NNN attente decision pilote » — sur
            # une tâche qui TOURNE, alors que la doctrine dit qu'une tâche qui
            # attend le pilote est `blocked`, jamais `running`.
            #
            # MAIS UNE ÉTAPE PRÉSERVÉE N'EST PAS UN MOTIF (T-00000578), et cette
            # ligne l'effaçait aussi. `block --on` SANS note PRÉSERVE l'étape en
            # vol : le champ porte alors l'étape, pas la raison d'attendre, et la
            # vider fait perdre à la tâche sa place dans le pipeline. Mesuré le
            # 2026-09-13 sur les TROIS sorties de `blocked` — `unblock`, `start`,
            # et la libération au `done` du bloqueur : `security-code-review`
            # ressortait vide à chaque fois. `stage_kept` est le seul moyen de
            # distinguer les deux contenus, puisqu'ils vivent dans le MÊME champ.
            if not task.get("stage_kept"):
                task["stage"] = ""
                task.pop("stage_actor", None)
        if state == "done":
            # LE MOTIF REMPLACE L'ÉTAPE EN VOL, il ne s'ajoute pas à côté. `stage`
            # nomme l'étape de pipeline en cours OU, sur une tâche terminale, ce
            # qui la termine : une tâche close n'a plus d'étape en vol, donc le
            # champ est libre et reste lisible par tout relevé existant, sans
            # qu'aucun consommateur change. C'est déjà là que `block` et `reopen`
            # écrivent les leurs.
            task["stage"] = stage.strip()
        if state != "blocked":
            task.pop("blocked_on", None)
            # LE MARQUEUR MEURT AVEC L'ÉTAT QUI LE JUSTIFIE — même discipline
            # que `blocked_on` juste au-dessus, et pour la même raison : il ne
            # décrit qu'un séjour dans `blocked`. Le laisser survivre ferait
            # qu'un blocage ULTÉRIEUR, celui-là avec un motif, croirait devoir
            # préserver une étape qui n'existe plus.
            task.pop("stage_kept", None)
        # `released_on_done` DÉCRIT UNE CLÔTURE ET UNE SEULE, donc il ne survit à
        # aucune transition — même discipline que `blocked_on`, et pour la même
        # raison : une liste laissée derrière ferait rétablir, à la prochaine
        # réouverture, des liens qu'une AUTRE clôture avait libérés. Il est effacé
        # ici et reposé juste en dessous si la transition est bien un `done`.
        task.pop("released_on_done", None)
        task["updated"] = today

        if state == "done":
            for other in data["tasks"]:
                if other["id"] != tid and other["state"] == "blocked" and other.get("blocked_on") == tid:
                    other_before = copy.deepcopy(other)
                    other.pop("blocked_on", None)
                    # UNE ÉTAPE PRÉSERVÉE SURVIT À LA LIBÉRATION (T-00000578).
                    # Ce chemin vidait `stage` sans regarder ce qu'il portait :
                    # sur une tâche bloquée par `--on` SANS note, le champ tient
                    # l'ÉTAPE EN VOL, pas un motif, et la vider faisait perdre à
                    # la tâche sa place dans le pipeline au moment même où elle
                    # la reprend. Mesuré le 2026-09-13.
                    garde = bool(other.pop("stage_kept", None))
                    other.update(state="pending", updated=today)
                    if not garde:
                        other["stage"] = ""
                        other.pop("stage_actor", None)
                    released.append((other_before, copy.deepcopy(other)))
            # LA MÉMOIRE DE CE QUE CETTE CLÔTURE A LIBÉRÉ, et c'est ce qui rend
            # `reopen` capable de défaire ce que `done` a fait. Sans elle, le
            # lien `blocked_on` était effacé et n'existait plus NULLE PART :
            # rouvrir ne pouvait pas le rétablir, et le disait.
            #
            # ELLE VIT SUR LA TÂCHE QUI FERME, pas sur celles qu'elle libère, et
            # ce choix est le fond du mécanisme. Un marqueur posé sur une tâche
            # tierce lui survivrait — elle peut être démarrée, re-bloquée pour
            # une autre raison, close — et re-bloquerait alors sur un motif
            # périmé, exactement le mode d'échec qu'un lien machine ne doit pas
            # avoir. Ici la liste naît et meurt avec la clôture qui l'a produite :
            # réécrite à chaque nouvelle fermeture, effacée à la réouverture,
            # disparue avec la tâche.
            if released:
                task["released_on_done"] = [after["id"] for _, after in released]

        if state == "running":
            jira_prepare_claim(task, acteur)

        # `BOARD_RUNNING_REPLACED` n'est plus émis : aucun `start` ne remplace une running
        # (T-01M5F7286N1EYGXAXA5244X86B) ; le genre reste au vocabulaire (`SYNC_EVENT_KINDS`).
        enqueue_sync_intent(data, tid, before, task)
        if released:
            # OUTSIDE the V3 suppression, deliberately. `suppress_sync` silences
            # the intent for the command the bridge is CURRENTLY applying — it is
            # the bridge's own effect, already an event on its side, and re-emitting
            # it would loop. A release is NOT that effect: it is a side effect on
            # ANOTHER task the bridge never asked about, so V3 learns of it here or
            # nowhere, and its projection would keep showing a blocked task the
            # board has already freed. Resetting the contextvar to None for these
            # enqueues only (the gate is `is not None`) leaves the suppression
            # intact for everything else in the operation.
            token = _SUPPRESSED_SYNC_OPERATION.set(None)
            try:
                for other_before, other_after in released:
                    enqueue_sync_intent(data, other_after["id"], other_before, other_after)
            finally:
                _SUPPRESSED_SYNC_OPERATION.reset(token)
        save(root, data)
    lines = [f"TASKS: {tid} → {state}"]
    lines += lignes_amont  # le DIRE de la jambe d'amont (REPRISE_DITE, dérogation, avis)
    lines += lignes_dep  # le DIRE des arêtes (sous --sans-cible), après la 1re ligne
    lines += [
        f"TASKS: {other_after['id']} → pending (was blocked on {tid})"
        for _, other_after in released
    ]
    if state == "done":
        # `depends_on` NEVER TOUCHES `state`, and `done` stays a DIRE: closing a task
        # whose upstream is still open is ALLOWED, but SAID — only `start` (and the
        # fournee) refuse an open upstream (S-01M4Z5VMP5E9YN8T6EMDTBAF0T). No state
        # changes and nothing is raised here (a BoardError would refuse a legitimate
        # close, e.g. the V3 bridge's). Only fired when at least one edge is unmet.
        motifs = task.get("depends_motif", {}) or {}
        unmet = []
        for dep in depends_on_of(task):
            other = next((t for t in data["tasks"] if t["id"] == dep), None)
            if other is None or other["state"] != "done":
                unmet.append(f"{dep} (motif : {(motifs.get(dep) or '').strip() or 'héritée'})")
        if unmet:
            lines.append(
                f"TASKS: {tid} close avec {len(unmet)} dépendance(s) non "
                f"satisfaite(s) : {', '.join(unmet)} — la clôture reste un DIRE ; "
                f"seul un `start` refuse un amont ouvert (`tasks.py deps-ready {tid}`)"
            )
    return "\n".join(lines)


def stage_task(root: str, tid: str, stage: str, acteur: dict[str, Any] | None = None) -> str:
    """Change only the stage — and its ``stage_actor`` (``poser_acteur_stage``) — and record
    one metadata observation."""
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        task["stage"] = stage
        poser_acteur_stage(task, acteur)
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    return f"TASKS: {tid} staged"


def stage_running_task(root: str, tid: str, stage: str, acteur: dict[str, Any] | None = None) -> str:
    """Stage only while ``tid`` is still ONE OF the running tasks, under lock.

    This was the tightest coupling to singularity in the module: it required the
    running list to equal ``[tid]``. It now requires ``tid`` to be running and to
    be IN that list (T-00000188). SINCE T-01M5F7286N1EYGXAXA5244X86B several running
    tasks are legitimate WITHOUT a shared group, so "one of the running tasks" no
    longer implies one proven group, and a stage on a running task OUTSIDE the
    clone's focus is NOT refused here. FN17 judges the claim at start/fournee only;
    stage, block and done do not recheck another author's claim. A task that is
    no longer running at all is still refused, which is what this guard is for
    (réserve C47)."""
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        running_ids = [item["id"] for item in data["tasks"] if item["state"] == "running"]
        if task["state"] != "running":
            raise BoardError(
                f"{tid} is no longer one of the running tasks "
                f"(running: {', '.join(running_ids) or 'none'}); refusing stage update"
            )
        before = copy.deepcopy(task)
        task["stage"] = stage
        poser_acteur_stage(task, acteur)
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, tid, before, task)
        save(root, data)
    return f"TASKS: {tid} staged"
