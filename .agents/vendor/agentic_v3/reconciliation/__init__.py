"""
Board reconciliation package — le pont entre TASKS.json et l'EventStore V3.

T-012 : `VisualReconciliationEngine` a ete RETIRE de ce paquet. Il ne servait
que la sous-commande `run-task`, que rien ne citait, et la porte d'interface
qu'il visait a ete retiree par T-00000505. Le re-export d'ici etait d'ailleurs
son seul consommateur reel : importer `board_bridge` chargeait un moteur de
diff visuel dont personne ne voulait.
"""

from agentic_v3.reconciliation.board_bridge import BoardBridge

__all__ = ["BoardBridge"]
