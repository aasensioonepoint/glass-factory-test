# tasks_retour.py — PARTIE de `tasks.py` (T-00001184) : LE CONTRÔLE DE RETOUR
# MÉCANIQUE d'une branche de dev, AVANT sa fusion — le verbe `retour`, ses neuf
# contrôles (a)-(i) et le relevé `retour` qu'il inscrit sur chaque tâche nommée.
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`, jamais
# importée seule : ses noms libres viennent de la façade et des parties amont
# (`tasks_stockage.py`, `tasks_sync.py`, `tasks_requetes.py`, `tasks_gardes.py`).
# Elle OUVRE SUR UN COMMENTAIRE, jamais sur une docstring (test_tasks_decoupe.py,
# témoin (d)) ; ses noms de tête sont préfixés `retour_`/`RETOUR_` (témoin (e)) ;
# elle ne lit à sa définition aucun nom d'une autre partie (témoin (h)) ; ses
# imports sont LOCAUX, comme ceux de `tasks_etats.py`. Stdlib seule.
#
# DÉCISIONS (pilote) : S-00004114 (le mécanique prime sur la prose), S-00004135
# (découpe : ce verbe, puis son appel par la fusion du workflow). Leçons :
# L-00000551 (sur une base fausse, le reste n'a aucun sens), L-00000554 (le
# contrôle est LU avant la fusion, sur un diff non vide).
#
# PORTÉE, DITE (L-00000079) : le verbe MESURE et INSCRIT. LE `done` LE LIT
# (T-00001182, volet 2 de S-00004135) : là où l'estampille `direct` FRANCHIT une
# garde armée, `retour_refus_done` et `retour_refus_securite` refusent la clôture
# sans un relevé ok de SA branche, fusionnée `git merge --no-ff` telle quelle,
# fichiers dans l'estampille, et un verdict de sécurité tracé après lui qui ne dit
# ni un blocage ni une revue absente. La fusion se lit sur la pré-mesure HORS
# verrou du dispatch `done` (`retour_premesure`, S-00004192 voie (a)), jamais sous
# le verrou. Ailleurs (dépôt désarmé, tâche non estampillée, `--sans-cible`) rien
# n'est refusé. Le relevé vaut pour l'état du dépôt À L'INSTANT de la mesure.
# CE QUI VOYAGE NE PORTE AUCUN ID DU KIT : l'aide, les causes et les remèdes
# sont lus chez l'adoptant ; les ids ne vivent que dans ces commentaires.
#
# CONTRAT FIGÉ (lu par la garde de clôture, `retour_refus_done`) : `task["retour"]` =
# {"verdict": "ok"|"refus", "base", "tip" (sha pleins), "branche", "taches",
# "fichiers" (triés), "causes", "notes", "specs_borne" (plus grand S-id de SPECS
# au relevé, "S-00000000" sans SPECS, null illisible), "le" (ISO UTC, seconde)},
# plus "vers" SOUS `--vers` SEULEMENT (voir plus bas).
# Posé sur CHAQUE tâche nommée ; un refus s'inscrit aussi ; le dernier relevé
# remplace le précédent, JAMAIS SANS L'AVOIR COMPARÉ À HEAD (contrôle (i), binôme
# c4f3 bis T1 : sans lui, un relevé refusé puis fusionné, ou une fusion qui glisse
# un passager, s'effaçait au relevé de la branche de correction et le `done`
# passait). Sur une tâche estampillée `direct` — la seule dont la garde de clôture
# lit le relevé —, un relevé antérieur dont la pointe est ENTRÉE dans HEAD doit
# avoir été admissible comme R-b l'exige au `done` : `ok`, entrée par une fusion
# du premier parent dont elle est le second parent (ni avance rapide ni fusion
# imbriquée), chacune ne portant que ses fichiers. Sinon (i) refuse, et ce refus
# est ABSORBANT : il se transmet à chaque relevé suivant du cycle, jusqu'au
# `reopen` (un rejeu ne l'efface pas). L'absorption est BORNÉE À LA TÂCHE (binôme
# c4f3 ter N1) : le relevé est un contrat identique inscrit sur chaque tâche
# nommée, donc seul un refus (i) qui NOMME la tâche se transmet à elle — une
# directe co-nommée dans un relevé refusé pour une AUTRE n'est pas refusée à vie.
# Un relevé antérieur REFUSÉ dont la pointe est hors de HEAD mais dont la branche
# VIT encore à cette pointe, que la pointe neuve ne contient pas, est « en
# suspens » (binôme c4f3 ter N2) : fusionnée APRÈS le relevé neuf, elle
# échapperait à (i). Un (i) non conclu (git sans réponse, HEAD non résolu, en
# suspens) n'écrit RIEN (rc 2) : une panne passagère n'efface pas un refus. Un
# relevé changé entre la lecture et l'écriture n'écrit rien non plus. Le refus (i)
# ne fait gagner aucune clé au contrat : il se lit dans `causes`. UNE SEULE CLÉ
# S'AJOUTE, ET SEULEMENT SOUS `--vers <L>` (T-01M4WTYSCEYHC6KZF2DC1PXBRN, décision
# S-01M4WTZ1QZQJZZNYRC5YA67AZW) : "vers" (le nom de la branche de livraison, sans
# `refs/heads/`), absente de tout relevé pris sans `--vers`. Sous elle, (a) et (e)
# lisent la pointe de L au lieu de HEAD, (h) exclut aussi HEAD, (v) exige L
# existante, distincte de la branche relevée, et portée par chaque tâche nommée
# (`livraison_de`) ; le `done` exige alors EXACTEMENT deux niveaux de fusion (le lot
# dans L, L dans HEAD), et (i) relit un antérieur `vers` à deux niveaux depuis HEAD
# ou à un niveau depuis la pointe de L (`retour_fusions_livraison`). BORNES NOMMÉES de
# « en suspens », non fermées : la branche refusée supprimée, sa pointe fusionnée
# ensuite par un autre nom (sha, autre ref, branche distante) échappe ; la
# fermeture complète serait une clé `en_suspens` relue au `done`, ce qui change
# le contrat figé.
#
# ROLLBACK (C2 du critique) : la clé `retour` n'entre PAS dans
# `SYNC_SNAPSHOT_FIELDS` (`tasks.py`) — l'intent de synchronisation porte
# l'instantané canonique (id, state, task, owner, stage, updated), jamais la clé.
# La projection V3 ne la voit donc pas, et un `git revert -m 1` du code laisse au
# board une clé INERTE, tolérée par `load` et rendue par `cell` (dict).
#
# DETTE NOMMÉE : `RETOUR_GIT_ENV_RETIRES` est RECOPIÉE de `tasks_etats.py`
# (`reprise_changee_depuis`), sans factorisation.

from __future__ import annotations

#: DÉLAI PAR APPEL GIT, en secondes (C4 du critique, S-00004162). Mesuré le
#: 2026-10-05 sur le poste du kit (EDR actif, charge 1 min ≈ 3) : l'appel le plus
#: lent du verbe, `log base..HEAD -- <1 045 chemins>` sur 1 800 commits, prend
#: 0,63 s ; le critique a relevé plus de 5 s pour un diff de ~1 600 fichiers sous
#: l'inspection de l'EDR. 60 s laisse plus de dix fois ce pire cas observé. Le
#: verrou du board n'est PAS tenu pendant la mesure : un délai long ne bloque que
#: l'appelant, jamais un autre verbe du board. BORNE NOMMÉE, non fermée : environ
#: 13 appels + 3 par worktree attaché à la branche, soit au pire ~16 min si CHAQUE
#: appel atteint le délai. Un délai dépassé est « non mesuré », donc un refus.
RETOUR_DELAI_S = 60

#: L'environnement qu'un appel git n'hérite JAMAIS : redirections du dépôt, config
#: désignée par l'environnement, modes de pathspec (liste de `tasks_etats.py`).
RETOUR_GIT_ENV_RETIRES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                          "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                          "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
                          "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_NO_REPLACE_OBJECTS",
                          "GIT_EXEC_PATH", "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS",
                          "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS")

#: La borne d'un SPECS absent : plus petit que tout S-id réel.
RETOUR_SPECS_VIDE = "S-00000000"

#: Combien de noms une cause cite avant de DIRE la coupe (« … et N autres ») :
#: une branche sur une base fausse porte des centaines de fichiers.
RETOUR_CITES = 20

#: Les états d'un contrôle qui font un REFUS ; « ok », « sans objet » et « note » n'en font pas.
#: « en suspens » (i) n'est jamais écrit (`retour_non_conclu`) : il fait le refus du `--dry-run`.
RETOUR_ETATS_REFUS = ("refus", "non mesuré", "non évalué", "en suspens")

RETOUR_PREFIXE_REF = "refs/heads/"

#: Le remède commun à une base qui n'est pas ancêtre (a) et à un HEAD qui a bougé (e).
RETOUR_REMEDE_REBASE = ("remède : rebase de la branche sur HEAD puis rejouer avec --base <nouvelle HEAD> ; "
                        "jamais fusionner le principal dans la branche")

#: (s2) LE LEXIQUE FERMÉ D'UNE REVUE ABSENTE (S-00004192), en formes NORMALISÉES
#: (`direct_normaliser`), bornées aux mots (`direct_porte_lexique`), lu sur le
#: TITRE et le TEXTE du dernier verdict de sécurité. BORNE MESURÉE le 2026-10-05
#: sur le SPECS du kit (248 verdicts titrés sécurité) : 20 frappes, dont 8 ne
#: disent pas une revue absente (décomptes pytest « N skipped », une négation,
#: des descriptions de code) — refus du côté SÛR, sortie `done --sans-cible`.
RETOUR_SECU_ABSENT = ("coverage degraded", "indisponible", "unavailable", "verdict absent",
                      "non joue", "non jouee", "not run", "skipped")

#: Un sha PLEIN (SHA-1 ou SHA-256) : la pré-mesure ne passe à git qu'une valeur de
#: cette forme — un relevé forgé au board ne devient jamais une option de git.
RETOUR_SHA_PLEIN = r"[0-9a-f]{40}|[0-9a-f]{64}"

#: La seule sortie d'une directe déjà fusionnée sans relevé valide.
RETOUR_SORTIE = "la seule sortie tracée est `done --sans-cible \"<pourquoi>\"`"


def retour_git(root: str, *args: str) -> str:
    """LE SEUL coureur git du verbe : argv en liste, aucun shell, `cwd=root`,
    `LC_ALL=C`, `GIT_OPTIONAL_LOCKS=0` (un `status` ne réécrit pas l'index),
    `--literal-pathspecs` et `core.quotePath=false`, `core.fsmonitor=false` et
    `core.hooksPath=/dev/null` (un script posé dans la config du DÉPÔT ne s'exécute
    pas au `status` des contrôles (f)/(g) — même forme que `porte_adoptant.git`), délai `RETOUR_DELAI_S`,
    environnement purgé de `RETOUR_GIT_ENV_RETIRES` et des `GIT_CONFIG_KEY_*`/
    `GIT_CONFIG_VALUE_*`. Rend la sortie standard (décodée `surrogateescape`, donc
    rendue telle quelle à git en argument). Tout rc ≠ 0, tout délai dépassé, toute
    `OSError` lève `RuntimeError` en nommant la cause : jamais un passage."""
    import subprocess

    env = {k: v for k, v in os.environ.items()
           if k not in RETOUR_GIT_ENV_RETIRES and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env["LC_ALL"] = "C"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        r = subprocess.run(["git", "--literal-pathspecs", "-c", "core.quotePath=false", "-c", "core.fsmonitor=false",
                            "-c", "core.hooksPath=/dev/null", *args],
                           cwd=root, env=env, capture_output=True, timeout=RETOUR_DELAI_S, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {args[0]} : délai de {RETOUR_DELAI_S} s dépassé") from None
    except OSError as exc:
        raise RuntimeError(f"git {args[0]} : {type(exc).__name__} : {exc}") from None
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "backslashreplace").strip().splitlines()
        raise RuntimeError(f"git {args[0]} en échec (rc {r.returncode} : {err[0] if err else 'stderr vide'})")
    return r.stdout.decode("utf-8", "surrogateescape")


def retour_lisible(texte: str) -> str:
    """Le texte SÛR à imprimer et à sauver : octets non UTF-8 (`surrogateescape`)
    rendus en `\\xNN`, caractères non imprimables (contrôle, ESC, bidi) échappés.
    Sans lui, un chemin non UTF-8 ferait lever `save` et un ESC atteindrait le
    terminal tel quel."""
    sur = texte.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode("ascii") for c in sur)


def retour_liste(noms: list[str]) -> str:
    """Au plus `RETOUR_CITES` noms, la coupe DITE."""
    tete = ", ".join(noms[:RETOUR_CITES])
    reste = len(noms) - RETOUR_CITES
    return f"{tete} … et {reste} autre(s)" if reste > 0 else tete


def retour_couvre(entree: str, chemin: str) -> bool:
    """L'entrée de write-set `entree` COUVRE-T-ELLE le chemin du diff `chemin` ?

    Re-dérivé de `kickoff_guard.writeset_covers` (sa table de parité est au banc ;
    l'import serait circulaire) sur `canonical_writeset_path` : préfixe À LA
    FRONTIÈRE DE SEGMENT, casse repliée — `src/a` ne couvre pas `src/ab.py`,
    `src/a/` couvre `src/a/b.py`. Une entrée INADMISSIBLE (`writeset_path_refusal`)
    ne couvre rien. PLUS STRICT que l'oracle, et dit : un chemin du diff
    inadmissible, porteur d'un antislash (que le repli lirait comme un `/`) ou
    d'octets non UTF-8 n'est couvert par rien — refus du côté sûr."""
    if (writeset_path_refusal(entree) is not None or writeset_path_refusal(chemin) is not None
            or "\\" in chemin or any("\udc80" <= ch <= "\udcff" for ch in chemin)):
        return False
    e = canonical_writeset_path(entree).split("/")
    c = canonical_writeset_path(chemin).split("/")
    return len(e) <= len(c) and c[: len(e)] == e


def retour_ancetre(racine: str, a: str, b: str) -> bool:
    """`a` est-il ancêtre de `b` (ou égal) ? Par `rev-list --count a --not b` = 0 :
    le « non » est une DONNÉE en rc 0, là où `merge-base --is-ancestor` le dirait
    en rc 1, que le coureur lirait « non mesuré »."""
    return retour_git(racine, "rev-list", "--count", a, "--not", b).strip() == "0"


def retour_ref_existe(racine: str, ref: str) -> str:
    """Le sha de la ref EXACTE `ref`, `""` si elle n'existe pas (rc 0 dans les deux
    cas : `for-each-ref` filtre par préfixe de composant, d'où l'égalité)."""
    for ligne in retour_git(racine, "for-each-ref", "--format=%(objectname) %(refname)", ref).splitlines():
        sha, _, nom = ligne.partition(" ")
        if nom == ref:
            return sha
    return ""


def retour_court(sha: str) -> str:
    return sha[:12] if sha else "?"


def retour_racine(racine: str) -> str | None:
    """`None` si `racine` EST le toplevel d'un dépôt git lisible, sinon la cause.
    Un `.git` englobant ferait mesurer l'AUTRE dépôt : refusé ici."""
    try:
        haut = retour_git(racine, "rev-parse", "--show-toplevel").rstrip("\n")
        if not os.path.samefile(haut, racine):
            return (f"le toplevel git {haut} n'est pas la racine {racine} — "
                    f"remède : lancer le verbe à la racine du dépôt principal")
    except (RuntimeError, OSError) as exc:
        return f"{exc} — remède : lancer le verbe à la racine d'un dépôt git lisible"
    return None


def retour_controle_a(m: dict[str, Any], base: str) -> list[tuple[str, str, str]]:
    """(a) la base et la branche se résolvent chacune en UN commit (sha plein) ; la
    base est ancêtre de la pointe ET de HEAD. Sinon (c)-(f) sont « non évalués »."""
    racine, out = m["racine"], []
    try:
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", base or ""):
            out.append(("a", "refus", f"--base {base!r} n'est pas un sha hexadécimal (7 à 40) — "
                                      f"remède : passer le sha de la base commune (`git rev-parse <base>`)"))
        else:
            # Lu en PRÉFIXE d'objet, jamais en nom : une ref homonyme ne passe pas devant.
            objets = retour_git(racine, "rev-parse", f"--disambiguate={base}").split()
            commits = [o for o in objets if retour_git(racine, "cat-file", "-t", o).strip() == "commit"]
            if len(commits) == 1:
                m["base"] = commits[0]
            else:
                out.append(("a", "refus", f"--base {base} désigne {len(commits)} commit(s) — "
                                          f"remède : passer le sha PLEIN de la base commune"))
        m["tip"] = retour_ref_existe(racine, m["ref"]) if m["nom"] else ""
        if not m["tip"]:
            out.append(("a", "refus", f"la branche {m['nom']!r} n'existe pas ({m['ref']}) — "
                                      f"remède : nommer la branche locale du dev (`git branch --list`)"))
        m["head"] = retour_git(racine, "rev-parse", "--verify", "HEAD^{commit}").strip()
        m["principal"] = m["head"]
        if m["vers"] is not None:
            # SOUS `--vers` : la branche se coupe sur la livraison L et s'y fusionne, (a) et (e)
            # lisent donc la pointe de L ; HEAD reste `principal`, pour (g), (h) et (i).
            m["head"] = retour_ref_existe(racine, RETOUR_PREFIXE_REF + m["vers"])
            if not m["head"]:
                out.append(("a", "non évalué", f"la pointe de la livraison {m['vers']!r} n'est pas résolue — voir (v)"))
        if m["base"] and m["tip"] and m["head"]:
            if not retour_ancetre(racine, m["base"], m["tip"]):
                out.append(("a", "refus", f"la base {retour_court(m['base'])} n'est pas ancêtre de la pointe "
                                          f"{retour_court(m['tip'])} : la branche est née sur une autre base — "
                                          + RETOUR_REMEDE_REBASE))
            if not retour_ancetre(racine, m["base"], m["head"]):
                out.append(("a", "refus", f"la base {retour_court(m['base'])} n'est pas ancêtre de {m['cible']} "
                                          f"{retour_court(m['head'])} — " + RETOUR_REMEDE_REBASE))
    except (RuntimeError, OSError) as exc:
        out.append(("a", "non mesuré", f"{exc} — remède : rejouer quand git répond"))
    if not out:
        m["base_ok"] = True
        out.append(("a", "ok", f"base {retour_court(m['base'])} ancêtre de la pointe {retour_court(m['tip'])} "
                               f"et de {m['cible']} {retour_court(m['head'])}"))
    return out


def retour_controle_b(m: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(b) au moins un commit sur la branche depuis la base."""
    if not (m["base"] and m["tip"]):
        return [("b", "non évalué", "base ou pointe non résolue")]
    try:
        n_commits = int(retour_git(m["racine"], "rev-list", "--count", f"{m['base']}..{m['tip']}").strip())
    except (RuntimeError, OSError, ValueError) as exc:
        return [("b", "non mesuré", f"{exc} — remède : rejouer quand git répond")]
    if n_commits == 0:
        return [("b", "refus", f"aucun commit sur {m['nom']} depuis la base — remède : vérifier que le dev a "
                               f"commité sur CETTE branche, pas sur son doublon `worktree-<dossier>`")]
    return [("b", "ok", f"{n_commits} commit(s) sur la branche depuis la base")]


def retour_controle_cd(m: dict[str, Any], tids: list[str], data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(c) chaque chemin du diff `base..tip` (`--no-renames` : la SOURCE d'un
    renommage compte) est couvert par le write-set DÉCLARÉ d'une des tâches
    nommées ; un write-set absent refuse. (d) le diff n'est pas vide.
    UNE DIRECTE = UNE BRANCHE (T-00001182, S-00004168) : une tâche estampillée
    `direct` nommée avec une autre refuse (c), calculé AVANT le retour « base
    fausse » — le refus tient même sur une base fausse."""
    nommees = {find(data, tid)["id"]: find(data, tid) for tid in tids}
    directes = sorted(t for t, tache in nommees.items() if "direct" in tache) if len(nommees) > 1 else []
    seule = [("c", "refus", f"{', '.join(directes)} estampillée(s) direct et nommée(s) avec une autre tâche : "
                            f"une directe se relève SEULE — remède : une branche et un relevé par directe")
             ] if directes else []
    if not m["base_ok"]:
        return seule + [("c", "non évalué", "base fausse"), ("d", "non évalué", "base fausse")]
    try:
        brut = retour_git(m["racine"], "diff", "--no-renames", "--name-only", "-z", m["base"], m["tip"])
    except (RuntimeError, OSError) as exc:
        cause = f"{exc} — remède : rejouer quand git répond"
        return seule + [("c", "non mesuré", cause), ("d", "non mesuré", cause)]
    m["fichiers"] = sorted({f for f in brut.split("\0") if f})
    out, entrees, sans = list(seule), [], []
    for tid in tids:
        declare = writeset_of(find(data, tid))
        if not declare:
            sans.append(tid)
        entrees += declare
    if sans:
        out.append(("c", "refus", f"{', '.join(sans)} sans write-set déclaré — "
                                  f"remède : `tasks.py writeset <id> <chemins>` puis rejouer"))
    hors = [f for f in m["fichiers"] if not any(retour_couvre(e, f) for e in entrees)]
    if hors:
        out.append(("c", "refus", f"{len(hors)} fichier(s) hors du write-set déclaré de {', '.join(tids)} : "
                                  f"{retour_liste(hors)} — remède : retirer ces fichiers de la branche, ou étendre "
                                  f"le write-set (`tasks.py writeset`) sur une décision tracée"))
    if not out:
        out.append(("c", "ok", f"{len(m['fichiers'])} fichier(s), tous couverts par le write-set déclaré"))
    if not m["fichiers"]:
        out.append(("d", "refus", "diff vide entre la base et la pointe — remède : rien à fusionner ; "
                                  "vérifier la branche et la base"))
    else:
        out.append(("d", "ok", f"diff non vide ({len(m['fichiers'])} fichier(s))"))
    return out


def retour_controle_e(m: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(e) `log base..HEAD -- <diff>` est vide : HEAD n'a touché aucun fichier du
    diff depuis la base. Un relevé pris APRÈS la fusion est donc refusé : le
    contrôle précède mécaniquement la fusion."""
    if not m["base_ok"]:
        return [("e", "non évalué", "base fausse")]
    if not m["fichiers"]:
        return [("e", "sans objet", "diff vide")]
    try:
        touches = retour_git(m["racine"], "log", "--format=%H", f"{m['base']}..{m['head']}", "--",
                             *m["fichiers"]).split()
    except (RuntimeError, OSError) as exc:
        return [("e", "non mesuré", f"{exc} — remède : rejouer quand git répond")]
    if touches:
        return [("e", "refus", f"{len(touches)} commit(s) de {m['cible']} depuis la base touchent le diff "
                               f"({retour_liste([retour_court(s) for s in touches])}) : {m['cible']} a bougé sur ces "
                               f"fichiers, ou la branche est déjà fusionnée (un relevé se prend AVANT la fusion) — "
                               + RETOUR_REMEDE_REBASE)]
    return [("e", "ok", f"{m['cible']} n'a touché aucun fichier du diff depuis la base")]


def retour_meme(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.realpath(a) == os.path.realpath(b)


def retour_arbres(m: dict[str, Any]) -> None:
    """Les worktrees ATTACHÉS à `refs/heads/<branche>`, hors la racine (son cas est
    (g)), dans `m["arbres"]` ; `None` et la cause dans `m["arbres_cause"]` si
    `worktree list` est illisible."""
    try:
        brut = retour_git(m["racine"], "worktree", "list", "--porcelain", "-z")
    except (RuntimeError, OSError) as exc:
        m["arbres"], m["arbres_cause"] = None, str(exc)
        return
    arbres, courant = [], {}
    for champ in brut.split("\0"):
        if not champ:
            if courant:
                arbres.append(courant)
            courant = {}
            continue
        cle, _, valeur = champ.partition(" ")
        courant[cle] = valeur
    if courant:
        arbres.append(courant)
    m["arbres"] = [a for a in arbres if a.get("branch") == m["ref"] and "worktree" in a
                   and not retour_meme(a["worktree"], m["racine"])]


def retour_controle_f(m: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(f) chaque worktree attaché à la branche a `status --porcelain -z` vide
    (non suivis compris) ; un worktree prunable ou illisible refuse."""
    if not m["base_ok"]:
        return [("f", "non évalué", "base fausse")]
    if m["arbres"] is None:
        return [("f", "non mesuré", f"{m['arbres_cause']} — remède : rejouer quand git répond")]
    out = []
    for a in m["arbres"]:
        chemin = a["worktree"]
        if "prunable" in a:
            out.append(("f", "refus", f"worktree {chemin} prunable ({a['prunable'] or 'sans raison'}) — "
                                      f"remède : vérifier ce qu'il portait, puis `git worktree prune`"))
            continue
        try:
            sales = [e for e in retour_git(chemin, "status", "--porcelain", "-z", "--untracked-files=all")
                     .split("\0") if e]
        except (RuntimeError, OSError) as exc:
            out.append(("f", "non mesuré", f"worktree {chemin} illisible : {exc} — "
                                           f"remède : le réparer, puis rejouer"))
            continue
        if sales:
            out.append(("f", "refus", f"worktree {chemin} non propre ({len(sales)} entrée(s) : "
                                      f"{retour_liste(sales)}) — remède : commiter ou retirer ces changements "
                                      f"dans le worktree, puis rejouer"))
    if not out:
        out.append(("f", "ok", f"{len(m['arbres'])} worktree(s) attaché(s) à la branche, propre(s)"))
    return out


def retour_controle_g(m: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(g) au principal : la branche n'est pas la branche COURANTE, l'index est
    vide, et aucun fichier du diff n'y est modifié."""
    out, racine = [], m["racine"]
    try:
        if retour_git(racine, "rev-parse", "--symbolic-full-name", "HEAD").strip() == m["ref"]:
            out.append(("g", "refus", f"{m['nom']} est la branche COURANTE du principal : une branche ne se "
                                      f"fusionne pas dans elle-même — remède : revenir sur la branche principale, "
                                      f"puis rejouer"))
        indexes = [f for f in retour_git(racine, "diff", "--cached", "--name-only", "-z").split("\0") if f]
        if indexes:
            out.append(("g", "refus", f"index du principal non vide ({retour_liste(indexes)}) — remède : commiter "
                                      f"ou désindexer (`git restore --staged`), puis rejouer"))
        if m["base_ok"] and m["fichiers"]:
            modifies = [e for e in retour_git(racine, "status", "--porcelain", "-z", "--untracked-files=all",
                                              "--", *m["fichiers"]).split("\0") if e]
            if modifies:
                out.append(("g", "refus", f"{len(modifies)} fichier(s) du diff modifié(s) au principal "
                                          f"({retour_liste(modifies)}) — remède : commiter ou remiser ces "
                                          f"changements au principal avant la fusion, puis rejouer"))
    except (RuntimeError, OSError) as exc:
        out.append(("g", "non mesuré", f"{exc} — remède : rejouer quand git répond"))
    if not out:
        out.append(("g", "ok", "principal : branche non courante, index vide, aucun fichier du diff modifié"))
    return out


def retour_controle_h(m: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(h) le doublon `worktree-<nom du dossier>` d'un worktree attaché : s'il porte
    des commits PROPRES (ni dans la pointe, ni dans HEAD, ni dans un remote),
    `branch -D` les perdrait — refus ; sinon une note « doublon vierge ». Sous
    `--vers`, ni dans la pointe de L NI dans HEAD : le doublon d'un dev isolé naît
    sur HEAD, que L ne contient pas forcément."""
    if not (m["tip"] and m["head"]):
        return [("h", "non évalué", "pointe ou HEAD non résolu")]
    if m["arbres"] is None:
        return [("h", "non mesuré", f"{m['arbres_cause']} — remède : rejouer quand git répond")]
    out = []
    try:
        for a in m["arbres"]:
            doublon = f"worktree-{os.path.basename(a['worktree'].rstrip('/'))}"
            if not retour_ref_existe(m["racine"], RETOUR_PREFIXE_REF + doublon):
                continue
            n_propres = int(retour_git(m["racine"], "rev-list", "--count", RETOUR_PREFIXE_REF + doublon,
                                       "--not", m["tip"], m["head"], m["principal"], "--remotes").strip())
            if n_propres > 0:
                out.append(("h", "refus", f"le doublon {doublon} porte {n_propres} commit(s) absent(s) de la "
                                          f"branche, de HEAD et des remotes : `git branch -D` les perdrait — "
                                          f"remède : les récupérer (cherry-pick sur la branche) avant toute "
                                          f"suppression"))
            else:
                out.append(("h", "note", f"doublon vierge, supprimable : {doublon}"))
    except (RuntimeError, OSError, ValueError) as exc:
        out.append(("h", "non mesuré", f"{exc} — remède : rejouer quand git répond"))
    if not out:
        out.append(("h", "ok", "aucun doublon worktree-<dossier>"))
    return out


def retour_anterieurs(tids: list[str], data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(i) Les relevés ANTÉRIEURS à comparer : ceux des tâches nommées estampillées
    `direct` (la garde de clôture ne lit que les leurs ; une tâche planifiée n'en
    a pas l'usage), lus au board AVANT la mesure. `(id, relevé)`, UN PAR TÂCHE :
    un relevé posé sur plusieurs tâches est comparé pour CHACUNE, parce que
    l'absorption de `retour_anterieur` est bornée à la tâche (compté une fois, le
    refus d'une tâche nommée en second se perdait)."""
    out: list[tuple[str, dict[str, Any]]] = []
    for tid in tids:
        tache = find(data, tid)
        prec = tache.get("retour")
        if "direct" not in tache or not isinstance(prec, dict):
            continue
        out.append((tache["id"], prec))
    return out


def retour_fusions_livraison(racine: str, depart: str, head: str,
                             pointe: str) -> list[tuple[list[str], list[str]]]:
    """EXACTEMENT DEUX NIVEAUX (T-01M4WTYSCEYHC6KZF2DC1PXBRN) : pour chaque fusion M
    du premier parent de `depart..head` (second parent X, la livraison fusionnée), les
    fusions N du premier parent de `M^1..X` dont `pointe` est le second parent — le lot
    fusionné dans la livraison, la livraison fusionnée dans la cible. `M^1..X`, JAMAIS
    `depart..X` : ce que la cible portait avant la fusion de la livraison n'est pas
    compté (un lot fusionné directement dans la cible, puis contenu par la livraison,
    passerait sinon pour livré par elle). Rend `(M, N)`, chacun `[sha, parent1,
    parent2, …]`. Un appel git par fusion du premier parent : borné par
    `RETOUR_DELAI_S` chacun. Lève `RuntimeError` si git ne répond pas."""
    paires: list[tuple[list[str], list[str]]] = []
    for externe in (ligne.split() for ligne in retour_git(
            racine, "rev-list", "--parents", "--merges", "--first-parent", f"{depart}..{head}").splitlines()):
        if len(externe) < 3:
            continue
        for interne in (ligne.split() for ligne in retour_git(
                racine, "rev-list", "--parents", "--merges", "--first-parent", f"{externe[1]}..{externe[2]}").splitlines()):
            if len(interne) > 2 and interne[2] == pointe:
                paires.append((externe, interne))
    return paires


def retour_anterieur(racine: str, head: str, tip: str, tid: str, prec: dict[str, Any]) -> tuple[str, str, str]:
    """(i) pour UN relevé antérieur : un constat. Dans l'ordre : un refus (i) déjà
    porté POUR `tid` se transmet (ABSORBANT, borné à la tâche : la cause doit
    contenir « de <tid> » — chaque texte de refus (i) ci-dessous nomme sa tâche
    ainsi, AVANT tout nom venu du dépôt ; un passager dont le nom l'imiterait ne
    ferait que sur-refuser) ; sans pointe, rien n'a pu entrer ; pointe non
    pleine → refus ; pointe absente du dépôt (`--ignore-missing` : l'absence est
    une DONNÉE en rc 0) → ok ; hors de HEAD → ok, SAUF un relevé refusé dont la
    branche vit encore à cette pointe et que la pointe neuve `tip` ne contient
    pas → « en suspens » (non conclu : rien n'est écrit ; remède, supprimer la
    branche ou la corriger puis la relever ; un nom de branche échappé au relevé
    n'est pas retrouvé) ; pointe ancêtre de sa base (aucun commit propre) → ok ;
    relevé non `ok` → refus ; sinon, comme R-b au `done`,
    la pointe est le second parent d'au moins une fusion du chemin
    `--first-parent` de `base..HEAD` (une avance rapide ou une fusion imbriquée
    refuse : par elle, un passager se blanchirait d'un niveau), et chacune de ces
    fusions ne porte que des fichiers du relevé. Un antérieur relevé `--vers V` : dans
    HEAD, sa pointe doit y être entrée à EXACTEMENT deux niveaux
    (`retour_fusions_livraison`, chaque fusion du lot dans V ne portant que ses
    fichiers) ; hors de HEAD mais ancêtre de la pointe de V, la marche se fait à UN
    niveau depuis cette pointe. Lève `RuntimeError` si git ne répond pas : jamais un
    passage."""
    pointe, depart = prec.get("tip"), prec.get("base")
    sortie = f"un relevé neuf ne l'efface pas — {RETOUR_SORTIE}, puis `reopen` pour un cycle neuf"
    causes = prec.get("causes")
    if any(isinstance(c, str) and c.startswith("(i) refus") and f" de {tid} " in c
           for c in (causes if isinstance(causes, list) else [])):
        return ("i", "refus", f"le relevé antérieur de {tid} porte déjà un refus (i), qui se transmet ; {sortie}")
    if pointe in (None, ""):
        return ("i", "ok", f"relevé antérieur de {tid} sans pointe : aucune branche n'a pu entrer dans HEAD")
    if not (isinstance(pointe, str) and re.fullmatch(RETOUR_SHA_PLEIN, pointe)):
        return ("i", "refus", f"relevé antérieur de {tid} illisible (pointe « {retour_lisible(str(pointe))} ») ; "
                              f"{sortie}")
    court = retour_court(pointe)
    if not retour_git(racine, "rev-list", "--no-walk", "--ignore-missing", pointe).strip():
        return ("i", "ok", f"pointe antérieure {court} de {tid} absente du dépôt, donc hors de HEAD")
    # UN ANTÉRIEUR `vers` (T-01M4WTYSCE) : sa pointe dans HEAD y est entrée par la livraison,
    # EXACTEMENT deux niveaux ; hors de HEAD mais dans la pointe de sa livraison, UN niveau
    # depuis cette pointe ; ailleurs, la marche inchangée. Sans `vers` : inchangé.
    vers = prec.get("vers") if isinstance(prec.get("vers"), str) and prec.get("vers") else None
    deux_niveaux = False
    if vers is not None and retour_ancetre(racine, pointe, head):
        deux_niveaux = True
    elif vers is not None:
        pointe_v = retour_ref_existe(racine, RETOUR_PREFIXE_REF + vers)
        if pointe_v and retour_ancetre(racine, pointe, pointe_v):
            head = pointe_v
    if not retour_ancetre(racine, pointe, head):
        branche = prec.get("branche")
        if (prec.get("verdict") != "ok" and isinstance(branche, str) and branche
                and retour_ref_existe(racine, RETOUR_PREFIXE_REF + branche) == pointe
                and not (tip and retour_ancetre(racine, pointe, tip))):
            return ("i", "en suspens", f"le relevé antérieur de {tid} est refusé et sa branche {branche} vit encore "
                                       f"à sa pointe {court}, hors de HEAD : fusionnée après ce relevé, elle "
                                       f"échapperait à (i) — remède : supprimer la branche refusée, ou la corriger "
                                       f"puis la relever")
        return ("i", "ok", f"pointe antérieure {court} de {tid} hors de HEAD : rien n'a été fusionné")
    lisible = isinstance(depart, str) and re.fullmatch(RETOUR_SHA_PLEIN, depart) is not None
    if lisible and retour_git(racine, "rev-list", "--count", "--ignore-missing", pointe,
                              "--not", depart).strip() == "0":
        return ("i", "ok", f"pointe antérieure {court} de {tid} sans commit propre depuis sa base")
    if prec.get("verdict") != "ok":
        return ("i", "refus", f"le relevé antérieur de {tid} était refusé et sa pointe {court} est dans HEAD : la "
                              f"branche a été fusionnée malgré le refus ; {sortie}")
    if not lisible:
        return ("i", "refus", f"relevé antérieur ok de {tid} sans base lisible : sa fusion ne se mesure pas ; {sortie}")
    fusions = [] if deux_niveaux else [p for p in (ligne.split() for ligne in retour_git(
        racine, "rev-list", "--parents", "--first-parent", "--merges", f"{depart}..{head}").splitlines())
        if len(p) > 2 and p[2] == pointe]
    if deux_niveaux:
        fusions = [interne for _externe, interne in retour_fusions_livraison(racine, depart, head, pointe)]
    if not fusions and deux_niveaux:
        return ("i", "refus", f"la pointe antérieure {court} de {tid}, relevée vers la livraison "
                              f"{retour_lisible(str(vers))}, est dans HEAD sans y être entrée à EXACTEMENT deux niveaux "
                              f"(le lot dans la livraison, la livraison dans HEAD) ; {sortie}")
    if not fusions:
        return ("i", "refus", f"la pointe antérieure {court} de {tid} est dans HEAD sans être le second parent "
                              f"d'une fusion du premier parent (avance rapide ou fusion imbriquée) ; {sortie}")
    fichiers = prec.get("fichiers")
    couverts = {f for f in (fichiers if isinstance(fichiers, list) else []) if isinstance(f, str)}
    for fusion in fusions:
        brut = retour_git(racine, "diff", "--name-only", "--no-renames", "-z", fusion[1], fusion[0])
        passagers = sorted({retour_lisible(f) for f in brut.split("\0") if f} - couverts)
        if passagers:
            return ("i", "refus", f"la fusion {retour_court(fusion[0])} de la pointe antérieure {court} de {tid} "
                                  f"porte {len(passagers)} fichier(s) hors de son relevé : "
                                  f"{retour_liste(passagers)} ; {sortie}")
    return ("i", "ok", f"relevé antérieur ok de {tid}, pointe {court} dans HEAD, {len(fusions)} fusion(s) "
                       f"telle(s) quelle(s)")


def retour_controle_i(m: dict[str, Any], tids: list[str], data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(i) UN RELEVÉ NEUF N'EFFACE PAS L'ANTÉRIEUR : `retour_anterieur` sur chaque
    relevé de `retour_anterieurs`. Aucun → « sans objet » (zéro appel git) ;
    HEAD non résolu → « non évalué » ; git sans réponse → « non mesuré » ; une
    branche refusée encore vivante → « en suspens ». Un (i) non conclu fait
    refuser l'ÉCRITURE (`retour_non_conclu`), pas seulement le relevé : écrit, il
    effacerait l'antérieur qu'il n'a pas lu, ou n'a pas pu clore."""
    anterieurs = retour_anterieurs(tids, data)
    if not anterieurs:
        return [("i", "sans objet", "aucun relevé antérieur sur une tâche estampillée direct")]
    # HEAD DU PRINCIPAL, jamais la pointe de L : sous `--vers`, `m["head"]` est la pointe de la
    # livraison ; un antérieur sans `vers` est entré dans HEAD, et c'est là que (i) le relit.
    if not m["principal"]:
        return [("i", "non évalué", "HEAD non résolu")]
    out = []
    for tid, prec in anterieurs:
        try:
            out.append(retour_anterieur(m["racine"], m["principal"], m["tip"], tid, prec))
        except (RuntimeError, OSError) as exc:
            out.append(("i", "non mesuré", f"relevé antérieur de {tid} : {exc} — remède : rejouer quand git répond"))
    return out


def retour_controle_v(m: dict[str, Any], tids: list[str], data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(v) SOUS `--vers` SEULEMENT (aucune ligne sans lui) : la livraison L a un nom
    admissible, EXISTE comme branche locale, n'est PAS la branche relevée (un lot se
    relève sur sa propre branche, fusionnée ensuite dans L), et CHAQUE tâche nommée
    porte la livraison L (`livraison_de`, déclarée par `tasks.py livraison`)."""
    if m["vers"] is None:
        return []
    out = [("v", "refus", f"{c.replace('--branche', '--vers', 1)} — remède : nommer la branche de livraison")
           for c in livraison_branche_refus(m["vers"])]
    try:
        if m["vers"] and not retour_ref_existe(m["racine"], RETOUR_PREFIXE_REF + m["vers"]):
            out.append(("v", "refus", f"la livraison {m['vers']} n'existe pas comme branche locale — remède : la "
                                      f"créer dans un worktree (`git worktree add -b <L> <dossier> <base>`), puis rejouer"))
    except (RuntimeError, OSError) as exc:
        out.append(("v", "non mesuré", f"{exc} — remède : rejouer quand git répond"))
    if m["vers"] == m["nom"]:
        out.append(("v", "refus", f"la branche relevée EST la livraison {m['vers']} : un lot se relève sur sa "
                                  f"propre branche, coupée sur la livraison et fusionnée ensuite dans elle"))
    sans = [find(data, tid)["id"] for tid in tids if (livraison_de(find(data, tid)) or {}).get("branche") != m["vers"]]
    if sans:
        out.append(("v", "refus", f"{', '.join(sans)} ne porte(nt) pas la livraison {m['vers']} — remède : "
                                  f"`tasks.py livraison <tâches> --branche {m['vers']}`, puis rejouer"))
    if not out:
        out.append(("v", "ok", f"livraison {m['vers']} : branche existante, distincte, portée par chaque tâche nommée"))
    return out


def retour_non_conclu(controles: list[tuple[str, str, str]]) -> None:
    """Un (i) NON CONCLU (« non mesuré », « non évalué », « en suspens ») →
    `BoardError`, rien n'est écrit : le relevé antérieur reste en place jusqu'à
    ce qu'il ait été comparé à HEAD, et qu'aucune branche refusée ne puisse plus
    y entrer derrière lui. Écrit, le relevé neuf l'effacerait, et une panne
    passagère ou une fusion tardive suffirait à rouvrir le trou que (i) ferme."""
    flous = [f"({x}) {etat} — {texte}" for x, etat, texte in controles
             if x == "i" and etat in ("non mesuré", "non évalué", "en suspens")]
    if flous:
        raise BoardError(f"{' ; '.join(flous)} — rien n'est écrit : le relevé antérieur reste en place ; rejouer "
                         f"`retour` une fois la cause levée (`--dry-run` montre tous les contrôles)")


def retour_mesurer(root: str, tids: list[str], base: str, branche: str,
                   data: dict[str, Any], vers: str | None = None) -> dict[str, Any]:
    """Les neuf contrôles (a)-(i), plus (v) sous `vers`, TOUTES les causes
    accumulées (aucun retour à la première). (i) tourne aussi hors git : sans relevé
    antérieur il est « sans objet », sinon « non évalué » (HEAD non résolu). Rend le
    relevé sans `specs_borne` ni `le` (avec `vers` sous `vers`), plus `controles` :
    une entrée (lettre, état, texte) par constat, pour l'affichage."""
    racine = os.path.abspath(normalize_root(root))
    nom = branche[len(RETOUR_PREFIXE_REF):] if branche.startswith(RETOUR_PREFIXE_REF) else branche
    if vers is not None and vers.startswith(RETOUR_PREFIXE_REF):
        vers = vers[len(RETOUR_PREFIXE_REF):]
    m: dict[str, Any] = {"racine": racine, "nom": nom, "ref": RETOUR_PREFIXE_REF + nom, "base": "", "tip": "",
                         "head": "", "base_ok": False, "fichiers": [], "arbres": None, "arbres_cause": "",
                         "vers": vers, "principal": "",
                         "cible": "HEAD" if vers is None else f"la pointe de {retour_lisible(vers)}"}
    hors_git = retour_racine(racine)
    if hors_git is not None:
        controles = [("a", "non mesuré", hors_git)] + [(x, "non évalué", "racine non mesurée") for x in "bcdefgh"]
        controles += retour_controle_i(m, tids, data)
    else:
        controles = retour_controle_a(m, base)
        controles += retour_controle_b(m)
        controles += retour_controle_cd(m, tids, data)
        controles += retour_controle_e(m)
        retour_arbres(m)
        controles += retour_controle_f(m)
        controles += retour_controle_g(m)
        controles += retour_controle_h(m)
        controles += retour_controle_i(m, tids, data)
    controles += retour_controle_v(m, tids, data)
    controles = [(x, etat, retour_lisible(texte)) for x, etat, texte in controles]
    causes = [f"({x}) {etat} — {texte}" for x, etat, texte in controles if etat in RETOUR_ETATS_REFUS]
    releve = {
        "verdict": "refus" if causes else "ok",
        "base": m["base"],
        "tip": m["tip"],
        "branche": retour_lisible(nom),
        "taches": list(tids),
        "fichiers": [retour_lisible(f) for f in m["fichiers"]],
        "causes": causes,
        "notes": [f"({x}) {texte}" for x, etat, texte in controles if etat == "note"],
        "controles": controles,
    }
    if vers is not None:
        releve["vers"] = retour_lisible(vers)
    return releve


def retour_specs_borne(root: str) -> str | None:
    """Le plus grand S-id de SPECS au relevé (`sort_key`), `RETOUR_SPECS_VIDE` si
    SPECS est absent ou sans entrée, `None` s'il est illisible (ou son lecteur
    unique, `plan_cible`, absent de l'arbre)."""
    pc = plan_cible_module()
    if pc is None:
        return None
    try:
        entrees = pc.entrees_specs(root)
    except (pc.CibleError, OSError, ValueError):
        return None
    ids = []
    for e in entrees:
        sid = e.get("id") if isinstance(e, dict) else None
        if isinstance(sid, str) and sid.startswith("S-"):
            try:
                sort_key(sid)
            except BoardError:
                continue
            ids.append(sid)
    return max(ids, key=sort_key) if ids else RETOUR_SPECS_VIDE


def retour_ouverte(task: dict[str, Any]) -> None:
    if task.get("state") == "done":
        raise BoardError(f"{task['id']} est close (done) : un relevé de retour ne s'inscrit que sur une tâche "
                         f"ouverte — rien n'est écrit")


def retour_inscrire(root: str, tids: list[str], base: str, branche: str,
                    dry_run: bool = False, vers: str | None = None) -> dict[str, Any]:
    """Mesure HORS verrou (une vingtaine d'appels git bornés), puis inscrit le
    relevé sur CHAQUE tâche nommée sous `board_lock` → `save`. Une tâche close ou
    un id inconnu → `BoardError` (rc 2, rien n'est écrit) ; un write-set changé
    entre la mesure et l'écriture aussi : (c) a été calculé sur l'ancien ; un
    relevé changé aussi : (i) a comparé l'ancien ; un (i) non conclu aussi
    (`retour_non_conclu`). `dry_run` mesure et n'écrit rien. `vers` : la livraison
    (contrôle (v), clé `vers`). Rend le contrat, plus `controles` et `inscrit` (les
    ids écrits)."""
    tids = list(dict.fromkeys(tids))
    lu = load(root)
    for tid in tids:
        retour_ouverte(find(lu, tid))
    releve = retour_mesurer(root, tids, base, branche, lu, vers=vers)
    borne = retour_specs_borne(root)
    contrat = {cle: releve[cle] for cle in ("verdict", "base", "tip", "branche", "taches", "fichiers",
                                            "causes", "notes")}
    if "vers" in releve:
        contrat["vers"] = releve["vers"]
    contrat["specs_borne"] = borne
    contrat["le"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inscrit: list[str] = []
    if dry_run:
        return {**contrat, "controles": releve["controles"], "inscrit": inscrit}
    retour_non_conclu(releve["controles"])
    with board_lock(root):
        data = load(root)
        for tid in tids:
            task = find(data, tid)
            retour_ouverte(task)
            if writeset_of(task) != writeset_of(find(lu, tid)):
                raise BoardError(f"le write-set de {tid} a changé pendant la mesure — rien n'est écrit ; "
                                 f"rejouer `retour`")
            if task.get("retour") != find(lu, tid).get("retour"):
                raise BoardError(f"le relevé de {tid} a changé pendant la mesure : (i) a comparé l'ancien — rien "
                                 f"n'est écrit ; rejouer `retour`")
        for tid_inscrit in tids:
            task = find(data, tid_inscrit)
            before = copy.deepcopy(task)
            task["retour"] = copy.deepcopy(contrat)
            task["updated"] = date.today().isoformat()
            enqueue_sync_intent(data, tid_inscrit, before, task)
            inscrit.append(tid_inscrit)
        save(root, data)
    return {**contrat, "controles": releve["controles"], "inscrit": inscrit}


def retour_rendu(releve: dict[str, Any]) -> str:
    """Une ligne par constat, l'identité du relevé, où il est inscrit, puis
    `RETOUR: ok|refus` en DERNIÈRE ligne."""
    lignes = [f"RETOUR ({x}) {etat} — {texte}" for x, etat, texte in releve["controles"]]
    lignes.append(f"RETOUR: base {releve['base'] or '?'} pointe {releve['tip'] or '?'} branche "
                  f"{releve['branche']} — {len(releve['fichiers'])} fichier(s), SPECS borné à "
                  f"{releve['specs_borne'] or 'illisible'}")
    if "vers" in releve:
        lignes.append(f"RETOUR: vers la livraison {releve['vers']} — fusion dans {releve['vers']}, pas dans HEAD")
    if releve["inscrit"]:
        lignes.append(f"RETOUR: relevé inscrit sur {', '.join(releve['inscrit'])}")
    else:
        lignes.append("RETOUR: --dry-run — rien n'est écrit")
    lignes.append(f"RETOUR: {releve['verdict']}")
    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# LA GARDE DE CLÔTURE (T-00001182, volet 2 de S-00004135) : le `done` d'une
# directe qui FRANCHIT une garde armée lit le relevé. `retour_premesure` tourne
# HORS verrou, appelée par le dispatch `done` de `tasks.py` (S-00004192 voie (a)) ;
# `retour_refus_done` et `retour_refus_securite` tournent SOUS le verrou de
# `set_state`, sans aucun appel git ni relecture du board. Ça empêche d'OUBLIER,
# pas de TRICHER : le relevé et le verdict sont déclaratifs.
# ---------------------------------------------------------------------------


def retour_premesure(root: str, tid: str) -> dict[str, Any] | None:
    """LA PRÉ-MESURE DU `done`, HORS VERROU. Lecture NUE du board (`load`, sans
    verrou, comme `list`), tâche cherchée sans lever ; `None` si la tâche est
    inconnue, sans estampille `direct` ou sans relevé `retour` objet — zéro appel
    git : tout `done` ordinaire est inchangé. Sinon `retour_racine`, puis des
    `retour_git` bornés (`RETOUR_DELAI_S` chacun) : HEAD, les fusions du chemin
    `--first-parent` de `base..HEAD` avec leurs parents, puis LE CONTENU de chaque
    fusion dont le second parent est la pointe relevée (`diff --name-only
    --no-renames -z <fusion>^1 <fusion>`, binôme c4f3 F1 : une fusion `--no-commit`
    qui ajoute un fichier n'est pas « telle quelle ») → `{"cle": (base, tip, le),
    "lignes": [...], "contenus": {fusion: [chemins lisibles]}}`. Racine qui n'est pas
    le toplevel git, sha non plein, toute panne → `{"cle": None}` (« non mesuré » au
    `done`) : JAMAIS une levée."""
    try:
        task = next((t for t in load(root)["tasks"] if isinstance(t, dict) and t.get("id") == tid), None)
        if task is None or "direct" not in task or not isinstance(task.get("retour"), dict):
            return None
        releve = task["retour"]
        base, tip = releve.get("base"), releve.get("tip")
        if not all(isinstance(v, str) and re.fullmatch(RETOUR_SHA_PLEIN, v) for v in (base, tip)):
            return {"cle": None}
        racine = os.path.abspath(normalize_root(root))
        if retour_racine(racine) is not None:
            return {"cle": None}
        head = retour_git(racine, "rev-parse", "--verify", "HEAD^{commit}").strip()
        lignes = retour_git(racine, "rev-list", "--first-parent", "--merges", "--parents",
                            f"{base}..{head}").splitlines()
        contenus: dict[str, list[str]] = {}
        for p in (ligne.split() for ligne in lignes):
            if len(p) > 2 and p[2] == tip:  # p[1] est le premier parent : `<fusion>^1`
                brut = retour_git(racine, "diff", "--name-only", "--no-renames", "-z", p[1], p[0])
                contenus[p[0]] = sorted({retour_lisible(f) for f in brut.split("\0") if f})
        livraison = retour_premesure_livraison(racine, releve, base, head, tip)
    except Exception:  # noqa: BLE001 — la pré-mesure ne lève JAMAIS : le `done` dit « non mesuré »
        return {"cle": None}
    pre = {"cle": (base, tip, releve.get("le")), "lignes": lignes, "contenus": contenus}
    if livraison is not None:
        pre["livraison"] = livraison
    return pre


def retour_premesure_livraison(racine: str, releve: dict[str, Any], base: str, head: str,
                               tip: str) -> dict[str, Any] | None:
    """La pré-mesure d'un relevé `--vers` (T-01M4WTYSCE), None sans `vers` : les paires
    (M, N) de `retour_fusions_livraison`, le contenu de chaque fusion du lot dans la
    livraison (`N^1..N`, `lots`) et de chaque fusion de la livraison dans la cible
    (`M^1..M`, `cibles`). RÉSERVE DU CRITIQUE DE PLAN (3/8), DITE : ces contenus sont
    lus ICI, HORS VERROU, comme toute la pré-mesure ; le `done` les compare SOUS le
    verrou aux fichiers du relevé et aux write-sets déclarés des membres, relus là. Un
    commit est immuable, seule l'identité de HEAD peut bouger entre les deux : un
    relevé changé est vu par la clé, une fusion arrivée après la mesure ne l'est pas."""
    if not isinstance(releve.get("vers"), str):
        return None
    out: dict[str, Any] = {"paires": [], "lots": {}, "cibles": {}}
    for externe, interne in retour_fusions_livraison(racine, base, head, tip):
        out["paires"].append([externe[0], interne[0]])
        for cle, p in (("lots", interne), ("cibles", externe)):
            if p[0] not in out[cle]:
                brut = retour_git(racine, "diff", "--name-only", "--no-renames", "-z", p[1], p[0])
                out[cle][p[0]] = sorted({retour_lisible(f) for f in brut.split("\0") if f})
    return out


def retour_refus_done(root: str, tid: str, task: dict[str, Any], data: dict[str, Any],
                      pre: dict[str, Any] | None) -> list[str]:
    """LE RELEVÉ AU `done` : TOUTES les causes, chacune nomme son geste, dans CET
    ordre — (R-a) un relevé `ok` ; (R-t) il ne nomme QUE cette tâche, chaque id
    résolu sans lever ; (R-c) des fichiers, pas plus que la voie directe n'en
    admet, chacun couvert par l'instantané de l'estampille ; (R-d) une borne SPECS
    lisible ; (R-b), SEULEMENT si R-a admet, la pré-mesure `pre` du dispatch : la
    clé du relevé inchangée et une fusion du chemin `--first-parent` de HEAD dont
    le SECOND parent est la pointe relevée, son CONTENU (lu par la pré-mesure)
    dans les fichiers du relevé. Un relevé `vers` (T-01M4WTYSCE) : (R-v) la tâche
    porte encore cette livraison, et (R-b) se lit à EXACTEMENT deux niveaux
    (`retour_refus_livraison`) ; le chemin à un niveau garde ses littéraux. Liste vide
    = admis. Aucun git ici."""
    releve = task.get("retour")
    if not isinstance(releve, dict):
        return [f"(R-a) aucun relevé de retour : lance `tasks.py retour {tid} --base <sha> --branche <branche>` "
                f"AVANT la fusion ; déjà fusionnée sans relevé : {RETOUR_SORTIE}"]
    causes: list[str] = []
    admis = releve.get("verdict") == "ok"
    if not admis:
        causes.append(f"(R-a) le dernier relevé de retour n'est pas ok (verdict "
                      f"« {retour_lisible(str(releve.get('verdict')))} ») : corrige ses causes et relève à nouveau "
                      f"AVANT la fusion ; déjà fusionnée : {RETOUR_SORTIE}")
    taches = releve.get("taches")
    autres: list[str] = []
    for nom in taches if isinstance(taches, list) else []:
        try:
            ident = find(data, nom)["id"]
        except BoardError:
            causes.append(f"(R-t) le relevé nomme « {retour_lisible(str(nom))} », introuvable au board — relève "
                          f"à nouveau AVANT la fusion ; déjà fusionnée : {RETOUR_SORTIE}")
            continue
        if ident != task["id"]:
            autres.append(ident)
    if not isinstance(taches, list) or not taches:
        causes.append(f"(R-t) le relevé ne nomme aucune tâche — relève à nouveau AVANT la fusion ; "
                      f"déjà fusionnée : {RETOUR_SORTIE}")
    if autres:
        causes.append(f"(R-t) le relevé nomme aussi {', '.join(sorted(set(autres)))} : une directe se relève "
                      f"SEULE, sur sa propre branche — relève-la seule AVANT la fusion ; déjà fusionnée : "
                      f"{RETOUR_SORTIE}")
    fichiers = releve.get("fichiers")
    tampon = task.get("direct")
    vus = tampon.get("writeset") if isinstance(tampon, dict) else None
    vus = [p for p in vus if isinstance(p, str)] if isinstance(vus, list) else []
    if not isinstance(fichiers, list) or not fichiers:
        causes.append(f"(R-c) le relevé ne porte aucun fichier — relève la branche du dev AVANT la fusion ; "
                      f"déjà fusionnée : {RETOUR_SORTIE}")
    else:
        if len(fichiers) > MAX_FICHIERS_DIRECT:
            causes.append(f"(R-c) le relevé porte {len(fichiers)} fichier(s), au-delà de ce que la voie directe "
                          f"admet ({MAX_FICHIERS_DIRECT}) : le chemin planifié ; déjà fusionnée : {RETOUR_SORTIE}")
        hors = [retour_lisible(str(f)) for f in fichiers
                if not (isinstance(f, str) and any(retour_couvre(e, f) for e in vus))]
        if hors:
            causes.append(f"(R-c) {len(hors)} fichier(s) du relevé hors de l'instantané de l'estampille : "
                          f"{retour_liste(hors)} — `tasks.py direct` ne les a pas validés ; déjà fusionnée : "
                          f"{RETOUR_SORTIE}")
    if direct_rang_specs({"id": releve.get("specs_borne")}) == DIRECT_RANG_ILLISIBLE:
        causes.append(f"(R-d) borne SPECS du relevé nulle (SPECS illisible au relevé) : aucun verdict de "
                      f"sécurité ne s'y borne — répare SPECS et relève à nouveau AVANT la fusion ; déjà "
                      f"fusionnée : {RETOUR_SORTIE}")
    if "vers" in releve and (livraison_de(task) or {}).get("branche") != releve.get("vers"):
        # (R-v) T-01M4WTYSCE : le relevé `--vers L` ne vaut que tant que la tâche porte la livraison L.
        causes.append(f"(R-v) le relevé est pris vers la livraison {retour_lisible(str(releve.get('vers')))}, que "
                      f"{task['id']} ne porte plus (retirée ou re-déclarée) — re-déclare-la (`tasks.py livraison`) ou "
                      f"relève à nouveau ; déjà fusionnée : {RETOUR_SORTIE}")
    if admis:
        tip = releve.get("tip")
        if pre is None:
            causes.append("(R-b) relevé non pré-mesuré — passe par `tasks.py done`, qui mesure la fusion HORS "
                          "verrou avant de clore")
        elif pre.get("cle") is None:
            causes.append("(R-b) fusion non mesurée (git sans réponse, racine hors du toplevel git ou relevé "
                          "illisible) — rejoue `done` quand git répond, à la racine du dépôt")
        elif tuple(pre["cle"]) != (releve.get("base"), tip, releve.get("le")):
            causes.append("(R-b) relevé changé pendant la mesure — rejoue `done`")
        elif "vers" in releve:
            causes += retour_refus_livraison(task, data, releve, tip, pre)
        elif not any(len(p) >= 3 and p[2] == tip for p in (ligne.split() for ligne in pre.get("lignes") or [])):
            causes.append(f"(R-b) la pointe relevée {retour_court(str(tip))} n'est le second parent d'aucune "
                          f"fusion de HEAD — le geste est `git merge --no-ff <branche>` ; une avance rapide ou une "
                          f"fusion imbriquée ne se rattrape pas, {RETOUR_SORTIE}")
        else:
            causes += retour_contenu_fusions(releve, tip, pre)
    return causes


def retour_contenu_fusions(releve: dict[str, Any], tip: Any, pre: dict[str, Any]) -> list[str]:
    """(R-b), suite : LE CONTENU de chaque fusion de la pointe relevée, lu par la
    pré-mesure, ne porte que des fichiers du relevé (binôme c4f3 F1). Une fusion
    dont le contenu n'a pas été lu refuse : jamais un passage."""
    releves = {f for f in releve.get("fichiers") or [] if isinstance(f, str)}
    contenus = pre.get("contenus") if isinstance(pre.get("contenus"), dict) else {}
    causes: list[str] = []
    for p in (ligne.split() for ligne in pre.get("lignes") or []):
        if len(p) < 3 or p[2] != tip:
            continue
        contenu = contenus.get(p[0])
        if not isinstance(contenu, list):
            causes.append(f"(R-b) contenu de la fusion {retour_court(p[0])} non mesuré — rejoue `done`")
            continue
        hors = [f for f in contenu if f not in releves]
        if hors:
            causes.append(f"(R-b) la fusion de {retour_court(str(tip))} porte {len(hors)} fichier(s) hors du "
                          f"relevé : {retour_liste(hors)} — elle n'est pas telle quelle ; {RETOUR_SORTIE}")
    return causes


def retour_refus_livraison(task: dict[str, Any], data: dict[str, Any], releve: dict[str, Any], tip: Any,
                           pre: dict[str, Any]) -> list[str]:
    """(R-b) SOUS `vers` (T-01M4WTYSCE) : la pointe relevée est entrée dans HEAD à
    EXACTEMENT deux niveaux — fusionnée dans la livraison, la livraison fusionnée dans
    HEAD (une fusion directe dans la cible a contourné la revue de la livraison) — et
    « telle quelle » aux deux : la fusion du lot dans la livraison ne porte que des
    fichiers du relevé ; la fusion de la livraison dans HEAD (`M^1..M`) ne porte que des
    chemins couverts par l'union des write-sets DÉCLARÉS des membres, lus ICI, sous le
    verrou (le contenu, lui, l'a été hors verrou : `retour_premesure_livraison`).
    Toutes les causes ; aucun git ici."""
    vers = retour_lisible(str(releve.get("vers")))
    mesure = pre.get("livraison")
    if not isinstance(mesure, dict):
        return [f"(R-b) fusion vers la livraison {vers} non mesurée — rejoue `done`"]
    paires = [p for p in mesure.get("paires") or [] if isinstance(p, list) and len(p) == 2]
    if not paires:
        return [f"(R-b) la pointe relevée {retour_court(str(tip))} n'est pas entrée dans HEAD par la livraison "
                f"{vers} à EXACTEMENT deux niveaux — `git merge --no-ff <branche>` dans {vers}, puis "
                f"`git merge --no-ff {vers}` dans la cible ; une fusion directe dans la cible contourne la revue "
                f"de la livraison, {RETOUR_SORTIE}"]
    fichiers_releve = {f for f in releve.get("fichiers") or [] if isinstance(f, str)}
    membres = livraison_membres(data, task) or [task]
    couverture = [e for membre in membres for e in writeset_of(membre)]
    causes: list[str] = []
    for fusion_cible, fusion_lot in paires:
        contenu_lot = (mesure.get("lots") or {}).get(fusion_lot)
        contenu_cible = (mesure.get("cibles") or {}).get(fusion_cible)
        if not (isinstance(contenu_lot, list) and isinstance(contenu_cible, list)):
            causes.append(f"(R-b) contenu des fusions {retour_court(fusion_lot)} / {retour_court(fusion_cible)} "
                          f"non mesuré — rejoue `done`")
            continue
        hors_lot = [f for f in contenu_lot if f not in fichiers_releve]
        if hors_lot:
            causes.append(f"(R-b) la fusion de {retour_court(str(tip))} dans {vers} porte {len(hors_lot)} fichier(s) "
                          f"hors du relevé : {retour_liste(hors_lot)} — elle n'est pas telle quelle ; {RETOUR_SORTIE}")
        hors_ws = [f for f in contenu_cible if not any(retour_couvre(e, f) for e in couverture)]
        if hors_ws:
            causes.append(f"(R-b) la fusion de {vers} dans la cible ({retour_court(fusion_cible)}) porte "
                          f"{len(hors_ws)} fichier(s) hors des write-sets déclarés des membres "
                          f"({', '.join(m['id'] for m in membres)}) : {retour_liste(hors_ws)} — remède : "
                          f"l'INTÉGRATION, l'index et la doc s'écrivent sur la cible APRÈS la fusion de {vers} ; le "
                          f"write-set d'un membre NON direct s'étend sur une décision tracée ; une directe étendue "
                          f"se ré-estampille (`tasks.py direct`) ; sinon {RETOUR_SORTIE}")
    return causes


def retour_refus_securite(root: str, tid: str, task: dict[str, Any], data: dict[str, Any],
                          borne: Any) -> tuple[list[str], str]:
    """LE VERDICT DE SÉCURITÉ APRÈS LE RELEVÉ : `(causes, note d'emprunt)`.
    Candidats : `kind=verdict`, titre portant `securite`/`security`, rang S-id
    STRICTEMENT au-delà de `borne` (la borne SPECS du relevé), sur la tâche OU
    sur un slot `running` de la MÊME portée de revue active (`tid` membre non consommé)
    ou du MÊME groupe parallèle déclaré — plus du chantier (T-01M5F728FGJ43QJX1RJKTWWKRB :
    la sécurité de T1 ne couvre pas T2). La borne reste celle du relevé, la PREMIÈRE
    disponible : un `security-code-review` tracé après lui et AVANT la déclaration de la
    portée compte (arbitrage C38, S-01M5E5WH6S).
    Le DERNIER : (s1) `direct_causes_securite` sur une tâche sans titre et ce seul
    verdict — un signal ouvert l'emporte (S-00004181) ; (s2) `RETOUR_SECU_ABSENT`
    au titre ou au texte → refus. Admis sur le slot → la note d'emprunt. SPECS
    illisible → refus. Borne illisible → `([], "")` : R-a ou R-d refusent déjà."""
    rang_borne = direct_rang_specs({"id": borne})
    if rang_borne == DIRECT_RANG_ILLISIBLE:
        return [], ""
    try:
        pc = plan_cible_module()
    except Exception:  # noqa: BLE001 — un frère CASSÉ ne se lit pas comme un frère absent : refus
        pc = None
    if pc is None:
        return ["(s) SPECS illisible : le verdict de sécurité n'est pas établi (plan_cible.py inchargeable)"], ""
    try:
        entrees = pc.entrees_specs(normalize_root(root))
    except (pc.CibleError, OSError, ValueError) as exc:
        return [f"(s) SPECS illisible : le verdict de sécurité n'est pas établi ({retour_lisible(str(exc))}) "
                f"— répare SPECS, puis rejoue `done`"], ""
    index = pc.index_par_tache(entrees)
    porteurs = [task["id"]]
    portee, groupe = portee_active(root), parallel_group_of(task)
    couverte = portee_couvre(portee, task["id"])
    if couverte or groupe:
        porteurs += [autre["id"] for autre in data["tasks"] if autre.get("id") != task["id"]
                     and autre.get("state") == "running"
                     and ((couverte and autre.get("id") in portee["members"])
                          or (groupe and parallel_group_of(autre) == groupe))]
    candidats = [(direct_rang_specs(e), porteur, e) for porteur in porteurs for e in pc.entrees_de(index, porteur)
                 if isinstance(e, dict) and e.get("kind") == "verdict"
                 and direct_porte_lexique(direct_normaliser(e.get("title")), ("securite", "security"))
                 and direct_rang_specs(e) > rang_borne]
    if not candidats:
        return [f"(s) aucun verdict de sécurité tracé après le relevé, ni sur {tid} ni sur un slot `running` de sa "
                f"portée de revue (`tasks.py review-scope`) ou de son groupe déclaré — fais jouer "
                f"`security-code-review` sur le diff, trace son verdict, puis rejoue `done`"], ""
    _rang, porteur, dernier = max(candidats, key=lambda c: c[0])
    causes = [f"(s) {c}" for c in direct_causes_securite({}, [dernier])]
    for champ, nom in (("title", "titre"), ("text", "texte")):
        jeton = direct_porte_lexique(direct_normaliser(dernier.get(champ)), RETOUR_SECU_ABSENT)
        if jeton is not None:
            causes.append(f"(s) le dernier verdict de sécurité dit une revue absente ({nom} : « {jeton} ») : "
                          f"fais jouer la revue, puis rejoue `done`")
            break
    if causes or porteur == task["id"]:
        return causes, ""
    return [], f"[revue de sécurité empruntée au slot {porteur} : {retour_lisible(str(dernier.get('id')))}]"


def retour_message_refus(tid: str, causes: list[str]) -> str:
    """Le refus du `done` : TOUTES les causes, puis l'exigence en une phrase."""
    lignes = "".join(f"  - {c}\n" for c in causes)
    return (f"TASKS: refus de clore {tid} — directe qui franchit une garde armée, {len(causes)} cause(s) :\n"
            f"{lignes}Son `done` exige le relevé `tasks.py retour` de SA branche, fusionnée `git merge --no-ff` "
            "telle quelle, fichiers dans l'estampille, et un verdict de sécurité tracé après lui, ni bloquant "
            "ni absent. Rien n'a été écrit.")
