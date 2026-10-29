# commands/ — source unique des commandes

Chaque `commands/<nom>.md` est la SOURCE UNIQUE d'une commande (une décision du
pilote). Ses cibles en sont RENDUES :

- `.claude/commands/<nom>.md`, identique à la source à l'octet ;
- hors `night` (Claude Code seul), le miroir cross-hôte
  `.agents/skills/source-command-<nom>/SKILL.md` : la description de la commande, puis son corps
  sous `## Command Template`, sans ligne `Effort:` (propre à Claude Code) et avec les traductions
  d'hôte (`/<commande>` lu `$<commande>`, « Claude Code session » lu « Codex session »,
  `.claude/skills/` sous sa forme hôte-neutre) — rien n'y est ajouté : la ligne
  `Shared process reference:` qui pointe `.agents/skills/<nom>/SKILL.md` s'écrit dans la source ;
- hors `night`, `.cursor/commands/<nom>.md` (cible dérivée, NON MESURÉE).

- éditer ici, puis `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire` ;
- ne jamais éditer à la main `.claude/commands/`, `.agents/skills/source-command-*/` ni
  `.cursor/commands/` : le
  rendu les réécrit ;
- `bash .agents/pyrun.sh .agents/bin/render_hosts.py --check` signale toute dérive (ABSENT,
  DERIVE, ORPHELIN, ETRANGER ; un fichier sans témoin du kit du même nom est HORS RENDU —
  compté, jamais nommé) des fichiers à plat de ces dossiers (un sous-dossier, un fichier
  caché ou un autre suffixe n'est pas lu) et nomme son remède.

Ce `README.md` n'est pas une source : `render_hosts.py` l'ignore.
