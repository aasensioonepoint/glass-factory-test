"""LE SERVICE SQL DU NOYAU — magasin de leçons et création des stores.

Phase 2 de T-012. Tout le SQL du noyau vit ici, derrière `store.py` (l'unique
ouverture de connexion `sqlite3` du service). Les autres modules opèrent sur une
connexion REÇUE : ils ne touchent ni le disque ni le réseau, ce que le banc de
discipline `test_cadre_ledger_purete.py` vérifie fichier par fichier.

Ce paquet naît à l'étape C (point 4) avec ce seul `__init__.py`. La raison est
mesurée : le filet `check_orchestration_purity` filtrait par NOM de fichier, donc
un `ledger/__init__.py` niché serait né EXEMPTÉ (trou P5). Le filtre passe au
CHEMIN RELATIF, et seul le `__init__.py` RACINE (`rel == "__init__.py"`) reste
exempté : ce `ledger/__init__.py`-ci entre donc au périmètre du filet — il doit
rester pur (ré-export seul). L'exemption `ledger/store.py` a été RETIRÉE du filet
global (le binôme C l'a mesurée inutile — voir `store.py`) ; store.py reste le
seul site `connect`, tenu par le banc LOCAL de pureté.
"""

from __future__ import annotations

from cadre.ledger import (
    ids, lessons, precedence, redaction, schema, store, stores, version,
)

__all__ = ["ids", "lessons", "precedence", "redaction", "schema", "store",
           "stores", "version"]

