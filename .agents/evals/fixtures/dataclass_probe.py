"""Fixture de T-00000134 — la PRECONDITION EXACTE de L-00000142, rien de plus.

Le motif `module_from_spec` -> `exec_module` SANS enregistrement prealable dans
`sys.modules` ne casse pas partout : il casse quand le module charge porte des
ANNOTATIONS EN CHAINE (`from __future__ import annotations`, ou des annotations
citees) ET que `typing` est deja dans `sys.modules`. `dataclasses` resout alors
les annotations en interrogeant `sys.modules[cls.__module__]`, qui n existe pas
encore — et leve.

Ce fichier reunit ces conditions et rien d autre : une fixture qui en ferait
plus mesurerait autre chose que la precondition.
"""
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Probe:
    name: str
    count: int = 0


def probe_fields() -> list[str]:
    """Force la resolution des annotations — c est CE point qui leve quand le
    module n est pas enregistre."""
    return [f.name for f in fields(Probe)]
