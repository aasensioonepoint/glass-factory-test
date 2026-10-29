"""
CLI Entry Point for Agentic V3 Scale-Up Engine.
Ingests specs with Hot Spec Mutation, queries projections, resumes session
checkpoints.

T-012 — `run-task` A ETE RETIREE, et avec elle tout le FSM qu'elle pilotait
(`orchestrator/`, `agents/`, `mcp/`). Mesure du 2026-09-12 : aucune surface du
depot ne citait `run-task`, la couche `agents/` renvoyait un dictionnaire ecrit
en dur au lieu d'appeler un modele, et `orchestrator/nodes.py` violait
l'invariant « aucun acces disque depuis la logique d'orchestration ». La chaine
d'orchestration reste en PROSE dans `/kickoff` et `AGENTS.md`, interpretee par
le LLM de l'hote — c'est la decision D1 de la refonte packaging.

`sync-spec` est la seule sous-commande citee ailleurs : la skill `specs-sync` et
la commande `/specs-sync` l'appellent par `python -m agentic_v3 sync-spec`.

Codes de sortie propres a ce CLI, chacun sur UNE ligne stderr et jamais un
traceback : 3 — `sync-spec` refuse d'ecrire sur une reconstruction avortee
(`ReconstructionAvorteeError`, T-00000691), ligne APLATIE (S-00003354,
`aplatir_message` : blancs reduits a une espace, non imprimables en `?`) ; 4
(`RC_STORE_REFUSE`, T-00001005, decision pilote S-00003324) — le store V3 est
REFUSE ; 5 (`RC_STORE_PANNE`, T-00001005, decision pilote S-00003348) — panne
d'infrastructure (`PanneInfrastructure`, couture `cadre` absente, verdict `EN
PANNE`). 4 et 5 valent pour les quatre verbes A LA CONSTRUCTION, sous la MEME
ligne (`agentic_v3 <verbe>: store V3 <verdict> (<cause>) — <chemin> — <origine>`,
`agentic_v3/db/refus_store.py`). Pour `sync-spec` SEUL, la meme ligne et les
memes codes valent aussi PENDANT le verbe (T-00001059, decision pilote
S-00003420 ; les trois soeurs `OSError` exceptees, S-00003602) : verrou d'un autre
ecrivain au premier write (en WAL la
construction passe, le write attend 30 s puis sort en `store verrouillé (attente
dépassée)`, code 4), store rouvert refuse (emplacement, ouverture, non SQLite,
lecture seule, corrompu, code 4), panne d'export (code 5). La ligne ne dit jamais « rien n'est ecrit » :
sur un spec a plusieurs sections, les sections anterieures sont deja commitees ;
une relance est idempotente. Un script appelant distingue ainsi succes (0),
reconstruction avortee (3), refus (4) et panne (5). Hors de ces cas, une erreur
survenue APRES la construction reste un traceback : toute erreur pour `status`,
`resume` et `dashboard-summary` ; pour `sync-spec`, ce qui sort de l'ensemble de
`classer_refus` (`ValueError` d'un store supprime pendant le run,
`OperationalError` 1032 (base déplacée ou supprimée sous la connexion du verbe),
`RunExportError`, `FileNotFoundError`, et les trois soeurs `OSError` —
`PermissionError`, `NotADirectoryError`, `FileExistsError` — levees PENDANT le
verbe : un spec illisible n'est pas un store refuse, S-00003602) — residus nommes
de T-00001005, T-00001059 et T-00001078.

NON PROMIS (mesure, T-00001059) :
  * R1 — un verrou qui tombe ENTRE le commit d'une version et celui de son
    `SPEC_MUTATED` fait echouer la compensation elle-meme : la ligne
    `agentic_v3 sync-spec: compensation IMPOSSIBLE … remede : supprimer cette
    version de spec_requirements puis relancer sync-spec` PRECEDE le refus
    (code 4). Relancer SANS appliquer d'abord ce remede perd l'evenement pour
    toujours : la relance voit la version UP-TO-DATE.
  * Base vide — une base par defaut VIDE dont `runs/` est a rejouer, sous un
    ecrivain tenu, sort en code 3 sur DEUX lignes : l'annonce `event_store:
    reconstruction AVORTEE … database is locked` puis la ligne du refus ;
    remede : attendre la fin de l'autre session, puis relancer.
  * L'attente de 30 s n'est pas raccourcie : le refus la nomme.
"""

import sys
import json
import contextlib
import argparse
from pathlib import Path
from agentic_v3.db.event_store import EventStore, ReconstructionAvorteeError
from agentic_v3.db.refus_store import EN_PANNE, StoreV3Refuse, aplatir_message, refus_nomme
from agentic_v3.db.schema import get_db_connection
from agentic_v3.ingestion.parse_specs import SpecParser
from agentic_v3.checkpoints.session_checkpoint import SessionCheckpointManager

#: Code de sortie d'un store V3 REFUSÉ à la construction (T-00001005), distinct du
#: 3 de la reconstruction avortée (décision pilote S-00003324).
RC_STORE_REFUSE = 4
#: Code de sortie d'une PANNE d'infrastructure à la construction (verdict
#: `EN PANNE`, couture `cadre` absente), distinct du refus (décision pilote S-00003348).
RC_STORE_PANNE = 5


def main():
    parser = argparse.ArgumentParser(description="Agentic Dev Kit Scale-Up V3 CLI")
    subparsers = parser.add_subparsers(dest="command", help="V3 Commands")

    # Command: sync-spec
    parser_spec = subparsers.add_parser("sync-spec", help="Parse and sync markdown specification file")
    parser_spec.add_argument("file_path", help="Path to markdown specification file")

    # Command: status
    parser_status = subparsers.add_parser("status", help="Get projected status of a task")
    parser_status.add_argument("task_id", help="Task ID")

    # Command: resume
    parser_resume = subparsers.add_parser("resume", help="Resume from latest session checkpoint")

    # Command: dashboard-summary
    parser_dash = subparsers.add_parser("dashboard-summary", help="Print summary of events and projections for dashboard")

    args = parser.parse_args()

    # T-00001005 : le dispatch ENTIER sous un seul `except StoreV3Refuse` — les
    # quatre ouvreurs (`SpecParser()`, `SessionCheckpointManager()` et les deux
    # `EventStore()` ci-dessous) lèvent ce type sur un store refusé ou en panne ;
    # T-00001059 : pour `sync-spec` SEUL, `refus_nomme` enveloppe AUSSI le verbe
    # (`process_and_sync_spec`), où le verrou d'un autre écrivain mord en WAL.
    # UNE ligne stderr, puis `RC_STORE_PANNE` (5) si le verdict est `EN PANNE`,
    # sinon `RC_STORE_REFUSE` (4). Le `sys.exit(3)` de `sync-spec` lève
    # `SystemExit`, que ce `except` ne touche pas.
    try:
        if args.command == "sync-spec":
            # T-00000691 : sur une base par défaut VIDE, construire le store déclenche
            # la reconstruction depuis runs/ ; tant qu'elle n'est pas commitée, le store
            # refuse toute écriture au registre d'événements et au pont board, et
            # sync-spec refuse AVANT sa première écriture (`exiger_ecriture_permise`,
            # donc aucune version de spec sans son SPEC_MUTATED) — UNE ligne et le
            # code 3, jamais un traceback. NON gardés, écrit : les baux de l'outbox,
            # les checkpoints et les leçons. `status` et `dashboard-summary`
            # n'écrivent aucun événement eux-mêmes ; la construction du store peut importer runs/.
            try:
                parser_engine = SpecParser()
                # T-00001059 : le verbe sous le refus nommé — verrou (codes
                # primaires 5 et 517) et store rouvert refusé -> 4, panne
                # d'export -> 5. La bibliothèque relève l'erreur BRUTE, après sa
                # compensation ; `ReconstructionAvorteeError`, non classée,
                # ressort MÊME objet vers le code 3 ci-dessous. T-00001078 : les codes
                # 8 (lecture seule) et 11 (corrompu) y sont classés comme à la
                # construction ; `erreurs_os=False` laisse REMONTER une sœur `OSError`
                # (`PermissionError` d'un spec illisible : ce n'est pas un store refusé).
                with refus_nomme(parser_engine.db_path, erreurs_os=False):
                    results = parser_engine.process_and_sync_spec(args.file_path)
            except ReconstructionAvorteeError as exc:
                # S-00003354 : le remède embarque des chemins — aplati, UNE ligne.
                print(f"agentic_v3 sync-spec: {aplatir_message(str(exc))}", file=sys.stderr)
                sys.exit(3)
            print(f"Synced {len(results)} specification sections from {args.file_path}:")
            for chunk, is_mutated in results:
                status_str = "MUTATED (New Version)" if is_mutated else "UP-TO-DATE"
                print(f" - [{chunk.req_id}] v{chunk.version} ({chunk.section_title}): {status_str}")

        elif args.command == "status":
            # Construction à ZÉRO argument, inchangée (SYM-09256 la fige).
            with refus_nomme(None):
                store = EventStore()
            proj = store.get_task_projection(args.task_id)
            if proj:
                print(json.dumps(proj, indent=2))
            else:
                print(f"No task projection found for ID: {args.task_id}")

        elif args.command == "resume":
            checkpoint_mgr = SessionCheckpointManager()
            ckpt = checkpoint_mgr.get_latest_checkpoint()
            if ckpt:
                print(f"Found active session checkpoint (Phase {ckpt['current_phase']}: {ckpt['phase_name']}):")
                print(json.dumps(ckpt["checkpoint_data"], indent=2))
            else:
                print("No active session checkpoint found.")

        elif args.command == "dashboard-summary":
            # Le refus ne couvre que la construction ; la lecture passe ensuite par
            # `schema.get_db_connection` (T-00001066). Une erreur APRÈS la
            # construction reste un traceback (résidu nommé de T-00001005).
            with refus_nomme(None):
                store = EventStore()
            with contextlib.closing(get_db_connection(store.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as total_events FROM events_ledger;")
                total_events = cursor.fetchone()["total_events"]
                cursor.execute("SELECT COUNT(*) as total_tasks FROM task_projections;")
                total_tasks = cursor.fetchone()["total_tasks"]
            print(json.dumps({"total_events": total_events, "total_tasks": total_tasks}, indent=2))

        else:
            parser.print_help()
    except StoreV3Refuse as exc:
        print(f"agentic_v3 {args.command}: {exc}", file=sys.stderr)
        sys.exit(RC_STORE_PANNE if exc.verdict == EN_PANNE else RC_STORE_REFUSE)


if __name__ == "__main__":
    main()
