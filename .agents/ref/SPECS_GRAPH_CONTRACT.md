# SPECS_GRAPH.json — contrat de publication du graphe de specs

Le dashboard sert une vue **`#/specs`** (« graphe des décisions ») qui rend la
section `specs_graph` de `/api/snapshot`. **Le kit ne parse JAMAIS les sources de
specs d'un projet** ; il lit un artefact, à ce chemin exact :

```
.agents/state/index/SPECS_GRAPH.json
```

Deux chemins de publication, avec une précédence stricte :

1. **Publication manuelle** (la plus riche) — un projet qui possède un corpus de
   specs structuré (epics, décisions `DEC-NN.k`…) publie son propre artefact,
   conforme au schéma ci-dessous. Exemple complet :
   `.agents/ref/SPECS_GRAPH_SAMPLE.json`.
2. **Génération par défaut** — sans publication manuelle, le kit dérive un
   graphe de ses trois stores d'état (`TASKS.json`, `SPECS.json`, `LEDGER.json`)
   via `.agents/bin/specs_graph.py` : la vue suit alors le projet au fur et à
   mesure, sans artefact écrit à la main (§ « Génération par défaut »).

La précédence tient à un marqueur : tout fichier généré porte
`"generator": "specs_graph.py v1"` en tête d'objet (champ ignoré au rendu).
`specs_graph.py generate` n'écrit que si le fichier est **absent** ou **porte ce
marqueur** — un artefact SANS marqueur (y compris illisible, peut-être une
publication manuelle en cours d'édition) n'est **jamais** écrasé ; `--force` est
le seul contournement, humain et explicite.

**Absence du fichier = état de repos légitime** (projet neuf, ou génération
jamais lancée) : la section répond `no_events`, la vue affiche un bloc d'état qui
DIT comment publier, jamais un cadre vide. Le générateur respecte cet état : un
projet sans tâche ni journal ne publie **RIEN**, jamais un graphe vide. Fichier
présent mais hors contrat = `degraded` **avec la raison**. Aucun de ces cas ne
casse le dashboard.

## Schéma

```json
{
  "version": 1,
  "generated_at": "2026-08-26T12:00:00Z",
  "title": "MonProjet — specs fonctionnelles",
  "source": "specs/backlog",
  "stats": {"decisions": 257, "prise": 12, "a_prendre": 40, "en_analyse": 205},
  "nodes": [
    {
      "id": "E-01",
      "title": "Cadrage, glossaire, gouvernance et décisions",
      "release": "R0",
      "size": {"tasks": 8, "br": 40, "lines": 862},
      "counts": {"prise": 10, "a_prendre": 0, "en_analyse": 0},
      "decisions": [
        {"id": "DEC-01.01", "status": "prise", "q": "…", "date": "2026-07-30"}
      ]
    }
  ],
  "edges": [{"source": "E-10", "target": "E-05", "weight": 25}],
  "arbitrages": [
    {"section": "C-1", "refs": ["DEC-11.3", "BR-11.15"], "text": "…"}
  ]
}
```

- `nodes[].id` (string, requis) — identifiant court du nœud (ex. epic `E-NN`).
- `nodes[].release` — anneau de layout : `R0` (centre) → `R3` (externe) ;
  valeur inconnue → anneau externe, jamais un nœud escamoté.
- `nodes[].counts` — décomptes par statut ; vocabulaire de statuts **fermé** :
  `prise` · `prise_a_clore` · `a_prendre` · `en_analyse`. La couleur du nœud est
  le **PIRE** statut présent (`a_prendre` > `en_analyse` > `prise_a_clore` >
  `prise`) — jamais une moyenne, qui noierait la seule décision qui attend un
  humain.
- `nodes[].size` — au choix `tasks`/`br`/`lines` (entiers) : dimensionne le nœud.
  Le rayon suit la **racine carrée** de la valeur, parce que l'œil compare des
  aires.
- `edges[]` — `source`/`target` doivent référencer des `nodes[].id` **retenus**
  (les autres sont écartées, jamais rendues pendantes) ; `weight` pilote
  l'épaisseur.
- `arbitrages[].refs` — IDs cités : le panneau de détail d'un nœud affiche les
  arbitrages dont une ref vaut l'id du nœud.

## Génération par défaut (`specs_graph.py`)

`python .agents/bin/specs_graph.py generate` projette les trois stores d'état
dans le schéma ci-dessus (`status` pour l'état de l'artefact, `--stdout` pour
prévisualiser sans écrire, `--force` pour écraser une publication manuelle).
Le mapping :

| Contrat | Source dans les stores |
|---|---|
| nœud | une tâche du board, plus un nœud **synthétique** par tâche citée dans le journal mais absente du board (travail purgé ≠ travail invisible) |
| `release` (anneau) | l'état : `done` → R0 (centre), `running` → R1, `blocked` → R2, `pending` → R3 — le centre grossit à mesure que le projet avance |
| `decisions[]` | entrées du journal : `decision` → `prise` ; `plan`/`verdict` → `en_analyse` tant que la tâche est ouverte, `prise` une fois close ; décisions actives du ledger (`related`) → `prise` ; une tâche `blocked` synthétise UN item `a_prendre` depuis son `stage` (bloquée = décision humaine attendue) |
| `size.tasks` | le nombre d'entrées du journal de la tâche (les `delta` comptent ici, pas en décision), plancher à 1 |
| `edges[]` | co-citations : un texte de journal, ou d'une entrée ACTIVE du ledger rattachée (`related`) à un nœud, qui nomme une autre tâche relie les deux nœuds ; `weight` = nombre de citations. Identité de tâche = `identity_key` de `tasks.py` (le journal et le ledger passent par une recopie locale `_task_num`, sans la borne à 15 chiffres) : un id ancien par sa VALEUR numérique (`T-1` ≡ `T-001` ≡ `T-00000001`), un `T-<ULID>` (26 symboles Crockford en majuscules, toute nouvelle tâche depuis la bascule C2 du kit) par son corps EXACT. Tri des arêtes : poids décroissant, puis clé d'identité croissante (tout id ancien avant tout ULID) ; les NŒUDS sont rangés à l'inverse (par état, puis récents d'abord : tout ULID avant tout id ancien), ordre qui décide la coupe à 200 |
| `arbitrages[]` | contraintes **actives** du ledger rattachées (`related`) à un nœud du graphe |

**UN SEUL déclencheur automatique est câblé, et l'autre est refusé nommément.**

- **Câblé** : `.agents/bin/post-task-done-index.sh`, à chaque `tasks.py … done`,
  après le commit des stores et celui des exports de run (T-00000703), sur les
  quatre hôtes qui enregistrent ce hook (Claude Code, Codex, Copilot, Kimi Code). Advisory : son échec est silencieux et ne peut
  pas faire échouer une clôture — le graphe est une VUE, jamais un invariant.
  Le canal est prouvé à ses **DEUX** bouts : l'écrivain par le cas 16 de
  `post-task-done-index.test.sh` (publication à la clôture **et** précédence
  manuelle préservée à travers le hook), le lecteur par `test_specs_graph.py`
  (aller-retour par le vrai `dashboard_readers`).
- **Refusé** : `session-start.sh`. Le kit amont l'y câble aussi ; ici le
  démarrage de session fait déjà l'injection du board, le contexte du ledger et
  un rebuild d'index gardé — un quatrième balayage des stores à chaque
  démarrage achèterait un rafraîchissement que la clôture a déjà produit. Un
  projet qui veut l'amorçage lance `specs_graph.py generate` une fois à la main.

**Conséquence assumée, dite plutôt qu'implicite** : sur un dépôt où aucune tâche
n'a été close depuis l'arrivée de ce mécanisme, l'artefact est ABSENT et la vue
répond `no_events`. C'est l'état de repos du contrat, pas une panne.

Le générateur applique lui-même les bornes du lecteur, pour qu'un artefact
généré ne soit jamais rendu tronqué ; ce qu'une borne écarte est dit sur stdout
ET consigné dans le champ `notes` de l'artefact (les hooks jettent stdout —
l'artefact garde la trace). Il est **idempotent** : un graphe inchangé n'est pas
réécrit (pas de churn de `generated_at`).

## Bornes (appliquées par le lecteur, jamais une erreur)

Le snapshot est pollé toutes les 5 s : le lecteur borne tout ce qui atteint le
payload — **200** nœuds, **600** arêtes, **60** décisions/nœud, **120**
arbitrages, textes tronqués à **240** caractères. Au-delà, la section porte un
bloc `truncated` chiffré et la vue l'affiche. Une troncature silencieuse se lit
comme une couverture complète ; celle-ci est toujours dite.

Ces bornes valent surtout pour une **publication manuelle** : elle ne passe par
aucun générateur, donc le lecteur est le seul endroit où elle peut être bornée.

## Suivi de l'artefact en versionné

Ce dépôt **ne suit pas** `SPECS_GRAPH.json` (`.gitignore`) : il est dérivé, et
le hook de clôture commite les stores par pathspec explicite sans le prendre.
**C'est un choix de ce dépôt, pas une loi du kit.** Un projet qui publie à la
main a toutes les raisons de versionner son artefact — il lui suffit de retirer
la ligne du `.gitignore`. La génération étant idempotente, le suivre ne coûte
aucun churn.

## Ce que ce contrat ne reprend PAS de son amont, et pourquoi

Le kit d'origine a **perdu la source React de son bundle**. Sa page specs est
donc manuscrite hors bundle (`specs.html`, `assets/specs.js`, `assets/specs.css`,
`assets/nav.js`), avec deux rustines manuelles — un `<script src="nav.js">` dans
`index.html` et un appendice dans `app.css` — que son propre contrat inscrit en
dette « à ré-appliquer si le front est un jour rebuildé ».

**Nous n'avons pas ce défaut.** `.agents/ui-src/` est la source maintenue, et
`vite.config.js` porte `emptyOutDir: true` sur `../ui` : un fichier posé à la
main dans `.agents/ui/` serait **supprimé au build suivant**. Les quatre
fichiers manuscrits ne sont donc pas repris — un contournement de leur défaut
n'est pas un manque du nôtre. La page entre comme une **vue de la SPA**
(`src/views/Specs.jsx`, route `#/specs`), construite depuis la source comme
toutes les autres, et l'entrée de menu est une **donnée** de `nav.jsx`, non une
injection DOM par un script tiers.
