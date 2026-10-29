"""Le kit Cadre — noyau packagé. Phase 1 de T-012.

Ce paquet est du NOYAU : privé, sans garantie interne, libre de bouger. Ce qui
est promis à un adoptant vit dans `contract.lock.json` et
`docs/contrat/CONTRAT-v0.md`, et rien d'autre.

Trois règles gouvernent tout ce qui s'écrit ici, chacune tenue par un check.

* **Aucun client réseau.** `check_no_network` refuse `requests`, `httpx`,
  `urllib`, `socket` et `aiohttp` dans ce paquet. C'est ce qui rend vraie
  l'affirmation « rien ne part de la machine » — pas une promesse, une absence
  vérifiable.
* **Aucun chemin résolu hors de `paths`.** `no_hardcoded_paths` refuse
  `__file__` et `git rev-parse --show-toplevel` partout sauf dans `paths.py`.
* **Aucune ÉCRITURE ni sous-processus depuis l'orchestration.**
  `check_orchestration_purity` sépare ce qui DÉCIDE de ce qui EXÉCUTE : `paths`
  résout — et LIT le disque pour résoudre (`os.scandir`/`os.lstat`, T-00000674),
  jamais n'y écrit —, `Workspace` fait les écritures, `Executor` lance les
  commandes. `paths.py` est EXEMPTÉ de ce check, et `IO_PAR_METHODE` ne couvre ni
  `stat` ni `scandir` : la borne est écrite ici, pas tenue là.

Cette dernière n'est pas de l'esthétique. Elle est la couture qui rendra
possible, plus tard, d'exécuter les tâches déterministes ailleurs que sur le
poste — sans que la logique qui les ordonne ait à changer.

Deux versions, et une seule promet quelque chose. `__version_contrat__` : SemVer
sur le contrat seul — `__version__` n'offre aucune garantie. C'est la clé du
lockstep que `.agents/kit.lock` porte, et c'est une CONSTANTE du noyau, pas un
fichier de données : la lire ne touche pas le disque.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

#: Doit égaler le champ `version_contrat` de `contract.lock.json` ; le banc
#: `test_cadre_kit_lock.py` le vérifie dans le kit.
__version_contrat__ = "0.6.0"

__all__ = ["__version__", "__version_contrat__"]
