# agents/ — source unique des défs d'agents

Chaque `agents/<nom>.md` est la SOURCE UNIQUE d'une déf d'agent (une décision du
pilote). Les défs des cinq hôtes et le roster JSON en sont RENDUS :

- éditer ici, puis `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire` ;
- ne jamais éditer à la main `.claude/agents/`, `.codex/agents/`, `.github/agents/`,
  `.gemini/agents/`, `.kimi-code/agents/` (ni `.agents/vendor/cadre/data/roster/`) : le rendu les réécrit ;
- `bash .agents/pyrun.sh .agents/bin/render_hosts.py --check` signale toute dérive (ABSENT,
  DERIVE, ORPHELIN, ETRANGER) des fichiers à plat de ces dossiers (un sous-dossier, un fichier
  caché ou un autre suffixe n'est pas lu) et nomme son remède.

Ce `README.md` n'est pas une source : `render_hosts.py` l'ignore.

Langue d'une source : la règle est `.agents/ref/WORKING_LANGUAGE.md`, étendue à toutes les défs
du kit par décision du pilote du kit. La prose s'écrit en anglais,
chaque corps porte une fois le renvoi à la fiche et `You answer in French.` (sauf
`language-detector`, qui n'imprime qu'un JSON — exception fermée, nommée par la fiche) ; ce que l'agent
imprime au pilote — blocs clôturés, lignes et spans `▸`, citations «…» — reste en français, à
l'octet. Deux bancs la tiennent dans le kit : `.agents/evals/test_working_language.py` et
`.agents/evals/test_defs_anglais.py` ; une déf neuve rédigée en français rougit dès sa naissance.
Changer À DESSEIN un bloc imprimé ou un span d'une déf : un commit à lui, puis un commit ULTÉRIEUR qui
mappe la déf sur le sha hexadécimal littéral de ce commit dans `EXT_BASE_PAR_DEF` (procédure : la fiche, § What the bench sees).

Les commandes suivent le même régime depuis `commands/` (voir `commands/README.md`) : le même
`render_hosts.py` rend `.claude/commands/` et les miroirs `.agents/skills/source-command-*`.

## Cursor (cible dérivée, non mesurée)

`render_hosts.py` rend aussi, depuis les mêmes sources :

- `.cursor/rules/<nom>.mdc` pour chaque déf qui porte un rendu `kimi` : un frontmatter
  `description:` (celle de l'entête kimi, sur une ligne) et `alwaysApply: false`, sans `globs`,
  puis le CORPS KIMI (hôte non tiéré, sans `model` ni `effort`) ;
- `.cursor/commands/<nom>.md` pour chaque commande hors Claude Code seul : les octets de
  `commands/<nom>.md` (frontmatter réduit à `description` s'il porte autre chose).

Ce qui n'est PAS rendu : une déf sans rendu kimi (`--check` la nomme : `cursor: sans rendu
kimi : <noms>`), et `night` (Claude Code seul).

Dans un dossier rendu (défs des cinq hôtes — `.claude`, `.codex`, `.github`, `.gemini`,
`.kimi-code` —, roster `.agents/vendor/cadre/data/roster/`, `.claude/commands/`, miroirs
`.agents/skills/source-command-*`, `.cursor/rules/`, `.cursor/commands/`), le rendu juge un
fichier par son TÉMOIN DU KIT du même nom : `<roster>/<nom>.json` pour une déf d'hôte ou une
règle Cursor, le miroir `source-command-<nom>` pour une commande ; un JSON du roster ou un
miroir est son propre témoin. Un nom de déf ou de commande du kit reste remplacé par `--ecrire`.
Pour le reste :

- SANS témoin, le fichier est HORS RENDU : jamais réécrit ni retiré, compté sans son nom par
  la note `hors rendu : <n> fichier(s) sans temoin du kit (roster ou miroir du meme nom) ou sans en-tete reconnu sous .cursor/, laisses intacts`,
  ni écart ni blocage de `--check` ou `--ecrire` ;
- AVEC témoin et l'en-tête reconnu (déf à ligne `name:`, commande à ligne `description:`,
  règle `.cursor/rules/<nom>.mdc` à `description:` puis `alwaysApply: false`), c'est un
  ORPHELIN : tant qu'il est là, `--ecrire` n'écrit rien, et `--retirer-orphelins` le retire ;
- AVEC témoin, sans l'en-tête : ETRANGER, sauf sous `.cursor/`, où il est hors rendu.

Bornes : une déf retirée AVEC son JSON du roster, ou une commande retirée AVEC son miroir,
laisse ses rendus hors rendu, intacts et encore invocables — à ôter à la main ; `night` n'a pas de
miroir : un `.cursor/commands/night.md` (jamais rendu) est hors rendu, et
`.claude/commands/night.md` le devient si sa source est retirée — à ôter à la main ; un fichier sans en-tête ni témoin (un `README.md` sous `.claude/agents/`)
n'est plus ETRANGER ; le marquage des fichiers rendus n'est pas construit, le témoin par nom
en tient lieu. Cursor n'entre PAS dans la liste fermée `cadre.config.HOTES`, qui n'en change pas.
**Rien ne prouve que Cursor lise ces fichiers** : aucune mesure n'a été faite sur Cursor.
