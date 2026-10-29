#!/usr/bin/env python3
"""LE NOYAU INSTALLÉ SOUS UN PRÉFIXE SYSTÈME EN LECTURE SEULE (T-00000884, BK-174).

POURQUOI CE BANC. La clause « Mode d'installation sous préfixe root optionnel
pour postes gérés » de la Phase 6 (`docs/PROMPT-refonte-packaging-cadre.md`) :
un administrateur pose le noyau UNE fois pour le poste, sous un préfixe que
l'utilisateur ne peut pas écrire, et chaque utilisateur garde SA configuration
et SON état. `cadre.paths` n'a rien de propre à ce mode — `PKG_ROOT` vaut
l'emplacement du paquet, `CONFIG_HOME` et `STATE_HOME` se résolvent sous
l'utilisateur — et ce banc MESURE que cela tient sur une vraie installation en
lecture seule, au lieu de le déduire de la lecture du code.

LA FORME D'INSTALLATION est celle du README (`uv tool install`, un venv isolé
par outil), déplacée par les deux variables de uv qui la déplacent :
`UV_TOOL_DIR` (les venvs d'outils) et `UV_TOOL_BIN_DIR` (les exécutables),
dirigées sous un PRÉFIXE jetable. Puis le préfixe entier passe en lecture seule
(`a-w` récursif, liens jamais suivis) : c'est ce que voit un utilisateur non
root devant un `/opt/…` posé par root.

CE QU'IL MESURE (`PrefixeSystemeTests`) — une construction et une installation
par exécution, en `setUpClass`. Chaque appel tourne en UTILISATEUR, hors du
dépôt, l'environnement réduit à la liste blanche de `test_cadre_cli_installed.py`
(ni `CADRE_*`, ni `XDG_*`, ni `UV_*`, ni `PYTHON*`, ni `GIT_*`), `HOME` jetable :
  (a) CALIBRATION du lecture seule : créer un fichier à la racine du préfixe et
      dans le paquet installé lève `PermissionError` — sans elle, un rouge de
      (e) n'accuserait pas le noyau (le préfixe resté inscriptible accepte
      l'écriture), et (b), (c), (d) ne joueraient pas le poste visé (un préfixe
      que l'utilisateur ne peut pas écrire) ;
  (b) `cadre paths --json`, la COMMANDE installée, lancée depuis un projet :
      `PKG_ROOT` sous le préfixe et hors de l'arbre source, `CONFIG_HOME` et
      `STATE_HOME` sous le `HOME` jetable, `STATE_PROJECT` sous `STATE_HOME` ;
  (c) l'écrivain réel de l'état machine du noyau, `creer_les_stores`, joué par
      l'interpréteur de l'outil : les deux magasins machine naissent sous
      `STATE_HOME`, celui d'équipe sous le projet, et le préfixe sort INCHANGÉ
      (inventaire chemin → taille, mtime, mode, relevé par `setUp` avant
      CHAQUE témoin et après lui : chacun juge ses propres écritures) ;
  (d) la même chose sous `XDG_STATE_HOME` et `XDG_CONFIG_HOME` jetables ;
  (e) REFUS NOMMÉ : `CADRE_STATE_DIR` dirigé DANS le préfixe — l'écriture
      échoue, rc ≠ 0, la DERNIÈRE ligne d'erreur est une `CadrePathError` qui
      NOMME le chemin refusé (jamais une `PermissionError` nue), et le préfixe
      sort inchangé ;
  (f) le bytecode du noyau PRÉCOMPILÉ à l'installation : le cache de
      `cadre.paths` existe sous le préfixe avant tout lancement — le seul
      témoin qui tienne `--compile-bytecode` sous le préfixe en lecture seule.
Sans uv (`RelevePrefixeSansUvTests`) : l'inventaire, l'écart, le « sous » et la
mise en lecture seule, éprouvés sur des données jetables — la part qui tourne
là où uv manque.

MUTANTS QUI ROUGISSENT (rejoués à la clôture de T-00000884) : `state_home()`
qui rend un chemin sous `pkg_root()` quel que soit `CADRE_STATE_DIR` (la
branche par défaut seule rougit (b), (c), (d)) — l'état écrit sous le
préfixe — rougit (b), (c), (d) et (e) ; le préfixe laissé inscriptible rougit
(a) et (e) — (b), (c), (d) et (f) restent verts, le bytecode étant précompilé ;
la traduction d'`OSError` retirée de `creer_les_stores` rougit (e).
`--compile-bytecode` retiré rougit (f) ; sans (f), rien ne rougirait sous le
préfixe en lecture seule (Python omet son cache sans erreur). Joint au préfixe
laissé inscriptible, il rougit (b) en plus de (a) et (e) — (b) est le premier
témoin qui importe le noyau — et (f) y reste VERT : (b) a écrit le cache que
(f) cherche ; (c) et (d), joués après, n'écrivent rien de neuf.

CE QU'IL NE MESURE PAS, écrit pour ne pas être relu comme couvert :
  * une installation par un root RÉEL : aucune élévation ici, le lecture seule
    est SIMULÉ par `chmod`. Sous uid 0 il ne mord pas — (a) et (e) sautent en
    l'annonçant ; (b), (c) et (d) tournent sur un préfixe que root PEUT écrire
    et n'y restent verts que parce que le bytecode est précompilé à
    l'installation : c'est le cas du préfixe laissé inscriptible, mesuré par
    mutant, jamais joué sous uid 0. `PYTHONDONTWRITEBYTECODE` n'y suffirait
    pas : la sonde tourne sous `-I`, qui ignore les variables `PYTHON*` (20
    écarts mesurés sous `-I` sans précompilation, la variable posée) ;
  * toute autre forme que `uv tool install` (pip et son option `--prefix`, un venv
    posé à la main) ;
  * Windows, sauté : `chmod` n'y rend pas un répertoire non inscriptible.
    Mesuré sous macOS à la livraison ; Linux non mesuré ;
  * une installation SANS `--compile-bytecode` : les écritures de
    l'INTERPRÉTEUR (cache de bytecode) sont ici précompilées à l'installation ;
    sans `--compile-bytecode`, un préfixe inscriptible les recevrait (24 écarts
    mesurés au premier témoin : 21 entrées `__pycache__` et les 3 dossiers qui
    les reçoivent), et sous un préfixe non inscriptible Python les omet sans
    erreur — ce banc ne joue que la forme précompilée.

SAUTS ANNONCÉS : uv absent, projet adoptant (marqueur `.agents/IS_THE_KIT`),
Windows — par décorateur —, uid 0 sur (a) et (e), et les trois sauts du build
de `batir_wheel` (`test_cadre_pkg_root.py`, importé, jamais recopié). Tout autre
échec — installation, commande, sonde, délai — est ROUGE avec son journal.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# IMPORTÉS TELS QUELS — des noms seuls, jamais une classe de test :
# `python_classes = *Tests` la ferait collecter une seconde fois ici.
from test_cadre_cli_installed import DELAI_CLI, env_blanche  # noqa: E402
from test_cadre_pkg_root import (  # noqa: E402
    EST_LE_KIT,
    SAUT_ADOPTANT,
    SAUT_UV,
    UV,
    _texte,
    batir_wheel,
    env_uv,
)

WINDOWS = os.name == "nt"
UID_ZERO = not WINDOWS and os.geteuid() == 0

#: Le nom du venv d'outil que `uv tool install` crée : celui de la distribution.
OUTIL = "cadre-kit"

SAUT_WINDOWS = ("SAUT ANNONCE : Windows — `chmod` n'y rend pas un repertoire non "
                "inscriptible ; le noyau sous un prefixe en lecture seule n'est PAS "
                "mesure par cette execution")
SAUT_UID_ZERO = ("SAUT ANNONCE : uid 0 — `chmod a-w` ne mord pas sur root ; le "
                 "lecture seule du prefixe n'est PAS mesure par cette execution")

#: LA SONDE D'ÉTAT, jouée par l'interpréteur de l'outil sous `-I`, depuis le
#: projet jetable (argv[1]). Elle RAPPORTE les racines et les chemins des trois
#: magasins que `creer_les_stores` a écrits ; elle ne juge pas. Une levée sort
#: telle quelle sur stderr : c'est elle que (e) lit.
SONDE = """\
import json, sys
from cadre.ledger.stores import creer_les_stores
from cadre.paths import config_home, pkg_root, state_home
crees = creer_les_stores(sys.argv[1])
print(json.dumps({
    "PKG_ROOT": str(pkg_root()),
    "CONFIG_HOME": str(config_home()),
    "STATE_HOME": str(state_home()),
    "v3_event_store": str(crees.v3_event_store),
    "index": str(crees.index),
    "events": str(crees.events),
}))
"""


def inventaire(racine: Path) -> dict[str, tuple[int, int, int]]:
    """Chaque entrée SOUS `racine` → `(taille, mtime_ns, mode)`, par `lstat` :
    un lien est relevé, jamais suivi. Le relevé que (b) à (e) comparent avant
    et après."""
    vu: dict[str, tuple[int, int, int]] = {}
    for base, dossiers, fichiers in os.walk(racine):
        for nom in dossiers + fichiers:
            chemin = Path(base) / nom
            st = os.lstat(chemin)
            vu[chemin.relative_to(racine).as_posix()] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return vu


def ecarts(avant: dict[str, tuple[int, int, int]],
           apres: dict[str, tuple[int, int, int]]) -> list[str]:
    """Le VERDICT « préfixe inchangé » : `+ chemin` apparu, `- chemin` disparu,
    `~ chemin` modifié, triés. Liste vide = vert."""
    return sorted([f"+ {c}" for c in apres.keys() - avant.keys()]
                  + [f"- {c}" for c in avant.keys() - apres.keys()]
                  + [f"~ {c}" for c in avant.keys() & apres.keys() if avant[c] != apres[c]])


def hors_de(rapport: dict[str, str | None], attendus: dict[str, Path]) -> list[str]:
    """Le VERDICT « chaque racine là où elle doit être » : `clé : chemin` pour
    chaque clé de `attendus` dont le chemin rapporté manque ou n'est pas SOUS
    sa base (la base elle-même compte comme dessous). Liste vide = vert."""
    fautes = []
    for cle, base in sorted(attendus.items()):
        brut = rapport.get(cle)
        if not brut or not Path(brut).resolve().is_relative_to(base.resolve()):
            fautes.append(f"{cle} : {brut} (attendu sous {base})")
    return fautes


def _chmod_arbre(racine: Path, regle: Callable[[int], int]) -> None:
    """Applique `regle` au mode de `racine` et de tout ce qu'elle contient, SANS
    SUIVRE AUCUN LIEN : le venv d'outil en porte vers l'interpréteur de base,
    HORS du préfixe, et le suivre changerait le mode d'un fichier qui n'est
    pas au banc."""
    def appliquer(chemin: Path) -> None:
        if not chemin.is_symlink():
            os.chmod(chemin, regle(stat.S_IMODE(os.lstat(chemin).st_mode)))

    appliquer(racine)
    for base, dossiers, fichiers in os.walk(racine):
        for nom in dossiers + fichiers:
            appliquer(Path(base) / nom)


def rendre_lecture_seule(racine: Path) -> None:
    """`chmod -R a-w`, liens exclus."""
    _chmod_arbre(racine, lambda mode: mode & ~0o222)


def rendre_inscriptible(racine: Path) -> None:
    """`chmod -R u+w`, liens exclus — le nettoyage en a besoin."""
    _chmod_arbre(racine, lambda mode: mode | stat.S_IWUSR)


def _supprimer(base: Path) -> None:
    """Rend l'arbre inscriptible puis le supprime. Tolère un reste : aucune
    assertion ne dépend du nettoyage."""
    try:
        rendre_inscriptible(base)
    except OSError:
        pass
    shutil.rmtree(base, ignore_errors=True)


def _lancer(argv: list[str], cwd: Path, env: dict[str, str],
            quoi: str) -> subprocess.CompletedProcess:
    """Un pas dont le code de retour est RENDU, jamais jugé ici — (e) attend un
    échec. Seul un dépassement de délai est ROUGE, nommé avec ce que le pas a
    écrit."""
    try:
        return subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=DELAI_CLI,
                              check=False)
    except subprocess.TimeoutExpired as e:
        raise AssertionError(f"{quoi} : {DELAI_CLI} s depasses\n"
                             f"{_texte(e.stdout)}{_texte(e.stderr)}") from None


def installer_sous_prefixe(roue: Path, prefixe: Path) -> tuple[Path, Path]:
    """`uv tool install` de `roue` seule, hors ligne et sans cache, ses venvs
    sous `prefixe/outils`, ses exécutables sous `prefixe/bin`, son bytecode
    PRÉCOMPILÉ (`--compile-bytecode`) : le cache de l'interpréteur naît à
    l'installation, jamais sous l'utilisateur. Rend la commande `cadre` et
    l'interpréteur de l'outil. Tout échec est ROUGE avec son journal."""
    env = env_uv() | {"UV_TOOL_DIR": str(prefixe / "outils"),
                      "UV_TOOL_BIN_DIR": str(prefixe / "bin")}
    # La cible reste sur la ligne du verbe (lisibilité ; le juge lit les lignes qui nomment cadre
    # ou portent un fragment uv/uvx, et celle qui les précède dans un pli).
    argv = [UV, "tool", "install", str(roue), "--offline", "--no-cache",
            "--compile-bytecode", "--python", sys.executable]
    r = _lancer(argv, prefixe.parent, env, "uv tool install")
    journal = r.stdout + r.stderr
    if r.returncode != 0:
        raise AssertionError(f"uv tool install en echec (rc={r.returncode}) :\n{journal}")
    commande = prefixe / "bin" / "cadre"
    python = prefixe / "outils" / OUTIL / "bin" / "python"
    for chemin in (commande, python):
        if not chemin.exists():
            raise AssertionError(f"{chemin} absent apres uv tool install :\n{journal}")
    return commande, python


def env_utilisateur(home: Path, prefixe: Path, **ajouts: str) -> dict[str, str]:
    """L'environnement d'un UTILISATEUR du poste : la liste blanche sans les
    deux clés de cache de uv, `HOME` jetable, les exécutables du préfixe en tête
    du `PATH`, puis `ajouts`."""
    env = {k: v for k, v in env_blanche(os.environ).items()
           if k.upper() not in {"XDG_CACHE_HOME", "UV_CACHE_DIR"}}
    env["HOME"] = str(home)
    env["PATH"] = os.pathsep.join([str(prefixe / "bin"), env.get("PATH", "")])
    env.update(ajouts)
    return env


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
@unittest.skipIf(WINDOWS, SAUT_WINDOWS)
class PrefixeSystemeTests(unittest.TestCase):
    """Le noyau installé sous un préfixe jetable en lecture seule, joué en
    utilisateur."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="cadre-prefixe-")).resolve()
        cls.addClassCleanup(_supprimer, cls.base)
        if cls.base.is_relative_to(ROOT):
            # Sous le dépôt, « hors de l'arbre source » ne discriminerait plus.
            raise AssertionError(f"TMPDIR est sous le depot ({cls.base}) : le temoin (b) "
                                 "ne mesurerait rien")
        roue = batir_wheel(cls.base / "wheel")
        cls.prefixe = cls.base / "prefixe"
        cls.prefixe.mkdir()
        cls.commande, cls.python = installer_sous_prefixe(roue, cls.prefixe)
        rendre_lecture_seule(cls.prefixe)

    def setUp(self):
        # Relevé PAR TÉMOIN : chacun juge ses propres écritures, jamais celles
        # d'un témoin joué avant lui (fin de la cascade b → c, d).
        self.releve = inventaire(self.prefixe)

    def _place(self, nom: str) -> tuple[Path, Path]:
        """Un `HOME` et un projet (porteur de `.agents/`, hors de tout dépôt git)
        neufs, propres au témoin `nom`."""
        home = self.base / f"home-{nom}"
        projet = self.base / f"projet-{nom}"
        home.mkdir()
        (projet / ".agents").mkdir(parents=True)
        return home, projet

    def _sonder(self, nom: str, **ajouts: str) -> tuple[subprocess.CompletedProcess, Path, Path]:
        home, projet = self._place(nom)
        r = _lancer([str(self.python), "-I", "-c", SONDE, str(projet)], projet,
                    env_utilisateur(home, self.prefixe, **ajouts), f"sonde {nom}")
        return r, home, projet

    def _rapport(self, r: subprocess.CompletedProcess, quoi: str) -> dict:
        self.assertEqual(r.returncode, 0, f"{quoi} en echec (rc={r.returncode}) :\n"
                                          f"{r.stdout}{r.stderr}")
        return json.loads(r.stdout)

    def _prefixe_inchange(self, quoi: str) -> None:
        self.assertEqual([], ecarts(self.releve, inventaire(self.prefixe)),
                         f"{quoi} : le prefixe a change sous l'utilisateur (+ apparu, "
                         "- disparu, ~ modifie)")

    def _etat_sous(self, rapport: dict, etat: Path, config: Path, projet: Path) -> None:
        self.assertEqual([], hors_de(rapport, {
            "PKG_ROOT": self.prefixe,
            "CONFIG_HOME": config,
            "STATE_HOME": etat,
            "v3_event_store": etat,
            "index": etat,
            "events": projet,
        }), "racine ou magasin hors de sa place")
        for cle in ("v3_event_store", "index", "events"):
            self.assertTrue(Path(rapport[cle]).is_file(),
                            f"{cle} rapporte mais absent du disque : {rapport[cle]}")

    @unittest.skipIf(UID_ZERO, SAUT_UID_ZERO)
    def test_a_calibration_le_prefixe_refuse_l_ecriture(self):
        """Sans ce refus, « le préfixe sort inchangé » ne dirait rien."""
        paquet = sorted(self.prefixe.glob(f"outils/{OUTIL}/lib/*/site-packages/cadre"))
        self.assertEqual(1, len(paquet), f"paquet installe introuvable : {paquet}")
        for dossier in (self.prefixe, paquet[0]):
            with self.subTest(dossier=str(dossier)):
                sonde = dossier / "sonde-ecriture"
                try:
                    sonde.touch()
                except PermissionError:
                    continue
                sonde.unlink()
                self.fail(f"{dossier} accepte une ecriture : le prefixe n'est pas en "
                          "lecture seule : un rouge de (e) n'accuse pas le noyau, et (b), "
                          "(c), (d) ne jouent pas le poste vise")

    def test_b_la_commande_installee_resout_pkg_root_sous_le_prefixe(self):
        """CRITÈRE : `PKG_ROOT` sous le préfixe, la configuration et l'état sous
        l'utilisateur — par la commande installée elle-même."""
        home, projet = self._place("paths")
        r = _lancer([str(self.commande), "paths", "--json"], projet,
                    env_utilisateur(home, self.prefixe), "cadre paths --json")
        rapport = self._rapport(r, "cadre paths --json")
        etat = home / ".local" / "state" / "cadre"
        self.assertEqual([], hors_de(rapport, {
            "PKG_ROOT": self.prefixe,
            "CONFIG_HOME": home / ".config" / "cadre",
            "STATE_HOME": etat,
            "STATE_PROJECT": etat,
            "PROJECT_ROOT": projet,
        }), "racine hors de sa place")
        self.assertFalse(Path(rapport["PKG_ROOT"]).resolve().is_relative_to(ROOT),
                         f"PKG_ROOT resout dans l'arbre source ({rapport['PKG_ROOT']}) : "
                         "c'est le paquet de l'arbre qui repond, pas le noyau installe")
        self._prefixe_inchange("cadre paths --json")

    def test_c_l_etat_s_ecrit_sous_le_home_et_jamais_sous_le_prefixe(self):
        """CRITÈRE : le noyau installé ÉCRIT l'état sous l'utilisateur."""
        r, home, projet = self._sonder("home")
        rapport = self._rapport(r, "sonde d'etat (HOME)")
        self._etat_sous(rapport, home / ".local" / "state" / "cadre",
                        home / ".config" / "cadre", projet)
        self._prefixe_inchange("creer_les_stores (HOME)")

    def test_d_l_etat_suit_xdg_quand_il_est_pose(self):
        r, _home, projet = self._sonder(
            "xdg", XDG_STATE_HOME=str(self.base / "xdg-etat"),
            XDG_CONFIG_HOME=str(self.base / "xdg-config"))
        rapport = self._rapport(r, "sonde d'etat (XDG)")
        self._etat_sous(rapport, self.base / "xdg-etat" / "cadre",
                        self.base / "xdg-config" / "cadre", projet)
        self._prefixe_inchange("creer_les_stores (XDG)")

    def test_f_le_bytecode_du_noyau_est_precompile_a_l_installation(self):
        """`--compile-bytecode` tenu : le cache de `cadre.paths` existe sous le
        prefixe AVANT tout lancement. Sans lui, seule une jambe root rougirait."""
        paquet = sorted(self.prefixe.glob(f"outils/{OUTIL}/lib/*/site-packages/cadre"))
        self.assertEqual(1, len(paquet), f"paquet installe introuvable : {paquet}")
        pyc = sorted((paquet[0] / "__pycache__").glob("paths.*.pyc"))
        self.assertTrue(pyc, f"aucun bytecode precompile sous {paquet[0]} : "
                             "`--compile-bytecode` absent de l'installation")

    @unittest.skipIf(UID_ZERO, SAUT_UID_ZERO)
    def test_e_un_etat_dirige_dans_le_prefixe_est_refuse_en_le_nommant(self):
        """`CADRE_STATE_DIR` sous le préfixe : refus, chemin nommé, rien d'écrit."""
        vise = self.prefixe / "outils" / "etat"
        r, _home, _projet = self._sonder("refus", CADRE_STATE_DIR=str(vise))
        self.assertNotEqual(0, r.returncode,
                            f"un etat dirige sous le prefixe a ete accepte :\n{r.stdout}")
        lignes = [ligne for ligne in r.stderr.splitlines() if ligne.strip()]
        derniere = lignes[-1] if lignes else ""
        self.assertTrue(derniere.startswith("cadre.paths.CadrePathError:"),
                        f"le refus n'est pas une CadrePathError nommee :\n{r.stderr}")
        self.assertIn(str(vise), derniere, f"le refus ne nomme pas {vise} :\n{r.stderr}")
        self._prefixe_inchange("refus CADRE_STATE_DIR")


class RelevePrefixeSansUvTests(unittest.TestCase):
    """L'inventaire, l'écart, le « sous » et la lecture seule, SANS uv."""

    def test_l_ecart_discrimine_les_trois_sortes(self):
        avant = {"a": (1, 1, 1), "b": (2, 2, 2), "c": (3, 3, 3)}
        apres = {"a": (1, 1, 1), "b": (2, 9, 2), "d": (4, 4, 4)}
        self.assertEqual(["+ d", "- c", "~ b"], ecarts(avant, apres))
        self.assertEqual([], ecarts(avant, dict(avant)), "inchange : vert")

    def test_l_inventaire_voit_un_ajout_et_une_modification_reels(self):
        with tempfile.TemporaryDirectory(prefix="cadre-releve-") as d:
            racine = Path(d)
            (racine / "sous").mkdir()
            (racine / "f").write_bytes(b"a")
            avant = inventaire(racine)
            (racine / "sous" / "nouveau").write_bytes(b"")
            (racine / "f").write_bytes(b"ab")
            vu = ecarts(avant, inventaire(racine))
        self.assertIn("+ sous/nouveau", vu)
        self.assertIn("~ f", vu)

    def test_hors_de_nomme_un_chemin_hors_de_sa_base_et_un_chemin_manquant(self):
        racine = Path(tempfile.gettempdir()).resolve()
        rapport = {"A": str(racine / "x" / "y"), "B": str(racine / "w"), "D": str(racine / "x")}
        attendus = {"A": racine / "x", "B": racine / "x", "C": racine / "x", "D": racine / "x"}
        self.assertEqual([f"B : {racine / 'w'} (attendu sous {racine / 'x'})",
                          f"C : None (attendu sous {racine / 'x'})"],
                         hors_de(rapport, attendus))

    @unittest.skipIf(WINDOWS, SAUT_WINDOWS)
    @unittest.skipIf(UID_ZERO, SAUT_UID_ZERO)
    def test_la_lecture_seule_mord_ne_suit_aucun_lien_et_se_leve(self):
        with tempfile.TemporaryDirectory(prefix="cadre-ro-") as d:
            racine, dehors = Path(d) / "prefixe", Path(d) / "dehors"
            (racine / "sous").mkdir(parents=True)
            (racine / "sous" / "f").write_bytes(b"a")
            dehors.write_bytes(b"")
            (racine / "lien").symlink_to(dehors)
            mode_dehors = stat.S_IMODE(os.lstat(dehors).st_mode)
            try:
                rendre_lecture_seule(racine)
                with self.assertRaises(PermissionError):
                    (racine / "sous" / "g").touch()
                with self.assertRaises(PermissionError):
                    (racine / "sous" / "f").write_bytes(b"b")
                self.assertEqual(mode_dehors, stat.S_IMODE(os.lstat(dehors).st_mode),
                                 "la cible d'un lien a perdu son droit d'ecriture : "
                                 "le lien a ete suivi")
            finally:
                rendre_inscriptible(racine)
            (racine / "sous" / "g").touch()


if __name__ == "__main__":
    unittest.main()
