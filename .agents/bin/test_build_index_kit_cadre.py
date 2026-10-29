"""Témoin T-00001100 : CHEZ UN ADOPTANT, `src/cadre` (LE NOYAU DU KIT EMBARQUÉ)
SORT DE L'INDEX ; DANS LE DÉPÔT DU KIT, IL Y RESTE.

Relevé de migration (ec-crm-multi) : `build_index` comptait `src/cadre` comme
code du projet, dans le fichier que la règle d'or fait lire EN PREMIER. Le
discriminant est celui d'`agentic_v3` : un marqueur de vendoring à la racine
exclut, `.agents/IS_THE_KIT` l'emporte et n'exclut rien. `src/cadre` est la
première racine de kit à DEUX segments : les deux sites qui ne comparaient que
le premier segment (`_walk_sources`, `_keep`) comparent donc un préfixe ancré à
la racine, coupé au `/`.

Chaque bras lit TROIS vues. L'élagage brut de `_walk_sources`, appelé
directement : son seul appelant, `all_source_files`, repasse sa sortie par
`_keep`, donc un build ne prouve jamais ce site seul (mesuré par mutation). Puis
l'index bâti sans dépôt git, et l'index bâti après `git_init()` (`git ls-files`
filtré par `_keep`, le chemin nominal d'un adoptant).

Réutilise la fixture `_Case` de `test_build_index_atomic.py`, importée par nom
comme le fait `test_build_index_non_suivi.py`. Les sources sont écrites AVANT
`git_init()` : son `add -A` les rend visibles à `git ls-files`, sinon le bras
« adoptant » passerait au vert pour une mauvaise raison (fichier non suivi).
"""
import unittest
from unittest import mock

import build_index as bi
from test_build_index_atomic import VENDORED, _Case

MARQUEUR = ".agents/protected-paths.local"
NOYAU = "src/cadre/x.py"
PROJET = "src/app/y.py"
# Un paquet du PROJET dont le nom COMMENCE par `cadre` : un préfixe de chaîne
# (`startswith("src/cadre")`) l'emporterait avec le noyau du kit.
HOMONYME = "src/cadre_metier/z.py"
MOTEUR_VENDOR = ".agents/vendor/agentic_v3/engine.py"
ARBRE = {
    NOYAU: "def cadre_noyau_entry(event):\n    return event\n",
    PROJET: "def app_projet_entry(value):\n    return value\n",
    HOMONYME: "def cadre_metier_entry(value):\n    return value\n",
}


class KitCadreScopeTests(_Case):
    """Le même `src/cadre` est le code source dans le dépôt du kit et la
    plomberie embarquée chez un adoptant : le marqueur tranche, jamais le nom."""

    def setUp(self):
        super().setUp()
        self.write_sources(ARBRE)

    def _marquer(self, *rels: str) -> None:
        for rel in rels:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# marqueur\n", encoding="utf-8")

    def _chemins(self) -> set:
        return {path for (path, _nom, _kind) in self.ids()}

    def _vues(self) -> dict:
        """L'élagage de `_walk_sources`, l'index sans git, l'index `git ls-files`."""
        elague = set(bi._walk_sources(self.root, bi.host_skip_dirs(self.root)))
        self.build("--full")
        parcours = self._chemins()
        self.git_init()
        self.build("--full")
        return {"_walk_sources (élagage)": elague, "index sans git": parcours,
                "index git ls-files": self._chemins()}

    def test_a_adoptant_exclut_src_cadre_et_garde_src_app(self):
        self._marquer(MARQUEUR)
        for chemin, vus in self._vues().items():
            self.assertNotIn(NOYAU, vus, f"{chemin} : noyau du kit indexé chez l'adoptant")
            self.assertIn(PROJET, vus, f"{chemin} : code du projet perdu")

    def test_b_depot_du_kit_garde_src_cadre(self):
        # Les DEUX marqueurs, comme le dépôt du kit réel (il porte aussi
        # `.agents/protected-paths.local`) : sans la préséance d'IS_THE_KIT, le
        # marqueur de vendoring exclurait `src/cadre`, donc ce bras peut rougir.
        self._marquer(MARQUEUR, bi.KIT_MARKER.as_posix())
        for chemin, vus in self._vues().items():
            self.assertIn(NOYAU, vus, f"{chemin} : le kit ne s'indexe plus lui-même")
            self.assertIn(PROJET, vus, f"{chemin} : code perdu dans le dépôt du kit")

    def test_c_homonyme_de_prefixe_reste_indexe(self):
        self._marquer(MARQUEUR)
        for chemin, vus in self._vues().items():
            # La paire est le témoin : l'exclusion est ACTIVE, et elle s'arrête
            # au `/` au lieu de mordre sur le nom voisin.
            self.assertNotIn(NOYAU, vus, f"{chemin} : exclusion inactive")
            self.assertIn(HOMONYME, vus, f"{chemin} : préfixe trop large")

    def test_d_adoptant_deja_indexe_purge_src_cadre_au_premier_if_stale(self):
        """Le cas du relevé : l'index de l'adoptant a été publié par un builder
        qui ne connaissait pas `src/cadre`. La portée entre dans l'empreinte
        `dirscope` (`scope_fingerprint`, champ `rootonly:`), donc le premier
        `--if-stale` voit l'empreinte changer, reconstruit EN ENTIER avec purge,
        et les lignes du noyau tombent au lieu de survivre aux incrémentaux."""
        self._marquer(MARQUEUR)
        self.git_init()
        ancien = bi.KIT_CODE_DIRS - {"src/cadre"}
        with mock.patch.object(bi, "KIT_CODE_DIRS", ancien):
            self.build("--full")
        self.assertIn(NOYAU, self._chemins(), "précondition : l'ancien index porte le noyau")
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertIn("full", out)
        self.assertNotIn(NOYAU, self._chemins())
        self.assertIn(PROJET, self._chemins())

    def test_vendor_seul_indexe(self):
        """Le moteur uniquement sous vendor est source du kit, plomberie adoptante."""
        self.assertIn(MOTEUR_VENDOR, VENDORED, "la fixture doit porter le moteur déplacé")
        self.write_sources({MOTEUR_VENDOR: VENDORED[MOTEUR_VENDOR]})
        for vue, chemins in self._vues().items():
            self.assertIn(MOTEUR_VENDOR, chemins, f"{vue} : moteur vendor perdu dans le kit")
            self.assertNotIn("agentic_v3/engine.py", chemins, f"{vue} : ancien emplacement recréé")
        self._marquer(MARQUEUR)
        self.build("--if-stale")
        self.assertNotIn(MOTEUR_VENDOR, self._chemins(), "moteur du kit indexé chez l'adoptant")


if __name__ == "__main__":
    unittest.main()
