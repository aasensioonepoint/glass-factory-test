#!/usr/bin/env python3
"""LE PAQUET `cadre` VOYAGE PAR LA TEMPLATE AUX DEUX EMPLACEMENTS — témoin T de
T-01M5BXTPQE3JZV3KZA6WD9P5XC (enfant 4/5 du chantier vendor-kit).

Run: python -m pytest .agents/bin/test_sync_template_vendor.py -q

Le paquet suivi par Git, qu'il vive à `src/cadre/` (ancien) ou à
`.agents/vendor/cadre/` (neuf, après le `git mv` de 5/5), voyage par TAKE :
aucune règle `strip:` du VRAI `.template-exclude` ne le vise. Les noms de
fichiers sont ceux du paquet RÉEL, trouvés par `vendor_paths.exiger` (chargé par
chemin, jamais par `sys.path`) ; leur contenu est synthétique, car seul le nom
décide du prédicat TAKE.

  T1 test_vendor_seul_t   canal réel : `sync_template.py --apply` d'un kit jetable
                          « vendor seul » vers une template orpheline → chaque
                          fichier du paquet en TAKE (new), présent sur la branche
                          template, octets identiques ; `.agents/IS_THE_KIT` n'y
                          voyage pas.
  T2 test_aucun_strip_aux_deux_emplacements
                          prédicat pur (`build_plan`) : aux deux emplacements, aucun
                          fichier du paquet n'est couvert par une règle, tous TAKE.
  T3 test_mutant_strip_vendor_rougit
                          mutant permanent : `strip: .agents/vendor/cadre/` ajouté au
                          `.template-exclude` jetable → `.agents/vendor/cadre/__init__.py`
                          sort de TAKE (new) — le témoin T1 peut rougir.

BORNES, DITES : la branche template est jetable, jamais la vraie ; la porte de
l'adoptant n'est pas jouée ici. Chez un adoptant sans `.template-exclude`, ou sans
paquet `cadre`, chaque test se SAUTE en le disant.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
VENDOR_CADRE = ".agents/vendor/cadre/"
ANCIEN_CADRE = "src/cadre/"
MARQUEUR = ".agents/IS_THE_KIT"


def _charger(nom: str, fichier: str):
    """Module de `.agents/bin` chargé par CHEMIN, enregistré avant exécution."""
    spec = importlib.util.spec_from_file_location(nom, HERE / fichier)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


vp = _charger("vendor_paths_sync_vendor", "vendor_paths.py")
T = sys.modules.get("test_sync_template") or _charger("test_sync_template", "test_sync_template.py")
st = T.st


def _exclude_reel() -> str:
    chemin = REPO / ".template-exclude"
    if not chemin.is_file():
        raise unittest.SkipTest(f"{chemin} absent : voyage vers la template non jugé")
    return chemin.read_text(encoding="utf-8")


def _fichiers_du_paquet() -> list[str]:
    """Chemins relatifs au dossier du paquet RÉEL (où qu'il vive), caches exclus."""
    try:
        dossier = vp.exiger(REPO, "cadre")
    except vp.PaquetIntrouvable as exc:
        raise unittest.SkipTest(f"paquet cadre absent : {exc}") from exc
    rels = sorted(p.relative_to(dossier).as_posix() for p in dossier.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    if "__init__.py" not in rels:
        raise AssertionError(f"{dossier} sans __init__.py : exiger aurait dû refuser")
    return rels


def _paquet_sous(prefixe: str) -> dict[str, str]:
    return {prefixe + rel: f"# {rel}\n" for rel in _fichiers_du_paquet()}


def _take_new_par_apply(base: Path, exclude: str, paquet: dict[str, str]) -> tuple[list[str], list[str]]:
    """`--apply` d'un kit jetable portant `paquet` ; rend (TAKE (new), fautes de la template)."""
    main = {"README.md": "kit\n", MARQUEUR: "kit\n", **paquet,
            **T._frozen_fixtures(st.parse_exclude(exclude))}
    T.make_repo(base, main_files=main, template_files={"README.md": "ancienne template\n"},
                exclude_text=exclude)
    T._git(base, "checkout", "-q", st.TEMPLATE_REF)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = st.main(["--root", str(base), *T._APPLY_OK])
    if code != st.EXIT_OK:
        return [], [f"apply rc {code} : {err.getvalue()}{out.getvalue()}"]
    take_new = out.getvalue().split("TAKE (new)", 1)[1].split("TAKE (overwrite)", 1)[0].split()
    suivis = set(T._git(base, "ls-files").stdout.splitlines())
    fautes = [f"{p} : absent de la branche template, ou octets différents" for p, texte in paquet.items()
              if p not in suivis or not (base / p).is_file()
              or (base / p).read_bytes() != texte.encode("utf-8")]
    if MARQUEUR in suivis or (base / MARQUEUR).exists():
        fautes.append(f"{MARQUEUR} : a voyagé, l'arbre de l'adoptant se croirait le kit")
    return take_new, fautes


class VoyageVendorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sync-vendor-", ignore_cleanup_errors=True)
        self.base = Path(self._tmp.name).resolve() / "kit"
        self.base.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_vendor_seul_t(self):
        """T1 — mutant : `strip: .agents/vendor/cadre/` au `.template-exclude` → rouge (T3)."""
        paquet = _paquet_sous(VENDOR_CADRE)
        take_new, fautes = _take_new_par_apply(self.base, _exclude_reel(), paquet)
        manquants = [p for p in paquet if p not in take_new]
        self.assertEqual(manquants, [], "fichiers du paquet vendor absents de TAKE (new)")
        self.assertEqual(fautes, [])

    def test_aucun_strip_aux_deux_emplacements(self):
        """T2 — mutant : une règle `strip:`/`keep:` sur l'un des deux emplacements → rouge."""
        regles = st.parse_exclude(_exclude_reel())
        for prefixe in (ANCIEN_CADRE, VENDOR_CADRE):
            with self.subTest(emplacement=prefixe):
                paquet = _paquet_sous(prefixe)
                vises = {p: st.match_rule(p, regles).raw.strip() for p in paquet
                         if st.match_rule(p, regles) is not None}
                self.assertEqual(vises, {}, f"règles qui visent le paquet sous {prefixe}")
                main = {**paquet, **T._frozen_fixtures(regles)}
                plan = st.build_plan(main, {}, regles)
                self.assertEqual(sorted(set(paquet) - set(plan.take_new)), [])

    def test_mutant_strip_vendor_rougit(self):
        """T3 — le témoin T1 peut rougir : le paquet vendor strippé ne voyage plus."""
        exclude = _exclude_reel() + f"\nstrip: {VENDOR_CADRE}\n"
        take_new, fautes = _take_new_par_apply(self.base, exclude, _paquet_sous(VENDOR_CADRE))
        self.assertNotIn(VENDOR_CADRE + "__init__.py", take_new)
        self.assertIn(f"{VENDOR_CADRE}__init__.py : absent de la branche template, ou octets différents",
                      fautes)


if __name__ == "__main__":
    unittest.main()
