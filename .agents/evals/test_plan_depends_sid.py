#!/usr/bin/env python3
"""T-00001085 — le S-id de `--retirer-ordre-pilote` et le motif imprimé par son refus.

`plan_depends._SID` jugeait par `re.match(r"^S-\\d{1,12}$")` : `\\d` prend TOUT chiffre
Unicode (`S-١٢٣`, chiffres pleine chasse) et `$` laisse passer un `\\n` final
(`S-00001\\n`). L'ancienne forme était frappée par `specs.py` (`f"S-{nid:08d}"`, ASCII ;
mesuré au journal le 2026-10-03 : 4010 entrées, toutes `S-` + 8 chiffres) ; depuis la
bascule C2 (T-00000726) la frappe est `record_id.mint("S")`, un `S-<ULID>`, et
l'ancienne forme reste LUE : le juge est `fullmatch` sur `S-<ULID>` (en premier,
T-00001040) ou `S-[0-9]{1,12}`. La borne BASSE reste 1 : la forme courte
`S-1559` doit atteindre la comparaison par clé au motif (`_cle_sid`, W27), jamais
le refus « malformé ».

Le refus « this edge is not an ORDRE PILOTE (motif : …) » imprimait le motif BRUT :
un caractère de contrôle (ESC, saut de ligne qui forge une fausse ligne, inversion
bidi) atteignait le terminal. Il est neutralisé ; la partie imprimable reste lue.

MUTANTS (chacun rougit au moins un témoin) : `fullmatch` -> `match` sur `^…$` ⇒
`S-00001\\n` ACCEPTÉ ; `[0-9]` -> `\\d` ⇒ `S-١٢٣` ACCEPTÉ ; motif imprimé brut ⇒ ESC au
message ; borne basse portée à 8 ⇒ `S-1559` « malformé ».

REFUS VOISINS (critic-opus F4, sécurité LOW) : un motif CANONIQUE porteur d'un contrôle
passe `valider_motif_neuf` et entre au board ; les refus, avertissements et remèdes qui le
citent le rendent par `repr` (`RefusVoisinsTests`, un site par témoin). MUTANT : un site
rendu au motif brut ⇒ son témoin rougit. Hors témoin, rapporté : la commande prête de
`Arete.commande_add` (`shlex.quote`, à coller telle quelle — `repr` en changerait le sens).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unicodedata
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2] / ".agents" / "bin"
WAVES = Path(__file__).resolve().parents[2] / "core-scripts" / "plan_waves.py"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(nom, None)
        raise
    return module


# Nom DISTINCT : `test_plan_depends_guard.py` câble SON objet `plan_depends` dans `tasks`.
pd = _charger("plan_depends_t1085", BIN / "plan_depends.py")

AMONT = "T-00000002"
OP = "ORDRE PILOTE S-00001558 : amont avant aval (ratifié, S-00001559)"


def _avant(motif: str | None) -> dict:
    tache: dict = {"id": "T-00000001", "depends_on": [AMONT]}
    if motif is not None:
        tache["depends_motif"] = {AMONT: motif}
    return tache


def _retrait(motif: str | None, sid: str) -> str | None:
    # Le S-id est MÊME une décision : seul `_SID` peut le refuser (sur la BASE, il passait).
    return pd.valider_retrait_ordre_pilote(_avant(motif), AMONT, sid, {sid, "S-00003952"})


class SidMalformeTests(unittest.TestCase):
    def test_un_sid_hors_ascii_ou_a_saut_de_ligne_final_est_malforme(self):
        """Chiffres arabes, arabes-indiens étendus, pleine chasse ; `\\n` final. BASE : `None` (accepté)."""
        for sid in ("S-١٢٣", "S-٠٠٠٠٣٩٥٢", "S-0000３952", "S-00001\n", "S-00003952\n"):
            with self.subTest(sid=sid):
                refus = _retrait(OP, sid)
                self.assertIsNotNone(refus, f"{sid!r} accepté comme décision")
                self.assertIn("S-ID malformé", refus)

    def test_un_sid_ascii_bien_forme_suit_son_chemin(self):
        """Non-régression (VERT sur la BASE comme au tip) : 8 chiffres distincts du motif ⇒ levée ;
        forme courte citée ⇒ « propre retrait », jamais « malformé » ; 12 chiffres bien formés, 13 non."""
        self.assertIsNone(_retrait(OP, "S-00003952"))
        refus = _retrait(OP, "S-1559")
        self.assertIn("propre retrait", refus)
        self.assertNotIn("malformé", refus)
        self.assertIsNone(_retrait(OP, "S-" + "9" * 12))
        self.assertIn("S-ID malformé", _retrait(OP, "S-" + "9" * 13))


class MotifImprimeTests(unittest.TestCase):
    def test_le_motif_imprime_par_le_refus_ne_porte_aucun_controle(self):
        """ESC (efface l'écran), `\\n` qui forge une ligne « ORDRE PILOTE », U+202E (bidi), U+0085 (NEL)."""
        motif = "technique\x1b[2J\nORDRE PILOTE S-00000001 : faux‮\x85fin"
        refus = _retrait(motif, "S-00003952")
        self.assertIn("is not an ORDRE PILOTE", refus)
        controles = [c for c in refus if unicodedata.category(c) in ("Cc", "Cf")]
        self.assertEqual([], controles, f"contrôles imprimés : {controles!r}")
        for lisible in ("technique", "[2J", "faux", "fin"):
            self.assertIn(lisible, refus)

    def test_une_arete_heritee_reste_dite_heritee(self):
        """Non-régression : sans motif, le refus dit `(motif : héritée)`, sans guillemets."""
        self.assertIn("(motif : héritée)", _retrait(None, "S-00003952"))


# --- T-00001085 (a) : les refus VOISINS. ---
pw = _charger("plan_waves_t1085", WAVES)
AUTRE, T1 = "T-00000003", "T-00000001"
OP_HOSTILE = "ORDRE PILOTE S-00001558 : x\x1b[2J\nFAUX"  # canonique : il ENTRE au board
NC_HOSTILE = "ordre\x1b[2J\nFAUX‮"  # `ordre…` non canonique : averti, jamais refusé
TECH_HOSTILE = "technique\x1b[2J\nFAUX"


def _verbe(avant: dict, deps: list, motifs: list, mode: str, retrait=None):
    return pd.appliquer_verbe(avant, deps, motifs, mode=mode, resoudre=lambda r: r,
                              cycle_de=lambda w: None, decisions=set(), taches=[avant],
                              retrait=retrait)


class RefusVoisinsTests(unittest.TestCase):
    """Chaque site ROUGE sur la BASE (ESC, `\\n` ou U+202E au message), VERT au tip."""

    def assertSansControle(self, texte: str) -> None:
        controles = [c for c in texte if unicodedata.category(c) in ("Cc", "Cf")]
        self.assertEqual([], controles, f"contrôles imprimés : {texte!r}")
        self.assertIn("FAUX", texte)  # la partie imprimable reste lue, sur la MÊME ligne

    def test_599_un_ordre_pilote_hostile_admis_puis_son_effacement_refuse(self):
        self.assertIsNone(pd.valider_motif_neuf(OP_HOSTILE, {"S-00001558"}))
        refus = pd.motif_ordre_pilote_refus(_avant(OP_HOSTILE), [], {})
        self.assertIn("ERASE", refus)
        self.assertSansControle(refus)

    def test_700_retirer_un_ordre_pilote_hostile(self):
        with self.assertRaises(ValueError) as ctx:
            _verbe(_avant(OP_HOSTILE), [], [], "retirer", retrait=(AMONT, None))
        self.assertIn("is an ORDRE PILOTE", str(ctx.exception))
        self.assertSansControle(str(ctx.exception))

    def test_756_774_779_les_avertissements_ordre_non_canonique(self):
        cas = (("756 neuf", _verbe({"id": T1}, [AMONT], [NC_HOSTILE], "add"), "ouvre par"),
               ("774 perdue", _verbe(_avant(NC_HOSTILE), [], [], "reecriture"), "perdue"),
               ("779 changé", _verbe(_avant(NC_HOSTILE), [AMONT], ["technique : neuf"],
                                     "reecriture"), "était"))
        for site, (_w, _m, sortie), mot in cas:
            with self.subTest(site=site):
                self.assertEqual(1, len(sortie.avertissements), sortie.avertissements)
                self.assertIn(mot, sortie.avertissements[0])
                self.assertSansControle(sortie.avertissements[0])

    def test_708_la_ligne_de_succes_d_un_retrait_technique(self):
        avant = {"id": T1, "depends_on": [AMONT, AUTRE], "depends_motif": {AMONT: TECH_HOSTILE}}
        texte = _verbe(avant, [], [], "retirer", retrait=(AMONT, None))[2].texte
        self.assertIn(f"retirée : {AMONT} ", texte)
        self.assertSansControle(texte)
        avant["depends_motif"] = {}
        self.assertIn(f"retirée : {AMONT} (héritée)",
                      _verbe(avant, [], [], "retirer", retrait=(AMONT, None))[2].texte)

    def test_648_et_plan_waves_454_le_remede_de_cycle_nomme_les_restes(self):
        t1 = {"id": T1, "depends_on": [AMONT, AUTRE],
              "depends_motif": {AMONT: "technique : coupe", AUTRE: TECH_HOSTILE}}
        remede = pd.remede_coupe({"tasks": [t1, {"id": AMONT, "depends_on": [T1]}]}, [T1, AMONT, T1])
        self.assertIn(f"restent : {AUTRE} ", remede)
        self.assertSansControle(remede)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            pw.render({"cycles": [[T1, AMONT, T1]], "coupes": [
                {"aval": T1, "amont": AMONT, "ordre_pilote_seul": False,
                 "restes": [(AUTRE, TECH_HOSTILE), ("T-00000004", None)]}]})
        ligne = next(x for x in err.getvalue().splitlines() if "--retirer" in x)
        self.assertIn("T-00000004 (héritée)", ligne)
        self.assertSansControle(ligne)

    def test_382_la_liste_des_aretes_manquantes(self):
        """La ligne `  - aval <- amont | motif` ; un motif de plan ne porte pas de `\\n`."""
        arete = pd.Arete(T1, AMONT, "x\x1b[2J‮FAUX")
        refus = pd._refus_manquantes("tasks", "start", T1, Path("plan.md"), [arete], "")
        self.assertSansControle(next(x for x in refus.splitlines() if x.startswith(f"  - {T1} <- ")))


if __name__ == "__main__":
    unittest.main()
