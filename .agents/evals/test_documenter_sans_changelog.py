"""TÉMOIN de la règle « No CHANGELOG writes » aux 5 défs documenter (lot B de
T-01M4ZWNEDCJCNFF4HWQEWZX1J0, décision pilote S-01M51H3PTQ75984NP7ZD7JZBMS).

Il lit les rendus du roster canonique (`<paquet cadre>/data/roster/documenter.json`, le
paquet que `vendor_paths` désigne : `.agents/vendor/cadre`, sinon `src/cadre`), que
`test_cadre_roster.py` tient égal aux défs vivantes : chaque rendu porte la règle
ET le nom de l'historique figé (`HISTORIQUE-0.1.0.md`). Retirer l'un ou l'autre d'un
seul rendu le fait rougir en nommant l'hôte.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: son absence EST le signal « projet adoptant » : ce filet y saute EN ENTIER.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant)")

_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_documenter_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
ROSTER = _VENDOR.exiger(ROOT, "cadre") / "data" / "roster" / "documenter.json"
REGLE = "No CHANGELOG writes"
FIGE = "HISTORIQUE-0.1.0.md"


def _texte(rendu: dict) -> str:
    return "\n".join(rendu.get("entete", []) + rendu.get("corps", []))


def test_la_regle_est_dans_les_cinq_rendus_du_documenter():
    rendus = json.loads(ROSTER.read_text(encoding="utf-8"))["rendus"]
    absents = [h for h, r in rendus.items() if REGLE not in _texte(r) or FIGE not in _texte(r)]
    assert len(rendus) == 5 and absents == [], absents
