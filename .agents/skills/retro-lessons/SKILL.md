---
name: retro-lessons
description: Consolidate the lessons journal retro/LESSONS.md and decide what gets promoted. Use for the weekly consolidation, when a verifier verdict carries a LECON_CANDIDATE, or before promoting a lesson into a skill or the router body.
---

# Boucle LESSONS — capture, consolidation, promotion

## Quand lire ce fichier

- **Consolidation hebdomadaire** du journal : `python .agents/bin/retro.py consolidate`.
- **Après un verdict** de `plan-critic` ou d'`exec-critic` dont `LECON_CANDIDATE != aucune`.
- **Avant de promouvoir** une leçon : c'est ici que se décide la destination, et le coût.

Le journal est `retro/LESSONS.md`. Il est **LOCAL** : `strip: retro/` dans `.template-exclude` fait
qu'il ne voyage jamais. Ce qui atteint un projet adoptant, c'est la **destination** d'une promotion —
une skill qui voyage — jamais la donnée brute.

## Les 5 critères d'extraction — et la provenance de chacun

Une leçon mérite d'être extraite (skill, ou corps du routeur) quand **au moins 2** de ces 5 critères
tiennent. La provenance est écrite pour que chaque critère puisse être CONTESTÉ, pas seulement obéi.

| # | Critère | Provenance |
|---|---|---|
| 1 | **répétition ≥ 2** — la même leçon revient | brief Annexe B §2 |
| 2 | **volume > 20 lignes** — le sujet ne tient pas en un invariant | brief Annexe B §2 |
| 3 | **spécificité** — la règle vaut pour un domaine nommé, pas partout | brief Annexe B §2 |
| 4 | **procédure vérifiable** — il y a des étapes qu'on peut rejouer | brief Annexe B §2 |
| 5 | **universalité mesurée** — vraie HORS de ce dépôt, **et** son ignorance a déjà coûté une session MESURÉE | `AGENTS.md` § Institutional memory |

Le critère 1 est **pré-coché par le compteur** de `consolidate` ; les quatre autres sont un jugement
humain. Le 5ᵉ est le critère de promotion du ledger et il est le plus exigeant : « une bonne idée » ne
suffit pas, il faut une session mesurée.

## Le processus

1. **Capture** — après un verdict :
   `python .agents/bin/retro.py add --cause <CAUSE_RACINE> --text "<leçon>" [--portee universelle]`.
   `CAUSE_RACINE` est le set fermé du vérificateur : `CONTEXTE_MANQUANT`, `PAS_DE_VERIFICATION`,
   `CONSIGNE_MAL_PLACEE`, `PERIMETRE_FLOU`, `AUTRE`. `--portee` vaut `locale` par défaut.
   Un payload commençant par `/` passe par STDIN (`--text -`) : un argv Git-Bash le transformerait
   sinon en chemin Windows.
2. **Consolidation** — `python .agents/bin/retro.py consolidate` compte, marque ` [à-promouvoir]`
   toute leçon répétée ≥ 2, restitue la checklist des 5 critères, purge les entrées > 90 j jamais
   re-déclenchées et non marquées, et garde le journal sous 50 entrées **sans jamais évincer une
   entrée marquée** (si c'est impossible, il déclare le plafond INATTEIGNABLE).
3. **Application** — la promotion est une **PR humaine**. `retro.py` restitue la commande,
   `ledger.py promote` MARQUE une entrée de registre et imprime un bloc à coller : **ni l'un ni
   l'autre n'écrit une surface d'atterrissage**. C'est ce qui force la curation avant qu'une leçon
   atteigne un tiers.

## Les 3 destinations de promotion

| Portée | Destination | Voyage ? |
|---|---|---|
| `locale` (défaut) | reste marquée dans `retro/LESSONS.md` | **non** — le journal est stripé |
| `universelle`, rentre dans un domaine | **skill de domaine** — `--ref ".agents/skills/<domaine>/SKILL.md"` | **oui** |
| `universelle`, transverse | **skill `lessons-seed`** — `--ref ".agents/skills/lessons-seed/SKILL.md"` | **oui** |
| invariant de 1er ordre (rare) | corps du routeur `AGENTS.md` | oui |

**Le corps du routeur n'accueille plus de leçon**, sauf invariant de 1er ordre qui doit rester lu à
CHAQUE session. C'est ce qui l'a fait gonfler ; une skill, elle, est lue quand on l'invoque.

Le coût exact de ce choix — ce qu'une promotion RETIRE de l'injection SessionStart — est restitué par
`retro.py consolidate` et repris dans la skill `lessons-seed`. Lis-le avant de promouvoir.

## Anti-patterns

- **REFORMULER CASSE LE COMPTEUR.** La répétition n'est mesurée qu'à formulation IDENTIQUE (casse et
  espaces près) et dans la fenêtre de 90 jours. Deux formulations d'une même leçon sont **deux clés**
  et n'atteignent jamais le seuil ≥ 2 par le compteur seul. Réutilise la formulation existante — ou
  assume que c'est la consolidation HUMAINE, pas le compteur, qui rattrapera la leçon.
- **Leçon narrative.** « On a eu un souci avec le cache » n'est pas une leçon. Écris une règle
  réutilisable, au présent, qui dit quoi faire ou ne pas faire, et ce qu'elle a coûté.
- **Journal non purgé.** Un journal de 200 entrées n'est plus lu ; le plafond et la purge existent
  pour que la lecture reste possible. Ne les désarme pas, consolide.
- **Promotion à la 1ʳᵉ occurrence.** Un incident unique est une anecdote. Le seuil ≥ 2 est là pour
  distinguer un accident d'un motif.
- **Promouvoir vers le corps du routeur par réflexe.** C'est le canal le plus cher (lu à chaque
  session, sur chaque hôte). Réserve-le aux invariants de 1er ordre.
