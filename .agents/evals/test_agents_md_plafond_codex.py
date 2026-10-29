"""PLAFOND CODEX D'AGENTS.md — T-01M5PY2DZ8W7744BMDNVHB3FZ6 (trou de la revue de clôture).

CE QU'IL JUGE : Codex ne lit d'AGENTS.md que les `project_doc_max_bytes` premiers octets
(`.codex/config.toml`) ; au-delà, la fin du routeur est tronquée en silence. Le banc exige
`len(AGENTS.md en octets) <= project_doc_max_bytes`, et rougit si la clé manque.
CE QU'IL NE PROUVE PAS : que Codex honore la clé à l'exécution (comportement d'hôte, non rejoué),
ni qu'un autre hôte lise AGENTS.md en entier.
"""
from __future__ import annotations

import re
from pathlib import Path

DEPOT = Path(__file__).resolve().parents[2]
CONFIG = Path(".codex") / "config.toml"
ROUTEUR = "AGENTS.md"
CLE = re.compile(r"^project_doc_max_bytes\s*=\s*(\d+)", re.MULTILINE)


def plafond(config: str) -> int | None:
    """La valeur de `project_doc_max_bytes`, ou None si la clé manque."""
    m = CLE.search(config)
    return int(m.group(1)) if m else None


def fautes(racine: Path) -> list[str]:
    """Liste vide = AGENTS.md tient sous le plafond Codex."""
    n = plafond((racine / CONFIG).read_text(encoding="utf-8"))
    if n is None:
        return [f"{CONFIG} : clé project_doc_max_bytes absente"]
    taille = len((racine / ROUTEUR).read_bytes())
    if taille > n:
        return [f"{ROUTEUR} : {taille} octets > project_doc_max_bytes = {n}"]
    return []


def test_agents_md_tient_sous_le_plafond_codex():
    assert fautes(DEPOT) == []


def _copie(tmp_path: Path, config: str) -> Path:
    (tmp_path / ".codex").mkdir()
    (tmp_path / CONFIG).write_text(config, encoding="utf-8")
    (tmp_path / ROUTEUR).write_bytes((DEPOT / ROUTEUR).read_bytes())
    return tmp_path


def test_mutant_cle_absente_rougit(tmp_path):
    config = (DEPOT / CONFIG).read_text(encoding="utf-8")
    r = _copie(tmp_path, CLE.sub("# project_doc_max_bytes retirée", config))
    assert fautes(r) == [f"{CONFIG} : clé project_doc_max_bytes absente"]


def test_mutant_plafond_abaisse_rougit(tmp_path):
    taille = len((DEPOT / ROUTEUR).read_bytes())
    config = (DEPOT / CONFIG).read_text(encoding="utf-8")
    r = _copie(tmp_path, CLE.sub(f"project_doc_max_bytes = {taille - 1}", config))
    assert fautes(r) == [f"{ROUTEUR} : {taille} octets > project_doc_max_bytes = {taille - 1}"]
