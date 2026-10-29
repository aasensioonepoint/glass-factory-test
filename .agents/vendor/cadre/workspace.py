"""LES ENTRÉES-SORTIES DE FICHIER PROJET. Phase 1 de T-012.

`paths` RÉSOUT, `Workspace` FAIT LES E/S, jamais l'inverse. Cette frontière est
une couture d'évolution nommée par le plan (§5-A) : le jour où les tâches
déterministes tourneront ailleurs que sur le poste, c'est cette classe qu'on
remplace, et la logique qui l'appelle n'a pas à savoir où le fichier vit.

CE QU'ELLE APPORTE QU'UN `open()` NU N'A PAS
--------------------------------------------
**Le confinement.** Chaque chemin est résolu SOUS la racine et refusé s'il en
sort. Un `..` de trop, un lien symbolique qui remonte, un chemin absolu qui tombe
HORS de la racine : les trois sont des refus nommés plutôt que des écritures hors
du projet. Un chemin absolu qui tombe SOUS la racine est accepté — `pathlib`
laisse l'opérande droit absolu effacer le gauche, et la garde porte sur le
résultat résolu, pas sur la forme écrite. Ce n'est pas une garde de sécurité — un
agent qui veut sortir a d'autres moyens — c'est une garde de COHÉRENCE, du même
genre que la disjonction des write-sets : elle attrape l'erreur, pas la
malveillance, et elle le dit. **Les quatorze méthodes publiques l'appliquent** —
`resolve` EST la garde, les treize autres passent par elle —, y compris
`iter_files`, qui globait sans passer par elle. `walk` confine sa DESCENTE, pas
les noms qu'il rend (borne écrite dans sa docstring). `identite`,
`creer_fichier_exclusif` (T-00000759) et `ecrire_fichier_exclusif`
(T-00000969) résolvent le PARENT et laissent la FEUILLE non suivie : c'est la
feuille qu'elles jugent, lien compris. `remplacer_avec_reprise` est une
primitive SANS racine (deux chemins déjà résolus par l'appelant) : elle vit
ici parce que ce module est celui qui touche le disque, pas parce qu'elle
confine.

**L'écriture atomique, ET CONTRE QUOI.** `write_text` passe par un temporaire du
même répertoire puis `os.replace`. Trois propriétés, chacune obtenue par un geste
distinct, parce que la première rédaction n'en tenait qu'une : un **crash** en
cours laisse l'ancien contenu intact plutôt qu'un fichier tronqué (`os.replace`) ;
une **coupure d'alimentation** ne laisse pas une cible renommée et vide
(`os.fsync` avant le renommage) ; un **écrivain concurrent** sur la même cible ne
supprime pas le temporaire en vol du premier (`mkstemp`, nom unique). Le mode du
fichier d'origine est reporté, sans quoi un hook exécutable réécrit ressortait en
0644. La revue de clôture de la Phase 0bis a relevé le premier défaut ailleurs
dans le kit, où une écriture interrompue laissait un marqueur de porte vide, donc
une garde qui passait en silence.

**Les octets, pas les lignes.** Le kit est développé sous Windows et vérifié
sous Linux ; `Path.write_text` traduit les fins de ligne et réécrit un fichier
entier au premier aller-retour. Tout passe donc par `read_bytes`/`write_bytes`,
avec l'encodage explicite au-dessus.
"""

from __future__ import annotations

import errno
import os
import stat
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Workspace", "HorsRacine", "Identite", "remplacer_avec_reprise",
           "REMPLACER_TENTATIVES", "REMPLACER_DELAI_S"]

#: Reprise bornée d'`os.replace` (L-00000054) : sous Windows, un lecteur
#: concurrent qui tient la cible ouverte fait lever `PermissionError`
#: (WinError 5), source pourtant fermée. Mêmes valeurs que les copies du kit,
#: 30 × 10 ms (`test_replace_parity.py`). LUES À CHAQUE APPEL par
#: `remplacer_avec_reprise`, jamais figées en défaut d'argument : un banc qui
#: les mute ICI est entendu (T-00000969, réserve C5).
REMPLACER_TENTATIVES = 30
REMPLACER_DELAI_S = 0.01


def remplacer_avec_reprise(src: str | os.PathLike[str],
                           cible: str | os.PathLike[str]) -> None:
    """`os.replace(src, cible)`, repris sur `PermissionError` SEULE.

    Au plus `REMPLACER_TENTATIVES` appels espacés de `REMPLACER_DELAI_S` ; à
    l'épuisement, la DERNIÈRE exception est relevée telle quelle, jamais une
    exception fabriquée. Toute autre `OSError` sort au PREMIER appel :
    reprendre un chemin réellement cassé changerait un échec clair en 300 ms de
    silence suivies du même échec. `ValueError` si `REMPLACER_TENTATIVES` ne
    permet aucun appel.

    Sans racine et sans garde : les deux chemins sont déjà résolus par
    l'appelant (`Workspace.write_bytes(..., reprises=True)`, ou un module de
    `.agents/bin/` qui la ré-exporte sous son nom historique)."""
    derniere: PermissionError | None = None
    for _ in range(REMPLACER_TENTATIVES):
        try:
            os.replace(src, cible)
            return
        except PermissionError as exc:
            derniere = exc
            time.sleep(REMPLACER_DELAI_S)
    if derniere is None:
        raise ValueError(f"REMPLACER_TENTATIVES={REMPLACER_TENTATIVES} : aucun "
                         "appel d'os.replace permis")
    raise derniere


def _umask() -> int:
    """Lit l'umask sans le changer durablement — `os.umask` n'a pas de getter.

    La fenêtre entre les deux appels est le seul moyen offert par la
    bibliothèque standard ; elle est étroite et ce module n'est pas
    multi-processus sur ce chemin.
    """
    u = os.umask(0o022)
    os.umask(u)
    return u


class HorsRacine(ValueError):
    """Un chemin résolu tombe hors de la racine du workspace."""


@dataclass(frozen=True)
class Identite:
    """Ce qu'est une FEUILLE à un instant : son chemin (parent résolu, feuille
    NON suivie), son `(dev, ino)`, si c'est un lien ou un fichier régulier, et
    son nombre de LIENS PHYSIQUES (`nliens`, `st_nlink`). Rendue par
    `Workspace.identite` (`lstat`) et `creer_fichier_exclusif` (`fstat` du
    descripteur créé). Deux identités d'un même fichier régulier sont ÉGALES
    champ pour champ ; c'est ce qu'un appelant compare pour savoir si
    l'emplacement a changé entre deux instants (T-00000759) — un lien physique
    AJOUTÉ entre-temps change `nliens`, donc l'identité.

    `nliens > 1` dit qu'un AUTRE nom désigne le même inode : écrire par ce nom
    écrirait aussi le fichier de l'autre (binôme F1 de T-00000759). C'est à
    l'appelant d'en juger ; `nliens` d'un lien SYMBOLIQUE est le sien, jamais
    celui de sa cible.

    BORNE (L-00000074) : `(dev, ino)` réduit la fenêtre mais ne PROUVE pas
    l'identité — un inode libéré peut être RECYCLÉ par un fichier neuf ; et
    `st_ino` peut valoir 0 sur FAT (Windows), `st_nlink` y est rendu par
    l'API de fichier : ni l'un ni l'autre n'est mesuré ici."""

    chemin: Path
    dev: int
    ino: int
    est_lien: bool
    est_regulier: bool
    nliens: int


class Workspace:
    """Les E/S d'un arbre de projet, confinées à sa racine.

    La racine est REÇUE, jamais calculée ici : c'est `paths.project_root()` qui
    la trouve, et ce module ne fait que travailler dedans. C'est ce qui rend un
    `Workspace` pointable sur un répertoire temporaire, donc testable.
    """

    def __init__(self, racine: str | os.PathLike[str]) -> None:
        self.racine = Path(racine).resolve()

    # -- résolution -----------------------------------------------------

    def resolve(self, relatif: str | os.PathLike[str]) -> Path:
        """Chemin absolu sous la racine, ou `HorsRacine`.

        La résolution passe par `Path.resolve()`, donc elle suit les liens
        symboliques : un lien qui pointe hors de l'arbre est refusé, ce qu'une
        comparaison purement lexicale laisserait passer.
        """
        candidat = (self.racine / Path(relatif)).resolve()
        if candidat != self.racine and self.racine not in candidat.parents:
            raise HorsRacine(
                f"{relatif!r} sort de la racine du workspace ({self.racine}) — "
                f"resolu en {candidat}. Un chemin de projet est relatif a sa "
                "racine ; passez par `paths` si vous visez une autre racine."
            )
        return candidat

    # -- lecture --------------------------------------------------------

    def exists(self, relatif: str | os.PathLike[str]) -> bool:
        try:
            return self.resolve(relatif).exists()
        except HorsRacine:
            return False

    def est_repertoire(self, relatif: str | os.PathLike[str] = ".") -> bool:
        """Vrai si `relatif` désigne un répertoire SOUS la racine (lien suivi).

        FAUX QUAND LA RÉPONSE EST NON, LEVÉE QUAND ELLE EST INCONNUE
        (T-00001232, contrat S-00004560). Faux : `HorsRacine` ; une absence
        (ENOENT) ; un composant fichier (ENOTDIR) ; EBADF ; un nom trop long
        (ENAMETOOLONG) ; une boucle de liens (ELOOP) à partir de 3.13 — en
        3.11/3.12 `resolve` lève `RuntimeError` avant le `stat`. Sous Windows,
        les winerror 21, 123 et 1921 rendent faux aussi : jeu repris de
        `pathlib` 3.11–3.13, NON mesuré ici (borne). Levée : `PermissionError`
        sur un refus de traversée (EACCES, EPERM), sur tout interpréteur, et
        toute autre `OSError` (EIO…) propagée telle quelle.

        POURQUOI `os.stat` ET PAS `Path.is_dir` : mesuré (3.11.16, 3.12.14,
        3.13.15, 3.14.7), `is_dir` LEVAIT `PermissionError` sur un parent non
        traversable en 3.11–3.13 et rendait FAUX en 3.14 (`os.path.isdir` avale
        toute `OSError`) — un refus de droits s'y lisait « absent ». Le jeu
        d'errnos est désormais tenu ici, pas par la version de `pathlib`.

        Répond sur la racine elle-même (`"."`, le défaut), acceptée par la garde
        `candidat == self.racine` de `resolve` — c'est ce dont un producteur de
        surface a besoin pour refuser une racine inexistante.
        """
        try:
            chemin = self.resolve(relatif)
        except HorsRacine:
            return False
        try:
            st = os.stat(chemin)
        except OSError as e:
            if e.errno in {errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP,
                           errno.ENAMETOOLONG} \
                    or getattr(e, "winerror", 0) in {21, 123, 1921}:
                return False
            raise
        return stat.S_ISDIR(st.st_mode)

    def age_secondes(self, relatif: str | os.PathLike[str]) -> float:
        """L'âge de `relatif` en secondes : maintenant moins son `mtime`.

        `HorsRacine` s'il sort de la racine ; `FileNotFoundError` s'il est
        absent — une LECTURE lève, comme `read_bytes` ; seuls `exists` et
        `est_repertoire` répondent faux sur une absence. `est_repertoire` lève
        `PermissionError` sur un refus de traversée, sur tout interpréteur ;
        `exists` garde la divergence 3.14 (il lève en 3.11–3.13, rend faux en
        3.14 — résidu, T-00001235). Un `mtime` dans le futur rend un âge
        NÉGATIF, rendu tel quel.

        Existe pour qu'un appelant de `ledger/`, où `stat` est refusé hors
        `Workspace` par le banc de pureté, juge un fichier-verrou par son âge
        comme son producteur le fait (`events.maintenance_lock` :
        `time.time() - lock.stat().st_mtime`, T-00000646, S-00002323).
        """
        return time.time() - self.resolve(relatif).stat().st_mtime

    def _feuille(self, relatif: str | os.PathLike[str]) -> Path:
        """`resolve(parent) / nom` : le PARENT est résolu et confiné (`HorsRacine`
        s'il sort), la FEUILLE reste telle qu'écrite, jamais suivie. Un nom vide,
        `.` ou `..` ne désigne pas une feuille : résolu en entier, par `resolve`."""
        p = Path(relatif)
        if p.name in ("", ".", ".."):
            return self.resolve(p)
        return self.resolve(p.parent) / p.name

    def identite(self, relatif: str | os.PathLike[str]) -> Identite | None:
        """L'identité de la FEUILLE `relatif`, lue par `os.lstat` — jamais
        suivie : un lien rend SA propre identité (`est_lien`, non régulier,
        l'inode du lien), jamais celle de sa cible, et un lien PENDANT en rend
        une. `None` si rien n'existe à ce nom ; `HorsRacine` si le parent sort
        de la racine ; toute autre `OSError` (un parent qui est un fichier) est
        levée.

        Existe pour qu'un appelant de `ledger/` refuse un lien (symbolique ou
        physique) à l'emplacement d'un store et vérifie qu'un emplacement n'a
        pas changé entre deux instants (T-00000759) — `exists` suit la
        feuille, donc dit « absent » d'un lien pendant. Le banc de pureté de
        `ledger/` y refuse `.stat()` hors `Workspace`, mais il est AVEUGLE à
        `os.lstat` et `os.fstat` : ni l'un ni l'autre n'est dans son jeu
        `IO_PAR_METHODE`, NON étendu (sa parité avec le filet global le fixe).
        Qu'aucun `os.lstat` nu n'y remplace cette méthode tient donc par la
        revue, pas par ce filet."""
        chemin = self._feuille(relatif)
        try:
            st = os.lstat(chemin)
        except FileNotFoundError:
            return None
        return Identite(chemin=chemin, dev=st.st_dev, ino=st.st_ino,
                        est_lien=stat.S_ISLNK(st.st_mode),
                        est_regulier=stat.S_ISREG(st.st_mode),
                        nliens=st.st_nlink)

    def read_bytes(self, relatif: str | os.PathLike[str]) -> bytes:
        return self.resolve(relatif).read_bytes()

    def read_text(self, relatif: str | os.PathLike[str], encoding: str = "utf-8") -> str:
        return self.read_bytes(relatif).decode(encoding)

    def iter_files(self, motif: str = "**/*") -> list[Path]:
        """Les fichiers de l'arbre, triés ET CONFINÉS comme le reste.

        Trié parce qu'un ordre de système de fichiers n'est pas stable d'une
        plateforme à l'autre, et qu'un banc qui en dépend est vert ici et rouge
        en CI.

        Confiné parce que `glob` ne passait par AUCUNE garde : la classe annonce
        en tête de module qu'un lien symbolique qui remonte est refusé, et une
        méthode sur six ne l'appliquait pas. Mesuré le 2026-09-12 — un lien
        interne vers `/etc/hosts` était rendu comme un fichier du projet.
        """
        out = []
        for p in self.racine.glob(motif):
            if not p.is_file():
                continue
            try:
                self.resolve(p.relative_to(self.racine))
            except (HorsRacine, ValueError):
                continue
            out.append(p)
        return sorted(out)

    def walk(
        self,
        sous: str | os.PathLike[str] = ".",
        *,
        elaguer: Callable[[str], bool] = lambda _nom: False,
        sur_erreur: Callable[[OSError], None] | None = None,
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        """Parcours ÉLAGUÉ de l'arbre, confiné sous la racine.

        Rend, par répertoire, un triplet `(rel, sous_reps, fichiers)` où `rel`
        est un chemin POSIX RELATIF à la racine — `"."` à la racine elle-même.
        Ce rendu relatif est DÉLIBÉRÉ : il fait disparaître le `resolve()` puis
        le `relative_to` que chaque appelant devait sinon refaire. C'est une
        DIVERGENCE ASSUMÉE avec `iter_files`, qui rend des `Path` ABSOLUS : la
        retourner « pour harmoniser » réintroduirait ce `resolve()`.

        `elaguer` est un PRÉDICAT sur un nom de sous-répertoire, pas une liste :
        la politique d'élagage reste chez l'appelant (`init_surfaces` passe
        `ELAGAGE.__contains__`), le noyau n'embarque aucune énumération close.
        Défaut = n'élague RIEN, identique à `os.walk`. L'élagage MORD EN PLACE
        (`sous_reps[:] = ...`), seule forme qui empêche `os.walk` de descendre —
        réaffecter le nom laisse le défaut SILENCIEUX.

        `sur_erreur=None` ⇒ ON LÈVE, au lieu d'avaler : inversion délibérée du
        défaut de `os.walk`, dont l'avalement silencieux a fait disparaître un
        répertoire de bancs sans une ligne (mesuré). Un appelant qui veut
        collecter puis lever EN BLOC passe `illisibles.append`.

        `followlinks=False` : la DESCENTE est confinée (`self.resolve(sous)` +
        pas de suivi de liens), mais les NOMS RENDUS ne le sont PAS. Un
        FICHIER-lien pointant HORS de l'arbre (`sub/dehors.txt -> /etc/hosts`)
        est listé tel quel dans `fichiers`, là où `iter_files` le REFUSE : c'est
        à l'appelant qui COMPTE des noms de le savoir — toute LECTURE ultérieure
        de ce nom par un `Workspace` sera refusée (`HorsRacine`), mais `walk` ne
        relit pas. Filtrer chaque entrée par `os.lstat`+`resolve` coûterait un
        appel PAR ENTRÉE : NON fait ici, borne assumée. Un arbre atteint par un
        lien de RÉPERTOIRE, lui, reste NON découvert (la descente est confinée).
        """
        depart = self.resolve(sous)

        def _onerror(err: OSError) -> None:
            if sur_erreur is None:
                raise err
            sur_erreur(err)

        for base, sous_reps, fichiers in os.walk(
            depart, onerror=_onerror, followlinks=False
        ):
            sous_reps[:] = [nom for nom in sous_reps if not elaguer(nom)]
            rel = Path(base).relative_to(self.racine).as_posix()
            yield rel, sous_reps, fichiers

    # -- écriture -------------------------------------------------------

    def creer_repertoire(self, relatif: str | os.PathLike[str]) -> Path:
        """Crée le RÉPERTOIRE `relatif` sous la racine, parents compris, et rend
        son chemin absolu. Idempotente (`exist_ok`) ; `HorsRacine` s'il en sort.

        Existe pour qu'un appelant puisse préparer l'emplacement d'un fichier
        SANS créer le fichier lui-même : `write_bytes` passe par `os.replace`,
        donc sur une cible apparue entre-temps elle REMPLACE l'inode — mesuré
        sur un store SQLite vivant, des lignes validées perdues (T-00000646,
        F5). Un fichier qu'un autre composant crée seul (SQLite à l'ouverture)
        n'a besoin que de son répertoire.
        """
        cible = self.resolve(relatif)
        cible.mkdir(parents=True, exist_ok=True)
        return cible

    def creer_fichier_exclusif(
        self, relatif: str | os.PathLike[str], mode: int = 0o600
    ) -> Identite | None:
        """Crée la FEUILLE `relatif`, VIDE, si et seulement si RIEN n'existe à ce
        nom — ni fichier, ni répertoire, ni lien, même pendant —, et rend
        l'identité du fichier CRÉÉ, lue sur son descripteur (`fstat`), pas par
        un second accès au nom. `None` si le nom est pris : rien n'est écrasé,
        rien n'est suivi, rien n'est retiré. `HorsRacine` si le parent sort de
        la racine ; parent absent ⇒ `FileNotFoundError` (le répertoire est
        l'affaire de `creer_repertoire`). Le fichier n'est jamais écrit ici.

        `O_CREAT|O_EXCL` refuse un nom pris, lien compris (POSIX : `EEXIST` sur
        un lien, même pendant) ; `O_NOFOLLOW` est le second verrou de la feuille
        là où il existe ; `O_CLOEXEC` ne laisse pas le descripteur à un enfant.
        T-00000759 : c'est ce qui remplace « SQLite crée le fichier à
        l'ouverture », où SQLite SUIVAIT un lien planté à sa place.

        MODE `0o600` PAR DÉFAUT, masqué par l'umask comme tout `open` — ÉCART
        VOULU avec `write_bytes`, qui fait naître un fichier en
        `0o666 & ~umask` : l'appelant de T-00000759 crée des stores SQLite,
        données d'exécution PRIVÉES d'un utilisateur, lues seulement par des
        processus du même uid (décision R1 du plan). Un appelant qui veut la
        convention du dépôt passe `mode=0o666`.

        BORNES, écrites plutôt que tues : un ANCÊTRE échangé entre la résolution
        et `open` fait naître le fichier vide AILLEURS (`os.open` suit les
        répertoires intermédiaires, seule la feuille est gardée) ; Windows n'a
        pas d'`O_NOFOLLOW` (repli : `O_EXCL`, soit `CREATE_NEW`), NON mesuré ici ;
        l'atomicité d'`O_EXCL` sur un système de fichiers réseau (NFS/SMB, faible
        sur les vieux NFS) n'est PAS mesurée."""
        chemin = self._feuille(relatif)
        drapeaux = (os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            fd = os.open(chemin, drapeaux, mode)
        except FileExistsError:
            return None
        try:
            st = os.fstat(fd)
        finally:
            os.close(fd)
        return Identite(chemin=chemin, dev=st.st_dev, ino=st.st_ino,
                        est_lien=stat.S_ISLNK(st.st_mode),
                        est_regulier=stat.S_ISREG(st.st_mode),
                        nliens=st.st_nlink)

    def ecrire_fichier_exclusif(
        self, relatif: str | os.PathLike[str], donnees: bytes, mode: int = 0o644
    ) -> Path | None:
        """Crée la FEUILLE `relatif` AVEC `donnees` si et seulement si RIEN
        n'existe à ce nom, et rend son chemin (parent résolu, feuille non
        suivie). `None` si le nom est pris — fichier, répertoire, lien même
        pendant : rien n'est écrasé, suivi ni retiré. `HorsRacine` si le parent
        sort de la racine ; parent absent ⇒ `FileNotFoundError` (le répertoire
        est l'affaire de `creer_repertoire`).

        CONTRAT DISTINCT DE `creer_fichier_exclusif`, qui n'écrit JAMAIS et dont
        la signature est figée par ses doubles (T-00000759) : ici création,
        écriture, `fsync` et fermeture font UN geste — l'identité d'un projet
        (T-00000969) naît pleine ou ne naît pas. Sur TOUTE `BaseException`
        après la création (`KeyboardInterrupt` au `fsync` compris), le fichier
        partiel est RETIRÉ puis l'exception relevée. `O_EXCL` est le seul
        arbitre (anti-TOCTOU, aucun `exists` préalable) : N créateurs
        concurrents, UN gagnant. `O_NOFOLLOW`, `O_CLOEXEC` et `O_BINARY` là
        où ils existent — le dernier pour que Windows n'écrive pas `\\r\\n`.

        MODE `0o644` PAR DÉFAUT, masqué par l'umask : la convention d'un
        fichier de projet que lisent d'autres processus du même uid — écart
        voulu avec le `0o600` de `creer_fichier_exclusif`.

        BORNES : celles de `creer_fichier_exclusif` (ancêtre échangé entre la
        résolution et `open`, Windows sans `O_NOFOLLOW`, `O_EXCL` sur NFS) ; et
        le partiel est retiré PAR SON NOM — un nom échangé entre la création et
        le retrait n'est pas détecté."""
        chemin = self._feuille(relatif)
        drapeaux = (os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_BINARY", 0))
        try:
            fd = os.open(chemin, drapeaux, mode)
        except FileExistsError:
            return None
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(donnees)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            try:
                os.unlink(chemin)
            except OSError:
                pass
            raise
        return chemin

    def write_bytes(self, relatif: str | os.PathLike[str], donnees: bytes, *,
                    reprises: bool = False, mode: int | None = None) -> Path:
        """Écriture ATOMIQUE : temporaire du même répertoire, puis `os.replace`.

        Le temporaire vit à côté de la cible et non dans `/tmp`, parce que
        `os.replace` n'est atomique qu'à l'intérieur d'un même système de
        fichiers. Un échec nettoie le temporaire plutôt que de laisser un
        résidu — la trace d'un `sed -i` oublié a coûté une entrée dans les
        actions du pilote sur ce chantier.

        `reprises=True` passe le renommage par `remplacer_avec_reprise`
        (Windows, lecteur concurrent : L-00000054) ; le défaut `False` garde
        un seul `os.replace`, donc aucun appelant existant ne change. Le
        nettoyage couvre TOUTE `BaseException` — un `KeyboardInterrupt` entre
        `mkstemp` et le renommage retire le temporaire puis est relevé tel
        quel (T-00000969, exec-critic : un Ctrl-C pendant `--rename` laissait
        `project.json.<rnd>.cadre-tmp`, non ignoré par git, porteur du
        `project_id`). Borne restante : un `SIGKILL` ou une coupure ne passe
        par aucun `except` — le temporaire peut rester, jamais la cible
        tronquée.

        MODE. Par défaut (`mode=None`), celui d'une cible existante est
        REPORTÉ, et une cible neuve reçoit `0o666` masqué par l'umask. Un
        `mode` fourni est IMPOSÉ, masqué par l'umask comme à une création
        (`os.open`) : création et réécriture rendent alors le même mode sous
        tout umask, quel que soit celui de la cible (T-00000969, décision
        pilote, tags git decision/T-00000969/01 et /02 (umask respecté) :
        `project.json` en 0644, même réécrit depuis un 0600).
        """
        cible = self.resolve(relatif)
        cible.parent.mkdir(parents=True, exist_ok=True)
        # NOM UNIQUE, PLUS `cible.name + ".cadre-tmp"`. Le nom FIXE faisait écrire
        # deux écrivains concurrents dans le MÊME inode, et le nettoyage de l'un
        # supprimait le temporaire en vol de l'autre : mesuré le 2026-09-12,
        # `FileNotFoundError` sous trois fils sur une même cible. L'atomicité
        # tenait le crash et pas le voisin, ce qui n'est pas ce que la docstring
        # ci-dessus promet à un lot de shards parallèles.
        fd, brut = tempfile.mkstemp(dir=str(cible.parent),
                                    prefix=cible.name + ".", suffix=".cadre-tmp")
        tmp = Path(brut)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(donnees)
                f.flush()
                # `os.replace` est atomique pour le NOM, pas pour les DONNÉES.
                # Sans `fsync`, une coupure d'alimentation laisse une cible
                # renommée et vide — exactement le marqueur de porte vide dont la
                # revue de clôture 0bis a fait un constat.
                os.fsync(f.fileno())
            if mode is not None:
                os.chmod(tmp, mode & ~_umask())
            elif cible.exists():
                # `os.replace` remplace la cible ET SES PERMISSIONS par celles du
                # temporaire. Mesuré : un `.sh` en 0755 réécrit ressortait en
                # 0644 — donc un hook non exécutable, donc une garde qui ne mord
                # plus. `mkstemp` crée en 0600 ; on reporte le mode d'origine.
                os.chmod(tmp, stat.S_IMODE(cible.stat().st_mode))
            else:
                os.chmod(tmp, 0o666 & ~_umask())
            if reprises:
                remplacer_avec_reprise(tmp, cible)
            else:
                os.replace(tmp, cible)
        except BaseException:
            # `BaseException`, ni `OSError` ni `Exception`, et ce sont DEUX
            # corrections : la premiere redaction ne nettoyait que les erreurs
            # disque (un `TypeError` laissait le temporaire), la seconde ne
            # voyait pas un `KeyboardInterrupt` (Ctrl-C) entre `mkstemp` et le
            # renommage (T-00000969). Un residu `.cadre-tmp` est exactement ce
            # qu'un `git add -A` ramasse ensuite sans que personne le voie.
            # Relevee telle quelle apres le nettoyage : rien n'est avale.
            tmp.unlink(missing_ok=True)
            raise
        return cible

    def write_text(
        self, relatif: str | os.PathLike[str], contenu: str, encoding: str = "utf-8"
    ) -> Path:
        """Écrit du texte SANS traduire les fins de ligne — voir la docstring du
        module : un aller-retour qui les traduit réécrit le fichier entier."""
        return self.write_bytes(relatif, contenu.encode(encoding))
