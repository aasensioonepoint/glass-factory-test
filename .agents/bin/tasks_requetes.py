# tasks_requetes.py — PARTIE de `tasks.py` (T-00000788) : les REQUÊTES —
# résolution d'id, grammaire du writeset, graphe des dépendances, filtres,
# et revendication Git (precontrole_revendication : fetch, sous-processus).
# Exécutée dans l'espace de noms de `tasks` par `_charger_parties()`,
# jamais importée seule : ses noms libres viennent de la façade et des parties amont.

from __future__ import annotations

import signal
import subprocess


# La revendication se lit AVANT le pont V3 et les verrous du board. Une preuve
# distante absente ne libère jamais une prise locale ou distante.
REVENDICATION_BUDGET = 30.0
REVENDICATION_BLOB_MAX = 4 * 1024 * 1024
REVENDICATION_HISTOIRE_MAX = 512
REVENDICATION_IDS_MAX = 32
REVENDICATION_POINTES_MAX = 16  # pointes gardées par prise levée (`reprise_levee[].pointes`)


def _rev_texte(value: object) -> str:
    """Une ref ou un acteur est une donnée non fiable, même dans un avis."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_rev_texte(k)}: {_rev_texte(v)}" for k, v in value.items()) + "}"
    return "".join(f"\\u{ord(c):04x}" if unicodedata.category(c) in ("Cc", "Cf") else c
                   for c in str(value))[:200]


class _RevGit:
    def __init__(self, root: str) -> None:
        self.root = root
        self.fin = time.monotonic() + REVENDICATION_BUDGET
        self.persistant = False
        self.env = {k: v for k, v in os.environ.items() if k not in {
            "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX",
        }}
        self.env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never",
                        GIT_CEILING_DIRECTORIES=str(Path(root).resolve().parent))

    def run(self, *args: str, timeout: float = 5.0) -> tuple[int, bytes]:
        restant = self.fin - time.monotonic()
        if self.persistant or restant <= 0:
            raise TimeoutError("budget Git épuisé")
        proc = subprocess.Popen(["git", "-C", self.root, *args], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
        try:
            out, _err = proc.communicate(timeout=min(timeout, restant))
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.communicate(timeout=max(0.01, self.fin - time.monotonic()))
            except subprocess.TimeoutExpired:
                self.persistant = True
            raise TimeoutError("Git a dépassé son délai" + (" ; processus persistant, verrou possible"
                                                       if self.persistant else ""))
        return proc.returncode, out


def _rev_blob(git: _RevGit, ref: str, chemin: str) -> bytes | None:
    spec = f"{ref}:{chemin}"
    rc, taille = git.run("cat-file", "-s", spec)
    if rc:
        return None
    if int(taille.strip()) > REVENDICATION_BLOB_MAX:
        raise ValueError("blob de board supérieur à 4 Mio")
    rc, contenu = git.run("show", spec)
    if rc or len(contenu) > REVENDICATION_BLOB_MAX:
        raise ValueError("blob de board illisible ou supérieur à 4 Mio")
    return contenu


def _rev_record(git: _RevGit, ref: str, tid: str) -> tuple[dict[str, Any] | None, list[str]]:
    chemins = (f".agents/state/board/tasks/{tid}.json", ".agents/state/board/TASKS.json")
    trouves: list[tuple[dict[str, Any], str]] = []
    for chemin in chemins:
        brut = _rev_blob(git, ref, chemin)
        if brut is None:
            continue
        try:
            valeur = json.loads(brut.decode("utf-8"))
            if chemin.endswith("TASKS.json"):
                valeur = next((t for t in valeur["tasks"] if isinstance(t, dict) and t.get("id") == tid), None)
            else:
                valeur = valeur["record"]
            if valeur is not None and (not isinstance(valeur, dict) or valeur.get("id") != tid):
                raise ValueError("record d'id différent")
        except (UnicodeError, ValueError, KeyError, TypeError, RecursionError) as exc:
            raise ValueError(f"record illisible ({type(exc).__name__})") from exc
        if valeur is not None:
            trouves.append((valeur, chemin))
    if len(trouves) == 2 and trouves[0][0] != trouves[1][0]:
        raise ValueError("formes dossier et monolithe divergentes")
    return (trouves[0][0] if trouves else None), [p for _v, p in trouves]


def _rev_etat(git: _RevGit, commit: str, chemin: str, tid: str) -> str | None:
    brut = _rev_blob(git, commit, chemin)
    if brut is None:
        return None
    try:
        valeur = json.loads(brut.decode("utf-8"))
        if chemin.endswith("TASKS.json"):
            valeur = next((t for t in valeur["tasks"] if isinstance(t, dict) and t.get("id") == tid), None)
        else:
            valeur = valeur["record"]
        return valeur.get("state") if isinstance(valeur, dict) and valeur.get("id") == tid else None
    except (UnicodeError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError(f"record historique illisible ({type(exc).__name__})") from exc


def _rev_transition(git: _RevGit, ref: str, chemins: list[str], tid: str,
                    entree: bool, restant: list[int], suivre_running: bool = False) -> str | None:
    """La transition la PLUS RÉCENTE ; un merge mixte d'entrée est ambigu.

    `suivre_running` (clé de levée locale seulement) : un merge dont un parent tenait déjà la tâche
    running n'est pas l'entrée — elle est plus bas, sur ce parent. Une clé fausse ne lève rien.
    """
    if restant[0] <= 0:
        raise ValueError("budget historique de 512 commits épuisé")
    rc, sortie = git.run("log", "--full-history", f"--max-count={restant[0]}",
                         "--format=%H", ref, "--", *chemins)
    if rc:
        raise ValueError("historique Git illisible")
    commits = sortie.decode("ascii", "replace").splitlines()
    restant[0] -= len(commits)
    for commit in commits:
        for chemin in chemins:
            etat = _rev_etat(git, commit, chemin, tid)
            if (etat == "running") != entree:
                continue
            rc, sortie_parents = git.run("rev-list", "--parents", "-n", "1", commit)
            if rc:
                raise ValueError("parents Git illisibles")
            parents = sortie_parents.decode("ascii", "replace").split()[1:]
            anciens = [_rev_etat(git, p, chemin, tid) for p in parents]
            if len(set(anciens)) > 1:
                if entree and suivre_running and "running" in anciens:
                    continue
                if entree:
                    raise ValueError("transition de merge ambiguë")
                continue  # sortie : la vraie transition est plus bas, sur le parent fusionné
            avant = anciens[0] if anciens else None
            if entree and avant != "running" or not entree and avant == "running":
                return commit
    if restant[0] <= 0:
        raise ValueError("budget historique de 512 commits épuisé")
    return None


def _rev_auteur(acteur: object) -> dict[str, str | None] | None:
    if not isinstance(acteur, dict):
        return None
    auteur = acteur.get("auteur")
    if not isinstance(auteur, dict):
        return None
    nom, email = auteur.get("nom"), auteur.get("email")
    if not (nom is None or isinstance(nom, str)) or not (email is None or isinstance(email, str)):
        return None
    return {"nom": nom, "email": email} if nom is not None or email is not None else None


def _rev_transfert(git: _RevGit, ref: str, chemins: list[str], tid: str,
                   auteur: dict[str, str | None], restant: list[int]) -> tuple[str, dict[str, str | None]] | None:
    """Commit publié qui a changé le pilote d'une tâche encore running.

    Une pointe portant simplement un autre auteur n'est pas une preuve de
    transfert. Les parents du commit doivent tous porter l'ancien pilote,
    quel que soit leur état (running, blocked, pending ou done).
    """
    if restant[0] <= 0:
        raise ValueError("budget historique de 512 commits épuisé")
    rc, sortie = git.run("log", "--full-history", f"--max-count={restant[0]}",
                         "--format=%H", ref, "--", *chemins)
    if rc:
        raise ValueError("historique Git illisible")
    commits = sortie.decode("ascii", "replace").splitlines()
    restant[0] -= len(commits)
    for commit in commits:
        present, _ = _rev_record(git, commit, tid)
        if present is None or present.get("state") != "running" or _rev_auteur(present.get("start_actor")) != auteur:
            continue
        rc, sortie_parents = git.run("rev-list", "--parents", "-n", "1", commit)
        if rc:
            raise ValueError("parents Git illisibles")
        parents = sortie_parents.decode("ascii", "replace").split()[1:]
        anciens = []
        for parent in parents:
            row, _ = _rev_record(git, parent, tid)
            anciens.append(_rev_auteur(row.get("start_actor")) if row else None)
        if anciens and all(old is not None and old != auteur for old in anciens) and all(old == anciens[0] for old in anciens):
            return commit, anciens[0]
        if not anciens or any(old is None for old in anciens):
            return None  # nouveau cycle : un transfert d'un cycle plus ancien ne compte pas
    if restant[0] <= 0:
        raise ValueError("budget historique de 512 commits épuisé")
    return None


def precontrole_revendication(root: str, tid: str | list[str], acteur: dict[str, Any],
                              fetch: bool = True,
                              preuves: dict[str, dict[str, Any]] | None = None,
                              levees: dict[str, list[dict[str, Any]]] | None = None) -> tuple[list[str], list[str]]:
    """(refus, avis), lecture locale puis Git ; propriété étrangère ou identité inconnue refuse.

    `levees` reçoit, par id, chaque prise étrangère `{"auteur", "transition", "pointe", "pointes"}` refusée
    ici : une reprise manuelle la garde au board (`reprise_levee`, S-01M5HH8QMC). Une prise distante
    du MÊME auteur et de la MÊME transition d'entrée n'est ensuite qu'un avis pour le nouveau
    propriétaire ; un nouveau cycle de l'ancien pilote (autre transition) refuse toujours.
    """
    refus: list[str] = []
    avis: list[str] = []
    data = load(root)
    ids = [tid] if isinstance(tid, str) else list(dict.fromkeys(tid))
    if len(ids) > REVENDICATION_IDS_MAX:
        refus.append(f"REVENDICATION: {len(ids)} tâches dans le précontrôle ; maximum {REVENDICATION_IDS_MAX}")
        return refus, avis  # borne avant toute lecture de HEAD ; aucun id n'est omis en silence
    if any(not any(t.get("id") == identifiant for t in data["tasks"]) for identifiant in ids):
        return refus, avis  # le verbe historique rend son propre « unknown task id » après le drain V3
    auteur = _rev_auteur(acteur)

    prises: list[tuple[dict[str, Any], str, str, str | None, str | None, str | None]] = []
    transferts: dict[str, tuple[str, dict[str, str | None]]] = {}
    transitions_locales: dict[str, str] = {}

    def lever(identifiant: str, autre: dict[str, str | None], transition: str | None,
              pointes: list[str] | None = None) -> None:
        """Chaque pointe vue est gardée (`pointes`, bornée) ; `pointe` reste la plus avancée par filiation,
        quel que soit l'ordre des refs — les records d'avant n'ont qu'elle."""
        if levees is None or transition is None:
            return
        existante = next((e for e in levees.setdefault(identifiant, [])
                          if e.get("auteur") == autre and e.get("transition") == transition), None)
        if existante is None:
            existante = {"auteur": copy.deepcopy(autre), "transition": transition}
            levees[identifiant].append(existante)
        for pointe in (p for p in map(pointe_sure, pointes or []) if p is not None):
            connues = existante.setdefault("pointes", [])
            if pointe not in connues and len(connues) < REVENDICATION_POINTES_MAX:
                connues.append(pointe)
            if "pointe" not in existante or ancetre(existante["pointe"], pointe) == 0:
                existante["pointe"] = pointe

    def pointes_de(entree: dict[str, Any]) -> list[str]:
        """Pointes gardées d'une entrée : `pointes` (bornée) puis `pointe`, chacune par `pointe_sure`."""
        brutes = entree.get("pointes")
        brutes = list(brutes[:REVENDICATION_POINTES_MAX]) if isinstance(brutes, list) else []
        brutes.append(entree.get("pointe"))
        return list(dict.fromkeys(p for p in map(pointe_sure, brutes) if p is not None))

    def deja_levee(identifiant: str, autre: dict[str, str | None] | None,
                   transition: str | None) -> dict[str, Any] | None:
        locale = find(data, identifiant)
        gardees = locale.get("reprise_levee")
        if (auteur is None or autre is None or transition is None
                or _rev_auteur(locale.get("start_actor")) != auteur or not isinstance(gardees, list)):
            return None
        return next((e for e in gardees if isinstance(e, dict) and e.get("auteur") == autre
                     and e.get("transition") == transition), None)

    def juger(prise: dict[str, Any], origine: str, identifiant: str,
              transition: str | None = None, cle: str | None = None,
              pointe: str | None = None) -> None:
        if prise.get("state") != "running" and origine != "board local":
            return
        if origine == "board local" and not isinstance(prise.get("start_actor"), dict):
            return
        prises.append((prise, origine, identifiant, transition, cle, pointe))

    def ancetre(commit: str, cible: str) -> int | None:
        """rc de `merge-base --is-ancestor` (0 ancêtre, 1 non) ; None si illisible."""
        try:
            return git.run("merge-base", "--is-ancestor", commit, cible)[0]
        except (OSError, TimeoutError, ValueError, subprocess.SubprocessError):
            return None

    def pointe_sure(valeur: object) -> str | None:
        """Une pointe gardée au board est une donnée : jamais passée brute à git."""
        return valeur if isinstance(valeur, str) and re.fullmatch(r"[0-9a-f]{40,64}", valeur) else None

    def present(commit: str) -> bool:
        try:
            return git.run("cat-file", "-e", f"{commit}^{{commit}}")[0] == 0
        except (OSError, TimeoutError, ValueError, subprocess.SubprocessError):
            return True  # illisible : `ancetre` tranche, filiation illisible = contenue

    def contenue(pointe: str, reference: str, transfert: str | None) -> bool:
        if reference == pointe:
            return True
        if transfert is not None and not present(reference):
            reference = transfert  # pointe gardée absente de ce clone : le commit de transfert la remplace
        return ancetre(pointe, reference) != 1

    def a_pousse(pointe: str | None, references: list[str], cle: str | None,
                 transfert: str | None = None) -> bool:
        """L'ancienne branche a avancé : sa pointe courante n'est contenue dans AUCUNE des pointes
        constatées à la reprise (miroir périmé ou ref divergente qui porte la même prise ne comptent
        pas) ; sans pointe constatée, la prise d'entrée est dans HEAD alors que la ref n'y est pas."""
        if pointe is None:
            return False
        sures = [r for r in map(pointe_sure, references) if r is not None]
        if sures:
            return not any(contenue(pointe, r, transfert) for r in sures)
        return cle is not None and ancetre(cle, "HEAD") == 0

    def conclure() -> tuple[list[str], list[str]]:
        for prise, origine, identifiant, transition, cle, pointe in prises:
            ancien = prise.get("start_actor")
            autre = _rev_auteur(ancien)
            transfert = transferts.get(identifiant)
            descendant = origine == "board local"
            if transfert and autre == transfert[1] and transition is not None and not descendant:
                try:
                    descendant = git.run("merge-base", "--is-ancestor", transition, transfert[0])[0] == 0
                except (OSError, TimeoutError, ValueError, subprocess.SubprocessError) as exc:
                    avis.append(f"PRISE GIT (avis): filiation illisible ({_rev_texte(exc)}) ; prise conservée")
            gardee = deja_levee(identifiant, autre, cle) if origine != "board local" else None
            if gardee is not None:
                # Comparer aux pointes constatées lors de la reprise, pas au commit de transition.
                lever(identifiant, autre, cle, pointes_de(gardee))
                if a_pousse(pointe, pointes_de(gardee), cle, transfert[0] if transfert else None):
                    avis.append(f"REVENDICATION: ancien pilote a poussé après reprise ({identifiant}, {origine})")
                else:
                    avis.append(f"REVENDICATION: prise levée par reprise encore publiée ({identifiant}, {origine})")
                continue
            if transfert and autre == transfert[1] and descendant:
                if origine == "board local" and preuves is not None:
                    preuves[identifiant] = {"ancien": copy.deepcopy(ancien), "nouveau": copy.deepcopy(acteur),
                                            "commit": transfert[0]}
                if origine != "board local":
                    # Référence : les pointes gardées par le transfert T (`reprise_levee`) ; T sans entrée, ou
                    # à la place d'une pointe gardée absente de ce clone. Record de T illisible : filiation
                    # illisible, jamais « a poussé » (AGENTS.md § propriété des tâches).
                    lisible = True
                    try:
                        gardees = (_rev_record(git, transfert[0], identifiant)[0] or {}).get("reprise_levee")
                    except (ValueError, UnicodeError, RecursionError, TimeoutError,
                            OSError, subprocess.SubprocessError):
                        gardees = None
                        lisible = False
                    entree = next((e for e in gardees if isinstance(e, dict) and e.get("auteur") == autre
                                   and e.get("transition") == cle), None) if isinstance(gardees, list) else None
                    if lisible and (a_pousse(pointe, [transfert[0]], None) if entree is None
                            else a_pousse(pointe, pointes_de(entree), cle, transfert[0])):
                        avis.append(f"REVENDICATION: ancien pilote a poussé après reprise ({identifiant}, {origine})")
                    else:
                        avis.append(f"REVENDICATION: prise levée par reprise encore publiée ({identifiant}, {origine})")
                continue
            if autre is None or auteur is None:
                if autre is not None and auteur is None:
                    refus.append(f"REVENDICATION: {identifiant} pris par {_rev_texte(autre)} sur {origine} ; "
                                 "identité courante inconnue")
                else:
                    avis.append(f"PRISE GIT (avis): {origine} — auteur inconnu ou pont V3 ; prise incertaine")
            elif autre != auteur:
                lever(identifiant, autre,
                      transitions_locales.get(identifiant) if origine == "board local" else cle,
                      [pointe] if origine != "board local" and pointe is not None else None)
                refus.append(f"REVENDICATION: {identifiant} pris par {_rev_texte(autre)} sur {origine} ; "
                             f"auteur courant {_rev_texte(auteur)}")
            elif isinstance(ancien, dict) and ancien.get("copie") != acteur.get("copie"):
                copie = ancien.get("copie")
                if copie is not None and not isinstance(copie, str):
                    avis.append(f"PRISE GIT (avis): {origine} — copie illisible ; même auteur")
                else:
                    avis.append(f"PRISE GIT (avis): {origine} — même auteur, autre copie "
                                f"{_rev_texte(copie)} / {_rev_texte(acteur.get('copie'))}")
        return refus, avis

    for identifiant in ids:
        juger(find(data, identifiant), "board local", identifiant)
    if not fetch:
        return conclure()
    git = _RevGit(root)
    try:
        rc, top = git.run("rev-parse", "--show-toplevel")
        if rc or Path(top.decode("utf-8", "replace").strip()).resolve() != Path(root).resolve():
            return conclure()  # --root jetable hors Git : jamais remonter au dépôt hôte
        rc, remotes = git.run("remote")
        if rc:
            raise ValueError("remotes illisibles")
        noms = remotes.decode("utf-8", "replace").splitlines()
        if not noms:
            return conclure()
        if len(noms) > 6:
            avis.append("PRISE GIT (avis): plus de six remotes ; fraîcheur incomplète")
        rc, commande_ssh = git.run("config", "--get", "core.sshCommand")
        if "GIT_SSH" in git.env:
            git.env.pop("GIT_SSH_COMMAND", None)  # le programme SSH hérité garde la priorité
        elif "GIT_SSH_COMMAND" in git.env:
            git.env["GIT_SSH_COMMAND"] += " -oBatchMode=yes"
        elif rc == 0:
            git.env["GIT_SSH_COMMAND"] = commande_ssh.decode("utf-8", "replace").strip() + " -oBatchMode=yes"
        else:
            git.env["GIT_SSH_COMMAND"] = "ssh -oBatchMode=yes"
        for nom in noms[:6]:
            try:
                rc, _ = git.run("-c", "gc.auto=0", "fetch", "--no-tags", "--prune",
                                "--no-auto-maintenance", "--", nom)
                if rc:
                    avis.append(f"PRISE GIT (avis): fetch {_rev_texte(nom)} échoué ; fraîcheur inconnue")
            except TimeoutError as exc:
                avis.append(f"PRISE GIT (avis): fetch {_rev_texte(nom)} : {exc} ; fraîcheur inconnue")
                if git.persistant:
                    return conclure()
        rc, upstream = git.run("rev-parse", "--verify", "@{u}")
        up = upstream.decode("ascii", "replace").strip() if rc == 0 else ""
        if not up:
            avis.append("PRISE GIT (avis): sans upstream ; seules les refs non ancêtres de HEAD sont vues")
        rc, sortie = git.run("for-each-ref", "--format=%(refname)%00%(objectname)",
                             "--no-merged=HEAD", "refs/remotes")
        if rc:
            raise ValueError("refs distantes illisibles")
        refs = [ligne.split("\x00", 1) for ligne in sortie.decode("utf-8", "replace").splitlines()
                if "\x00" in ligne]
        if up:
            rc, sortie_amont = git.run("for-each-ref", "--format=%(refname)%00%(objectname)",
                                      f"--no-merged={up}", "refs/remotes")
            if rc:
                raise ValueError("refs relatives à l'upstream illisibles")
            # Le second ensemble montre les pointes que l'upstream n'a pas
            # encore absorbées ; HEAD reste le filtre de base ci-dessus.
            refs_amont = {ligne.split("\x00", 1)[1]
                          for ligne in sortie_amont.decode("utf-8", "replace").splitlines()
                          if "\x00" in ligne}
            refs.sort(key=lambda pair: pair[1] not in refs_amont)
        if up and git.run("merge-base", "--is-ancestor", up, "HEAD")[0] != 0:
            rc, nom_up = git.run("rev-parse", "--symbolic-full-name", "@{u}")
            if rc == 0:
                refs.append([nom_up.decode("utf-8", "replace").strip(), up])
        uniques: dict[str, str] = {}
        for nom, sha in refs:
            if up and sha != up and sha not in refs_amont:
                continue
            if sha not in uniques or (uniques[sha].endswith("/HEAD") and not nom.endswith("/HEAD")):
                uniques[sha] = nom
        restant = [REVENDICATION_HISTOIRE_MAX]
        for identifiant in ids:
            sortie_up = None
            # HEAD a SON budget, par id, hors des 512 commits partagés des refs distantes (S-01M5HYRYRF) :
            # une fournée à plusieurs ids n'épuise jamais la lecture distante par ses lectures locales.
            restant_tete = [REVENDICATION_HISTOIRE_MAX]
            locale_auteur = _rev_auteur(find(data, identifiant).get("start_actor"))
            if auteur is not None and locale_auteur == auteur:
                # LA REPRISE DÉJÀ PORTÉE PAR HEAD (S-01M5HH8QMC) : le transfert local reconnaît la prise
                # de l'ancien pilote qui pousse encore après lui — un avertissement, jamais un refus.
                try:
                    tete, chemins_tete = _rev_record(git, "HEAD", identifiant)
                    if tete is not None:
                        transfert = _rev_transfert(git, "HEAD", chemins_tete, identifiant, auteur, restant_tete)
                        if transfert is not None:
                            transferts.setdefault(identifiant, transfert)
                except (ValueError, UnicodeError, RecursionError, TimeoutError) as exc:
                    avis.append(f"PRISE GIT (avis): HEAD — {exc} ; transfert local non prouvé")
            elif auteur is not None and locale_auteur is not None:
                # La prise locale étrangère : sa transition d'entrée dans HEAD est ce qu'une reprise lève
                # (la même prise, publiée sur une branche non fusionnée, porte la même transition).
                try:
                    tete, chemins_tete = _rev_record(git, "HEAD", identifiant)
                    if (tete is not None and tete.get("state") == "running"
                            and _rev_auteur(tete.get("start_actor")) == locale_auteur):
                        entree = _rev_transition(git, "HEAD", chemins_tete, identifiant, True, restant_tete,
                                                 suivre_running=True)
                        if entree is not None:
                            transitions_locales[identifiant] = entree
                except (ValueError, UnicodeError, RecursionError, TimeoutError) as exc:
                    avis.append(f"PRISE GIT (avis): HEAD — {exc} ; transition locale non lue")
            for sha, nom in uniques.items():
                try:
                    prise, chemins = _rev_record(git, sha, identifiant)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    avis.append(f"PRISE GIT (avis): {_rev_texte(nom)} — {exc} ; prise illisible")
                    continue
                if prise is None or prise.get("state") != "running":
                    continue
                autre = _rev_auteur(prise.get("start_actor"))
                if auteur is not None and autre == auteur:
                    try:
                        transfert = _rev_transfert(git, sha, chemins, identifiant, auteur, restant)
                        if transfert is not None:
                            transferts[identifiant] = transfert
                    except (ValueError, UnicodeError, RecursionError, TimeoutError) as exc:
                        avis.append(f"PRISE GIT (avis): {_rev_texte(nom)} — {exc} ; transfert non prouvé")
                if auteur is None or _rev_auteur(prise.get("start_actor")) in (None, auteur):
                    juger(prise, _rev_texte(nom), identifiant)
                    continue
                transition = None
                try:
                    transition = _rev_transition(git, sha, chemins, identifiant, True, restant)
                    if transition is None:
                        raise ValueError("transition vers running introuvable")
                    if up:
                        amont, chemins_up = _rev_record(git, up, identifiant)
                        if amont is not None and amont.get("state") != "running":
                            if sortie_up is None:
                                sortie_up = _rev_transition(git, up, chemins_up, identifiant, False, restant) or ""
                        if sortie_up and git.run("merge-base", "--is-ancestor", transition, sortie_up)[0] == 0:
                            continue
                except (ValueError, UnicodeError, RecursionError, TimeoutError) as exc:
                    avis.append(f"PRISE GIT (avis): {_rev_texte(nom)} — {exc} ; prise conservée")
                cle = transition
                if cle is None:
                    try:
                        cle = _rev_transition(git, sha, chemins, identifiant, True, restant,
                                              suivre_running=True)
                    except (ValueError, UnicodeError, RecursionError, TimeoutError):
                        cle = None
                juger(prise, _rev_texte(nom), identifiant, transition, cle, sha)
                if git.persistant or time.monotonic() >= git.fin:
                    if time.monotonic() >= git.fin:
                        avis.append("PRISE GIT (avis): budget Git épuisé ; fraîcheur incomplète")
                    return conclure()
    except (OSError, TimeoutError, ValueError, subprocess.SubprocessError) as exc:
        avis.append(f"PRISE GIT (avis): Git indisponible ({_rev_texte(exc)}) ; fraîcheur inconnue")
    return conclure()


def find(data: dict[str, Any], tid: str) -> dict[str, Any]:
    for task in data["tasks"]:
        if task["id"] == tid:
            return task
    raise BoardError(f"unknown task id: {tid}")


def resolve_id(data: dict[str, Any], ref: str) -> str:
    """Resolve a task REFERENCE to a stored id, tolerating short forms.

    EXACT MATCH FIRST — the same rule ``specs.py list --task`` applies, so the
    documented full form can never change meaning. Only when nothing matches
    exactly does this fall back to the reference's NUMERIC value, and that
    fallback is not a second id convention: ``numeric_id`` is already this
    module's id primitive for LEGACY ids, used for sorting, allocation and
    collision detection. So ``T-108``, ``t-108`` and ``108`` all reach whatever
    padding the store actually uses for 108.

    THE FALLBACK READS LEGACY IDS ONLY (T-00000726). A ``T-<ULID>`` has no
    numeric value — its 26 symbols may even end in digits — so it is skipped
    here and reached by its exact id alone; the number ``2`` never resolves to
    a ULID whose body happens to end in ``2``.

    Unambiguous BY CONSTRUCTION rather than by luck: ``load`` rejects any store
    where two LEGACY ids share a numeric value, so at most one task can ever
    answer to a given number.

    Deliberately READ-ONLY tolerance. The write verbs keep exact-match
    ``find``: a mistyped ``done 5`` must never silently close T-00000005.
    """
    for task in data["tasks"]:
        if task["id"] == ref:
            return task["id"]
    match = re.fullmatch(r"(?:[Tt]-)?0*(\d{1,15})", (ref or "").strip())
    if not match:
        raise BoardError(f"unknown task id: {ref}")
    wanted = int(match.group(1))
    for task in data["tasks"]:
        if is_ulid_id(task["id"]):
            continue
        if numeric_id(task["id"]) == wanted:
            return task["id"]
    raise BoardError(f"unknown task id: {ref}")


def chantier_of(task: dict[str, Any]) -> str:
    """The task's thematic group, ``""`` when it has none — the ONE place that
    decides an absent key and an empty string are the same thing. A ``chantier``
    that is stored as ``null`` by a hand-edit reads ungrouped here rather than
    crashing a list, which is the right failure for a read surface the three
    hosts' SessionStart hooks consume."""
    return task.get("chantier") or ""


def responsable_of(task: dict[str, Any]) -> str:
    """The HUMAN in charge (T-01M54GEHJBGA5996W0T48JXNQ4), ``""`` when none — same
    single shape as ``chantier_of``. ``owner`` stays the AGENT; the two never mix."""
    return task.get("responsable") or ""


# ---------------------------------------------------------------------------
# LES LIMITES PAR TÂCHE (T-01M54GEMCH3JWA95G61N2J70KS, E-48 C4, décision pilote S-01M54GFZ2VCYVA8RSJYBV6539H).
# Trois champs OPTIONNELS, absents par défaut : `echeance` (instant UTC `AAAA-MM-JJTHH:MM:SSZ`), `limite_jetons`
# (entier > 0) et `jetons` (cumul DÉCLARÉ par `tasks.py conso`, entier ≥ 0). Un lot de fournée EST une tâche :
# il porte les siens. FAIRE VOIR d'abord — une ligne `LIMITE-DEPASSEE:` ; l'ARRÊT ne mord que sous le marqueur
# `LIMITE_ARRET`, posé par le pilote, jamais semé.
#
# LECTURE TOLÉRANTE : une valeur éditée à la main hors forme ne fait jamais lever ; elle est DITE
# `LIMITE-ILLISIBLE` et ne compte ni comme dépassement ni pour l'arrêt. CANAL DE DONNÉES : seuls un id au motif
# d'id, des nombres et des instants RE-FORMATÉS s'impriment — jamais le titre, jamais une valeur brute du store.
#
# BORNES, DITES : la conso est DÉCLARÉE (l'orchestrateur recopie le `subagent_tokens` que l'hôte rend pour
# chaque sous-agent terminé — son DERNIER appel, pas sa consommation : 1× à 194× sous les jetons traités,
# médiane 39× —, mesuré sur Claude Code seul) ; un oubli rend la limite de jetons muette — ça empêche d'OUBLIER
# une fois câblé, pas de TRICHER. Le marqueur n'est pas protégé (un agent peut l'éditer) ; le jugement de
# `main` se fait hors verrou (une `conso` concurrente entre jugement et `start` passe).
# ---------------------------------------------------------------------------
LIMITE_ARRET_REL = Path(".agents") / "state" / "gates" / "LIMITE_ARRET"
LIMITE_REFUS = "dépasse sa limite et LIMITE_ARRET est armé"
# Pourquoi l'arrêt est armé : le marqueur est posé, OU son état ne se lit pas (fail-closed,
# `limite_arret_arme`) — le refus le dit pour qu'un dossier illisible ne passe pas pour une pose.
LIMITE_ARME_POURQUOI = "(marqueur posé ou illisible)"
LIMITE_REMEDE = ("remède, geste du pilote : `tasks.py limite <T> --jetons <N>[k|M]` ou `--delai <N>(m|h|j)` "
                 "pour relever, ou `tasks.py limite <T> --retirer`")
LIMITE_ECHEANCE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_LIMITE_ECHEANCE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?Z")
_LIMITE_JETONS = re.compile(r"([1-9][0-9]{0,11})([kM]?)")
_LIMITE_DELAI = re.compile(r"([1-9][0-9]{0,5})([mhj])")
_LIMITE_FACTEUR = {"": 1, "k": 1000, "M": 1000000}
_LIMITE_MINUTES = {"m": 1, "h": 60, "j": 1440}


def limite_lire_jetons(brut: str, quoi: str) -> int:
    """`<N>[k|M]` → entier > 0, sinon `BoardError` (rc 2) ; la valeur tapée n'est jamais recopiée."""
    m = _LIMITE_JETONS.fullmatch(brut or "")
    if m is None:
        raise BoardError(f"{quoi} : attendu `<N>[k|M]`, N entier de 1 à 12 chiffres sans zéro de tête "
                         "(ex. 500k, 2M, 120000) — 0, négatif ou autre suffixe refusés, board NON écrit")
    return int(m.group(1)) * _LIMITE_FACTEUR[m.group(2)]


def limite_lire_delai(brut: str, maintenant: datetime) -> datetime:
    """`--delai <N>(m|h|j)` → l'échéance ABSOLUE maintenant + N, à la seconde (le board ne
    porte aucun instant de départ fiable : `lancee_le` n'est posé que sous une trace de plan)."""
    m = _LIMITE_DELAI.fullmatch(brut or "")
    if m is None:
        raise BoardError("--delai : attendu `<N>(m|h|j)`, N entier de 1 à 6 chiffres (ex. 90m, 2h, 3j), "
                         "board NON écrit")
    return maintenant.replace(microsecond=0) + timedelta(minutes=int(m.group(1)) * _LIMITE_MINUTES[m.group(2)])


def _limite_instant(valeur: Any) -> datetime | None:
    """Un instant UTC `AAAA-MM-JJTHH:MM[:SS]Z`, ou `None` — jamais de levée."""
    if not isinstance(valeur, str) or _LIMITE_ECHEANCE.fullmatch(valeur) is None:
        return None
    forme = LIMITE_ECHEANCE_FORMAT if len(valeur) == 20 else "%Y-%m-%dT%H:%MZ"
    try:
        return datetime.strptime(valeur, forme).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def limite_lire_echeance(brut: str) -> datetime:
    """`--echeance AAAA-MM-JJTHH:MMZ` (secondes admises), UTC, sinon `BoardError` (rc 2)."""
    quand = _limite_instant(brut)
    if quand is None:
        raise BoardError("--echeance : attendu `AAAA-MM-JJTHH:MMZ` en UTC (ex. 2026-10-20T18:00Z), "
                         "board NON écrit")
    return quand


def limite_iso(quand: datetime) -> str:
    return quand.astimezone(timezone.utc).strftime(LIMITE_ECHEANCE_FORMAT)


def limite_id(task: dict[str, Any]) -> str:
    """L'id imprimable : au motif d'id, sinon un libellé fixe (jamais la chaîne relue)."""
    tid = task.get("id")
    return tid if isinstance(tid, str) and _SESSION_ID.fullmatch(tid) else "<id illisible>"


def _limite_entier(valeur: Any, plancher: int) -> int | None:
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < plancher:
        return None
    return valeur


def limite_champs(task: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """C-champs, lecture TOLÉRANTE : `({echeance, limite_jetons, jetons}, champs illisibles)`.
    Absent : `None` (`jetons` : 0) ; présent hors forme : `None` ET nommé. Jamais de levée."""
    lus: dict[str, Any] = {"echeance": None, "limite_jetons": None, "jetons": 0}
    if "echeance" in task:
        lus["echeance"] = _limite_instant(task["echeance"])
    for champ, plancher in (("limite_jetons", 1), ("jetons", 0)):
        if champ in task:
            lus[champ] = _limite_entier(task[champ], plancher)
    illisibles = [c for c in ("echeance", "limite_jetons", "jetons") if c in task and lus[c] is None]
    return lus, illisibles


def limite_arret_arme(root: str | os.PathLike[str]) -> bool:
    """Le marqueur `LIMITE_ARRET` est-il posé ? Lu par `os.lstat`, sans suivre de lien : un lien pendant ou en
    boucle compte comme POSÉ (`Path.exists()` le suivait et désarmait). Pas `os.path.lexists`, qui avale toute
    `OSError` en « absent » : ici seule l'absence PROUVÉE (le fichier ou un dossier parent manque) désarme ;
    toute autre erreur du système de fichiers compte comme ARMÉ (fail-closed : une garde dont on ne lit pas
    l'état ne se tient pas pour levée)."""
    try:
        os.lstat(Path(root) / LIMITE_ARRET_REL)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return True
    return True


def depassements(data: dict[str, Any], maintenant: datetime | None = None,
                 arme: bool = False) -> list[dict[str, Any]]:
    """C-dépassement et C-json : les tâches NON `done` au-delà de leur échéance (maintenant > `echeance`) ou de
    leur limite (`jetons` > `limite_jetons`), puis chaque valeur illisible. Une entrée : `{tache, type:
    delai|jetons|illisible, valeur, limite, etat, arret}` — délai : `valeur` = l'instant du jugement, `limite` =
    l'échéance ; jetons : les deux entiers ; illisible : `valeur` = le NOM du champ, `limite` nulle, `arret`
    faux. Jamais de levée."""
    quand = maintenant or datetime.now(timezone.utc)
    sortie: list[dict[str, Any]] = []
    for task in data.get("tasks", []):
        if not isinstance(task, dict) or task.get("state") == "done":
            continue
        lus, illisibles = limite_champs(task)
        base = {"tache": limite_id(task), "etat": task.get("state") if task.get("state") in STATES else "?"}
        if lus["echeance"] is not None and quand > lus["echeance"]:
            sortie.append({**base, "type": "delai", "valeur": limite_iso(quand),
                           "limite": limite_iso(lus["echeance"]), "arret": arme})
        if lus["limite_jetons"] is not None and lus["jetons"] is not None and lus["jetons"] > lus["limite_jetons"]:
            sortie.append({**base, "type": "jetons", "valeur": lus["jetons"],
                           "limite": lus["limite_jetons"], "arret": arme})
        sortie += [{**base, "type": "illisible", "valeur": c, "limite": None, "arret": False} for c in illisibles]
    return [{k: d[k] for k in ("tache", "type", "valeur", "limite", "etat", "arret")} for d in sortie]


def limite_jugement(root: str, verbe: str, tid: str,
                    maintenant: datetime | None = None) -> tuple[str | None, str | None]:
    """`(alerte, refus)` d'un `start`/`fournee`/`stage`/`conso` de `tid` : les lignes stderr à DIRE (rc
    inchangé), et sous `LIMITE_ARRET` le REFUS de `start` et de `fournee` (parent ou lot existant dépassé,
    C-arrêt). `main` le juge AVANT tout appel du verbe et tout drain : un refus n'écrit rien (M10). Jamais de
    levée ; id inconnu → `(None, None)`, le verbe dit sa propre faute. Un jugement qui LÈVE (board illisible…)
    ne lève jamais l'arrêt : armé, `start` et `fournee` sont refusés ; désarmé, ou pour `stage`/`conso`, une
    ligne `LIMITE-ILLISIBLE:` dit que l'alerte n'a pas été rendue — jamais un silence."""
    arme = limite_arret_arme(root)
    try:
        data = load(root)
        if not any(t.get("id") == tid for t in data["tasks"]):
            return None, None
        membres = {tid}
        if verbe == "fournee":
            membres |= {t.get("id") for t in fournee_lots_existants(data, tid).values()}
        trouves = depassements({"tasks": [t for t in data["tasks"] if t.get("id") in membres]}, maintenant, arme)
        if not trouves:
            return None, None
        alerte = "\n".join(limite_ligne(d) for d in trouves)
        franchies = sorted({d["tache"] for d in trouves if d["type"] != "illisible"})
        if arme and franchies and verbe in ("start", "fournee"):
            return alerte, (f"{', '.join(franchies)} {LIMITE_REFUS} {LIMITE_ARME_POURQUOI} — {verbe} refusé, "
                            f"board NON écrit ; {LIMITE_REMEDE}")
        return alerte, None
    except Exception:  # noqa: BLE001 — l'alerte ne casse jamais le verbe ; l'arrêt armé, lui, tient
        if arme and verbe in ("start", "fournee"):
            return None, (f"{limite_id({'id': tid})} : jugement des limites illisible et LIMITE_ARRET est armé"
                          f" {LIMITE_ARME_POURQUOI} — {verbe} refusé, board NON écrit ; la cause : "
                          "`python .agents/bin/tasks.py list`")
        return (f"LIMITE-ILLISIBLE: {limite_id({'id': tid})} jugement illisible — alerte non rendue ; "
                "la cause : `python .agents/bin/tasks.py list`"), None


# ---------------------------------------------------------------------------
# LE REGISTRE DES SESSIONS (T-01M54GEHJBGA5996W0T48JXNQ4, E-48 D2)
#
# FAIRE VOIR, JAMAIS EMPÊCHER (T-00000306) : une session Claude Code qui fait
# `start`/`fournee` laisse une MARQUE `claude-<pid>.json` sous `sessions/` ; une
# autre session qui lit le même board voit les marques VIVANTES des autres. Aucun
# horizon de temps : la vivacité est le pid, plus l'identité de démarrage contre le
# pid recyclé. Rien ici ne refuse, ne verrouille ni ne change un rc.
#
# BORNES, DITES : Claude Code seul (`CLAUDE_PID`, sinon aucune marque) ; une session
# relancée (pid neuf) ne tient plus ses tâches d'avant jusqu'à son prochain start ou
# fournée ; une marque d'un AUTRE hôte (`hote`) n'est ni jugée ni élaguée — un autre
# espace de pid ne se sonde pas d'ici ; une paire sous un `tasks.py` antérieur à D2
# n'écrit aucune marque. Le registre est un canal de DONNÉES : seuls le pid (entier),
# les ids au motif d'id, un démarrage au format fermé et un âge CALCULÉ s'impriment.
# ---------------------------------------------------------------------------
SESSIONS_REL = VIEW_REL / "sessions"
SESSION_MAX_TACHES = 50
SESSION_TETE_TACHES = 5
_SESSION_PID = re.compile(r"[1-9][0-9]*")
_SESSION_ID = re.compile(r"T-(?:[0-9]{1,15}|[0-9A-HJKMNP-TV-Z]{26})")
_SESSION_DEMARRAGE = re.compile(r"ticks:[0-9]{1,20}|[A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{1,2} [0-9:]{8} [0-9]{4}")


def session_identite() -> int | None:
    """``CLAUDE_PID`` validé ``^[1-9][0-9]*$``, sinon ``None`` (aucune marque écrite)."""
    brut = os.environ.get("CLAUDE_PID", "")
    return int(brut) if _SESSION_PID.fullmatch(brut) else None


def _session_hote() -> str:
    import socket

    try:
        return socket.gethostname()
    except OSError:
        return ""


def _session_demarrage(pid: int) -> str:
    """L'identité de DÉMARRAGE du processus, ``""`` si illisible — patron `lock_start`
    (sca-scan.sh:308-330) : Linux, champ 22 de ``/proc/<pid>/stat`` ; ailleurs
    ``ps -o lstart=`` sous ``LC_ALL=C TZ=UTC0`` (deux sessions sous deux TZ liraient
    deux dates), argv sans shell, 5 s au plus — 2 s rendaient, sous la charge d'un EDR,
    un démarrage illisible donc une alerte au pid seul (S3'' intermittent, 1 passe sur 2).
    Windows : rien (MSYS refuse ``ps -o``)."""
    import subprocess

    stat = Path("/proc") / str(pid) / "stat"
    try:
        if stat.is_file():
            champs = stat.read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].split()
            return f"ticks:{champs[19]}" if len(champs) > 19 else ""
    except (OSError, IndexError):
        return ""
    if os.name == "nt":
        return ""
    env = dict(os.environ, LC_ALL="C", TZ="UTC0")
    try:
        proc = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=5, env=env)
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    lu = " ".join((proc.stdout or "").split())
    return lu if proc.returncode == 0 and _SESSION_DEMARRAGE.fullmatch(lu) else ""


def _session_vivante_nt(pid: int) -> bool:
    """Sonde Windows, patron `pid_alive` (dashboard_registry.py:189-215) : OpenProcess, JAMAIS ``os.kill``
    (qui, sous Windows, TUE le processus visé)."""
    import ctypes

    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return False


def _session_vivante(pid: int) -> bool:
    if os.name == "nt":
        return _session_vivante_nt(pid)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, OverflowError, ValueError):
        return False
    return True


def _session_lire(chemin: Path) -> dict[str, Any] | None:
    """Une marque VALIDÉE, ou ``None`` (une ligne stderr) : jamais de levée."""
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
        pid = brut["pid"]
        nom = _SESSION_PID.fullmatch(chemin.name[len("claude-"):-len(".json")])
        if type(pid) is not int or nom is None or int(nom.group(0)) != pid:
            raise ValueError("pid")
        taches = brut.get("taches")
        if not isinstance(taches, list):
            raise ValueError("taches")
        coupees = brut.get("coupees", 0)
        return {
            "pid": pid,
            "demarrage": brut.get("demarrage") if isinstance(brut.get("demarrage"), str) else "",
            "hote": brut.get("hote") if isinstance(brut.get("hote"), str) else "",
            "maj": brut.get("maj") if isinstance(brut.get("maj"), str) else "",
            "taches": [t for t in taches if isinstance(t, str) and _SESSION_ID.fullmatch(t)],
            "coupees": coupees if type(coupees) is int and coupees > 0 else 0,
        }
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        if chemin.name not in _SESSION_SIGNALEES:  # UNE ligne par marque et par processus
            _SESSION_SIGNALEES.add(chemin.name)
            print(f"tasks.py: SESSION-PAIRE — marque illisible ignorée : {chemin.name[:40]!r}", file=sys.stderr)
        return None


_SESSION_SIGNALEES: set[str] = set()


def _session_marques(root: str) -> list[tuple[Path, dict[str, Any]]]:
    dossier = Path(root) / SESSIONS_REL
    try:
        chemins = sorted(p for p in dossier.iterdir() if p.name.startswith("claude-") and p.name.endswith(".json"))
    except OSError:
        return []
    return [(p, m) for p in chemins if (m := _session_lire(p)) is not None]


def _session_juge(marque: dict[str, Any]) -> str:
    """``vivante`` / ``morte`` / ``etrangere`` (autre hôte : jamais jugée). Vivante = pid
    vivant ET démarrage relu égal à l'inscrit quand les DEUX sont lisibles."""
    if marque["hote"] and marque["hote"] != _session_hote():
        return "etrangere"
    if not _session_vivante(marque["pid"]):
        return "morte"
    inscrit = marque["demarrage"]
    relu = _session_demarrage(marque["pid"]) if inscrit else ""
    return "morte" if inscrit and relu and relu != inscrit else "vivante"


def sessions_paires(root: str) -> list[dict[str, Any]]:
    """Les marques VIVANTES d'AUTRES sessions, plus récentes d'abord. Jamais de levée."""
    try:
        soi = session_identite()
        vues = [m for _p, m in _session_marques(root) if m["pid"] != soi]
        vivantes = [m for m in vues if _session_juge(m) == "vivante"]
        return sorted(vivantes, key=lambda m: m["maj"], reverse=True)
    except Exception as exc:  # noqa: BLE001 — canal d'alerte : jamais un verbe cassé par lui
        print(f"tasks.py: SESSION-PAIRE — registre illisible ({type(exc).__name__})", file=sys.stderr)
        return []


def marquer_session(root: str, ids: list[str], fournee_de: str | None = None) -> None:
    """Inscrit ``ids`` (et, sous ``fournee_de``, les lots de ce parent) à la marque de
    CETTE session (union, plus récentes d'abord, seules les tâches encore ``running``,
    coupe à ``SESSION_MAX_TACHES`` COMPTÉE), puis élague les marques MORTES de ce même
    hôte. Écriture tmp + ``os.replace``. Jamais de levée."""
    pid = session_identite()
    if pid is None:
        return
    try:
        dossier = Path(root) / SESSIONS_REL
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"claude-{pid}.json"
        demarrage = _session_demarrage(pid)
        ancienne = _session_lire(chemin) if chemin.exists() else None
        if ancienne and ancienne["demarrage"] and demarrage and ancienne["demarrage"] != demarrage:
            ancienne = None  # le pid d'une session morte, recyclé : rien n'en est hérité
        tenues = ancienne["taches"] if ancienne else []
        data = load(root)
        neuves = list(ids) + ([t["id"] for t in fournee_lots_existants(data, fournee_de).values()] if fournee_de else [])
        en_vol = {t["id"] for t in running_tasks(data["tasks"])}
        union = [i for i in dict.fromkeys(neuves + tenues) if i in en_vol]
        coupe = union[SESSION_MAX_TACHES:]
        marque = {
            "pid": pid, "demarrage": demarrage, "hote": _session_hote(), "racine": str(Path(root).resolve()),
            "maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "taches": union[:SESSION_MAX_TACHES], "coupees": (ancienne["coupees"] if ancienne else 0) + len(coupe),
        }
        tmp = dossier / f".claude-{pid}.{uuid.uuid4().hex}.tmp"
        tmp.write_text(json.dumps(marque, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, chemin)
        for autre, m in _session_marques(root):
            if m["pid"] != pid and _session_juge(m) == "morte":
                autre.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 — l'alerte ne casse jamais le verbe qu'elle accompagne
        print(f"tasks.py: SESSION-PAIRE — marque de session non écrite ({type(exc).__name__})", file=sys.stderr)


def session_age(maj: str, maintenant: datetime | None = None) -> str:
    """L'âge CALCULÉ d'une marque (jamais la chaîne relue) : « il y a 13 h »."""
    try:
        quand = datetime.strptime(maj, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "âge inconnu"
    secondes = max(0, int(((maintenant or datetime.now(timezone.utc)) - quand).total_seconds()))
    if secondes < 3600:
        return f"il y a {secondes // 60} min"
    return f"il y a {secondes // 3600} h" if secondes < 172800 else f"il y a {secondes // 86400} j"


def session_lancee(marque: dict[str, Any]) -> str:
    d = marque["demarrage"]
    return d if _SESSION_DEMARRAGE.fullmatch(d) else "démarrage illisible, alerte au pid seul"


SESSION_REMEDE = ("  remède : clore ou bloquer d'abord, ou déclarer le groupe avec l'autre session ; "
                  "un worktree n'isole que s'il écrit SON board (--root)")
SESSION_BORNE = ("  borne : registre tenu depuis le lancement de chaque session : relancée (pid neuf), elle ne "
                 "tient plus ses tâches d'avant jusqu'à son prochain start ou fournée")


def alerte_session_paire(root: str, verbe: str, tid: str) -> str | None:
    """Les lignes ``SESSION-PAIRE:`` qu'un ``start``/``fournee`` de ``tid`` doit DIRE, ou
    ``None``. Redérive les deux règles sans les factoriser : ``start`` ne rétrograde plus
    personne, il PREND le focus du clone (``poser_focus``, une session active par clone) ;
    la fournée PRÉSERVE les running hors du parent et de ses lots (lot B de
    T-01M5DBFPWCXH54VW0VMN8HWRX7 : ni groupées ni rétrogradées) et prend, elle aussi, le
    focus. Jamais de levée."""
    try:
        paires = sessions_paires(root)
        if not paires:
            return None
        data = load(root)
        cible = next((t for t in data["tasks"] if t["id"] == tid), None)
        if cible is None:
            return None
        en_vol = {t["id"]: t for t in running_tasks(data["tasks"])}
        if verbe == "fournee":
            membres = {tid} | {t["id"] for t in fournee_lots_existants(data, tid).values()}
            touche = lambda t: t["id"] not in membres  # noqa: E731
            suffixe = ("— cette fournée la PRÉSERVE (ni groupée ni rétrogradée) mais lui PREND le focus du "
                       "clone ; elle ne refuse qu'un recouvrement de write-set")
        else:
            touche = lambda t: t["id"] != tid  # noqa: E731
            suffixe = ("— ce start ne la rétrograde pas, mais lui PREND le focus du clone (une session "
                       "active par clone)")
        lignes: list[str] = []
        for m in paires:
            for i in m["taches"]:
                if i in en_vol and touche(en_vol[i]):
                    lignes.append(f"SESSION-PAIRE: {i} tenue par la session pid {m['pid']} "
                                  f"(lancée {session_lancee(m)}) {suffixe}")
            if m["coupees"] and lignes:
                lignes.append(f"  registre de la session pid {m['pid']} coupé à {SESSION_MAX_TACHES} : "
                              f"{m['coupees']} tâche(s) plus ancienne(s) non vue(s)")
        return "\n".join(lignes + [SESSION_REMEDE, SESSION_BORNE]) if lignes else None
    except Exception:  # noqa: BLE001 — l'alerte ne casse jamais le verbe qu'elle accompagne
        return None


# ---------------------------------------------------------------------------
# WRITESETS AND PARALLEL GROUPS (T-00000188)
#
# A COHERENCE GUARD, NOT A SECURITY ONE. Everything below proves that the file
# sets tasks DECLARE are disjoint; nothing here observes what an agent actually
# writes. That is the pilot's decision (L-00000173, hybrid approach), and it is
# written down rather than masked: no observation of the actual writes exists. A
# group these functions admit is exactly as safe as its declarations are
# faithful.
#
# THE PROOF IS TEXTUAL. Symbolic links, Windows junctions, 8.3 short aliases,
# HARD LINKS and real targets are out of its reach: two strings this module
# calls disjoint can name one file through any of them. The fail rule is the
# strict one — an impossible proof COUNTS AS AN OVERLAP, and the refusal leaves
# the tasks to be serialised.
#
# THE DISCIPLINE THIS COST SIX CRITIC ROUNDS, in one line: a REFUSAL clause is
# safe by MONOTONY — it shrinks the admitted set and can never add to it — while
# a TRANSFORMATION (the `\` fold, the trailing `/` removal, the canonicalisation)
# REMAPS THE DOMAIN and obliges you to replay the degenerate cases (empty
# string, bare `/`, one segment, one character). The round-5 regression was born
# of a transformation introduced at round 4, not of a forgotten case. Whoever
# touches the predicate below inherits that rule.
# ---------------------------------------------------------------------------

# CLOSED list, casefolded. Windows resolves these names in EVERY directory, so a
# declared `src/con` names a device rather than the file the pilot means. The
# superscript forms are here because `casefold()` does NOT fold `¹²³` down to
# digits while Win32 does. Over-refusal is ASSUMED (a `src/aux.md` would be
# legitimate under Linux) and was MEASURED NULL on this repository.
#
# THE LIST IS SYMMETRIC, and it was not (T-00000188 review, MEDIUM d): the
# comment above justifies the superscripts by a property of `casefold()` that
# holds for `lpt\u00b9` exactly as for `com\u00b9`, then the list carried them for `com`
# only \u2014 so `src/com\u00b9` was refused and `src/lpt\u00b9` admitted, on one and the same
# argument. A closed list that contradicts its own stated reason is not closed.
# The reviewer could NOT reproduce Win32 device resolution on this machine, so
# this is corrected as an incoherence of the list, never as a demonstrated alias.
_WIN32_DEVICE_NAMES = frozenset(
    ["con", "nul", "prn", "aux"]
    + [f"com{d}" for d in "123456789"]
    + [f"lpt{d}" for d in "123456789"]
    + [f"com{d}" for d in "\u00b9\u00b2\u00b3"]
    + [f"lpt{d}" for d in "\u00b9\u00b2\u00b3"]
)

# What a refusal SHOWS instead of only naming what it rejects.
WRITESET_CANONICAL_EXAMPLE = "src/auth/ · docs/tasks/T-00000188.md"

# The closed vocabulary of clauses, in EVALUATION ORDER. A refusal always names
# one of these, and a test pins the pairing case → clause: a guard that blocks
# without naming its clause blocks its own diagnosis.
WRITESET_CLAUSES = (
    "at-least-one-segment",
    "non-empty-segment",
    "no-dot-segment",
    "no-trailing-dot-or-space",
    "no-colon",
    "no-win32-device-name",
)


def fold_writeset_path(raw: str) -> str:
    """TRANSFORMATION 1 — `\\` becomes `/`. Replay the degenerate cases."""
    return (raw or "").replace("\\", "/")


def split_writeset_path(folded: str) -> tuple[list[str], bool]:
    """TRANSFORMATION 2 — remove AT MOST ONE trailing `/`, then cut on `/`.

    Returns ``(segments, trailing_slash)``. THE EMPTY REMAINDER GIVES ZERO
    SEGMENTS, deliberately: ``"".split("/")`` is ``[""]`` in Python, so a naive
    split would hand the caller a phantom segment and make ``""`` and a bare
    ``/`` fail by the wrong clause — or, worse, make "each segment is valid"
    VACUOUSLY true. Vacuity is never a proof here.
    """
    trailing = folded.endswith("/")
    body = folded[:-1] if trailing else folded
    return (body.split("/") if body else []), trailing


def _writeset_refusal(raw: str, clause: str, why: str, segment: str | None = None) -> str:
    where = "" if segment is None else f" (segment {segment!r})"
    return (
        f"{raw!r} is not an admissible writeset path{where} — failed clause "
        f"{clause}: {why}. Canonical form: {WRITESET_CANONICAL_EXAMPLE}"
    )


def writeset_path_refusal(raw: str) -> str | None:
    """``None`` when the path is ADMITTED, else the DIAGNOSTIC line.

    THE PREDICATE IS POSITIVE AND CLOSED, PER SEGMENT. After the two
    transformations above, a path is admitted IF AND ONLY IF it is the `/` join
    of AT LEAST ONE segment, each of which is non-empty, is neither `.` nor
    `..`, ends with neither a dot nor a space, contains no `:` and is not a
    Win32 device name. Anything unforeseen therefore falls on the REFUSAL side
    by the predicate itself — that is what "closed" buys, and turning this into
    a list of cases to reject is the mistake that cost five critic rounds.

    Every documented property DERIVES from a clause, and each derivation names
    the clause that actually fails it — no derivation is asserted:

    ==================== ================ ============================
    property             case             clause that refuses it
    ==================== ================ ============================
    relative only        ``/src/a``       non-empty-segment (head)
    no UNC               ``\\\\srv\\share``  non-empty-segment (fold first)
    no drive letter      ``C:\\repo\\src``  no-colon
    no double separator  ``src//a``       non-empty-segment
    one trailing `/`     ``docs//``       non-empty-segment (one removed)
    neither root nor ""  ``/`` and ``""`` at-least-one-segment
    ==================== ================ ============================
    """
    folded = fold_writeset_path(raw)
    segments, _ = split_writeset_path(folded)
    if not segments:
        return _writeset_refusal(
            raw,
            "at-least-one-segment",
            "a writeset path is the join of at least one segment; the empty "
            "string and a bare '/' carry none, and an empty set proves nothing",
        )
    for segment in segments:
        if not segment:
            return _writeset_refusal(
                raw,
                "non-empty-segment",
                "every segment must carry a name; an absolute path, a UNC share "
                "and a doubled separator all produce an empty one",
                segment,
            )
        if segment in (".", ".."):
            return _writeset_refusal(
                raw,
                "no-dot-segment",
                "'.' and '..' name a directory by traversal, so two different "
                "strings could designate one file",
                segment,
            )
        if segment.endswith(".") or segment.endswith(" "):
            return _writeset_refusal(
                raw,
                "no-trailing-dot-or-space",
                "Windows silently strips a trailing dot or space, so the name "
                "stored is not the name opened",
                segment,
            )
        if ":" in segment:
            return _writeset_refusal(
                raw,
                "no-colon",
                "a ':' introduces a drive letter or an NTFS alternate data "
                "stream, neither of which is the file it looks like",
                segment,
            )
        # The base is taken before the FIRST dot (so `con.txt` is caught), and
        # its trailing spaces and dots are stripped: Win32 discards them, so
        # `con .txt` reaches the same device as `con.txt` while differing by one
        # byte — admitted before this strip (T-00000188 review, MEDIUM d). The
        # trailing-dot-or-space clause above only sees the END of the segment,
        # which `con .txt` does not trip.
        if segment.casefold().split(".", 1)[0].rstrip(" .") in _WIN32_DEVICE_NAMES:
            return _writeset_refusal(
                raw,
                "no-win32-device-name",
                "Win32 resolves this reserved device name in every directory, "
                "extension included, instead of opening a file",
                segment,
            )
    return None


def admitted_writeset_path(raw: str) -> str:
    """The ADMITTED path — the folded form — or ``BoardError`` with the
    diagnostic. Refusal happens AT THE DECLARATION, where the pilot can still
    fix the string, never later at a read surface."""
    refusal = writeset_path_refusal(raw)
    if refusal is not None:
        raise BoardError(refusal)
    return fold_writeset_path(raw)


def canonical_writeset_segment(segment: str) -> str:
    """``NFC ∘ casefold ∘ NFC`` — re-normalised AFTER the fold, because
    ``casefold()`` can de-normalise its own output."""
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFC", segment).casefold()
    )


def canonical_writeset_path(path: str) -> str:
    """The COMPARISON form of a path: its canonical segments joined by `/`,
    with no trailing separator. TRANSFORMATION 3.

    DEFINED ON ADMITTED PATHS, and the precondition is load-bearing rather than
    decorative. On that domain — plus the degenerate inputs ``""`` and ``/`` —
    the function is IDEMPOTENT, and that is PINNED BY TEST rather than asserted
    here. Outside it, it is not: ``docs//`` canonicalises to ``docs/`` and then
    to ``docs``, because dropping ONE trailing separator does not idempotently
    absorb two. That is the C21 discipline in the flesh — a REFUSAL clause is
    safe by monotony, a TRANSFORMATION remaps the domain — and the answer is not
    to widen the transformation but to admit first: every caller here compares
    only paths ``writeset_path_refusal`` has already accepted.

    It never claims two equal canonical forms name one file: that is precisely
    what a textual proof cannot say, and demanding it would turn this guard into
    an oracle of the filesystem."""
    segments, _ = split_writeset_path(fold_writeset_path(path))
    return "/".join(canonical_writeset_segment(s) for s in segments)


def writeset_of(task: dict[str, Any]) -> list[str]:
    """The task's declared writeset, ``[]`` when it has none — the ONE place
    that decides an absent key, a null and an empty list are the same thing."""
    declared = task.get("writeset")
    return [p for p in declared if isinstance(p, str)] if isinstance(declared, list) else []


def parallel_group_of(task: dict[str, Any]) -> str:
    """The task's declared parallel group, ``""`` when it has none."""
    group = task.get("parallel_group")
    return group if isinstance(group, str) else ""


def depends_on_of(task: dict[str, Any]) -> list[str]:
    """The task's declared dependencies, ``[]`` when it has none — the ONE place
    that decides an absent key, a null and an empty list are the same thing."""
    declared = task.get("depends_on")
    return [d for d in declared if isinstance(d, str) and d] if isinstance(declared, list) else []


def _depends_adjacency(
    tasks: list[dict[str, Any]], overrides: dict[str, list[str]] | None = None
) -> dict[str, list[str]]:
    """``{task id: its dependencies}`` over the whole board, with ``overrides``
    substituted for the stored value — so a WOULD-BE write can be tested against
    the graph it would produce, before a byte is written."""
    graph = {task["id"]: depends_on_of(task) for task in tasks}
    for tid, deps in (overrides or {}).items():
        graph[tid] = list(deps)
    return graph


def depends_path_between(
    graph: dict[str, list[str]], start: str, target: str
) -> list[str] | None:
    """The dependency chain ``[start, …, target]`` if ``start`` reaches ``target``
    by following ``depends_on``, else ``None``.

    TRANSITIVE ON PURPOSE. A direct-edge check alone would be vacuously true on
    ``a -> x -> b`` and would let ``parallel`` group two tasks that are one behind
    the other through a third — the very emptiness the rest of that function
    refuses. Iterative rather than recursive: a hand-edited store may carry a
    cycle (``load`` accepts one by design), and the ``seen`` set is what makes
    this terminate on it instead of blowing the stack."""
    seen = {start}
    stack = [(start, [start])]
    while stack:
        node, path = stack.pop()
        for dep in graph.get(node, []):
            if dep == target:
                return path + [dep]
            if dep not in seen:
                seen.add(dep)
                stack.append((dep, path + [dep]))
    return None


def dependency_cycle(
    graph: dict[str, list[str]], tid: str, wanted: list[str]
) -> list[str] | None:
    """The cycle ``[tid, …, tid]`` that declaring ``wanted`` for ``tid`` would
    close, or ``None``. Names the WHOLE path: a refusal that says only "cycle"
    leaves the pilot to find which of five edges to drop."""
    probe = dict(graph)
    probe[tid] = list(wanted)
    for dep in wanted:
        back = depends_path_between(probe, dep, tid)
        if back is not None:
            return [tid] + back
    return None


def writeset_paths_overlap(left: list[str], right: list[str]) -> tuple[str, str] | None:
    """The FIRST overlapping pair, or ``None``.

    PREFIX TEST AT A SEGMENT BOUNDARY, on canonical segment lists — which is
    what makes ``src/a`` and ``src/ab`` disjoint while ``src/a/`` covers
    ``src/a/b.py``. A string-level prefix test would fuse the first pair.

    AN INADMISSIBLE STORED PATH COUNTS AS AN OVERLAP, and that is the module's
    own fail rule finally APPLIED here rather than merely declared (T-00000188
    review, MEDIUM a). Admission happens at the declaration, but this function
    reads what the STORE holds, and a store can carry a path no declaration
    produced — hand-edited, or written before this guard existed. Such a path is
    exactly the case where the proof is IMPOSSIBLE: ``docs//`` canonicalises to
    segments ``['docs', '']``, which compares unequal to ``docs`` and would
    report a disjunction that does not hold. "An impossible proof VALUES AS AN
    OVERLAP" — so it refuses instead of reassuring."""
    for one in left:
        one_inadmissible = writeset_path_refusal(one) is not None
        one_segments = canonical_writeset_path(one).split("/")
        for other in right:
            if one_inadmissible or writeset_path_refusal(other) is not None:
                return one, other
            other_segments = canonical_writeset_path(other).split("/")
            shortest = min(len(one_segments), len(other_segments))
            if one_segments[:shortest] == other_segments[:shortest]:
                return one, other
    return None


def running_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every ``running`` task, IN STORE ORDER — which is creation order."""
    return [
        t for t in tasks if isinstance(t, dict) and t.get("state") == "running"
    ]


# PLUSIEURS `running` SONT LÉGITIMES (T-01M5F7286N1EYGXAXA5244X86B, S-01M5DBTHMEAEXGD93Q284GJPJE) :
# `running_group_refusal` (T-00000188), qui refusait au `load` ET au `save` tout ensemble de running
# hors d'UN groupe déclaré, est RETIRÉ avec la rétrogradation du `start`. Le groupe reste la preuve
# de disjonction de `parallel` ; il ne conditionne plus la lecture du board.


def focus_task(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """THE FOCUS TASK: the FIRST running task in store order, i.e. the oldest of
    a parallel group. ONE rule, shared by the statusline and by the peer summary
    (`dashboard.build_peer_summary`), so the two surfaces can never name a
    different task — and pinned by test so a future sort cannot move the focus
    in silence. A DISPLAY rule over the board alone: the clone's focus that
    ``tasks.py focus`` writes (``lire_focus``) is another fact, read elsewhere."""
    running = running_tasks(tasks)
    return running[0] if running else None


# ---------------------------------------------------------------------------
# LE FOCUS DU CLONE ET LA PORTÉE DE REVUE (T-01M5F7286N1EYGXAXA5244X86B, lot A ;
# S-01M5E50AJX9V9AP8A8VBBHS6B4, S-01M5E50ABADJA72966YQF4J285). Deux JSON LOCAUX (git-ignorés,
# `.agents/state/local/`) du dépôt PRINCIPAL : `focus.json` = {task_id, updated_at}, écrit par
# `start`, `fournee` (sur le parent) et `focus` ; `review-scope.json` = {focus, members,
# consumed, declared_at}, écrit par `review-scope`, dont un `done` réussi consomme le membre.
# Une session active par clone : un seul focus par dépôt principal, worktrees compris.
# ---------------------------------------------------------------------------
FOCUS_NOM = "focus.json"
PORTEE_NOM = "review-scope.json"


def racine_principale(root: str | os.PathLike[str]) -> Path:
    """La racine du dépôt PRINCIPAL dont ``root`` est un worktree, LUE SUR LE DISQUE, sans git :
    ``<root>/.git`` FICHIER (``gitdir: …``) → son ``commondir`` → le parent du ``.git`` commun.
    ``.git`` dossier, absent (hors Git, ``--root`` jetable), illisible, ou sans ``commondir``
    (sous-module) : ``root`` lui-même — une racine jetable ne vise JAMAIS le vrai dépôt. Aucun
    sous-processus : lisible sous le verrou du board.

    UN POINTEUR FORGÉ NE DÉTOURNE RIEN (revue de sécurité, advisory) : la forme d'un VRAI
    worktree est exigée — ``gitdir`` est un dossier DIRECT de ``<commun>/worktrees/``, et son
    lien retour ``<gitdir>/gitdir`` désigne ``<root>/.git`` ; sinon ``root`` lui-même. Un
    ``.git`` LIEN SYMBOLIQUE n'est jamais suivi : ``root`` lui-même."""
    base = Path(normalize_root(root))
    point_git = base / ".git"
    try:
        if point_git.is_symlink() or not point_git.is_file():
            return base
        ligne = point_git.read_text(encoding="utf-8").strip()
        if not ligne.startswith("gitdir:"):
            return base
        gitdir = Path(ligne[len("gitdir:"):].strip())
        gitdir = (gitdir if gitdir.is_absolute() else base / gitdir).resolve()
        commun = Path((gitdir / "commondir").read_text(encoding="utf-8").strip())
        commun = (commun if commun.is_absolute() else gitdir / commun).resolve()
        retour = Path((gitdir / "gitdir").read_text(encoding="utf-8").strip())
        retour = (retour if retour.is_absolute() else gitdir / retour).resolve()
    except (OSError, UnicodeDecodeError, ValueError):
        return base
    vrai_worktree = gitdir.parent == commun / "worktrees" and retour == point_git.resolve()
    return commun.parent if vrai_worktree and commun.name == ".git" and commun.parent.is_dir() else base


PORTEE_VERROU = "REVIEW_SCOPE.lock"


def verrou_portee(root: str | os.PathLike[str]) -> Any:
    """Le verrou de ``review-scope.json``, au dépôt PRINCIPAL (worktrees compris) : distinct de
    celui du board, pris APRÈS lui par ``declarer_portee``, seul par ``consommer_portee``."""
    return board_lock(racine_principale(root), name=PORTEE_VERROU)


def chemin_focus(root: str | os.PathLike[str]) -> Path:
    return racine_principale(root) / VIEW_REL / FOCUS_NOM


def chemin_portee(root: str | os.PathLike[str]) -> Path:
    return racine_principale(root) / VIEW_REL / PORTEE_NOM


def _lire_json_local(chemin: Path, cles: dict[str, type]) -> dict[str, Any] | None:
    """``None`` si le fichier est ABSENT ; sinon le dict, ou ``BoardError`` s'il est illisible ou
    hors forme (chaque clé de ``cles`` présente, du type dit) — jamais une forme devinée."""
    try:
        brut = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise BoardError(f"{chemin.name} illisible ({type(exc).__name__}) — réécris-le par son verbe") from None
    try:
        data = json.loads(brut)
    except ValueError:
        data = None
    if not isinstance(data, dict) or any(not isinstance(data.get(k), t) for k, t in cles.items()):
        raise BoardError(f"{chemin.name} hors forme (attendu les clés {', '.join(cles)}) — réécris-le par son verbe")
    return data


def lire_focus(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    return _lire_json_local(chemin_focus(root), {"task_id": str, "updated_at": str})


def lire_portee(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    portee = _lire_json_local(chemin_portee(root), {"focus": str, "members": list, "consumed": list,
                                                    "declared_at": str})
    if portee is not None and not all(isinstance(i, str) for i in portee["members"] + portee["consumed"]):
        raise BoardError(f"{PORTEE_NOM} hors forme (members et consumed : des identifiants) — réécris-le par son verbe")
    return portee


def ecrire_json_local(chemin: Path, contenu: dict[str, Any]) -> None:
    """Écriture ATOMIQUE : un temporaire du même dossier, puis ``os.replace`` (``_replace_with_retry``).
    UN DOSSIER LIEN N'EST JAMAIS SUIVI (revue de sécurité, advisory) : ``.agents``, ``state`` ou
    ``local`` lien symbolique ⇒ ``BoardError``, rien n'est écrit hors de la racine. Le même
    contrôle tient ``board_lock`` (``.lock`` compris) ; la vue ``TASKS.md`` ne le refait pas :
    une sauvegarde l'écrit sous ce verrou, qui refuse d'abord, mais ``tasks.py render`` (hors
    verrou) traverse ENCORE le lien — borne dite."""
    for dossier in (chemin.parent, chemin.parent.parent, chemin.parent.parent.parent):
        if dossier.is_symlink():
            raise BoardError(f"{chemin.name} non écrit : {dossier} est un lien symbolique, jamais suivi")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{chemin.name}.", suffix=".tmp", dir=str(chemin.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fichier:
            fichier.write(json.dumps(contenu, ensure_ascii=False, indent=2) + "\n")
        _replace_with_retry(tmp, chemin)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def poser_focus(root: str | os.PathLike[str], tid: str) -> None:
    ecrire_json_local(chemin_focus(root), {"task_id": tid, "updated_at": horodatage_done()})


def consommer_portee(root: str | os.PathLike[str], tid: str) -> str | None:
    """Un ``done`` RÉUSSI consomme son membre : ``tid`` ajouté à ``consumed`` s'il est membre et
    pas encore consommé. Rend la ligne à DIRE, ou ``None`` (aucune portée, ou ``tid`` hors d'elle).
    Lecture ET réécriture sous ``verrou_portee``, le verrou que ``declarer_portee`` tient aussi :
    un ``done`` concurrent d'une déclaration ne réécrit jamais l'ancienne."""
    with verrou_portee(root):
        portee = lire_portee(root)
        if portee is None or tid not in portee["members"] or tid in portee["consumed"]:
            return None
        portee["consumed"] = portee["consumed"] + [tid]
        ecrire_json_local(chemin_portee(root), portee)
    return (f"TASKS: review-scope — {tid} consommé ({len(portee['consumed'])}/{len(portee['members'])}, "
            f"focus {portee['focus']})")


def filter_label(
    task: str | None = None,
    state: str | None = None,
    chantier: str | None = None,
    blocked_by: str | None = None,
    depends_on: str | None = None,
    responsable: str | None = None,
) -> str:
    """The filter, echoed back in the words the caller used — so an empty
    result names WHAT was asked, not just that nothing came back."""
    parts = []
    if responsable is not None:
        parts.append(f"responsable={responsable or '(sans responsable)'}")
    if task is not None:
        parts.append(f"task={task}")
    if state is not None:
        parts.append(f"state={state}")
    if chantier is not None:
        # An empty value is a REAL filter ("the ungrouped tasks"), so it must
        # echo as something a reader can read; `chantier=` alone looks truncated.
        parts.append(f"chantier={chantier or NO_CHANTIER}")
    if blocked_by is not None:
        # ``filter_tasks`` refuses an empty or unknown ``blocked_by`` before the
        # label is ever built, so this only ever echoes a resolvable reference.
        parts.append(f"blocked-by={blocked_by}")
    if depends_on is not None:
        parts.append(f"depends-on={depends_on}")
    return ", ".join(parts)


def filter_tasks(
    data: dict[str, Any],
    task: str | None = None,
    state: str | None = None,
    chantier: str | None = None,
    blocked_by: str | None = None,
    depends_on: str | None = None,
    responsable: str | None = None,
) -> list[dict[str, Any]]:
    """The board narrowed by the CLI filters, combinable, in board order.

    ``responsable`` (T-01M54GEHJBGA5996W0T48JXNQ4) follows ``chantier`` exactly:
    free text, ``None`` = no filter, ``""`` = the tasks with no human in charge.

    ``state`` is the CLOSED vocabulary, enforced here as well as by argparse:
    an unknown value is a loud usage error, never a quietly empty result that
    reads as "no such task".

    ``chantier`` is the opposite — FREE TEXT, so there is nothing to close and
    an unknown group legitimately matches nothing. ``None`` means "no filter",
    ``""`` means "the tasks that carry no chantier": the two are distinct, which
    is why the default is not ``""``, and ``--chantier ""`` is the read that
    answers ``regroup <tid> ""``'s write.

    ``blocked_by`` answers the INVERSE of a ``blocked_on`` link (T-00000185):
    the tasks whose ``blocked_on`` points at the given task. Unlike ``chantier``
    it CLOSES its input — a reference to a task that must exist. ``None`` means
    "no filter"; anything else is resolved through ``resolve_id`` (short forms
    ``T-14`` / ``14`` accepted), so an UNKNOWN id is a loud refusal here rather
    than an empty result that would read as "nobody waits on it". ``""`` has no
    meaning here (no task waits on "nothing"), so it is refused explicitly rather
    than smuggled into ``resolve_id``'s generic "unknown id". A blocker that is
    ``done`` legitimately matches nothing: its links were purged when it closed,
    so the empty result is an announced absence, not a refusal.

    ``depends_on`` is the SAME inverse read on the PERSISTENT axis (T-00000530):
    the tasks whose ``depends_on`` names the given task — "who is behind this
    one?". Strict parity with ``blocked_by``: closed input, short forms accepted,
    unknown id refused loudly, ``""`` refused. ONE semantic difference, and it is
    the point of the field: a ``done`` task legitimately matches SEVERAL here,
    because ``depends_on`` edges SURVIVE closure where ``blocked_on`` links are
    purged at it. That is the morning-retrospective read — "what was behind this,
    and did the night respect it?" — and it exists only because ``done`` erases
    nothing.

    THE DONE CAP IS NOT APPLIED. ``MAX_DONE_SHOWN`` is a digest bound for the
    whole board; handing back 3 of 20 ``done`` rows to someone who explicitly
    asked ``--state done`` would be exactly the silent truncation this kit
    forbids. Callers print the match count instead, so nothing is hidden.
    """
    if state is not None and state not in STATES:
        raise BoardError(f"unknown state {state!r}; expected one of {', '.join(STATES)}")
    if blocked_by == "":
        raise BoardError(
            '--blocked-by needs a task id; "" is not a filter here — unlike '
            "--chantier, an empty value has no meaning (no task waits on nothing)"
        )
    if depends_on == "":
        raise BoardError(
            '--depends-on needs a task id; "" is not a filter here — unlike '
            "--chantier, an empty value has no meaning (no task depends on nothing)"
        )
    tasks = data["tasks"]
    if task is not None:
        tid = resolve_id(data, task)
        tasks = [t for t in tasks if t["id"] == tid]
    if state is not None:
        tasks = [t for t in tasks if t["state"] == state]
    if chantier is not None:
        tasks = [t for t in tasks if chantier_of(t) == chantier]
    if responsable is not None:
        tasks = [t for t in tasks if responsable_of(t) == responsable]
    if blocked_by is not None:
        blocker_id = resolve_id(data, blocked_by)
        tasks = [t for t in tasks if t.get("blocked_on") == blocker_id]
    if depends_on is not None:
        target_id = resolve_id(data, depends_on)
        tasks = [t for t in tasks if target_id in depends_on_of(t)]
    return sorted_tasks(tasks, cap_done=False)
