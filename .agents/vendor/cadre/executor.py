"""L'EXÉCUTION DE COMMANDES. Phase 1 de T-012.

Une interface, une implémentation locale, et c'est délibéré : le plan (§5-A)
demande que l'orchestration et l'exécution soient séparées **avant** que le
déport existe, pour qu'il n'ait pas à réécrire ce qui les appelle. Une seule
implémentation aujourd'hui n'est donc pas une abstraction prématurée — c'est la
couture posée pendant qu'elle est gratuite.

DEUX NATURES D'OPÉRATION, JAMAIS LA MÊME INTERFACE. Le plan l'exige, et la
raison tient en une phrase : une tâche DÉTERMINISTE — indexer, scanner, tester,
construire — est rejouable, cacheable et déportable ; un APPEL AU MODÈLE ne l'est
pas. Les confondre derrière un même appel ferait perdre cette distinction au
moment précis où elle devient utile. Cette classe ne fait que le déterministe ;
l'appel au modèle n'a pas sa place ici et n'en aura pas.

CE QU'ELLE REFUSE D'ÊTRE
------------------------
**Elle ne passe jamais par un shell.** `shell=True` n'existe pas dans ce module.
Une valeur re-parsée comme du shell est un finding de classe 1 non-waivable dans
ce dépôt, et la doctrine mesure le coût : `bash -c "cd '$d' && …"` ECHOUE dès
qu'un chemin porte une apostrophe. Les arguments sont une liste, toujours.

**Elle ne décide de rien.** Pas de retry, pas de fallback, pas d'interprétation
du code de retour. Elle lance, elle rend ce qui s'est passé. Décider est le
travail de l'appelant — c'est ce qui garde l'orchestration pure au sens de
`check_orchestration_purity`.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

__all__ = ["Resultat", "Executor", "LocalExecutor", "ExecutionRefusee"]


class ExecutionRefusee(ValueError):
    """La commande est malformée — refusée AVANT d'être lancée."""


@dataclass(frozen=True)
class Resultat:
    """Ce qui s'est passé. Immuable : un résultat qu'on peut modifier après coup
    est un résultat dont on ne sait plus s'il décrit la commande ou son
    interprétation."""

    argv: tuple[str, ...]
    code: int
    stdout: str
    stderr: str
    expire: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.expire

    def resume(self) -> str:
        """Une ligne pour un journal — jamais la sortie complète.

        Le kit borne ce qu'il RETOURNE, pas ce qu'il mesure : un contexte noyé
        de sorties brutes déclenche une compaction, et une compaction perd un
        plan approuvé.
        """
        etat = "TIMEOUT" if self.expire else f"rc={self.code}"
        return f"{' '.join(self.argv[:4])}… → {etat}"


class Executor(Protocol):
    """Le contrat que le déport implémentera un jour, à côté du local."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Resultat: ...


class LocalExecutor:
    """L'exécution sur le poste. La seule implémentation d'aujourd'hui."""

    #: Borne par défaut. Une commande sans borne peut geler un hook, et un hook
    #: gelé bloque la session entière — mesuré sur ce dépôt, où les lanceurs
    #: portent tous une borne dure pour cette raison.
    TIMEOUT_DEFAUT = 300.0

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Resultat:
        args = [str(a) for a in argv]
        if not args:
            raise ExecutionRefusee("commande vide")
        if any("\x00" in a for a in args):
            raise ExecutionRefusee("un argument contient un octet nul")

        borne = self.TIMEOUT_DEFAUT if timeout is None else timeout
        environnement = dict(os.environ, **env) if env else None
        try:
            p = subprocess.run(
                args,
                cwd=str(Path(cwd)) if cwd is not None else None,
                env=environnement,
                capture_output=True,
                text=True,
                # L'ENCODAGE EST NOMME, JAMAIS CELUI DU POSTE. `text=True` seul
                # decode avec l'encodage LOCAL : sous cp1252 (Windows), le glyphe
                # ⏸ de `cadre tasks --statusline` (UTF-8 E2 8F B8) porte l'octet
                # 0x8F, sans correspondance en cp1252 — `UnicodeDecodeError`
                # traversait alors le contrat `-> Resultat` (mesure, rc 2). La CI
                # Windows ne le voyait pas : elle pose `PYTHONUTF8=1`.
                # `errors="replace"` comme `_txt` plus bas : un octet invalide
                # se lit, il ne casse pas l'appelant.
                encoding="utf-8",
                errors="replace",
                timeout=borne,
                check=False,
                # JAMAIS `shell=True` — voir la docstring du module.
            )
        except subprocess.TimeoutExpired as exp:
            # SOUS POSIX, `TimeoutExpired.stdout` EST EN OCTETS MEME EN `text=True`
            # (mesure du 2026-09-12 : `bytes b'PARTIEL\n'`) ; sous Windows,
            # `subprocess` rappelle `communicate()` et rend du `str`. Le garde
            # `isinstance(..., str)` de la premiere redaction rendait donc "" au
            # lieu de decoder : la sortie partielle d'une commande expiree etait
            # perdue EN SILENCE, et sur UNE SEULE des deux plateformes que ce kit
            # vise. Un test qui expire perdait son journal en CI et le gardait sur
            # le poste — la divergence exacte que ce paquet dit surveiller.
            # Les deux branches decodent en UTF-8 : les octets POSIX ici, le
            # `str` Windows par l'`encoding=` du `run` ci-dessus.
            def _txt(v: object) -> str:
                if isinstance(v, bytes):
                    return v.decode("utf-8", errors="replace")
                return v if isinstance(v, str) else ""

            return Resultat(
                argv=tuple(args), code=124, expire=True,
                stdout=_txt(exp.stdout),
                stderr=_txt(exp.stderr) + f"\ncadre: expire apres {borne}s",
            )
        except FileNotFoundError as exc:
            # UN EXECUTABLE ABSENT N'EST PAS UNE EXCEPTION, C'EST UN RESULTAT.
            # Le kit degrade bruyamment plutot que de casser : un scanner absent
            # rend COVERAGE DEGRADED, jamais une trace d'erreur.
            #
            # MAIS IL Y A DEUX CAUSES, PAS UNE. `subprocess` leve le meme
            # `FileNotFoundError` pour l'executable introuvable ET pour un `cwd`
            # qui n'existe pas. La premiere redaction en supposait une : mesure du
            # 2026-09-12, `run([python3, ...], cwd='/n/existe/pas')` annoncait
            # « executable introuvable sur le PATH : python3 » alors que python3
            # est installe. Un diagnostic faux envoie chercher un binaire present.
            if cwd is not None and not Path(cwd).is_dir():
                motif = f"repertoire de travail introuvable : {cwd}"
            else:
                motif = f"executable introuvable sur le PATH : {args[0]}"
            return Resultat(
                argv=tuple(args), code=127, stdout="",
                stderr=f"cadre: {motif} ({exc.strerror})",
            )
        except OSError as exc:
            # `PermissionError` (fichier present mais non executable),
            # `NotADirectoryError`, `ETXTBSY` : meme classe d'echec, meme contrat.
            # Le `Protocol` annonce `-> Resultat`, donc il ne LEVE pas — sinon un
            # appelant qui ecrit `if not r.ok:` recoit une trace Python au lieu
            # d'un resultat. Mesure : `run(['/etc/hosts'])` levait un
            # `PermissionError` a travers le contrat.
            #
            # 126 est la convention POSIX « trouve mais non executable », 127
            # « introuvable » — les deux codes que `Resultat.code` porte deja.
            return Resultat(
                argv=tuple(args), code=126, stdout="",
                stderr=f"cadre: lancement refuse ({type(exc).__name__}: {exc})",
            )
        return Resultat(argv=tuple(args), code=p.returncode, stdout=p.stdout, stderr=p.stderr)
