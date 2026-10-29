# tasks_fournee.py — PARTIE de `tasks.py` (T-01M4V1JD628K07PXF7FFDSN0Q3) : LA FOURNÉE —
# le verbe `fournee <T-parent>`, qui fait d'un plan APPROUVÉ découpé en lots
# (`plan_lots.py`) N sous-tâches lancées EN PARALLÈLE, en un geste. Exécutée dans
# l'espace de noms de `tasks` par `_charger_parties()`, jamais importée seule : ses
# noms libres viennent de la façade et des parties amont. Elle OUVRE SUR UN
# COMMENTAIRE, jamais sur une docstring (test_tasks_decoupe.py, témoin (d)).
#
# DÉCISION PILOTE : S-01M4V1K1DG9WY2WKWKWN7ZGFC7. CE QUI VOYAGE NE PORTE AUCUN ID DU
# KIT : les sorties et les refus sont lus sur le board de chaque adoptant.
#
# LA TRACE. La dernière décision du parent titrée EXACTEMENT `plan approuvé`
# (`plan_cible.trace_plan_approuve` : jamais `night-eligible`, jamais un verdict),
# `plan=` sûr, sha256 recalculé identique. Exigée, marqueurs armés ou non, recopiée
# en `fournee.trace`. Auto-déclarative : elle empêche d'OUBLIER, pas de TRICHER.
#
# LE PRÉVOL est PUR et recalculé à CHAQUE appel ; il liste TOUS ses refus et
# n'écrit rien : la grammaire et l'enrôlement du parent ; l'état du parent
# (`pending`, `running` sans groupe, ou `running` dans le groupe de SA fournée) ;
# pas d'estampille `direct` sur le parent ; le sha256 des lots OUVERTS égal à
# celui de la trace élue (un lot CLOS reste clos sous son ancien plan : sauté,
# jamais refait, et ce que le nouveau plan lui ajoute est DIT sans porteur) ; aucun
# lot ouvert sur le chemin du plan ; la garde de mesure rejouée pour chaque lot à
# créer ; les jambes `start` du parent rejouées à blanc ; R, les `running` hors
# fournée, dont le write-set DÉCLARÉ ne doit recouvrir aucun ensemble de la fournée,
# puis l'UNION du parent et des lots ouverts deux à deux (les tests de `parallel`).
# `--dry-run` rend le même code que le vrai lancement : un refus est rc 2.
#
# LES RUNNING ÉTRANGÈRES SONT PRÉSERVÉES (T-01M5F728B4CS1ZDZTH9YWJ0AZ1,
# S-01M5DBTHMEAEXGD93Q284GJPJE) : plusieurs `running` sont légitimes, donc R n'est NI
# embarquée dans le groupe de la fournée NI rétrogradée — état, stage et groupe gardés.
# Une R SANS write-set refuse toujours (disjonction vide, S-01M5FDAP4N) ; une R réduite à
# son plan est DITE ; les liens et recouvrements entre deux R ne regardent pas la
# fournée ; un lien d'un lot `pending` vers R est jugé par le relevé d'amont du lot.
#
# LA DÉGÉNÉRÉE (`LOTS: aucun`, ou aucune forme) : le parent seul, dont le write-set
# DÉCLARÉ au board (`tasks.py writeset` AVANT la fournée) est exigé — chaque chemin
# ADMISSIBLE (un chemin écrit à la main que `writeset` refuserait est refusé, nommé), au
# moins un hors du plan, en forme canonique —, jamais réécrit, et, avec son plan, juge de la
# disjonction contre R ; une `running` de R parent de dégénérée réduite à son plan
# (board abîmé par l'ancien code) est DITE, son remède nommé.
#
# LE CHOIX B (constat C1 de l'itération 2), borné au groupe du PARENT qui tourne : la
# relance n'y garde un groupe que si TOUS ses membres non clos tournent — les membres
# de la fournée elle-même (parent et lots, démarrés à l'étape 6) exceptés. Sinon refus
# nommé : `parallel` poserait un id NEUF sur nos seuls membres, et un membre `pending`
# ou `blocked` du groupe, que rien ne protège, en sortirait. JAMAIS de rétrogradation.
#
# L'ÉCRITURE, sous UN `board_lock` réentrant, en six étapes qui COMPLÈTENT le
# manquant sans jamais réécrire : (1) les lots absents, `new_task` avec leur lien,
# en UNE sauvegarde chacun ; (2) les write-sets ; (3) `direct` tenté sur chaque lot
# sans estampille ; (4) `parallel` sur le parent et les lots ouverts ; (5) `start`
# du parent, qui paie la chaîne UNE fois, à son nom ; (6) `start` des lots `pending`,
# par emprunt nommé au parent ou par la jambe directe. Chaque étape est une fonction
# de module appelée PAR SON NOM : un banc y injecte une panne. Un échec nomme ce qui
# a été écrit ; la relance est le remède.
#
# BORNES, DITES : le prévol ne voit que les write-sets DÉCLARÉS (cohérence, jamais
# sécurité) ; la revue de
# clôture d'une R reste la sienne (hors du groupe, imprimé) ; un lot `blocked` n'est pas démarré ; le
# write-set d'une dégénérée doit EXISTER, rien ne vérifie qu'il soit JUSTE (aucun code
# ne le compare au plan) : ça empêche d'OUBLIER, pas de TRICHER.

from __future__ import annotations

_PLAN_LOTS_MOD: Any = None


def fournee_plan_lots() -> Any:
    """`plan_lots` (frère, stdlib + `plan_cible`), chargé PARESSEUSEMENT, comme
    `plan_cible_module` ; absent : `None`, et seul ce verbe refuse — un harnais qui
    copie `tasks*.py` sans lui garde tous les autres verbes."""
    global _PLAN_LOTS_MOD
    if _PLAN_LOTS_MOD is None:
        bin_dir = str(Path(__file__).resolve().parent)
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        try:
            import plan_lots as _pl
        except ModuleNotFoundError:
            return None
        _PLAN_LOTS_MOD = _pl
    return _PLAN_LOTS_MOD


def fournee_lots_existants(data: dict[str, Any], parent_id: str) -> dict[str, dict[str, Any]]:
    """Les lots déjà au board, par clé : le lien `fournee.parent` les retrouve."""
    lots: dict[str, dict[str, Any]] = {}
    for t in data["tasks"]:
        lien = t.get("fournee")
        if isinstance(lien, dict) and lien.get("parent") == parent_id and isinstance(lien.get("lot"), str):
            lots.setdefault(lien["lot"], t)
    return lots


def fournee_mesure_du_lot(parent: dict[str, Any], cle: str, sha: str) -> dict[str, str | None]:
    """La mesure qu'un lot HÉRITE du parent (garde de mesure rejouée par `new_task`)."""
    motif = parent.get("motif")
    if motif in ("garde", "securite", "decision-pilote"):
        return {"mesure": parent.get("mesure"), "pas_un_defaut": None, "motif": motif}
    if motif in ("gros", "sans-fournee"):
        return {"mesure": None, "motif": None,
                "pas_un_defaut": f"lot {cle} du plan {sha[:12]} (défaut mesuré sur {parent['id']})"}
    # Un parent SANS `motif` ni `pas_un_defaut` (né avant la garde de mesure) : ses
    # lots naissent déclarés non-défauts À SON NOM, jamais refusés par la garde.
    return {"mesure": None, "motif": None, "pas_un_defaut": parent.get("pas_un_defaut")
            or f"lot {cle} du plan {sha[:12]} de {parent['id']} (antérieur à la garde de mesure)"}


def fournee_titre(parent_id: str, lot: Any) -> str:
    return f"Lot {lot.cle} de {parent_id} : {lot.libelle}"


def fournee_jambes_start(root: str, parent: dict[str, Any], data: dict[str, Any],
                         sans_chaine: str, sans_cible: str, sans_dependances: str) -> list[str]:
    """Les jambes `start` du parent, REJOUÉES À BLANC dans l'ordre de `set_state` :
    cible, amont, arêtes, chaîne. Un parent qui tourne déjà n'en rejoue aucune."""
    if parent.get("state") == "running":
        return []
    tid, refus = parent["id"], []
    _pc = plan_cible_module()
    if not sans_cible and cible_inexploitable(root):
        refus.append(_REFUS_CIBLE_INEXPLOITABLE.format(geste="démarrer"))
    elif not sans_cible and _pc is not None:
        try:
            r = _pc.refus_au_start(root, tid, data)
        except (_pc.CibleError, OSError, ValueError) as exc:  # racine retirée, remède gardé (W26b)
            r = str(exc).replace(os.path.abspath(normalize_root(root)) + os.sep, "")
        if r:
            refus.append(r)
    # L'AMONT D'ABORD (S-01M4Z5VMP5E9YN8T6EMDTBAF0T), au PRÉVOL : un amont ouvert refuse la fournée
    # avant le moindre lot écrit (le `start` du parent, à l'étape 5, le refuserait trop tard).
    if not sans_dependances:
        releve = releve_amont(root, tid, data)
        if releve["jeton"] not in DEPS_READY_PASSANTS:
            refus.append(refus_amont("lancer la fournée de", tid, releve, data))
    _pd = plan_depends_module() if (sans_dependances or cible_marqueur_present(root)) else None
    if _pd is None and sans_dependances:
        refus.append(_REFUS_DEPENDS_VERBE_SANS_MODULE.format(geste="démarrer avec --sans-dependances"))
    elif _pd is None and not sans_cible and cible_marqueur_present(root):
        refus.append(_REFUS_DEPENDS_INEXPLOITABLE.format(geste="démarrer"))
    elif _pd is not None:
        r, _lignes, _marque = _pd.jambe_start(root, tid, data, sans_dependances=sans_dependances)
        if r:
            refus.append(r)
    if (not sans_chaine and (Path(normalize_root(root)) / PLAN_GATE).exists()
            and not parent.get("plan_chain_consumed")):
        r = plan_chain_refusal(root, tid)
        if r:
            refus.append(r)
    return refus


def fournee_cause_trace(root: str, parent_id: str, _pc: Any) -> str:
    """Pourquoi aucune trace `plan approuvé` n'est élue pour le parent — la plus précise."""
    index = _pc.index_par_tache(_pc.entrees_specs(root))
    entrees = _pc.entrees_de(index, parent_id)
    titre = _pc.normalise_titre("plan approuvé")
    traces = [e for e in entrees if e.get("kind") == "decision" and _pc.normalise_titre(e.get("title") or "") == titre]
    if not traces:
        nuit = any(_pc.normalise_titre(e.get("title") or "") == _pc.normalise_titre("night-eligible: approved")
                   for e in entrees)
        return (f"aucune décision `plan approuvé` sur {parent_id}"
                + (" (une `night-eligible: approved` ne lance jamais une fournée)" if nuit else "")
                + f" — trace l'approbation : `specs.py add --task {parent_id} --kind decision \"plan approuvé\" "
                  "--text \"plan=<docs/tasks/….md> sha256=<hex>\"`")
    for e in _pc._plus_recentes_par_plan(traces):
        diag = _pc._diag_trace(root, e, None)
        if diag:
            return f"aucune trace `plan approuvé` valide sur {parent_id} — {diag}"
    return f"aucune trace `plan approuvé` de {parent_id} ne résout un plan sûr sous la racine"


#: Le refus d'une fournée dégénérée dont le parent ne déclare aucun chemin hors de son
#: plan : texte FIGÉ (la doctrine le recopie), remède compris.
FOURNEE_REFUS_DEGENEREE = (
    "{tid} : fournée dégénérée sans write-set réel — aucun chemin déclaré hors de son plan `{plan}` : la "
    "disjonction serait prouvée à vide. Remède : `tasks.py writeset {tid} <chemins…>` AVANT la fournée (groupe "
    "clos d'abord s'il en a un : `block`/`done` de ses co-membres), puis relance ; un plan qui n'a rien à écrire "
    "hors de lui-même n'appelle pas de fournée")
#: Le refus d'un chemin INADMISSIBLE au write-set d'une dégénérée (écrit à la main au board :
#: `writeset` l'aurait refusé) — jamais compté « hors du plan » ; le diagnostic d'admission suit.
FOURNEE_REFUS_INADMISSIBLE = (
    "{tid} : fournée dégénérée dont le write-set porte `{chemin}`, chemin inadmissible — jamais compté hors "
    "de son plan. Remède : `tasks.py writeset {tid} <chemins…>` AVANT la fournée (groupe clos d'abord s'il en "
    "a un : `block`/`done` de ses co-membres), puis relance. Diagnostic : {cause}")
#: Une `running` de R SANS write-set : la disjonction contre elle serait vide — REFUSÉ (décision
#: S-01M5FDAP4N, NO_GO de l'exec-critic : non groupée, elle écrit quand même à côté de la fournée).
FOURNEE_REFUS_R_SANS_WS = (
    "{rid} tourne sans write-set déclaré : la disjonction serait vide — "
    "`tasks.py writeset {rid} <chemins…>`, ou clos-la")
#: Une `running` de R réduite à son plan (board abîmé par l'ancien code) : elle n'est plus groupée
#: avec la fournée (T-01M5F728B4CS1ZDZTH9YWJ0AZ1) ; la disjonction, jugée sur ce seul plan, est DITE.
FOURNEE_INFO_R_REDUIT = (
    "{rid} tourne comme parent d'une fournée dégénérée réduit à son plan `{plan}` : disjonction jugée sur "
    "ce seul plan — `tasks.py writeset {rid} <chemins…>` pour qu'elle le soit sur ses vrais chemins")


def fournee_reduit_au_plan(ws: list[str], plan: str) -> bool:
    """Vrai si `ws` ne porte AUCUN chemin hors de `plan`, en forme canonique (`\\` et
    casse repliés, comme `writeset_paths_overlap`) ; un write-set vide l'est aussi."""
    canon = canonical_writeset_path(plan)
    return all(canonical_writeset_path(c) == canon for c in ws)


def fournee_prevol(root: str, tid: str, data: dict[str, Any], sans_chaine: str = "",
                   sans_cible: str = "", sans_dependances: str = "") -> dict[str, Any]:
    """LE PRÉVOL, PUR : `{"refus": [...], ...}` — tout ce que l'écriture lira."""
    p: dict[str, Any] = {"refus": [], "infos": []}
    refus = p["refus"]
    parent = find(data, tid)
    p["parent"] = parent
    _pc, _pl = plan_cible_module(), fournee_plan_lots()
    if _pc is None or _pl is None:
        refus.append("`.agents/bin/plan_cible.py` ou `.agents/bin/plan_lots.py` est absent : la fournée ne lit "
                     "ni la trace ni les lots — `git checkout -- .agents/bin/plan_cible.py .agents/bin/plan_lots.py`")
        return p
    lien_parent = parent.get("fournee") if isinstance(parent.get("fournee"), dict) else {}
    if lien_parent.get("parent"):
        refus.append(f"{tid} est lui-même un lot de {lien_parent['parent']} : un lot ne lance pas de fournée")
    if "direct" in parent:
        refus.append(f"{tid} porte une estampille `direct` : une fournée est le chemin planifié — "
                     f"`tasks.py direct {tid} --retirer`, puis relance")
    groupe = parallel_group_of(parent)
    if parent["state"] in ("blocked", "done"):
        refus.append(f"{tid} est `{parent['state']}` : seul un parent `pending` ou `running` lance une fournée")
    elif parent["state"] == "running" and groupe and not lien_parent:
        refus.append(f"{tid} tourne dans le groupe {groupe}, qui n'est pas celui de sa fournée — clos ou "
                     "bloque ce groupe d'abord")
    try:
        elue = _pc.trace_plan_approuve(root, tid)
        if elue is None:
            refus.append(fournee_cause_trace(root, tid, _pc))
            return p
    except (_pc.CibleError, OSError, ValueError) as exc:
        # SPECS corrompu (exec-critic, reste 6b) : `CibleError` n'hérite pas de `BoardError` et sortait en
        # traceback rc 1. Refus PROPRE au prévol (rc 2, 0 lot), racine retirée, remède de `plan_cible` gardé.
        refus.append(str(exc).replace(os.path.abspath(normalize_root(root)) + os.sep, ""))
        return p
    chemin, sid = elue
    octets = chemin.read_bytes()
    sha = hashlib.sha256(octets).hexdigest()
    racine = Path(normalize_root(root)).resolve()
    try:
        rel = chemin.resolve().relative_to(racine).as_posix()
    except (OSError, ValueError):
        refus.append(f"plan {chemin} : hors de la racine {racine} une fois les liens résolus — la trace {sid} "
                     "ne désigne pas un plan de CE dépôt")
        return p
    p.update(plan=rel, sha=sha, trace=sid)
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError:
        refus.append(f"plan {rel} : n'est pas en UTF-8")
        return p
    decoupe = _pl.lire(texte, racine=normalize_root(root), chevauche=writeset_paths_overlap,
                       admis=writeset_path_refusal)
    p["decoupe"] = decoupe
    refus += [f"plan {rel} : {r}" for r in decoupe.refus]
    if not _pc.enrolling_line(texte, tid):
        refus.append(f"plan {rel} : il n'ENRÔLE pas {tid} (ligne 1 ou première ligne `Tâches :`)")
    # DÉGÉNÉRÉE : le write-set DÉCLARÉ du parent est son write-set (jamais réécrit,
    # étape 2) et, avec son plan (ajouté plus bas), le juge de la disjonction ; un chemin hors du plan est exigé,
    # comparé en forme canonique (barres et casse repliées, comme le recouvrement).
    # ADMETTRE D'ABORD : un chemin inadmissible (écrit à la main au board, aucun verbe ne
    # l'admet) n'est jamais « hors du plan » — `canonical_writeset_path` n'est défini que sur
    # l'admis. Chacun est refusé, nommé ; le test « réduit à son plan » n'est alors pas joué.
    ws_parent = writeset_of(parent)
    inadmissibles = [c for c in ws_parent if writeset_path_refusal(c) is not None] if decoupe.degeneree else []
    for chemin_ws in inadmissibles:
        refus.append(FOURNEE_REFUS_INADMISSIBLE.format(tid=tid, chemin=chemin_ws,
                                                       cause=writeset_path_refusal(chemin_ws)))
    if decoupe.degeneree and not inadmissibles and fournee_reduit_au_plan(ws_parent, rel):
        refus.append(FOURNEE_REFUS_DEGENEREE.format(tid=tid, plan=rel))
    voulu_parent = ws_parent if decoupe.degeneree else [rel]
    existants = fournee_lots_existants(data, tid)
    p["existants"] = existants
    ouverts_perimes = [t["id"] for t in existants.values() if t["state"] != "done"]
    plan_lots = {lot.cle: lot for lot in decoupe.lots}
    for cle, t in sorted(existants.items()):
        if t["state"] == "done":
            # Ce que le nouveau plan AJOUTE à un lot clos n'a plus de porteur : c'est DIT.
            lot = plan_lots.get(cle)
            orphelins = [c for c in (lot.chemins if lot is not None else [])
                         if c != rel and writeset_paths_overlap([c], writeset_of(t)) is None]
            if orphelins:
                p["infos"].append(f"lot {cle} ({t['id']}) clos sous l'ancien plan : {', '.join(orphelins)} "
                                  "sans porteur")
            continue  # un lot CLOS reste clos sous son ancien plan : sauté, jamais refait
        if str(t["fournee"].get("sha256") or "").lower() != sha:
            refus.append(f"lot {cle} ({t['id']}) porte sha256={t['fournee'].get('sha256')}, la trace élue {sid} "
                         f"sha256={sha} : le plan a changé depuis la découpe — re-découpe : `tasks.py delete "
                         f"--force <lot>` sur chaque lot ouvert ({', '.join(ouverts_perimes) or 'aucun'}), puis "
                         "relance (un lot clos reste clos sous son ancien plan)")
    for cle, t in sorted(existants.items()):
        lot = plan_lots.get(cle)
        if t["state"] == "done" or lot is None or not writeset_of(t):
            continue
        # Comparé à la forme STOCKÉE par `writeset` (`\` replié en `/`, doublons ôtés).
        voulu = list(dict.fromkeys(fold_writeset_path(c) for c in lot.chemins))
        if writeset_of(t) != voulu:
            refus.append(f"lot {cle} ({t['id']}) déclare un write-set différent du plan — rien n'est réécrit")
    if ws_parent and ws_parent != voulu_parent and groupe:
        refus.append(f"{tid} déclare un write-set autre que son plan et appartient au groupe {groupe} : le "
                     "réécrire retirerait la preuve du groupe — rien n'est réécrit")
    for lot in decoupe.lots:
        if lot.cle not in existants:
            m = fournee_mesure_du_lot(parent, lot.cle, sha)
            r = mesure_refusal(root, m["mesure"], m["pas_un_defaut"], motif=m["motif"],
                               titre=fournee_titre(tid, lot))
            if r:
                refus.append(f"lot {lot.cle} : {r}")
    refus += fournee_jambes_start(root, parent, data, sans_chaine, sans_cible, sans_dependances)
    membres = {tid} | {t["id"] for t in existants.values()}
    r_taches = [t for t in data["tasks"] if t["state"] == "running" and t["id"] not in membres]
    p["R"] = r_taches
    # La règle B ne lit plus que le groupe du PARENT : R n'est jamais jointe, ses groupes sont les siens.
    vivants = {groupe} if parent["state"] == "running" and groupe else set()
    for g in sorted(vivants):
        for t in data["tasks"]:
            if (parallel_group_of(t) == g and t["id"] not in membres
                    and t["state"] not in ("running", "done")):
                refus.append(f"le groupe vivant {g} a un membre {t['id']} `{t['state']}` : la fournée ne rejoint "
                             "un groupe que si TOUS ses membres non clos tournent — démarre-le, clos-le, ou attends")
    graphe = _depends_adjacency(data["tasks"])
    # Le write-set du parent : le DÉCLARÉ d'une dégénérée (ce que `parallel` lira à l'étape
    # (4)) + son plan, AJOUTÉ, que seule la fournée compare ; le plan seul sinon.
    porteur = (f"le write-set de {tid}", ws_parent) if decoupe.degeneree else (f"le plan de {tid}", [rel])
    ensembles = ([porteur] + ([(f"le plan de {tid}", [rel])] if decoupe.degeneree else [])
                 + [(f"le lot {lot.cle}", lot.chemins) for lot in decoupe.lots])
    # Le plan EST le write-set du parent (étape 2) : un lot ouvert qui le déclare ferait
    # refuser `parallel` à l'étape (4), APRÈS les écritures des étapes (1) à (3).
    for lot in decoupe.lots:
        clos = (existants.get(lot.cle) or {}).get("state") == "done"
        paire_plan = None if clos else writeset_paths_overlap([rel], lot.chemins)
        if paire_plan is not None:
            refus.append(f"le lot {lot.cle} déclare `{paire_plan[1]}`, qui recouvre le plan `{paire_plan[0]}` — "
                         "le write-set du parent : retire-le du lot")
    partagee = []
    for t in r_taches:
        ws = writeset_of(t)
        # Un parent de fournée SANS lots (un lot porte `parent`, jamais `lots`) dont le
        # write-set est son seul plan : l'ancien code l'écrasait ainsi — DIT, remède nommé.
        # `lots: []` est la forme que l'étape (1) écrit sur tout parent dégénéré depuis la
        # naissance du verbe (mesuré sur chaque version) : aucun parent n'a de lien SANS
        # `lots` — c'est la forme d'un LOT (`plan` sans `lots`), jamais lue comme un parent.
        lien_r = t.get("fournee") if isinstance(t.get("fournee"), dict) else {}
        if (ws and lien_r.get("lots") == [] and isinstance(lien_r.get("plan"), str)
                and fournee_reduit_au_plan(ws, lien_r["plan"])):
            p["infos"].append(FOURNEE_INFO_R_REDUIT.format(rid=t["id"], plan=lien_r["plan"]))
        if not ws:
            refus.append(FOURNEE_REFUS_R_SANS_WS.format(rid=t["id"]))
            continue
        # Une R DÉGÉNÉRÉE : son plan est AJOUTÉ à son write-set comparé, jamais omis.
        if lien_r.get("lots") == [] and isinstance(lien_r.get("plan"), str):
            ws = [*ws, lien_r["plan"]]
        for nom, chemins in ensembles:
            paire = writeset_paths_overlap(ws, chemins)
            if paire is not None:
                refus.append(f"{t['id']} (`{paire[0]}`) recouvre {nom} (`{paire[1]}`) : la fournée ne tourne pas "
                             "à côté d'elle")
        if decoupe.integration and writeset_paths_overlap(ws, decoupe.integration) is not None:
            partagee.append(t["id"])
    # L'UNION DEUX À DEUX — le parent et les lots ouverts : les membres de l'étape (4), jugés
    # ICI par les tests de `parallel` ; sans eux, (4) refuserait APRÈS les étapes (1) à (3),
    # et un refus aurait écrit. R n'en est plus (préservée hors du groupe) : ses liens, et
    # ses recouvrements avec une autre R, ne regardent pas la fournée. Un lot à créer n'a
    # pas d'id, donc aucun lien ; les recouvrements prévus (R/fournée, lot/plan, lot/lot)
    # sont jugés plus haut. Un lot CLOS n'est pas membre : ses liens ne refusent rien. Une
    # RELANCE dont tous les lots existent et dont tous les membres sont DÉJÀ dans le groupe
    # du parent ne rappelle pas `parallel` (étape 4) : rien n'y est rejugé — un `block B
    # --on A` posé après le lancement ne la refuse pas, et l'attente du pilote reste.
    ouverts = [t for _c, t in sorted(existants.items()) if t["state"] != "done"]
    unis = [parent] + ouverts
    deja = (bool(groupe) and all(lot.cle in existants for lot in decoupe.lots)
            and all(parallel_group_of(t) == groupe for t in unis))
    for i, t in enumerate([] if deja else unis):
        for u in unis[i + 1:]:
            lies = (t.get("blocked_on") == u["id"] or u.get("blocked_on") == t["id"]
                    or depends_path_between(graphe, t["id"], u["id"]) or depends_path_between(graphe, u["id"], t["id"]))
            if lies:
                refus.append(f"{t['id']} et {u['id']} sont liés (`depends_on` ou `blocked_on`) : l'une est DERRIÈRE "
                             "l'autre, jamais à côté — `parallel` ne les grouperait pas ; délie-les")
    # L'AMONT DE CHAQUE LOT `pending` EXISTANT, AU PRÉVOL (S-01M5FDAP4N) : R n'est plus dans l'union, donc un
    # `depends <lot> <R>` n'y est plus vu ; sans ce relevé, (4) et (5) écriraient avant que (6) refuse.
    for t in ouverts:
        if t["state"] == "pending" and not sans_dependances:
            releve = releve_amont(root, t["id"], data)
            if releve["jeton"] not in DEPS_READY_PASSANTS:
                refus.append(refus_amont("démarrer le lot", t["id"], releve, data))
    if r_taches:
        ids = ", ".join(t["id"] for t in r_taches)
        p["infos"].append(f"running hors fournée, préservées : {ids} — ni groupées ni rétrogradées ; leur revue de "
                          "clôture reste la leur")
    if partagee:
        p["infos"].append(f"intégration partagée avec {', '.join(partagee)} : l'INTÉGRATION est écrite après la "
                          "fusion, à côté de leur travail")
    return p


def fournee_sans(sans_chaine: str, sans_cible: str, sans_dependances: str) -> dict[str, str]:
    return {"sans_chaine": sans_chaine, "sans_cible": sans_cible, "sans_dependances": sans_dependances}


def fournee_etape_lots(root: str, p: dict[str, Any]) -> list[str]:
    """(1) Chaque lot ABSENT naît avec son lien, en UNE sauvegarde ; puis le parent
    porte la liste de ses lots (complétée, jamais réécrite sur le même plan)."""
    parent, lignes = p["parent"], []
    for lot in p["decoupe"].lots:
        if lot.cle in p["existants"]:
            continue
        m = fournee_mesure_du_lot(parent, lot.cle, p["sha"])
        lien = {"parent": parent["id"], "lot": lot.cle, "plan": p["plan"], "sha256": p["sha"], "trace": p["trace"]}
        sortie = new_task(root, fournee_titre(parent["id"], lot), lot.dev, parent.get("chantier") or "",
                          mesure=m["mesure"], pas_un_defaut=m["pas_un_defaut"], motif=m["motif"],
                          champs={"fournee": lien})
        nouveau = re.match(r"TASKS: (\S+) → pending", sortie)
        lignes.append(f"FOURNEE: lot {lot.cle} → {nouveau.group(1) if nouveau else '?'} (créé)")
    data = load(root)
    existants = fournee_lots_existants(data, parent["id"])
    ids = [existants[lot.cle]["id"] for lot in p["decoupe"].lots if lot.cle in existants]
    voulu = {"lots": ids, "plan": p["plan"], "sha256": p["sha"], "trace": p["trace"]}
    if find(data, parent["id"]).get("fournee") != voulu:
        task = find(data, parent["id"])
        before = copy.deepcopy(task)
        task["fournee"] = voulu
        task["updated"] = date.today().isoformat()
        enqueue_sync_intent(data, parent["id"], before, task)
        save(root, data)
    return lignes


def fournee_etape_writesets(root: str, p: dict[str, Any]) -> list[str]:
    """(2) Lot : absent écrit, égal gardé (le différent est refusé au prévol) ; parent : son
    plan seul — sauf DÉGÉNÉRÉE, dont le write-set déclaré (exigé au prévol) n'est JAMAIS réécrit."""
    data = load(root)
    existants = fournee_lots_existants(data, p["parent"]["id"])
    for lot in p["decoupe"].lots:
        t = existants.get(lot.cle)
        if t is not None and not writeset_of(t):
            set_writeset(root, t["id"], lot.chemins)
    if not p["decoupe"].degeneree and writeset_of(find(data, p["parent"]["id"])) != [p["plan"]]:
        set_writeset(root, p["parent"]["id"], [p["plan"]])
    return []


#: Le stage d'un lot que `direct` a refusé : ses CODES, jamais la prose.
FOURNEE_STAGE_PLANIFIE = "lot planifié — direct refusé : "


def fournee_etape_direct(root: str, p: dict[str, Any],
                         acteur: dict[str, Any] | None = None) -> list[str]:
    """(3) `direct` tenté sur chaque lot `pending` SANS estampille (un lot qui tourne
    garde sa route) ; un refus le laisse planifié, ses CODES de cause au stage (jamais
    la prose : `refus_direct` relit le stage au lexique d'une décision), signé `acteur`."""
    lignes = []
    data = load(root)
    for cle, t in sorted(fournee_lots_existants(data, p["parent"]["id"]).items()):
        if t["state"] != "pending" or "direct" in t:
            continue
        causes = refus_direct(root, t)
        if not causes:
            estampiller(root, t["id"])
            lignes.append(f"FOURNEE: lot {cle} ({t['id']}) — voie directe")
            continue
        codes = sorted({c.split()[0] for c in causes})
        stage = FOURNEE_STAGE_PLANIFIE + ", ".join(codes)
        if not (t.get("stage") or "").startswith(stage):
            stage_task(root, t["id"], stage, acteur=acteur)
        lignes.append(f"FOURNEE: lot {cle} ({t['id']}) — planifié, direct refusé ({', '.join(codes)})")
    return lignes


def fournee_membres(root: str, p: dict[str, Any]) -> list[str]:
    """Le parent et les lots ouverts, dans cet ordre, relus au board — JAMAIS R : une
    `running` étrangère garde son groupe (T-01M5F728B4CS1ZDZTH9YWJ0AZ1)."""
    data = load(root)
    lots = [t["id"] for _c, t in sorted(fournee_lots_existants(data, p["parent"]["id"]).items())
            if t["state"] != "done"]
    return [p["parent"]["id"]] + lots


def fournee_etape_groupe(root: str, p: dict[str, Any]) -> list[str]:
    """(4) `parallel`, rejoué dès qu'un membre n'est pas dans le groupe du parent."""
    membres = fournee_membres(root, p)
    if len(membres) < 2:
        return []
    data = load(root)
    groupe = parallel_group_of(find(data, p["parent"]["id"]))
    if groupe and all(parallel_group_of(find(data, m)) == groupe for m in membres):
        return [f"FOURNEE: groupe {groupe} déjà déclaré — {', '.join(membres)}"]
    return [declare_parallel_group(root, membres)]


def _propriete(tid: str, preuves: dict[str, dict[str, Any]] | None,
               proprietes: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """Les noms que `set_state` attend pour CETTE tâche : la preuve de reprise confirmée au
    terminal et le propriétaire lu après le drain V3 — `set_state` les revalide sous verrou."""
    return {"preuve_reprise": (preuves or {}).get(tid), "propriete_attendue": (proprietes or {}).get(tid)}


def fournee_etape_parent(root: str, p: dict[str, Any], sans: dict[str, str],
                         acteur: dict[str, Any] | None = None,
                         preuves: dict[str, dict[str, Any]] | None = None,
                         proprietes: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """(5) Démarrer le parent, ou transférer sa propriété si sa reprise est prouvée."""
    tid = p["parent"]["id"]
    if find(load(root), tid)["state"] == "running" and not (preuves or {}).get(tid):
        return []
    return [set_state(root, tid, "running", acteur=acteur, **_propriete(tid, preuves, proprietes), **sans)]


def fournee_etape_lots_start(root: str, p: dict[str, Any], sans: dict[str, str],
                             acteur: dict[str, Any] | None = None,
                             preuves: dict[str, dict[str, Any]] | None = None,
                             proprietes: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """(6) `start` de chaque lot `pending` : emprunt nommé au parent, ou jambe directe.
    Les codes du refus `direct` (étape 3) restent au stage, la marque s'y ajoute — une
    seule fois : un stage qui porte déjà un emprunt n'est pas repassé."""
    lignes = []
    data = load(root)
    for cle, t in sorted(fournee_lots_existants(data, p["parent"]["id"]).items()):
        if t["state"] == "pending":
            courant = t.get("stage") or ""
            garde = (courant if courant.startswith(FOURNEE_STAGE_PLANIFIE)
                     and "[chaîne de plan empruntée" not in courant else None)
            lignes.append(set_state(root, t["id"], "running", stage=garde, acteur=acteur,
                                    **_propriete(t["id"], preuves, proprietes), **sans))
        elif t["state"] == "running" and (preuves or {}).get(t["id"]):
            # Un lot déjà lancé doit suivre le transfert confirmé du parent ;
            # `set_state` revalide sa propriété sous le même verrou. Un lot clos
            # ou bloqué ne change jamais de propriétaire dans cette étape.
            lignes.append(set_state(root, t["id"], "running", acteur=acteur,
                                    **_propriete(t["id"], preuves, proprietes), **sans))
        elif t["state"] == "blocked":
            lignes.append(f"FOURNEE: lot {cle} ({t['id']}) est `blocked` — non démarré : `unblock`, puis relance")
    return lignes


def fournee(root: str, tid: str, dry_run: bool = False, sans_chaine: str = "",
            sans_cible: str = "", sans_dependances: str = "",
            preuves_reprise: dict[str, dict[str, Any]] | None = None,
            sans_revendication: str = "",
            acteur: dict[str, Any] | None = None,
            proprietes_attendues: dict[str, dict[str, Any]] | None = None) -> str:
    """Le verbe `fournee` : prévol pur, puis les six étapes sous UN `board_lock`
    réentrant. `dry_run` : le prévol seul, sans verrou, rien d'écrit. `acteur`
    (T-01M5DBFK3XKKM2VHQM5RE4TP6K) est résolu par l'APPELANT, hors verrou ; il signe
    les stages (3) et les `start` (5) (6) — `None` : aucun acteur posé. `preuves_reprise` et
    `proprietes_attendues` (S-01M5HH8QMC) sont PAR TÂCHE, bâtis par la CLI après le drain V3 ;
    chaque `start` les reçoit sous les noms de `set_state`, qui les revalide sous verrou."""
    if sans_revendication:
        raise BoardError("REVENDICATION : --sans-revendication est refusé ; le pilote reprend "
                         "au terminal avec --reprise <raison>")
    if sans_dependances and not sans_dependances.strip():  # refusé AVANT tout lot, jamais à l'étape (5)
        raise BoardError(REFUS_SANS_DEPENDANCES_VIDE.format(geste=f"lancer la fournée de {tid}",
                                                            raison=sans_dependances))
    sans = fournee_sans(sans_chaine, sans_cible, sans_dependances)
    if dry_run:
        p = fournee_prevol(root, tid, load(root), **sans)
        if p["refus"]:  # même code que le vrai lancement : rc 2
            raise BoardError(fournee_rendu(tid, p, dry_run=True))
        return fournee_rendu(tid, p, dry_run=True)
    with board_lock(root):
        p = fournee_prevol(root, tid, load(root), **sans)
        if p["refus"]:
            raise BoardError(fournee_rendu(tid, p, dry_run=False))
        tid = p["parent"]["id"]
        lignes = [fournee_entete(tid, p)]
        etapes = (
            ("(1) lots", lambda: fournee_etape_lots(root, p)),
            ("(2) write-sets", lambda: fournee_etape_writesets(root, p)),
            ("(3) voie directe", lambda: fournee_etape_direct(root, p, acteur)),
            ("(4) groupe", lambda: fournee_etape_groupe(root, p)),
            ("(5) start du parent", lambda: fournee_etape_parent(root, p, sans, acteur, preuves_reprise,
                                                                proprietes_attendues)),
            ("(6) start des lots", lambda: fournee_etape_lots_start(root, p, sans, acteur, preuves_reprise,
                                                                   proprietes_attendues)),
        )
        faites: list[str] = []
        for nom, etape in etapes:
            try:
                lignes += etape()
            except BoardError as exc:
                raise BoardError(
                    f"{exc}\nFOURNEE: échec à l'étape {nom} de {tid} — écrit avant l'échec : "
                    f"{', '.join(faites) or 'rien'} (et ce que l'étape a déjà sauvegardé). Remède : corrige la "
                    f"cause, puis relance `tasks.py fournee {tid}` : elle complète le manquant, sans doublon, sans "
                    "réécriture ni seconde consommation de chaîne.") from exc
            faites.append(nom)
    return "\n".join(lignes + p["infos"] + ["FOURNEE: ok"])


def fournee_entete(tid: str, p: dict[str, Any]) -> str:
    d = p["decoupe"]
    if d.degeneree:
        quoi = ("`LOTS: aucun`" + (f" ({d.aucun})" if d.aucun else "")) if d.forme else "aucune forme de lots écrite"
        n = len(writeset_of(p["parent"]))
        forme = f"dégénérée — le parent seul ({quoi}, ANNONCÉ), write-set déclaré gardé ({n} chemin(s))"
    else:
        forme = f"{len(d.lots)} lot(s) : {', '.join(lot.cle for lot in d.lots)}"
    return f"FOURNEE: {tid} — plan {p['plan']} (sha256 {p['sha'][:12]}…, trace {p['trace']}) — {forme}"


def fournee_rendu(tid: str, p: dict[str, Any], dry_run: bool) -> str:
    """Le refus (TOUTES les causes) ou, à blanc, ce que l'écriture ferait."""
    if p["refus"]:
        lignes = "".join(f"  - {r}\n" for r in p["refus"])
        return (f"TASKS: refus de la fournée de {tid} — {len(p['refus'])} cause(s) :\n{lignes}"
                "Rien n'a été écrit.")
    entete = [fournee_entete(p["parent"]["id"], p)]
    for lot in p["decoupe"].lots:
        t = p["existants"].get(lot.cle)
        etat = f"existant {t['id']} ({t['state']})" if t is not None else "à créer"
        # Un lot clos porte son ANCIEN write-set, jamais celui du nouveau plan.
        n = len(writeset_of(t)) if t is not None and t["state"] == "done" else len(lot.chemins)
        entete.append(f"FOURNEE: lot {lot.cle} — {lot.dev} — {n} fichier(s) — {etat}")
    return "\n".join(entete + p["infos"] + ["FOURNEE: --dry-run, prévol ok — rien n'est écrit"
                                            if dry_run else "FOURNEE: prévol ok"])
