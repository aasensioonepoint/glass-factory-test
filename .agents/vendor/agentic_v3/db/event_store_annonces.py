"""Les ANNONCES de la reconstruction V3 et la sonde d'ecart runs/ -> base, dites sur stderr
(T-01M4N1FJC2X6YNA0XR51AYQKK1, T-01M4N496YD7BZDA2NHYQ73JND9).

Extrait de `event_store.py` : celui-ci est au CLIQUET des 1600 lignes (`.agents/evals/python_file_length_cliquet.json`,
plafond lu dans le JSON du cliquet, aucun passe-droit : `test_python_file_length.py` ROUGIT au moindre octet de
plus, R2, ou de moins, R2b).
`EventStore` HERITE de `AnnoncesRunsMixin`. Ce module ne porte AUCUN litteral SELECT / INSERT / UPDATE
(`test_cadre_sql_locality.py` refuse un fichier neuf qui en porte, et borne la dette a neuf fichiers) : les trois
fonctions SQL du decompte (`_banc_a_blanc`, `_appliquable_a_blanc`, `_manquants_nommes`) restent dans `event_store.py`.
"""
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from agentic_v3.db import run_export

#: T-01M4N1FJC2X6YNA0XR51AYQKK1 : les bases (`str(db_path)`) dont l'ECART runs/ -> base a deja ete
#: ANNONCE dans CE processus. Memoire de l'ANNONCE, jamais de la sonde : un memo « sonde » aveuglerait
#: une fusion survenue entre deux ouvertures du meme processus.
_ECARTS_RUNS_ANNONCES: Set[Any] = set()

#: T-01M4N1FJC2X6YNA0XR51AYQKK1 : borne du TOTAL que la sonde d'ecart lit dans `runs/` a CHAQUE
#: ouverture. La lecture coute 4 a 5 x ce qu'elle lit et le total n'est pas borne (ci-dessus) ; un
#: OOM-kill n'est attrapable par personne. Au-dela, la sonde ne lit PAS et le DIT (UNE ligne).
#: Valeur : la borne d'UN fichier (64 MiB, ~250-320 MiB de RAM). Mesure le 2026-10-11 : runs/ ~18 MiB.
_SONDE_RUNS_MAX_OCTETS = 64 * 1024 * 1024  # = `event_store._TAILLE_FICHIER_MAX_OCTETS` (T63 le fige)

#: C5 (NO_GO it. 3) : la partition pour laquelle S-00002370 a decide le geste de reconstruction en place, et
#: celle qu'il exclut. Le texte de l'ecart ne cite la decision et ces deux ids QUE dans la partition du kit.
_PARTITION_GESTE_S2370 = "d5dbf35ba35777da"
_PARTITION_PERSO_EXCLUE = "2af11384315eb8aa"


#: R5 (cloture fournee 4) : controle (`Cc`), format (`Cf` : U+202E retourne l'affichage), separateurs de ligne
#: (`Zl`, U+2028) et de paragraphe (`Zp`, U+2029) - un terminal ou une visionneuse rend les deux derniers en saut.
_CATEGORIES_ECHAPPEES = frozenset(("Cc", "Cf", "Zl", "Zp"))


def _echappe(c: str) -> str:
    """`\\xNN`, `\\uNNNN` ou `\\UNNNNNNNN` selon le point de code (la forme d'un litteral Python)."""
    n = ord(c)
    return f"\\x{n:02x}" if n <= 0xFF else f"\\u{n:04x}" if n <= 0xFFFF else f"\\U{n:08x}"


def _sans_controle(nom: str) -> str:
    """C6 (NO_GO it. 4) : un nom d'auteur ou de copie vient d'un dossier de `runs/` FUSIONNE ; un caractere de
    controle (saut de ligne, ESC) y forgerait une fausse ligne d'annonce ou piloterait le terminal - echappe
    (`_CATEGORIES_ECHAPPEES`, R5 ; la categorie `Cc` couvre C0, DEL et C1)."""
    return "".join(_echappe(c) if unicodedata.category(c) in _CATEGORIES_ECHAPPEES else c for c in nom)


class AnnoncesRunsMixin:
    """Les annonces stderr d'`EventStore` et la plomberie de la sonde d'ecart (rien d'autre : pas de SQL de rejeu)."""

    def _connexion_lecture(self) -> sqlite3.Connection:
        """Connexion de LECTURE de la sonde d'ecart, ouverte SANS SUIVRE et SANS CREER (T-00000770) par
        la couture de `get_db_connection` (`run_export._couture_ledger_store`, que
        `schema._couture_ledger_store` enveloppe) : `refuser_les_liens` puis
        `ouvrir_sans_suivre(creer=False)` - un lien a la place du store, pendant ou vers une base
        victime, leve `EmplacementRefuse` au lieu d'etre suivi ou de faire naitre sa cible. Puis
        `PRAGMA query_only=ON`, SANS `journal_mode` ni `foreign_keys`, attente courte (`timeout=1`).
        Pas `mode=ro` : mesure (M7b) - sur une base WAL sans session, il CREE `-wal`/`-shm` et les LAISSE."""
        store_mod, ws_mod = run_export._couture_ledger_store()
        atelier = ws_mod.Workspace(self.db_path.parent)
        store_mod.refuser_les_liens(atelier, self.db_path.name)
        conn, _ident, _cree = store_mod.ouvrir_sans_suivre(
            atelier, self.db_path.name, creer=False,
            connecter=lambda uri: sqlite3.connect(uri, uri=True, timeout=1),
        )
        conn.execute("PRAGMA query_only=ON")
        return conn

    def _texte_ecart_runs(self, nommes: Dict[str, str]) -> str:
        """Annonce historique sous AGENTS_V3_AUTO_SYNC=0 : compte, copies et
        geste encadré de S-00002370 ; la voie active sauvegarde puis importe."""
        from agentic_v3.db.event_store import _CHEMINS_ANNONCES_MAX  # import PARESSEUX : event_store importe ce module

        par_copie: Dict[str, int] = {}
        for copie in nommes.values():
            par_copie[copie] = par_copie.get(copie, 0) + 1
        rang = sorted(par_copie.items(), key=lambda kv: (-kv[1], kv[0]))
        noms = ", ".join(f"{_sans_controle(copie)} ({k})" for copie, k in rang[:_CHEMINS_ANNONCES_MAX])
        if len(rang) > _CHEMINS_ANNONCES_MAX:
            noms += f", et {len(rang) - _CHEMINS_ANNONCES_MAX} autres"
        nom = self.db_path.name
        trois = f"{nom}, {nom}-wal, {nom}-shm"
        copie = (
            f"COPIER a part, hors de {self.db_path.parent} : {trois} (ceux qui existent) - la copie garde "
            "aussi ce que la base porte et que runs/ n'a pas, que la reconstruction RETIRE de la base vivante"
        )
        suppression = (
            f"supprimer ces trois noms EXACTS : {trois} (jamais un joker : des sauvegardes voisines portent "
            "le meme prefixe)"
        )
        if self.db_path.parent.parent.name == _PARTITION_GESTE_S2370:
            acteur = (
                "ils n'y entrent que par le geste de S-00002370, geste de l'ORCHESTRATEUR sur feu vert du "
                f"PILOTE, decide pour la seule partition {_PARTITION_GESTE_S2370} et jamais la partition "
                f"perso {_PARTITION_PERSO_EXCLUE} (toute autre partition : decision du pilote d'abord)"
            )
        else:
            acteur = (
                "ils n'y entrent que par une reconstruction, geste de l'ORCHESTRATEUR sur feu vert du "
                "PILOTE : decision du pilote d'abord pour cette partition"
            )
        return (
            f"event_store: ecart runs/ -> base V3 vivante - {len(nommes)} evenement(s) de runs/ absents "
            f"de la base (apportes par : {noms}) ; une base non vide n'est JAMAIS reconstruite d'office : "
            f"{acteur}. Geste : arreter les "
            f"autres sessions ; {copie} ; PUIS {suppression} ; python3 .agents/bin/tasks.py replay-sync ; "
            "comparer evenements, liens et projections avant/apres"
        )

    def _taille_runs(self, racine: Path) -> int:
        """Octets des exports candidats de `runs/` (meme enumeration SANS LIEN que `_lire_exports`,
        `lstat`) ; un fichier qui leve compte 0 - la lecture le comptera illisible."""
        total = 0
        for chemin in run_export.parcourir_runs(racine, [], []):
            try:
                total += chemin.lstat().st_size
            except OSError:
                pass
        return total

    def _annoncer_ecart_runs(self) -> None:
        """Dit le résultat de la synchro ou, sous opt-out, l'écart historique.

        Le résultat évite une seconde lecture après `_rejouer_journaux_attente`.
        Sous AGENTS_V3_AUTO_SYNC=0, l'ancienne sonde lit sans lien ni verrou,
        annonce une fois par processus et base, et n'écrit rien.
        """
        cle = str(self.db_path)
        resultat = getattr(self, "_auto_sync_result", None)
        if resultat is not None and not resultat.get("non_sonde"):
            if resultat.get("avortee"):
                message = ("event_store: synchro V3 AVORTEE, rien importe : "
                           f"{_sans_controle(resultat.get('erreur', 'erreur inconnue'))} ; "
                           "contournement : AGENTS_V3_AUTO_SYNC=0 (sonde historique, aucune ecriture)")
            elif resultat["inhibee"]:
                if cle in _ECARTS_RUNS_ANNONCES:
                    return
                _ECARTS_RUNS_ANNONCES.add(cle)
                marqueur = self.db_path.parent / "v3-auto-sync" / f"autorise-{self.db_path.parent.parent.name}"
                message = (self._texte_ecart_runs(resultat["nommes"])
                           + f" ; synchro V3 inhibee (kit) : sur feu vert du PILOTE, poser {marqueur}")
            elif resultat.get("apres") is not None or any(resultat.get(c) for c in (
                "echecs", "malformes", "ignores", "fichiers_illisibles", "fichiers_trop_gros",
                "lignes_illisibles", "pont_ecartes")):
                etat = "appliquee" if resultat.get("apres") is not None else "sondee"
                message = (f"event_store: synchro V3 {etat} : "
                           f"ecart={resultat['ecart']} applied={resultat['applied']} "
                           f"sauvegarde={resultat['sauvegarde']} "
                           + (f"evenements/liens/projections {resultat['avant']} -> {resultat['apres']} "
                              if resultat.get("apres") is not None else "")
                           + f"echecs={resultat.get('echecs', 0)} malformes={resultat.get('malformes', 0)} "
                           + f"ulid_hors_forme={resultat.get('ignores', 0)} "
                           + f"fichiers_illisibles={resultat.get('fichiers_illisibles', 0)} "
                           + f"fichiers_trop_gros={resultat.get('fichiers_trop_gros', 0)} "
                           + f"lignes_illisibles={resultat.get('lignes_illisibles', 0)} "
                           + f"pont_ecartes={resultat.get('pont_ecartes', 0)}")
            elif not resultat.get("divergentes"):
                return
            else:
                message = None
            if message is not None:
                print(message, file=sys.stderr)
            if resultat.get("divergentes"):
                signature = (cle, tuple(resultat["divergentes_ulid"]))
                if signature not in _ECARTS_RUNS_ANNONCES:
                    _ECARTS_RUNS_ANNONCES.add(signature)
                    self._annoncer_divergences(resultat)
            return
        if cle in _ECARTS_RUNS_ANNONCES:
            return
        message: Optional[str] = None
        try:
            racine = self._racine_runs()
            taille = self._taille_runs(racine)
            if taille > _SONDE_RUNS_MAX_OCTETS:
                message = (
                    f"event_store: ecart runs/ -> base NON sonde (runs/ pese {taille} o > "
                    f"{_SONDE_RUNS_MAX_OCTETS} o, borne de la sonde a l'ouverture : la lire couterait 4 a "
                    "5 x en memoire a chaque commande) - l'ecart eventuel n'est pas annonce"
                )
            else:
                resume = {"fichiers_illisibles": 0, "fichiers_trop_gros": 0, "lignes_illisibles": 0, "ignores": 0}
                chemins: Dict[str, List[Path]] = {
                    "fichiers_illisibles": [], "fichiers_trop_gros": [], "lignes_illisibles": [],
                }
                evenements = self._lire_exports(racine, resume, chemins)
                if evenements:
                    evenements.sort(key=lambda t: (t[0], t[1]))
                    conn = self._connexion_lecture()
                    try:
                        nommes = self._manquants_nommes(conn.cursor(), evenements)
                    finally:
                        conn.close()
                    if nommes:
                        message = self._texte_ecart_runs(nommes)
        except Exception as exc:
            message = (
                f"event_store: ecart runs/ -> base NON sonde ({type(exc).__name__}: {_sans_controle(str(exc))}) "
                "- l'ecart eventuel n'est pas annonce sur cette ouverture"
            )
        if message is not None:
            _ECARTS_RUNS_ANNONCES.add(cle)
            print(message, file=sys.stderr)

    @staticmethod
    def _annoncer_divergences(resume: Dict[str, Any]) -> None:
        nommees = resume["divergentes_ulid"]
        reste = resume["divergentes"] - len(nommees)
        print(
            f"event_store: runs/ - {resume['divergentes']} ULID DIVERGENT(S) : un meme ULID porte des "
            "contenus differents (merge=union laisse passer les deux) ; la PREMIERE ligne dans l'ordre "
            "(ULID, auteur/copie) est gardee, l'autre ECARTEE, comptee et jamais reparee (le magasin est "
            "en ajout seul) - ulid : " + ", ".join(nommees) + (f" et {reste} autres" if reste > 0 else ""),
            file=sys.stderr,
        )

    def _annoncer_reconstruction(
        self,
        root: Path,
        resume: Dict[str, Any],
        chemins: Dict[str, List[Path]],
        *,
        si_vide: bool,
        cause_redaction: Optional[BaseException],
        raison_pont: Optional[str],
        pont_ecartes_nommes: List[str],
        manquants_saute: Optional[int] = None,
    ) -> None:
        """Les annonces stderr (§ 2 point 11) — HORS filet, sans SQLite ni disque.
        AVORTÉE est déjà dite par le filet R. `saute_non_vide` n'est muet que si la
        base trouvée non vide porte déjà tout ce que `runs/` porte de valide
        (`manquants_saute` = 0) ; sinon « reconstruction NON faite » et son remède
        (S-00002518 F5 : muet, il laissait l'historique dehors sans un mot)."""
        if resume["avortee"]:
            return
        if resume["saute_non_vide"]:
            if manquants_saute:
                print(
                    "event_store: reconstruction NON faite — base trouvee NON vide "
                    "sous le verrou (une autre session y a ecrit pendant l'ouverture) : "
                    f"{manquants_saute} evenements de runs/ absents de la base, jamais "
                    "reconstruits d'office (base non vide) ; remede : arreter les "
                    f"autres sessions, supprimer {self.db_path.name}* sous "
                    f"{self.db_path.parent}, puis python3 .agents/bin/tasks.py replay-sync",
                    file=sys.stderr,
                )
            return
        if resume["differee"]:
            print(
                "event_store: reconstruction automatique DIFFEREE, rien ecrit "
                f"(redaction indisponible : {type(cause_redaction).__name__}: "
                f"{cause_redaction}) — ecritures V3 refusees sur cette instance ; "
                f"{self._remede_reconstruction('DIFFEREE')}",
                file=sys.stderr,
            )
            return
        sautes = []
        for cle, libelle in (
            # « ou refuses » : un LIEN sous runs/ (jamais suivi) et un DOSSIER
            # illisible y sont comptés aussi (S-00002509, S-00002518 F4).
            ("fichiers_illisibles", "fichiers illisibles ou refuses"),
            ("fichiers_trop_gros", "fichiers trop gros (> 64 MiB, non lus)"),
            ("lignes_illisibles", "lignes illisibles"),
        ):
            if resume[cle]:
                sautes.append(
                    f"{libelle} ({resume[cle]}) : {self._nommer_chemins(chemins[cle], root)}"
                )
        if sautes:
            print(
                "event_store: runs/ — contenu SAUTE, perdu pour ce clone jusqu'au "
                "remede : " + " ; ".join(sautes) + " — remede : corriger ou retirer "
                "la ligne (reduire le fichier sous 64 MiB si trop gros ; remplacer "
                "tout lien symbolique sous runs/ par le fichier lui-meme, un lien "
                "n'est jamais suivi ; rendre lisible un dossier illisible), supprimer "
                f"{self.db_path.name}* sous {self.db_path.parent}, puis python3 "
                ".agents/bin/tasks.py replay-sync",
                file=sys.stderr,
            )
        if resume["divergentes"]:
            self._annoncer_divergences(resume)
        if resume["pont_non_rebati"]:
            print(
                f"event_store: pont board NON rebati ({raison_pont}) — liens et "
                "projections board laisses tels quels",
                file=sys.stderr,
            )
        elif any(
            resume[cle] for cle in (
                "pont_ecartes", "pont_deja_vus", "pont_remplaces", "faux_failed",
                "echecs_sans_failed", "failed_hors_intent",
            )
        ):
            detail = (
                " ; ecartes : " + ", ".join(pont_ecartes_nommes)
                + (" et autres" if resume["pont_ecartes"] > len(pont_ecartes_nommes) else "")
                if pont_ecartes_nommes else ""
            )
            print(
                f"event_store: pont rebati — intents={resume['pont_intents']} "
                f"ecartes={resume['pont_ecartes']} deja_vus={resume['pont_deja_vus']} "
                f"remplaces={resume['pont_remplaces']} faux_failed={resume['faux_failed']} "
                f"echecs_sans_failed={resume['echecs_sans_failed']} "
                f"failed_hors_intent={resume['failed_hors_intent']} "
                f"failed_v3_vers_board={resume['failed_v3_vers_board']}{detail}",
                file=sys.stderr,
            )
        ecartees = resume["ignores"] + resume["malformes"]
        auteurs = ",".join(resume["auteurs_rejoues"]) or "aucun"
        if si_vide and not resume["applied"]:
            # S-00002560 : « reconstruite 0/N », répétée à chaque ouverture, se lisait
            # comme un succès. Rien n'est entré : la base RESTE vide, donc elle est
            # re-sondée — et ceci redit — à chaque ouverture, jusqu'à ce que runs/
            # porte un événement lisible ou qu'une écriture la remplisse.
            print(
                "event_store: base V3 vide, RIEN reconstruit depuis runs/ (aucun "
                f"evenement lisible : evenements=0/{resume['total']} ecartees={ecartees} "
                f"echecs={resume['echecs']} lignes_illisibles={resume['lignes_illisibles']} "
                f"fichiers_illisibles={resume['fichiers_illisibles']} "
                f"fichiers_trop_gros={resume['fichiers_trop_gros']}) — base laissee "
                "vide, re-sondee a la prochaine ouverture",
                file=sys.stderr,
            )
        elif si_vide:
            print(
                "event_store: base V3 vide, reconstruite depuis runs/ a l'ouverture : "
                f"evenements={resume['applied']}/{resume['total']} ecartees={ecartees} "
                f"echecs={resume['echecs']} lignes_illisibles={resume['lignes_illisibles']} "
                f"fichiers_illisibles={resume['fichiers_illisibles']} "
                f"fichiers_trop_gros={resume['fichiers_trop_gros']} "
                f"intents_board={resume['pont_intents']} "
                f"pont_ecartes={resume['pont_ecartes']} "
                f"pont_deja_vus={resume['pont_deja_vus']} "
                f"faux_failed={resume['faux_failed']} auteurs_rejoues={auteurs}",
                file=sys.stderr,
            )
        elif ecartees or resume["echecs"] or sautes:
            # MAJEUR 6 : une reconstruction qui écarte des lignes doit être
            # discernable d'une reconstruction propre.
            print(
                "event_store: reconstruction terminee — "
                f"appliquees={resume['applied']} ecartees_hors_forme={ecartees} "
                f"(ulid={resume['ignores']}, champs={resume['malformes']}) "
                f"echecs_base={resume['echecs']} "
                f"lignes_illisibles={resume['lignes_illisibles']} "
                f"fichiers_illisibles={resume['fichiers_illisibles']} "
                f"fichiers_trop_gros={resume['fichiers_trop_gros']} "
                f"total={resume['total']} auteurs_rejoues={auteurs}",
                file=sys.stderr,
            )
