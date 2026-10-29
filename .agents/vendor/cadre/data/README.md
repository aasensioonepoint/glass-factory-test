# `src/cadre/data/` — le référentiel embarqué

Ce répertoire est la **couche la plus faible** de la précédence de
configuration, celle que `config.py` annonce en premier :

    embarqué  <  utilisateur  <  hôte  <  projet

`cadre.json` y est **délibérément vide**, et c'est un état déclaré plutôt qu'un
oubli. Il est posé ici parce que la revue de clôture du 2026-09-12 a mesuré que
la couche n'existait pas du tout : `config.fichiers()` interrogeait
`pkg_root()/data/cadre.json`, le répertoire n'était pas dans le paquet, et le
banc de précédence n'écrivait que les trois autres couches — donc il était vert
sur une couche vide. Une précédence annoncée à quatre couches qui en a trois ment
sur la plus faible, celle que personne ne pense à vérifier, et `cadre config
explain` ne pouvait jamais répondre `posee par : embarque`.

**Ce qu'on y met est une décision du pilote**, pas une conséquence de ce
correctif. Tant qu'elle n'est pas prise, la couche existe et ne pose aucune clé —
ce qui est exactement ce que `charger().effective == {}` doit continuer de dire
sur un poste vierge.

Deux contraintes de forme, appliquées par `config._lire` :

- la racine du fichier **doit** être un objet JSON, tout le reste est refusé ;
- les tables fusionnent en profondeur, les listes sont **remplacées** — une
  allowlist fusionnée réinjecterait ce qu'une couche forte croit avoir retiré.

Le contenu de ce répertoire doit voyager dans la wheel. Le backend est
`hatchling`, dont la cible `packages = ["src/cadre"]` embarque tout ce qui vit
sous le paquet, fichiers non-Python compris — donc aucune déclaration
supplémentaire n'est nécessaire, et c'est précisément pour cela qu'il faut le
mesurer plutôt que le supposer. Un défaut livré qui n'arrive pas chez l'adoptant
est pire qu'une absence de défaut, parce qu'il est vrai en editable et faux en
installé. La vérification appartient à `check_wheel_contents`, prévu en Phase 4.

## `roster/` — le roster canonique des défs d'agents

Une déf par fichier, `roster/<nom>.json`, lue par `cadre.roster.charger()` —
sans paramètre, sur le modèle de `socle.charger()`. `cadre.roster.cardinal()` en
dérive le nombre de défs : aucun littéral ne l'écrit.

**La forme, FORMAT 1**, tenue par `roster._valider` (stdlib seule) :

    {"version_format": 1, "nom": "<nom>",
     "rendus": {"<hôte>": {"entete": [<lignes>], "corps": [<lignes>] | {"comme": "claude"}}}}

Les hôtes sont ceux de `config.HOTES`, et `claude` est obligatoire. Le texte d'un
rendu est fait de ses lignes jointes par `\n`, entre les délimiteurs de son
format : le frontmatter `---` d'un Markdown, ou `developer_instructions = """`
dans le TOML de codex. Un corps identique à celui de `claude` s'écrit
`{"comme": "claude"}`, et `comme` ne vise que `claude`. Aucun marqueur
`cadre.managed` n'est stocké ici : il se pose au rendu. Une ligne
d'entête qui porte `cadre.` en commentaire (`#`, `<!--`), à toute indentation,
ou, hors TOML, en clé nue ou quotée (`cadre.managed: true`, la forme d'avant)
est refusée, clé connue ou non. C'est PLUS STRICT que `managed.lire`, qui ne
juge que la colonne 0 du frontmatter et la tête d'un TOML (mesuré : il accepte
`  # cadre.autre: x` indenté). Borne : en TOML, une clé `cadre.managed = …`
n'est pas refusée par le roster ; `managed.poser` la refuse au rendu.

**Ce que le répertoire peut contenir.** Des fichiers `<nom>.json`, à plat. Un
sous-répertoire est REFUSÉ (`RosterIllisible` le nomme) : une déf qu'on y
rangerait serait perdue sans un mot. Une entrée dont le nom ouvre sur `.`
(fichier ou répertoire, `.json` compris) est IGNORÉE : c'est un artefact d'OS
invisible à git, comme `.DS_Store`. BORNE : seul le point initial est ignoré ;
`desktop.ini` et `Thumbs.db` (Windows) restent refusés, comme tout fichier qui
n'est pas un `.json`.

**Le sens de vérité.** La source `agents/<nom>.md` fait foi (une décision du pilote) ; ce
répertoire en est RENDU, jamais écrit à la main, par

    bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire

dans le même commit que toute modification de la source, et chaque
`roster/<nom>.json` qu'il touche entre au write-set de la tâche (`tasks.py
writeset`). `--regenerer` reste une seconde voie qui n'est plus le remède :

    python3 .agents/evals/test_cadre_roster.py --regenerer

Le banc `test_cadre_roster.py` rougit (T1, T2) sur un roster qui ne suit plus
les défs vivantes. `--regenerer` écrit le
`.json` de chaque déf vivante dont les octets changent, et retire un `.json`
sans déf vivante — jamais une entrée qui ouvre sur `.`, que le module ignore.
Elle REFUSE, avant toute écriture, tant qu'`apply-mode` est actif
(`.agents/state/local/MODEL_MODE` présent : les défs portent les tiers
`expert` ; `python3 core-scripts/apply-mode.py restore` d'abord), et devant un
lien symbolique sur le chemin du roster ou sur une cible.

**Dette nommée : la convergence des rendus.** Chaque rendu est
stocké tel quel, parce qu'aucun modèle typé ne rend aujourd'hui les fichiers des
cinq hôtes à l'octet. Mesuré le 2026-10-09 : le corps diffère de celui de
`claude` pour chaque déf sur codex, pour toutes sauf load-tester sur copilot
(load-tester, ajoutée le 2026-10-10, y a un corps identique), pour 20 d'entre elles sur
gemini et pour 9 sur kimi. `terraform-deployer` (2026-10-18) et `reverse-engineer`
(2026-10-22) sont venues après cette mesure : leurs corps n'y sont pas comptés.
Les entêtes, eux, diffèrent d'un hôte à l'autre
(outils, modèles), si bien qu'ajouter un hôte demande aujourd'hui ses entêtes, et
pas seulement un renderer. La tâche de convergence que prévoit Q7 n'existe sur
aucun des deux boards au 2026-10-09. Tant qu'elle n'est pas ouverte, ce doublon
d'environ 1 Mo dans la wheel reste une dette, pas un état voulu.
