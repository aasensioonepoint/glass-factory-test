#!/usr/bin/env python3
"""BANC DE PRÉCÉDENCE DES LEÇONS — `check_lesson_precedence` (T-00000639).

Étape D (point 6) de T-012, bloquant B-C3 du plan LOT-2 phase 2. La règle
`embarquee < distante < locale` s'applique À L'ÉCRITURE : une mise à jour du kit
ou un futur `lessons pull` n'écrase JAMAIS une leçon locale, et la provenance de
la leçon appliquée reste lisible.

CE FICHIER PORTE DEUX SUJETS, ET LA SÉPARATION EST STRUCTURELLE :

  1. `PrecedenceTests` EST L'IMPLÉMENTATION DÉCLARÉE DE `check_lesson_precedence`
     (statut `actif`). Cette partie ne lit AUCUN fichier qui ne voyage pas (ni
     spec, ni plan, ni état) : elle n'opère que sur un magasin en FICHIER
     TEMPORAIRE RÉEL et sur le paquet `cadre.ledger`, qui voyage. Aucun `skip` ne
     s'y applique — sur ce poste comme sur un arbre adoptant — pour qu'elle ne
     « tourne pas mais saute » (faute que `test_checks_manifest.py` refuse).

  2. `SurfacesDeLeconsTests` (T-00000644, étape E point 9) énumère les QUATRE
     surfaces de leçons du kit, écrit la règle d'autorité `LEDGER.json` >
     `retro/LESSONS.md`, et rejoue le `git grep` R-B1 pour qu'un magasin de leçons
     NON DÉCLARÉ rougisse. CETTE partie LIT des surfaces KIT-ONLY qui ne voyagent
     pas (le registre `lesson_surfaces.json`, `strip:`-é ; les chemins `retro/` et
     `.agents/state/` remontés par le grep) : elle est donc gardée par `EST_LE_KIT`
     et SAUTE sur un arbre adoptant, où ces surfaces n'existent pas. Ce saut ne
     concerne JAMAIS `test_checks_manifest.py`, qui tourne sur le kit (où
     `EST_LE_KIT` est vrai et rien ne saute). Les deux références littérales à un
     chemin non voyageur (`.agents/IS_THE_KIT`, le registre) portent le marqueur
     `# adopting-tree:` — forme (d) du localisateur de `test_adopting_gate.py`.

LE TÉMOIN DE PRÉCÉDENCE PROUVE LES TROIS SENS de B-C3, et un CONTRÔLE NÉGATIF
prouve que ces sens sont portants : un « magasin qui ajoute sans règle » (la
décision de précédence remplacée par « toujours appliquer la dernière écrite »)
fait ROUGIR le témoin — et ce banc le démontre lui-même. Deux autres contrôles
négatifs (partie 2) prouvent leurs assertions portantes : inverser l'autorité
`LEDGER.json` ↔ `retro/LESSONS.md` rougit, et une surface de leçon non déclarée
ajoutée au résultat du grep rougit.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
#: Le résolveur du paquet `cadre`, chargé PAR CHEMIN (patron v3prep, S-01M5BXT85VP4JBBMXVXR9STP5F) :
#: `charger_paquet` charge `.agents/vendor/cadre` (ou l'ancien `src/cadre`) sans toucher `sys.path`.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_precedence_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = VENDOR
_SPEC_VENDOR.loader.exec_module(VENDOR)
VENDOR.charger_paquet(ROOT, "cadre")

from cadre.ledger import ids, lessons, precedence, schema, store, version  # noqa: E402

T = dict(tenant_id="t", project_id="p")

# ---------------------------------------------------------------------------
# T-00000644 — LES QUATRE SURFACES DE LEÇONS, ET LE REGISTRE KIT-ONLY QUI LES PORTE
# ---------------------------------------------------------------------------
# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « arbre adoptant », où la partie 2 saute.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

# adopting-tree: le registre des surfaces de leçons est kit-only (strip:) ; absent
# chez l'adoptant, la partie 2 saute avant de le lire.
REGISTRE = ROOT / ".agents" / "evals" / "lesson_surfaces.json"

#: Les deux surfaces VIVANTES que la règle d'autorité départage (chaînes nues,
#: jamais accolées à `ROOT` : le localisateur ne les signale donc pas).
LEDGER = ".agents/state/memory/LEDGER.json"
RETRO = "retro/LESSONS.md"

#: EXCLUSIONS NOMMÉES du grep R-B1 : des surfaces qui CITENT les leçons sans en
#: STOCKER. Par préfixe de répertoire (catégories entières, SAUF un fichier de
#: magasin : voir `MAGASIN_SUFFIXES`) ou par prédicat de nom (bancs). Un fichier
#: remonté par le grep qui n'est ni un `fichier_de_surface` du registre ni couvert
#: ici est un magasin NON DÉCLARÉ, et il rougit.
CITENT_PREFIXES = {
    "docs/": "documentation, plans, ADR : citent la boucle de leçons",
    ".agents/skills/": "skills : décrivent la boucle (context-retro, lessons-seed, retro-lessons)",
    ".agents/evals/": "bancs et fixtures du kit (dont ce banc et le registre)",
    ".agents/state/board/": "board : stocke des TÂCHES ; le texte des tâches cite",
    "runs/": "exports du run (T-00000677) : sérialisent des observations board dont le texte de tâche cite ; ne stockent AUCUNE leçon",
    ".agents/state/specs/": "specs : stocke des checkpoints ; leur texte cite",
    ".agents/state/index/": "index machine : cite les symboles, ne stocke pas de leçon",
    ".claude/agents/": "défs d'agents (Claude) : citent la boucle",
    ".codex/agents/": "défs d'agents (Codex)",
    ".gemini/agents/": "défs d'agents (Gemini)",
    ".github/agents/": "défs d'agents (Copilot)",
    ".kimi-code/agents/": "défs d'agents (Kimi)",
    "agents/": "source unique des défs d'agents (S-01M5C01EAKQACKA27PNH804CR3), rendue vers les hôtes : cite la boucle",
    ".cursor/rules/": "rendus Cursor des défs d'agents (render_hosts.py) : citent la boucle",
    ".claude/hooks/": "hooks : invoquent retro, ne stockent pas",
    "src/cadre/data/roster/": "roster canonique (T-00000973) : rendus des défs d'agents, citent la boucle de leçons sans la stocker",
}
CITENT_EXACTS = {
    ".template-exclude": "canal template : nomme retro/ pour le strip",
    "verifier-agent.md": "contrat exec-critic portable : cite les causes de leçons",
    "PLAN-ETAT-DETAIL.md": "état de chantier : cite",
}

#: T-00000672 — FORMES DE MAGASIN : un fichier dont l'extension (casse ignorée) est
#: celle d'une base ou d'un DDL ne CITE jamais, il STOCKE. Aucun préfixe, nom ni
#: exact de ce banc ne l'admet : sans ce refus, un `lecons.db` posé sous
#: `.agents/state/index/`, `board/`, `specs/` ou `.agents/evals/` passait le grep
#: R-B1 en bloc. `.sql` en est, parce que le contrôle négatif du motif prend
#: `fantome.sql` pour l'archétype d'un magasin fantôme. Les COMPAGNONS SQLite
#: (`COMPAGNON_SUFFIXES` : `lecons.db-wal`, `x.sqlite-journal`, `LECONS.DB-SHM`)
#: en sont aussi : une connexion WAL ouverte pendant `git add` laisse le DDL dans
#: le seul `-wal`, l'unique fichier que le grep R-B1 remonte (S-00004523). Liste
#: BORNÉE, non exhaustive : une autre forme (`.duckdb`, `.db.bak`, `.db.gz`, un
#: `.json`, `.jsonl` ou `.py` qui stocke) reste admise par son préfixe, le
#: prédicat ne lisant que le chemin, jamais le contenu ; les compagnons NON
#: retirés aussi — `-wal2` (mode WAL2) et le super-journal `-mjXXXXXXXX` d'une
#: transaction sur plusieurs bases (`lecons.db-wal2` reste admis).
MAGASIN_SUFFIXES = (".db", ".db3", ".sqlite", ".sqlite3", ".sql")
COMPAGNON_SUFFIXES = ("-wal", "-shm", "-journal")


def est_un_fichier_de_magasin(base: str) -> bool:
    """Le nom de base `base` a-t-il la FORME d'un magasin ? Casse ignorée ; un
    suffixe compagnon (`-wal`, `-shm`, `-journal`) est retiré avant le test."""
    nom = base.lower()
    for compagnon in COMPAGNON_SUFFIXES:
        if nom.endswith(compagnon):
            nom = nom[: -len(compagnon)]
            break
    return nom.endswith(MAGASIN_SUFFIXES)


def cite_sans_stocker(chemin: str) -> bool:
    """`chemin` (relatif à ROOT) CITE-t-il les leçons sans en stocker ? Un banc,
    une doc, une skill, une déf d'agent, un autre store — jamais un magasin de
    leçons. Un fichier de magasin ou son compagnon (`est_un_fichier_de_magasin`)
    n'est JAMAIS admis, quel que soit son répertoire. Fail-closed : ce qui n'est
    pas reconnu ici (et pas au registre) rougit."""
    base = chemin.rsplit("/", 1)[-1]
    if est_un_fichier_de_magasin(base):
        return False
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith(".test.sh"):
        return True
    if chemin in CITENT_EXACTS:
        return True
    return any(chemin.startswith(p) for p in CITENT_PREFIXES)


#: Un `fichier_de_surface` fini par `/` déclare un DOSSIER d'enregistrements (T-01M4KKMY43ZKCW1YD2Y8JX9MKH : le ledger
#: en forme dossier, `memory/entries/`) : il n'y admet QUE des noms d'enregistrement de leçon — `L-<1 à 15
#: chiffres>.json` ou `L-<ULID>.json`, directement dedans ; tout autre nom (un `lecons.db` posé là, T-672) reste NON
#: DÉCLARÉ.
_NOM_ENREGISTREMENT_LECON = re.compile(r"L-(?:[0-9]{1,15}|[0-9A-HJKMNP-TV-Z]{26})\.json")


def declaree_au_registre(chemin: str, proprietes: set[str]) -> bool:
    """`chemin` est un `fichier_de_surface` du registre : nommé tel quel, ou enregistrement de leçon d'un DOSSIER."""
    if chemin in proprietes:
        return True
    return any(p.endswith("/") and chemin.startswith(p) and _NOM_ENREGISTREMENT_LECON.fullmatch(chemin[len(p):])
               for p in proprietes)


def surfaces_grep(root: Path, env: dict[str, str] | None = None) -> list[str]:
    """R-B1 rejoué : `git grep -lEi '<motif>'` sur les fichiers SUIVIS du dépôt.
    Rend les chemins relatifs à `root`. rc 1 (aucun match) ou rc 0 (matches) sont
    tous deux normaux ; toute autre sortie laisse la liste parler d'elle-même.

    `env` : l'environnement du `git grep` (défaut : celui du processus). Un banc
    qui greppe un dépôt JETABLE passe `env_git_jetable(...)` — sans quoi, lancé
    hors pytest avec un `GIT_DIR` hérité, `git -C <tmp> grep` lit le dépôt HÔTE
    (T-00000672, revue de clôture S-00004528).

    MOTIF ÉLARGI par le binôme PORTE 3 (C5) : il remonte désormais AUSSI le
    magasin de leçons de Phase 2 (`schema.py` via `TABLE = "lecons"`,
    `precedence.py` via `lecon_appliquee`), tous deux déclarés au registre."""
    motif = ('lessons_learned|LESSONS\\.md|CREATE TABLE.*(lesson|lecon)|'
             'TABLE = "lecons"|lecon_appliquee')
    # T-00000671 — `LC_ALL=C` N'EST PAS UNE COMMODITÉ, C'EST CE QUI REND LES DEUX
    # JAMBES DE LA PORTE COMPARABLES. Mesuré le 2026-09-20 sur le MÊME git 2.55.0
    # et le même fichier (`.agents/state/v3_event_store.db`, qui porte `lecon_…`
    # en DONNÉE) : sous `fr_FR.UTF-8` ce `git grep -lEi` rend rc 1, sous `LC_ALL=C`
    # il rend rc 0 ; avec `-a` (forcer texte) il rend rc 1 AUSSI, et en `-F`
    # (littéral, hors regex) rc 0. Ce n'est donc ni la version de `git` ni la
    # détection de binaires : c'est le moteur de regex de la libc, qui n'apparie
    # pas une ligne à octets invalides sous une locale UTF-8. La jambe conteneur
    # de `verify.sh --linux` ne reçoit aucun `LANG` (`docker run` ne passe que
    # `-e APT_PKGS`), donc elle tourne en POSIX et VOIT ce que la jambe locale
    # saute. Sans cette ligne, ce banc est vert chez le développeur et rouge en
    # CI sans qu'une ligne ait bougé — et l'inverse dès qu'un dev exporte
    # `LC_ALL=C`. On fixe la locale pour que le PÉRIMÈTRE du balayage ne dépende
    # plus de l'environnement de celui qui le joue.
    # T-00000677 (2026-09-21) : le fichier-EXEMPLE ci-dessus,
    # `.agents/state/v3_event_store.db`, a QUITTÉ les suivis (désindexé par ce lot),
    # donc `git grep` ne le remonte plus. `LC_ALL=C` est CONSERVÉ tel quel — la
    # sensibilité à la locale du moteur regex de la libc reste un fait général, la
    # divergence local/conteneur reste réelle, et AUCUNE assertion n'est relâchée
    # (plancher `> 20` mesuré avant/après : 71 → 70, sans approche de la borne).
    out = subprocess.run(
        ["git", "-C", str(root), "grep", "-lEi", motif],
        capture_output=True, text=True,
        env={**(os.environ if env is None else env), "LC_ALL": "C"},
    )
    return list(dict.fromkeys(alias_paquet(ligne) for ligne in out.stdout.split("\n") if ligne))


#: ALIAS DU PAQUET (S-01M5BXT85VP4JBBMXVXR9STP5F, PLAN_GRAMMAIRE § 4) : `src/cadre/` nomme le paquet `cadre`
#: où qu'il vive ; un fichier remonté sous `.agents/vendor/cadre/` est lu sous son nom `src/cadre/`, celui du
#: registre et des exclusions. Une entrée par règle, jamais une règle dupliquée par préfixe.
ALIAS_VENDOR = (".agents/vendor/cadre/", "src/cadre/")


def alias_paquet(chemin: str) -> str:
    """`chemin` sous son nom de registre : le préfixe vendor du paquet `cadre` réécrit en `src/cadre/`."""
    neuf, ancien = ALIAS_VENDOR
    return ancien + chemin[len(neuf):] if chemin.startswith(neuf) else chemin


def env_git_jetable(xdg: Path) -> dict[str, str]:
    """Environnement des `git` qui CONSTRUISENT un dépôt jetable (forme `_git_env`
    de `test_docs_only_route_contract.py`). Toute variable `GIT_*` héritée est
    retirée : lancé depuis un hook, `GIT_DIR`, `GIT_INDEX_FILE` ou `GIT_WORK_TREE`
    feraient viser au `git -C <tmp>` le dépôt HÔTE (S-00004524). La config globale
    est vide, aucune config système n'est lue, et `XDG_CONFIG_HOME` est jetable :
    `$XDG_CONFIG_HOME/git/ignore`, l'`excludesFile` PAR DÉFAUT, est lu même sous
    `GIT_CONFIG_GLOBAL` — sans quoi un `*-wal` du poste vide le témoin WAL."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["XDG_CONFIG_HOME"] = str(xdg)
    return env


class _StoreReelMixin(unittest.TestCase):
    def _store_reel(self):
        """Un magasin sur FICHIER RÉEL, schéma v2 garanti (jamais `:memory:`, qui
        rend 0 objet à l'appelant). Nettoyage enregistré."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        conn = store.connect(Path(tmp.name) / "lecons.db")
        self.addCleanup(conn.close)
        version.garantir_schema(conn)
        return conn

    def _compte(self, conn, cle_sujet: str) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM " + schema.TABLE + " WHERE cle_sujet = ?",
            (cle_sujet,),
        ).fetchone()[0]

    def _insP(self, conn, *, cle_sujet, provenance, contenu,
              tenant_id="t", project_id="p",
              statut_partage="revue_faite",
              revue_par="kit", revue_horodatage="2026-01-01T00:00:00+00:00"):
        """Insère (bas niveau) UNE ligne PARTAGEABLE — l'exact objet qu'un import du
        kit écrira (`portee='partageable'`, provenance donnée, jamais `locale`,
        spec:287-289). `inserer` ne déduplique pas et n'applique AUCUNE précédence,
        donc cette ligne n'a AUCUN pointeur : le cas que seule `lecons_appliquees`
        peut voir.

        DÉFAUT `revue_faite` (avec `revue_par`/`revue_horodatage` ENSEMBLE — sans quoi
        le CHECK schema.py:153-154 lève avant l'assertion) depuis la décision pilote
        `S-00001665` : une partageable d'un AUTRE tenant ne s'applique QUE revue ; une
        fixture par défaut `en_attente_de_revue` serait donc écartée du résultat
        cross-tenant. Les témoins qui veulent un BROUILLON non revu le demandent
        EXPLICITEMENT (`statut_partage='en_attente_de_revue'`)."""
        ul = ids.nouvel_ulid()
        lessons.inserer(conn, lessons.Lecon(
            ulid=ul, hash_contenu="h:" + contenu, contenu=contenu, cle_sujet=cle_sujet,
            portee="partageable", provenance=provenance, statut_partage=statut_partage,
            statut_sync="local", version_schema_lecon=1, tenant_id=tenant_id,
            project_id=project_id, horodatage="2026-01-01T00:00:00+00:00",
            revue_par=revue_par, revue_horodatage=revue_horodatage))
        return ul

    def _scenario_sens_c(self, conn):
        """LE SENS (c) sous le NOUVEAU modèle, extrait pour être relu.

        Sur un sujet PORTANT une locale, `lecon_appliquee` rend la locale ; sur un
        sujet SANS locale mais avec une partageable embarquée, `lecon_appliquee`
        rend `None` (aucun pointeur) tandis que `lecons_appliquees` rend la
        partageable (spec:291). C'est l'assertion que le contrôle négatif de bras 1
        (pour la locale) ne touche plus : ce scénario n'entre PAS sous patch.
        """
        lessons.ecrire_lecon(conn, contenu="A locale", cle_sujet="A",
                             provenance="locale", **T)
        app_a = precedence.lecon_appliquee(conn, "A", **T)
        self.assertIsNotNone(app_a, "aucune leçon appliquée pour un sujet à locale")
        self.assertEqual(app_a["provenance"], "locale",
                         "l'appliquée d'un sujet à locale N'EST PAS la locale")

        emb = self._insP(conn, cle_sujet="B", provenance="embarquee",
                         contenu="B embarquee")
        self.assertIsNone(precedence.lecon_appliquee(conn, "B", **T),
                          "un sujet SANS locale ne doit poser AUCUN pointeur local")
        app_b = precedence.lecons_appliquees(conn, "B", **T)
        self.assertEqual([r["ulid"] for r in app_b], [emb],
                         "sur un sujet SANS locale, lecons_appliquees doit rendre la "
                         "partageable là où lecon_appliquee rend None")

    def _scenario_local(self, conn):
        """Précédence du POINTEUR LOCAL (bras 1 du contrôle négatif) : une locale
        puis une distante sur un sujet neuf. La locale (rang 2) DOMINE la distante
        (rang 1), donc l'appliquée reste la locale. Sous `doit_devenir_appliquee`
        forcée à `True`, la distante écrite après volerait le pointeur → échec."""
        lessons.ecrire_lecon(conn, contenu="C locale", cle_sujet="C",
                             provenance="locale", **T)
        lessons.ecrire_lecon(conn, contenu="C distante", cle_sujet="C",
                             provenance="distante", **T)
        app = precedence.lecon_appliquee(conn, "C", **T)
        self.assertEqual(app["provenance"], "locale",
                         "une distante écrite APRÈS ne doit pas voler le pointeur à "
                         "la locale (précédence du pointeur local rompue)")

    def _scenario_partageable(self, conn):
        """Précédence entre PARTAGEABLES (bras 2 du contrôle négatif) : deux
        partageables de rangs DIFFÉRENTS sur le même sujet. La locale (rang 2)
        domine l'embarquée (rang 0), donc UNE seule s'applique. Sous
        `gagnantes_partageables` remplacée par l'identité (sans filtre de rang), les
        DEUX sortent → échec."""
        self._insP(conn, cle_sujet="D", provenance="locale", contenu="D part locale",
                   tenant_id="t1", project_id="p1")
        self._insP(conn, cle_sujet="D", provenance="embarquee", contenu="D part kit",
                   tenant_id="tKit", project_id="pKit")
        app = precedence.lecons_appliquees(conn, "D", tenant_id="t9", project_id="p9")
        self.assertEqual(len(app), 1,
                         "entre partageables de rangs différents, seule la dominante "
                         "s'applique")
        self.assertEqual(app[0]["provenance"], "locale")


class PrecedenceTests(_StoreReelMixin):
    def test_la_precedence_des_lecons_survit_a_un_lot_embarque(self):
        """RÉÉCRIT sous le nouveau modèle (spec:287-289) : un lot embarqué est une
        PARTAGEABLE (`portee='partageable'`, `provenance='embarquee'`), jamais une
        locale. La locale garde son pointeur (rien d'écrasé), la partageable est
        présente (rien d'oublié), et `lecons_appliquees` rend LES DEUX (portées
        différentes, spec:293-295)."""
        conn = self._store_reel()

        # (a) RIEN D'ÉCRASÉ. La locale est écrite (pointeur posé), puis une
        #     PARTAGEABLE embarquée arrive sur le MÊME sujet : la locale relue est
        #     IDENTIQUE et son pointeur est INCHANGÉ.
        loc, _ = lessons.ecrire_lecon(conn, contenu="la locale du sujet",
                                      cle_sujet="S", provenance="locale", **T)
        avant = lessons.lire_lecon(conn, loc)
        ptr = precedence.ulid_applique(conn, "S", **T)
        emb = self._insP(conn, cle_sujet="S", provenance="embarquee",
                         contenu="le lot embarqué")
        apres = lessons.lire_lecon(conn, loc)
        self.assertEqual(apres, avant, "la locale a été MODIFIÉE par le lot embarqué")
        self.assertEqual(precedence.ulid_applique(conn, "S", **T), ptr,
                         "le pointeur local a bougé à l'arrivée d'une embarquée "
                         "partageable — la locale a été écrasée")

        # (b) RIEN D'OUBLIÉ. La partageable embarquée est PRÉSENTE, provenance et
        #     portée lisibles.
        rel_emb = lessons.lire_lecon(conn, emb)
        self.assertIsNotNone(rel_emb, "le lot embarqué a été JETÉ")
        self.assertEqual((rel_emb["portee"], rel_emb["provenance"]),
                         ("partageable", "embarquee"))

        # POPULATION NON VIDE : locale + partageable coexistent sur le sujet.
        self.assertEqual(self._compte(conn, "S"), 2,
                         "locale et partageable embarquée doivent coexister")

        # (c) lecons_appliquees rend LES DEUX (portées différentes).
        app = precedence.lecons_appliquees(conn, "S", **T)
        self.assertEqual({r["ulid"] for r in app}, {loc, emb},
                         "lecons_appliquees ne rend pas LES DEUX (locale + partageable)")
        self._scenario_sens_c(conn)

    def test_un_magasin_qui_ajoute_sans_regle_fait_ROUGIR_le_temoin(self):
        """CONTRÔLE NÉGATIF, DEUX BRAS, PROUVÉ PAR CE BANC LUI-MÊME.

        La précédence a désormais DEUX points d'injection : `doit_devenir_appliquee`
        (le POINTEUR LOCAL, à l'écriture) et `gagnantes_partageables` (entre
        PARTAGEABLES, en lecture). Un « magasin qui ajoute sans règle » se fabrique
        en remplaçant l'une OU l'autre — et chaque scénario doit alors ÉCHOUER, puis
        PASSER hors patch, sans quoi l'échec ne prouverait rien.
        """
        # BRAS 1 : décision du POINTEUR LOCAL nullifiée (« toujours appliquer »).
        with mock.patch.object(precedence, "doit_devenir_appliquee",
                               lambda rn, rc: True):
            with self.assertRaises(AssertionError):
                self._scenario_local(self._store_reel())
        self._scenario_local(self._store_reel())  # HORS patch : la règle tient

        # BRAS 2 : décision entre PARTAGEABLES nullifiée (aucun filtre de rang).
        with mock.patch.object(precedence, "gagnantes_partageables",
                               lambda lignes: list(lignes)):
            with self.assertRaises(AssertionError):
                self._scenario_partageable(self._store_reel())
        self._scenario_partageable(self._store_reel())  # HORS patch : la règle tient

    # -- TÉMOINS de `lecons_appliquees` : la précédence par portée EN LECTURE ------

    def test_une_locale_et_une_partageable_du_meme_sujet_sont_TOUTES_DEUX_appliquees(self):
        """TÉMOIN 1. Une locale (pointeur posé) et sa forme généralisée (partageable,
        SANS pointeur) sur le même sujet : `lecons_appliquees` rend LES DEUX. Mord
        sur CETTE fixture parce que la partageable n'a AUCUN pointeur — seule la
        branche neuve (membre 2) peut la voir."""
        conn = self._store_reel()
        loc, gen = lessons.ecrire_lecon(conn, contenu="contexte projet", cle_sujet="S",
                                        forme_generalisee="leçon générique", **T)
        self.assertIsNotNone(gen, "aucune forme généralisée écrite")
        app = precedence.lecons_appliquees(conn, "S", **T)
        self.assertEqual({r["ulid"] for r in app}, {loc, gen},
                         "la locale ET la partageable doivent TOUTES DEUX s'appliquer")
        self.assertEqual(len(app), 2)

    def test_sur_un_sujet_SANS_locale_la_partageable_est_rendue_la_ou_lecon_appliquee_rend_None(self):
        """TÉMOIN 2. Un sujet neuf ne portant QU'UNE partageable embarquée du kit,
        aucune locale, aucun pointeur : vue d'un tenant adoptant, `lecon_appliquee`
        rend `None` et `lecons_appliquees` rend cette ligne. C'est l'INVERSION de
        spec:291. Mord parce que la fixture n'a AUCUNE locale : le membre (1) ne
        rend rien."""
        conn = self._store_reel()
        emb = self._insP(conn, cle_sujet="K", provenance="embarquee",
                         contenu="leçon du kit", tenant_id="tKit", project_id="pKit")
        self.assertIsNone(
            precedence.lecon_appliquee(conn, "K", tenant_id="t1", project_id="p1"),
            "aucun pointeur local ne doit exister sur un sujet sans locale")
        app = precedence.lecons_appliquees(conn, "K", tenant_id="t1", project_id="p1")
        self.assertEqual([r["ulid"] for r in app], [emb],
                         "la partageable du kit doit être rendue là où "
                         "lecon_appliquee rend None")

    def test_entre_partageables_le_rang_tranche_TOUS_TENANTS_confondus(self):
        """TÉMOIN 3. Deux partageables de rangs DIFFÉRENTS sur le même sujet, chez
        deux tenants : `t1` locale (rang 2), `tKit` embarquee (rang 0). Vue de
        `tKit` : la partageable de `t1` SEULE. Mord : filtre au rang maximal
        retiré → les deux sortent."""
        conn = self._store_reel()
        p1 = self._insP(conn, cle_sujet="R", provenance="locale", contenu="R part t1",
                        tenant_id="t1", project_id="p1")
        self._insP(conn, cle_sujet="R", provenance="embarquee", contenu="R part kit",
                   tenant_id="tKit", project_id="pKit")
        app = precedence.lecons_appliquees(conn, "R", tenant_id="tKit", project_id="pKit")
        self.assertEqual([r["ulid"] for r in app], [p1],
                         "entre partageables, le rang tranche TOUS TENANTS confondus")

    def test_une_distante_domine_une_embarquee_entre_partageables(self):
        """B-(4) — le rang MÉDIAN (`distante`) n'était plus témoigné : le seul témoin
        de rang opposait `locale` à `embarquee`, si bien que permuter `distante` et
        `embarquee` dans `PRECEDENCE` laissait 32 verts. Deux partageables REVUES
        (donc applicables cross-tenant, défaut `_insP`) de rangs `distante`/`embarquee`
        sur le même sujet, lues par un tiers : seule la `distante` (rang 1) est rendue.
        Mord : permuter `distante`/`embarquee` dans `precedence.PRECEDENCE`."""
        conn = self._store_reel()
        d = self._insP(conn, cle_sujet="V", provenance="distante", contenu="V dist",
                       tenant_id="t1", project_id="p1")
        self._insP(conn, cle_sujet="V", provenance="embarquee", contenu="V kit",
                   tenant_id="tKit", project_id="pKit")
        app = precedence.lecons_appliquees(conn, "V", tenant_id="t9", project_id="p9")
        self.assertEqual([r["ulid"] for r in app], [d],
                         "une distante doit dominer une embarquée (rang médian témoigné)")

    def test_S1665_un_brouillon_EN_ATTENTE_d_un_AUTRE_tenant_ne_s_applique_pas(self):
        """S-00001665 (option A), moitié CROSS-TENANT. Un brouillon
        `en_attente_de_revue` d'un AUTRE tenant, sur un sujet où le kit a une leçon
        REVUE, ne s'applique pas chez moi ET ne masque plus la leçon revue. Mord :
        retirer la clause `AND ((tenant auteur) OR statut_partage IN ('revue_faite',
        'partage'))` (revenir à l'avant-correctif) → le brouillon d'autrui (rang
        locale) repasse et masque le kit (rang embarquee)."""
        conn = self._store_reel()
        kit = self._insP(conn, cle_sujet="G", provenance="embarquee", contenu="G kit",
                         tenant_id="tKit", project_id="pKit")  # revue_faite (défaut)
        self._insP(conn, cle_sujet="G", provenance="locale", contenu="G brouillon t-A",
                   tenant_id="t-A", project_id="p-A",
                   statut_partage="en_attente_de_revue")
        app = precedence.lecons_appliquees(conn, "G", tenant_id="t-B", project_id="p-B")
        self.assertEqual([r["ulid"] for r in app], [kit],
                         "le brouillon non revu d'un autre tenant s'applique encore "
                         "chez moi (ou masque la leçon revue du kit)")

    def test_S1665_un_brouillon_EN_ATTENTE_de_MON_tenant_s_applique_chez_MOI(self):
        """S-00001665 (option A), moitié TENANT AUTEUR — le témoin qui MANQUAIT. Mon
        propre brouillon `en_attente_de_revue` CONTINUE de s'appliquer chez moi : la
        revue n'est exigée que pour la partageable d'AUTRUI. Mord : retirer la branche
        `(l.tenant_id = ? AND l.project_id = ?)` de la requête — mon brouillon, non
        revu, disparaît alors du résultat."""
        conn = self._store_reel()
        mien = self._insP(conn, cle_sujet="W", provenance="locale",
                          contenu="W mon brouillon", tenant_id="t1", project_id="p1",
                          statut_partage="en_attente_de_revue")
        app = precedence.lecons_appliquees(conn, "W", tenant_id="t1", project_id="p1")
        self.assertEqual([r["ulid"] for r in app], [mien],
                         "le brouillon en attente de MON tenant ne s'applique plus "
                         "chez moi (branche tenant auteur perdue)")

    def test_deux_partageables_ex_aequo_sont_TOUTES_DEUX_rendues(self):
        """TÉMOIN 4. Deux partageables `locale` (MÊME rang) sur le même sujet, chez
        `t1` et `t2` → LES DEUX rendues, ordre déterministe (portee, tenant, projet,
        ulid). Mord : « la plus récente gagne » à la place du rang max → 1 seule."""
        conn = self._store_reel()
        a = self._insP(conn, cle_sujet="X", provenance="locale", contenu="X chez t1",
                       tenant_id="t1", project_id="p1")
        b = self._insP(conn, cle_sujet="X", provenance="locale", contenu="X chez t2",
                       tenant_id="t2", project_id="p2")
        app = precedence.lecons_appliquees(conn, "X", tenant_id="t9", project_id="p9")
        self.assertEqual({r["ulid"] for r in app}, {a, b},
                         "deux partageables ex æquo doivent TOUTES DEUX être rendues")
        self.assertEqual([r["tenant_id"] for r in app], ["t1", "t2"],
                         "l'ordre n'est pas déterministe (portee, tenant, projet, ulid)")

    def test_une_partageable_REVOQUEE_ne_s_applique_pas_et_ne_masque_pas_les_autres(self):
        """TÉMOIN 5. Une partageable `revoque` (rang locale 2) et une `revue_faite`
        (rang embarquee 0), même sujet. La révoquée ne s'applique pas ET ne masque
        pas la valide → seule la `revue_faite` est rendue. La ligne `revue_faite`
        porte `revue_par` ET `revue_horodatage` (sans eux schema.py:153-154 lève
        avant toute assertion). Mord : écart `revoque` retiré → le rang max devient
        2, la valide sort et la révoquée entre. `revoque` n'a aucun écrivain
        aujourd'hui, la fixture l'insère à la main : filtre PROSPECTIF.

        LECTURE DU TENANT AUTEUR de la révoquée (`t1`) — et c'est LOAD-BEARING depuis
        `S-00001665` : une révoquée d'un AUTRE tenant est déjà écartée AU SQL (non
        revue) et n'atteindrait jamais `gagnantes_partageables`, ce qui rendait ce
        témoin MORT (mutation « écart revoque retiré » restait verte, mesuré). En
        lisant du tenant `t1`, la révoquée passe la branche tenant du filtre, atteint
        `gagnantes_partageables`, et l'écart `revoque` y reste EXERCÉ."""
        conn = self._store_reel()
        rev = self._insP(conn, cle_sujet="Q", provenance="locale", contenu="Q révoquée",
                         tenant_id="t1", project_id="p1", statut_partage="revoque")
        ok = self._insP(conn, cle_sujet="Q", provenance="embarquee", contenu="Q valide",
                        tenant_id="t2", project_id="p2", statut_partage="revue_faite",
                        revue_par="Alice", revue_horodatage="2026-02-02T00:00:00+00:00")
        app = precedence.lecons_appliquees(conn, "Q", tenant_id="t1", project_id="p1")
        self.assertEqual([r["ulid"] for r in app], [ok],
                         "la révoquée ne doit pas s'appliquer, ni masquer la valide")
        self.assertNotIn(rev, {r["ulid"] for r in app})

    def test_un_pointeur_qui_nomme_une_partageable_ne_la_rend_pas_DEUX_fois(self):
        """TÉMOIN 6 — le témoin du DOUBLON. Une seule partageable, et un pointeur
        `lecon_appliquee` posé À LA MAIN sur elle (le seul cas où un pointeur nomme
        une partageable, rendu possible par la PK à 3 colonnes et la FK
        schema.py:202 ; aucun écrivain de production ne le produit). Attendu : UNE
        ligne, ulids deux à deux distincts. Mord : écart du geste (3) retiré → deux
        lignes IDENTIQUES, car lecon_appliquee ne filtre pas la portée de la ligne
        pointée."""
        conn = self._store_reel()
        ul = self._insP(conn, cle_sujet="P", provenance="locale", contenu="P partageable")
        conn.execute(
            "INSERT INTO " + schema.TABLE_APPLIQUEE
            + " (tenant_id, project_id, cle_sujet, ulid) VALUES (?, ?, ?, ?)",
            ("t", "p", "P", ul))
        conn.commit()
        app = precedence.lecons_appliquees(conn, "P", **T)
        self.assertEqual(len(app), 1,
                         "le pointeur et la partageable rendent la MÊME ligne DEUX fois")
        ulids = [r["ulid"] for r in app]
        self.assertEqual(len(set(ulids)), len(ulids), "un ulid est rendu deux fois")

    def test_une_lecon_locale_n_est_JAMAIS_candidate_au_partage_et_sa_forme_generalisee_est_un_objet_DISTINCT(self):
        """AXE DUALITÉ, angle « jamais candidate au partage » — COMPLÉMENTAIRE de
        `test_cadre_ledger.py::DualiteTests`, qui prouve le LIEN et la non-fusion.
        Ici : la locale (`statut_partage='prive'`) n'apparaît dans AUCUNE requête
        de leçons sortables, et sa forme généralisée est un enregistrement
        DISTINCT, seul marqué partageable.
        """
        conn = self._store_reel()
        loc, gen = lessons.ecrire_lecon(
            conn, contenu="contexte projet", cle_sujet="D", origine_projet="projet-X",
            forme_generalisee="leçon générique sans contexte", **T)
        self.assertIsNotNone(gen, "aucune forme généralisée écrite")
        self.assertNotEqual(loc, gen, "les deux enregistrements ne sont pas distincts")

        # « ne SORT jamais par construction » : une requête de candidates au
        # partage (statut ≠ 'prive') rend la généralisée, JAMAIS la locale.
        sortables = {r["ulid"] for r in conn.execute(
            "SELECT ulid FROM " + schema.TABLE + " WHERE statut_partage <> 'prive'")}
        self.assertTrue(sortables, "aucune candidate au partage — banc vide")
        self.assertIn(gen, sortables, "la forme généralisée doit être candidate")
        self.assertNotIn(loc, sortables,
                         "la locale est candidate au partage — garantie de fond rompue")

        rloc = lessons.lire_lecon(conn, loc)
        self.assertEqual(rloc["portee"], "locale")
        self.assertEqual(rloc["statut_partage"], "prive")
        self.assertEqual(rloc["ref_forme_generalisee"], gen, "le lien local→généralisée est rompu")
        rgen = lessons.lire_lecon(conn, gen)
        self.assertEqual(rgen["portee"], "partageable")
        self.assertIsNone(rgen["origine_projet"], "la généralisée porte un contexte projet")
        # DISTINCTS, jamais fusionnés : deux lignes pour ce sujet.
        self.assertEqual(self._compte(conn, "D"), 2,
                         "locale + généralisée doivent être DEUX enregistrements")

    def test_la_montee_v2_pose_la_table_de_precedence_de_facon_idempotente(self):
        """La précédence vit dans une table posée par une MIGRATION v2 idempotente
        (`schema.MIGRATIONS[2]`), pas par un DDL ajouté à `lecons`. On vérifie que
        la montée s'est faite (table présente, `user_version == 2`) et qu'un second
        `garantir_schema` ne rejoue rien ni ne lève."""
        conn = self._store_reel()
        self.assertEqual(version.lire_version(conn), 2,
                         "la montée n'a pas atteint la v2")
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn(schema.TABLE_APPLIQUEE, tables,
                      "la table de précédence n'a pas été posée par la v2")
        # IDEMPOTENCE : rejouer la montée ne lève pas et laisse la version stable.
        self.assertEqual(version.garantir_schema(conn), 2)
        self.assertEqual(version.lire_version(conn), 2)
        # et l'écriture reste opérante après le rejeu.
        lessons.ecrire_lecon(conn, contenu="post-rejeu", cle_sujet="Z",
                             provenance="locale", **T)
        self.assertEqual(precedence.lecon_appliquee(conn, "Z", **T)["provenance"], "locale")

    # -- B1 : la dédup ne contourne plus la précédence -----------------------

    def test_B1_la_dedup_locale_ne_vole_plus_la_precedence_S1(self):
        """B1 (bloquant) — embarquée X sur S, puis locale X (MÊME contenu) sur S,
        puis embarquée Y sur S : l'appliquée DOIT être la LOCALE X. Avant le
        correctif, la locale X réutilisait la ligne embarquée (dédup sans
        provenance) et la précédence relisait « embarquee »."""
        conn = self._store_reel()
        X = "contenu partage X"
        lessons.ecrire_lecon(conn, contenu=X, cle_sujet="S", provenance="embarquee", **T)
        lessons.ecrire_lecon(conn, contenu=X, cle_sujet="S", provenance="locale", **T)
        lessons.ecrire_lecon(conn, contenu="contenu Y", cle_sujet="S",
                             provenance="embarquee", **T)
        app = precedence.lecon_appliquee(conn, "S", **T)
        self.assertIsNotNone(app, "aucune appliquée pour S")
        self.assertEqual(app["provenance"], "locale",
                         "la dédup a fait relire la provenance embarquée à la place "
                         "de la locale")
        self.assertEqual(app["contenu"], X)
        # La locale X est une ligne DISTINCTE de l'embarquée X (provenance dans la clé).
        provs = sorted(r["provenance"] for r in conn.execute(
            "SELECT provenance FROM " + schema.TABLE
            + " WHERE cle_sujet='S' AND portee='locale'"))
        self.assertEqual(provs, ["embarquee", "embarquee", "locale"],
                         "les écritures n'ont pas dédupliqué par provenance")

    def test_B1_la_dedup_locale_isole_par_sujet_S2(self):
        """B1 — embarquée X sur S1, locale X sur S2, embarquée Z sur S2 :
        l'appliquée de S2 est la LOCALE, `cle_sujet=='S2'`. Avant le correctif, la
        locale X sur S2 réutilisait la ligne de S1 (dédup sans cle_sujet)."""
        conn = self._store_reel()
        X = "contenu partage X"
        lessons.ecrire_lecon(conn, contenu=X, cle_sujet="S1", provenance="embarquee", **T)
        lessons.ecrire_lecon(conn, contenu=X, cle_sujet="S2", provenance="locale", **T)
        lessons.ecrire_lecon(conn, contenu="contenu Z", cle_sujet="S2",
                             provenance="embarquee", **T)
        app = precedence.lecon_appliquee(conn, "S2", **T)
        self.assertIsNotNone(app, "aucune appliquée pour S2")
        self.assertEqual(app["provenance"], "locale")
        self.assertEqual(app["cle_sujet"], "S2")
        self.assertEqual(app["contenu"], X)

    # -- N2 : rattrapage v2 d'un store v1 déjà peuplé ------------------------

    def test_N2_la_montee_v2_rattrape_la_meilleure_locale_d_un_store_v1(self):
        """N2 — un store v1 déjà peuplé (embarquée + locale sur S, écrites AVANT
        que le pointeur d'application existe) est migré vers v2 : l'appliquée de S
        devient la LOCALE, posée par le rattrapage de `creer_table_appliquee`."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "lecons_v1.db"
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        # STORE v1 : schéma de leçon SEUL, PAS la table de précédence.
        schema.creer_schema(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        self.assertEqual(version.lire_version(conn), 1, "le store n'est pas en v1")

        def _loc(prov, contenu, ts):
            return lessons.Lecon(
                ulid=ids.nouvel_ulid(), hash_contenu="h_" + prov, contenu=contenu,
                cle_sujet="S", portee="locale", provenance=prov,
                statut_partage="prive", statut_sync="local", version_schema_lecon=1,
                tenant_id="t", project_id="p", horodatage=ts)

        # Écrites SANS précédence (inserer bas niveau), comme un store d'avant v2.
        lessons.inserer(conn, _loc("embarquee", "S embarquee", "2026-01-01T00:00:00+00:00"))
        lessons.inserer(conn, _loc("locale", "S locale", "2026-01-02T00:00:00+00:00"))
        conn.commit()
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn(schema.TABLE_APPLIQUEE, tables,
                         "la table de précédence existe déjà — le store n'est pas v1")

        # MONTÉE v2 → rattrapage.
        version.garantir_schema(conn)
        self.assertEqual(version.lire_version(conn), 2)
        app = precedence.lecon_appliquee(conn, "S", tenant_id="t", project_id="p")
        self.assertIsNotNone(app, "le rattrapage v2 n'a posé aucune appliquée")
        self.assertEqual(app["provenance"], "locale",
                         "le rattrapage n'a pas choisi la meilleure provenance (locale)")
        self.assertEqual(app["contenu"], "S locale")

    # -- Précédence (fable) : `>=` et isolation par tenant -------------------

    def test_fable_une_seconde_locale_plus_recente_devient_l_appliquee(self):
        """FABLE — le `>=` de `doit_devenir_appliquee` : une SECONDE locale (contenu
        différent, écrite après) sur R devient l'appliquée. Mutation `>=`→`>` : la
        seconde (même rang) ne détrônerait plus la première → ce témoin rougit."""
        conn = self._store_reel()
        lessons.ecrire_lecon(conn, contenu="R locale 1", cle_sujet="R",
                             provenance="locale", **T)
        self.assertEqual(precedence.lecon_appliquee(conn, "R", **T)["contenu"],
                         "R locale 1")
        lessons.ecrire_lecon(conn, contenu="R locale 2", cle_sujet="R",
                             provenance="locale", **T)
        app = precedence.lecon_appliquee(conn, "R", **T)
        self.assertEqual(app["provenance"], "locale")
        self.assertEqual(app["contenu"], "R locale 2",
                         "une seconde locale plus récente n'est pas devenue "
                         "l'appliquée (>= cassé)")

    def test_fable_le_tenant_isole_l_appliquee(self):
        """FABLE — isolation par tenant : une locale sur R pour tenant t1 ne rend
        AUCUNE appliquée pour tenant t2. Mutation (filtre tenant retiré) : t2
        verrait le pointeur de t1 → rougit."""
        conn = self._store_reel()
        lessons.ecrire_lecon(conn, contenu="R chez t1", cle_sujet="R",
                             provenance="locale", tenant_id="t1", project_id="p")
        self.assertIsNone(
            precedence.lecon_appliquee(conn, "R", tenant_id="t2", project_id="p"),
            "un autre tenant voit l'appliquée — l'isolation par tenant est rompue")
        app_t1 = precedence.lecon_appliquee(conn, "R", tenant_id="t1", project_id="p")
        self.assertIsNotNone(app_t1, "le tenant propriétaire ne voit pas son appliquée")
        self.assertEqual(app_t1["contenu"], "R chez t1")

    # -- N3 : le verrou d'écriture est pris EN TÊTE (course) -----------------

    def test_N3_ecrire_lecon_prend_un_verrou_IMMEDIATE_avant_la_lecture_de_precedence(self):
        """N3 (course) — `ecrire_lecon` prend `BEGIN IMMEDIATE` EN TÊTE, donc AVANT
        la lecture read-modify-write du pointeur de précédence. Témoin DÉTERMINISTE
        à deux connexions : `conn2` tient le verrou d'écriture (RESERVED) via son
        propre BEGIN IMMEDIATE ; avec `busy_timeout=0`, le BEGIN IMMEDIATE
        d'`ecrire_lecon` échoue AUSSITÔT — AVANT tout SELECT de dédup, donc
        `_ulid_existant` n'est JAMAIS atteint. Sans le verrou immédiat (transaction
        différée), le SELECT partagé de `_ulid_existant` PASSERAIT (compatible avec
        le RESERVED de conn2) et seul l'INSERT échouerait plus tard — ce témoin
        rougirait alors."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "lecons.db"
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        version.garantir_schema(conn)
        conn.execute("PRAGMA busy_timeout = 0")
        conn2 = store.connect(chemin)
        self.addCleanup(conn2.close)
        conn2.execute("PRAGMA busy_timeout = 0")
        conn2.execute("BEGIN IMMEDIATE")  # conn2 tient le verrou d'écriture
        self.addCleanup(conn2.rollback)

        lu = {"appelee": False}
        reel = lessons._ulid_existant

        def espion(*a, **k):
            lu["appelee"] = True
            return reel(*a, **k)

        with mock.patch.object(lessons, "_ulid_existant", espion):
            with self.assertRaises(sqlite3.OperationalError):
                lessons.ecrire_lecon(conn, contenu="x", cle_sujet="S",
                                     provenance="locale", **T)
        self.assertFalse(lu["appelee"],
                         "une lecture de dédup a eu lieu AVANT l'échec du verrou : "
                         "le verrou IMMEDIATE n'est pas pris en tête")


@unittest.skipUnless(
    EST_LE_KIT,
    "arbre adoptant : les surfaces de leçons kit-only (registre, retro/, "
    ".agents/state/) n'existent pas — R-B1 ne s'applique qu'au kit",
)
class SurfacesDeLeconsTests(unittest.TestCase):
    """T-00000644 — LA QUATRIÈME SURFACE, L'AUTORITÉ, ET LE GREP R-B1.

    Cette partie ne fait PAS partie du témoin `check_lesson_precedence` (partie 1) :
    elle garde l'énumération des surfaces de leçons du kit. Elle saute sur un arbre
    adoptant (`EST_LE_KIT`), jamais sur le kit — donc jamais sous le regard de
    `test_checks_manifest.py`.
    """

    def _registre(self) -> dict:
        self.assertTrue(REGISTRE.is_file(),
                        "registre des surfaces de leçons absent — la garde ne mesure rien")
        return json.loads(REGISTRE.read_text(encoding="utf-8"))

    # -- (1) les quatre surfaces sont énumérées, exhaustivité NON affirmée -----

    def test_le_registre_cite_les_QUATRE_surfaces_du_releve(self):
        """Critère de sortie du point 9 : le banc cite les QUATRE surfaces. Et
        R-B1 : aucune exhaustivité affirmée — le champ le DIT."""
        reg = self._registre()
        cles = [s["cle"] for s in reg["surfaces"]]
        self.assertEqual(
            cles, ["ledger", "lessons_learned", "magasin_phase2", "retro"],
            "les quatre surfaces du relevé du 2026-09-16 doivent être énumérées "
            f"dans cet ordre ; vu : {cles}",
        )
        self.assertIn("AUCUNE", reg["exhaustivite"].upper(),
                      "R-B1 : l'exhaustivité ne doit PAS être affirmée")
        # `retro/LESSONS.md` entre comme exception kit-only NOMMÉE, rang `locale`.
        retro = next(s for s in reg["surfaces"] if s["cle"] == "retro")
        self.assertEqual(retro["chemin"], RETRO)
        self.assertTrue(retro.get("exception_kit_only"),
                        "retro/LESSONS.md doit entrer comme EXCEPTION KIT-ONLY nommée")
        self.assertFalse(retro["voyage"], "retro/LESSONS.md ne voyage jamais")
        # rangs de précédence : retro ET ledger = `locale`.
        rangs = {s["cle"]: s["rang_precedence"] for s in reg["surfaces"]}
        self.assertEqual(rangs["retro"], "locale")
        self.assertEqual(rangs["ledger"], "locale")
        # `lessons_learned` : gelée, HORS précédence.
        ll = next(s for s in reg["surfaces"] if s["cle"] == "lessons_learned")
        self.assertEqual(ll["statut"], "gelee")
        self.assertIsNone(ll["rang_precedence"],
                          "lessons_learned est HORS précédence (vide, aucun écrivain)")

    # -- (2) l'autorité LEDGER.json > retro/LESSONS.md ------------------------

    def _assert_autorite(self, autorite: dict) -> None:
        """L'ASSERTION D'AUTORITÉ, extraite pour être rejouée sous le contrôle
        négatif. `LEDGER.json` FAIT AUTORITÉ ; `retro/LESSONS.md` est le journal
        BRUT. Inverser les deux fait échouer ces deux égalités."""
        self.assertEqual(autorite["fait_autorite"], LEDGER,
                         "LEDGER.json (mémoire classée) doit FAIRE AUTORITÉ")
        self.assertEqual(autorite["journal_brut"], RETRO,
                         "retro/LESSONS.md est le JOURNAL BRUT dont on promeut")

    def test_le_ledger_fait_autorite_sur_le_journal_brut(self):
        reg = self._registre()
        self._assert_autorite(reg["autorite"])

    def test_inverser_l_autorite_fait_ROUGIR(self):
        """CONTRÔLE NÉGATIF de la règle d'autorité, prouvé par ce banc. Si le
        journal brut passait pour la mémoire qui fait foi, `_assert_autorite`
        DOIT échouer ; puis, HORS inversion, le registre réel PASSE — sans quoi
        l'échec ne prouverait rien."""
        inverse = {"fait_autorite": RETRO, "journal_brut": LEDGER,
                   "regle": "(inversée pour le contrôle négatif)"}
        with self.assertRaises(AssertionError):
            self._assert_autorite(inverse)
        self._assert_autorite(self._registre()["autorite"])

    # -- (3) le grep R-B1 : aucun magasin de leçons non déclaré ---------------

    def _valider_surfaces(self, hits, proprietes) -> None:
        """Chaque fichier remonté par le grep R-B1 est SOIT un `fichier_de_surface`
        du registre, SOIT une exclusion NOMMÉE (`cite_sans_stocker`). Ce qui reste
        est un magasin de leçons NON DÉCLARÉ."""
        non_classes = sorted(
            h for h in hits if not declaree_au_registre(h, proprietes) and not cite_sans_stocker(h)
        )
        self.assertEqual(
            non_classes, [],
            "surface(s) de leçons NON DÉCLARÉE(S) remontée(s) par le grep R-B1 : "
            f"{non_classes}. Déclare-la au registre `lesson_surfaces.json` si c'est "
            "un magasin — un fichier de FORME magasin (`MAGASIN_SUFFIXES`) n'est "
            "admis QUE par le registre ; une surface qui CITE sans stocker va dans "
            "les exclusions NOMMÉES du banc. N'élargis pas cette assertion à "
            "l'aveugle.",
        )

    def test_toute_surface_remontee_par_le_grep_RB1_est_declaree_ou_exemptee(self):
        reg = self._registre()
        proprietes = set(reg["grep_rb1"]["fichiers_de_surface"])
        hits = surfaces_grep(ROOT)
        self.assertGreater(
            len(hits), 20,
            "le grep R-B1 ne remonte presque rien — motif cassé ou dépôt vide, "
            f"l'assertion serait verte par vacuité ; vu : {hits}",
        )
        # C5 : le magasin de leçons de Phase 2 est DÉCLARÉ au registre ET remonté
        # par le motif élargi — les deux, sinon la déclaration serait décorative.
        self.assertIn("src/cadre/ledger/schema.py", proprietes,
                      "le magasin de Phase 2 (schema.py) n'est pas déclaré au registre")
        self.assertIn("src/cadre/ledger/schema.py", hits,
                      "le motif élargi ne remonte pas src/cadre/ledger/schema.py")
        self.assertIn("src/cadre/ledger/precedence.py", proprietes,
                      "precedence.py n'est pas déclaré au registre")
        self._valider_surfaces(hits, proprietes)

    def test_un_magasin_de_lecons_non_declare_fait_ROUGIR(self):
        """CONTRÔLE NÉGATIF du grep R-B1, prouvé par ce banc. On ajoute au résultat
        du grep un chemin qui n'est NI un fichier de surface NI une exclusion —
        exactement un magasin de leçons apparu sans déclaration — et la validation
        DOIT échouer ; puis, hors injection, le résultat réel PASSE."""
        reg = self._registre()
        proprietes = set(reg["grep_rb1"]["fichiers_de_surface"])
        faux = "src/cadre/ledger/fuite_de_lecons.py"
        self.assertNotIn(faux, proprietes, "le faux magasin ne doit pas être déjà déclaré")
        self.assertFalse(cite_sans_stocker(faux), "le faux magasin ne doit pas être exempté")
        with self.assertRaises(AssertionError):
            self._valider_surfaces(surfaces_grep(ROOT) + [faux], proprietes)
        self._valider_surfaces(surfaces_grep(ROOT), proprietes)

    def test_le_dossier_d_entrees_n_admet_que_des_noms_de_lecon(self):
        """T-01M4KKMY43ZKCW1YD2Y8JX9MKH : `memory/entries/` est déclaré comme DOSSIER (le ledger en forme
        dossier) ; un enregistrement de leçon y PASSE, un autre nom y ROUGIT — `lecons.db`, un suffixe de plus,
        un sous-dossier. MUTANT M-tout-nom-admis : admettre tout nom sous le dossier → rouge."""
        proprietes = set(self._registre()["grep_rb1"]["fichiers_de_surface"])
        self.assertIn(".agents/state/memory/entries/", proprietes)
        reels = surfaces_grep(ROOT)
        self._valider_surfaces(reels + [".agents/state/memory/entries/L-00000455.json",
                                        ".agents/state/memory/entries/L-01M4KKMY43ZKCW1YD2Y8JX9MKH.json"], proprietes)
        for faux in (".agents/state/memory/entries/lecons.db", ".agents/state/memory/entries/L-1.json.bak",
                     ".agents/state/memory/entries/sous/L-1.json", ".agents/state/memory/entries/T-1.json"):
            with self.subTest(faux=faux):
                with self.assertRaises(AssertionError):
                    self._valider_surfaces(reels + [faux], proprietes)

    # -- T-00000672 : un préfixe d'exclusion n'admet JAMAIS un fichier de magasin --

    #: Préfixes d'exclusion sous lesquels un magasin de leçons atterrirait le plus
    #: vraisemblablement (état machine, bancs), plus deux autres pour montrer que
    #: le refus vaut pour TOUS les préfixes.
    PREFIXES_DU_DEFAUT = (".agents/state/index/", ".agents/state/board/",
                          ".agents/state/specs/", ".agents/evals/")
    PREFIXES_SONDES = PREFIXES_DU_DEFAUT + ("docs/", "runs/")

    def test_T672_un_fichier_de_magasin_sous_un_prefixe_n_est_PLUS_admis(self):
        """(a) Un fichier dont la FORME est un magasin (`.db`, `.db3`, `.sqlite`,
        `.sqlite3`, `.sql`, casse ignorée) ou un COMPAGNON SQLite d'un magasin
        (`-wal`, `-shm`, `-journal`) n'est PLUS admis en bloc par un préfixe de
        `CITENT_PREFIXES` : un vrai `lecons.db` posé sous l'index, le board, les
        specs ou les bancs rougit le grep R-B1 au lieu d'y passer."""
        for prefixe in self.PREFIXES_SONDES:
            for nom in ("lecons.db", "lecons.db3", "lecons.sqlite", "lecons.sqlite3",
                        "lecons.sql", "LECONS.DB", "lecons.db3-wal",
                        "lecons.db-wal", "lecons.db-shm", "lecons.db-journal",
                        "lecons.sqlite-journal", "lecons.sqlite3-wal",
                        "LECONS.DB-SHM"):
                chemin = prefixe + nom
                with self.subTest(chemin=chemin):
                    self.assertFalse(
                        cite_sans_stocker(chemin),
                        f"{chemin} : un fichier de magasin est admis en bloc par son "
                        "préfixe — la promesse fail-closed du grep R-B1 est défaite")

    def test_T672_les_temoins_hors_prefixe_restent_refuses(self):
        """(b) Contrôle : hors préfixe, le refus existait déjà et ne bouge pas."""
        for chemin in (".agents/state/memory/lecons.db", "src/lecons.db"):
            with self.subTest(chemin=chemin):
                self.assertFalse(cite_sans_stocker(chemin))

    def test_T672_les_citations_legitimes_sous_les_prefixes_restent_admises(self):
        """(c) Le resserrement ne casse aucune exclusion légitime : des fichiers
        RÉELLEMENT remontés par le grep R-B1 (relevé du 2026-10-09) sous ces
        préfixes restent admis, bancs nommés `test_*.py` compris."""
        for chemin in (".agents/evals/lesson_surfaces.json",
                       ".agents/evals/fixtures/adopting_offender.py",
                       ".agents/evals/test_cadre_ledger_precedence.py",
                       ".agents/state/board/TASKS.json",
                       ".agents/state/specs/SPECS.json",
                       ".agents/state/index/SYMBOLS_cadre.md",
                       "docs/tasks/T-00000677-plan.md",
                       "runs/92675bafd6b6c3c5/backfill/2026-09.jsonl"):
            with self.subTest(chemin=chemin):
                self.assertTrue(cite_sans_stocker(chemin),
                                f"{chemin} : une citation légitime n'est plus admise")

    def test_T672_un_magasin_sous_un_prefixe_fait_ROUGIR_la_validation_RB1(self):
        """Bout en bout : le refus du prédicat ATTEINT l'assertion R-B1. Un
        `lecons.db` ou son compagnon `lecons.db-wal`, injecté SEUL sous chacun des
        QUATRE préfixes du défaut, fait échouer `_valider_surfaces` ; puis, hors
        injection, le résultat réel PASSE."""
        reg = self._registre()
        proprietes = set(reg["grep_rb1"]["fichiers_de_surface"])
        reels = surfaces_grep(ROOT)
        for prefixe in self.PREFIXES_DU_DEFAUT:
            for nom in ("lecons.db", "lecons.db-wal"):
                faux = prefixe + nom
                with self.subTest(faux=faux):
                    self.assertNotIn(faux, proprietes)
                    with self.assertRaises(AssertionError):
                        self._valider_surfaces(reels + [faux], proprietes)
        self._valider_surfaces(reels, proprietes)

    def test_T672_un_VRAI_magasin_sqlite_en_WAL_fait_ROUGIR_la_validation_RB1(self):
        """Bout en bout sur un VRAI magasin binaire, pas une chaîne injectée. Dans
        un dépôt git JETABLE, un `lecons.db` SQLite en WAL portant `CREATE TABLE
        lecons` est posé sous chacun des quatre préfixes du défaut, et `git add`
        tourne PENDANT que la connexion est ouverte : le DDL vit alors dans le
        compagnon `-wal`, seul fichier que le grep R-B1 remonte (mesuré par
        l'exec-critic, S-00004523). Chaque chemin remonté, validé SEUL, doit
        faire échouer `_valider_surfaces`.

        PRÉCONDITION, et non décor : chaque `-wal` doit être remonté. Sans elle, le
        témoin n'exercerait plus le refus des compagnons, et un mutant qui le
        retire resterait vert."""
        self._verifier_magasin_wal()

    def test_T672_le_temoin_WAL_ne_depend_pas_de_la_config_git_du_poste(self):
        """GO_AVEC_RESERVES de l'exec-critic, it. 2 : `git add -A` honore les
        exclusions de l'UTILISATEUR. Mesuré : un `excludesFile` du poste qui
        ignore `*-wal` vidait la précondition sur les quatre préfixes. Le témoin
        WAL reste VERT sous une config globale hostile désignée par
        `GIT_CONFIG_GLOBAL`, sous un `$HOME/.gitconfig` hostile (la config RÉELLE
        du poste : seule la ligne `GIT_CONFIG_GLOBAL=os.devnull` l'écarte), puis
        sous un `$XDG_CONFIG_HOME/git/ignore` hostile (avec une config globale
        vide, pour que ce soit bien l'`excludesFile` par défaut qui parle)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            hostile = Path(d)
            ignore = hostile / "ignore-hostile"
            ignore.write_text("*-wal\n", encoding="utf-8")
            cfg = hostile / "gitconfig-hostile"
            cfg.write_text(f"[core]\n\texcludesFile = {ignore.as_posix()}\n",
                           encoding="utf-8")
            xdg = hostile / "xdg"
            (xdg / "git").mkdir(parents=True)
            (xdg / "git" / "ignore").write_text("*-wal\n", encoding="utf-8")
            home = hostile / "home"
            home.mkdir()
            (home / ".gitconfig").write_text(
                f"[core]\n\texcludesFile = {ignore.as_posix()}\n", encoding="utf-8")
            variantes = (
                ("GIT_CONFIG_GLOBAL", {"GIT_CONFIG_GLOBAL": str(cfg)}),
                ("HOME", {"HOME": str(home)}),
                ("XDG_CONFIG_HOME", {"GIT_CONFIG_GLOBAL": os.devnull,
                                     "XDG_CONFIG_HOME": str(xdg)}),
            )
            for nom, env in variantes:
                with self.subTest(config_hostile=nom), mock.patch.dict(os.environ, env):
                    self._verifier_magasin_wal()

    def test_T672_l_env_git_jetable_retire_les_redirections_heritees(self):
        """Avis sécurité S-00004524 : sous un hook, git exporte `GIT_DIR` (et
        consorts) ; `git -C <tmp>` viserait alors le dépôt hôte. L'environnement
        des git du témoin WAL n'en porte AUCUNE, et neutralise les deux configs."""
        heritees = {"GIT_DIR": "/hote/.git", "GIT_INDEX_FILE": "/hote/.git/index",
                    "GIT_WORK_TREE": "/hote", "GIT_CONFIG_GLOBAL": "/hote/gitconfig",
                    "GIT_CONFIG_PARAMETERS": "'core.excludesfile=/hote/ignore'"}
        xdg = Path("/jetable/xdg")
        with mock.patch.dict(os.environ, heritees):
            env = env_git_jetable(xdg)
        for nom in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                    "GIT_CONFIG_PARAMETERS"):
            with self.subTest(retiree=nom):
                self.assertNotIn(nom, env)
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["XDG_CONFIG_HOME"], str(xdg))

    def _magasin_wal_remonte(self) -> list[str]:
        """Dans un dépôt git JETABLE, pose sous chacun des quatre préfixes du
        défaut un `lecons.db` SQLite en WAL (`CREATE TABLE lecons`), lance
        `git add -A` connexions OUVERTES, et rend ce que `surfaces_grep` remonte.
        Les `git` qui construisent le dépôt tournent sous `env_git_jetable`."""
        connexions = []
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            arbre = Path(d) / "arbre"
            arbre.mkdir()
            env = env_git_jetable(Path(d) / "xdg")
            try:
                subprocess.run(["git", "-C", str(arbre), "init", "-q"],
                               check=True, env=env, timeout=60)
                for prefixe in self.PREFIXES_DU_DEFAUT:
                    rep = arbre / prefixe
                    rep.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(rep / "lecons.db")
                    connexions.append(conn)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("CREATE TABLE lecons (id INTEGER, texte TEXT)")
                    conn.execute("INSERT INTO lecons VALUES (1, 'x')")
                    conn.commit()
                subprocess.run(["git", "-C", str(arbre), "add", "-A"],
                               check=True, env=env, timeout=60)
                return surfaces_grep(arbre, env)
            finally:
                for conn in connexions:
                    conn.close()

    def _verifier_magasin_wal(self) -> None:
        """La précondition (chaque `-wal` remonté), puis le refus : chaque chemin
        remonté, validé SEUL, fait échouer `_valider_surfaces`."""
        proprietes = set(self._registre()["grep_rb1"]["fichiers_de_surface"])
        hits = self._magasin_wal_remonte()
        for prefixe in self.PREFIXES_DU_DEFAUT:
            wal = prefixe + "lecons.db-wal"
            with self.subTest(wal=wal):
                self.assertIn(wal, hits,
                              f"précondition : le compagnon {wal} n'est pas remonté par "
                              f"le grep R-B1 ; vu : {hits}")
        for h in hits:
            with self.subTest(remonte=h):
                with self.assertRaises(AssertionError,
                                       msg=f"{h} : un vrai magasin passe R-B1 au vert"):
                    self._valider_surfaces([h], proprietes)

    def test_le_motif_RB1_detecte_reellement_un_magasin_fantome(self):
        """CONTRÔLE NÉGATIF DU MOTIF (C5), pas seulement d'un chemin injecté. Un
        fichier jetable portant `CREATE TABLE lecons_fantome` dans un ARBRE GIT
        temporaire est REMONTÉ par `surfaces_grep` — ce qui prouve que le motif
        détecte VRAIMENT un magasin non déclaré, au lieu de supposer qu'injecter
        un chemin dans la liste suffirait. Contrôle de VACUITÉ : un fichier sans
        le motif n'est PAS remonté.

        Ses `git` tournent sous `env_git_jetable` (T-00000672, S-00004528) :
        mesuré, lancé HORS pytest avec un `GIT_DIR` hérité, l'ancien `git add -A`
        réécrivait l'index du dépôt HÔTE (1717 suppressions, 2 ajouts)."""
        with tempfile.TemporaryDirectory() as d:
            arbre = Path(d) / "arbre"
            arbre.mkdir()
            env = env_git_jetable(Path(d) / "xdg")
            subprocess.run(["git", "-C", str(arbre), "init", "-q"],
                           check=True, env=env, timeout=60)
            (arbre / "fantome.sql").write_text(
                "CREATE TABLE lecons_fantome (id INTEGER);\n", encoding="utf-8")
            (arbre / "innocent.txt").write_text(
                "une note sans aucun magasin\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(arbre), "add", "-A"],
                           check=True, env=env, timeout=60)
            hits = surfaces_grep(arbre, env)
        self.assertIn("fantome.sql", hits,
                      "le motif R-B1 ne détecte pas un CREATE TABLE lecon fantôme")
        self.assertNotIn("innocent.txt", hits,
                         "le motif R-B1 remonte un fichier sans magasin — trop lâche")


class VendorSeulTests(unittest.TestCase):
    """Témoin I (T-01M5BXTPQE3JZV3KZA6WD9P5XC, S-01M5BXT85VP4JBBMXVXR9STP5F) : le paquet chargé est celui que
    `vendor_paths` désigne (vendor d'abord), et le grep R-B1 lit le magasin de Phase 2 sous son nom de registre
    `src/cadre/ledger/` où que le paquet vive — vendor seul, ou les deux emplacements (une fois chacun)."""

    MAGASINS = ("ledger/schema.py", "ledger/precedence.py")

    def _remontes(self, emplacements: tuple[str, ...]) -> list[str]:
        source = VENDOR.exiger(ROOT, "cadre")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            arbre = Path(d) / "arbre"
            env = env_git_jetable(Path(d) / "xdg")
            for lieu in emplacements:
                for rel in self.MAGASINS:
                    (arbre / lieu / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / rel, arbre / lieu / rel)
            subprocess.run(["git", "-C", str(arbre), "init", "-q"], check=True, env=env, timeout=60)
            subprocess.run(["git", "-C", str(arbre), "add", "-A"], check=True, env=env, timeout=60)
            return surfaces_grep(arbre, env)

    def test_vendor_seul_i(self):
        dossier, _ = VENDOR.verifier_charge(ROOT, "cadre")
        self.assertEqual(Path(schema.__file__).resolve(), (dossier / "ledger" / "schema.py").resolve(),
                         "cadre.ledger chargé hors du paquet que vendor_paths désigne")
        attendus = sorted("src/cadre/" + rel for rel in self.MAGASINS)
        for emplacements in ((".agents/vendor/cadre",), (".agents/vendor/cadre", "src/cadre")):
            with self.subTest(emplacements=emplacements):
                self.assertEqual(sorted(self._remontes(emplacements)), attendus)

    def _kit_i(self, base: Path, leurre: bool) -> Path:
        """Kit jetable du lot I, sur le patron du témoin J : `vendor_paths.py`, les modules de `LOT_I` copiés
        tels quels, deux paquets vendor réduits à leur `__init__.py`, et en « les deux » un `src/cadre` leurre."""
        kit = base / ("les-deux" if leurre else "vendor-seul")
        (kit / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(ROOT / ".agents" / "bin" / "vendor_paths.py", kit / ".agents" / "bin" / "vendor_paths.py")
        (kit / ".agents" / "evals").mkdir()
        for nom in LOT_I:
            shutil.copy2(ROOT / ".agents" / "evals" / f"{nom}.py", kit / ".agents" / "evals" / f"{nom}.py")
        for paquet in ("cadre", "agentic_v3"):
            (kit / ".agents" / "vendor" / paquet).mkdir(parents=True)
            (kit / ".agents" / "vendor" / paquet / "__init__.py").write_text("", encoding="utf-8")
        if leurre:
            (kit / "src" / "cadre").mkdir(parents=True)
            (kit / "src" / "cadre" / "__init__.py").write_text(
                'raise ImportError("leurre src/cadre charge")\n', encoding="utf-8")
        return kit

    def test_vendor_seul_i_sonde_lot_i(self):
        """Les modules de `LOT_I` (dont `test_cadre_ledger_stores`, à son plafond de lignes) chargent `cadre`
        depuis `.agents/vendor/cadre` : leur prologue — tout ce qui précède le premier `from cadre…` — est
        exécuté dans le kit jetable, puis `import cadre`. Mutant : `sys.path.insert(0, str(ROOT / "src"))` à
        la place de `charger_paquet(ROOT, "cadre")` → le leurre est importé, rouge."""
        sobre = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TMPDIR", "TEMP", "TMP", "HOME", "USERPROFILE")
        env = {k: v for k, v in os.environ.items() if k in sobre}
        with tempfile.TemporaryDirectory() as tmp:
            for leurre in (False, True):
                kit = self._kit_i(Path(tmp), leurre)
                attendu = (kit / ".agents" / "vendor" / "cadre").resolve()
                for nom in LOT_I:
                    with self.subTest(arbre="les deux" if leurre else "vendor seul", module=nom):
                        r = subprocess.run(
                            [sys.executable, "-X", "utf8", "-I", "-B", "-c", SONDE_I,
                             str(kit / ".agents" / "evals" / f"{nom}.py")],
                            capture_output=True, text=True, encoding="utf-8", env=env, cwd=tmp, timeout=120)
                        self.assertEqual(r.returncode, 0, r.stderr)
                        vu = json.loads(r.stdout.strip().splitlines()[-1])
                        self.assertTrue(vu["prologue"], vu)
                        self.assertEqual(Path(vu["cadre"]).resolve().parent, attendu, vu)


#: Les bancs des lots E/F/H/I (T-01M5BXTPQE3JZV3KZA6WD9P5XC) qui importent `cadre` au niveau module, sondés
#: par `test_vendor_seul_i_sonde_lot_i`. Hors sonde, sans import de `cadre` au niveau module :
#: test_cadre_cli_installed, test_cadre_package (chargement dans une fonction), test_cadre_pkg_root,
#: test_cadre_prefix_install (`from cadre` dans une sonde jouée en venv), test_capacites_hotes,
#: test_cadre_ledger_purete, test_spec_citation_par_nom.
LOT_I = ("test_cadre_cmd_tasks",
         "test_cadre_config", "test_cadre_hook", "test_cadre_hook_table", "test_cadre_identifiants",
         "test_cadre_ledger", "test_cadre_ledger_ids", "test_cadre_ledger_anciennes_bases",
         "test_cadre_ledger_promotion", "test_cadre_ledger_precedence", "test_cadre_ledger_redaction_cf",
         "test_cadre_ledger_store_identite", "test_cadre_ledger_stores")
#: Le prologue d'un module (instructions de niveau module avant le premier `from cadre…` ou `import cadre…`),
#: exécuté avec le `__file__` de sa copie, puis `import cadre` : UN module par processus, comme au témoin J.
SONDE_I = (
    "import ast, json, sys\n"
    "src = open(sys.argv[1], encoding='utf-8').read()\n"
    "corps = ast.parse(src).body\n"
    "fin = next(i for i, n in enumerate(corps) if (isinstance(n, ast.ImportFrom)"
    " and (n.module or '').split('.')[0] == 'cadre') or (isinstance(n, ast.Import)"
    " and any(a.name.split('.')[0] == 'cadre' for a in n.names)))\n"
    "g = {'__name__': 'sonde_i', '__file__': sys.argv[1]}\n"
    "exec(compile(ast.Module(body=corps[:fin], type_ignores=[]), sys.argv[1], 'exec'), g)\n"
    "import cadre\n"
    "print(json.dumps({'cadre': cadre.__file__, 'prologue': fin}))\n"
)


if __name__ == "__main__":
    unittest.main()
