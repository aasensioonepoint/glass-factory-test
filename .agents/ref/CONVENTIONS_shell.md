# Conventions — Shell (bash / sh)

## §1 — Règles canoniques du kit

### LA RÈGLE QUI PRIME : ÉCRIRE DU SHELL QUE LE SAST PEUT LIRE

Le scanner SAST de classe 1 du kit (`semgrep`, parseur `tree-sitter-bash`) bute
sur des constructions que **`bash -n` accepte sans un mot**. Ce n'est pas une
contrainte du langage : c'est une contrainte de l'ANALYSEUR, et c'est
précisément ce qui la rend invisible — le script tourne parfaitement.

**CE QUE ÇA COÛTE.** Un SEUL site de ces formes fait échouer le parse du
**fichier ENTIER**, qui est alors **retiré du compte des cibles inspectées**.
La porte annonce `clean` sur un périmètre qu'elle n'a **jamais lu**.

Mesuré sur ce dépôt le 2026-09-09 : **17 fichiers shell sur 121** étaient hors
lecture — 14 % du shell. Les corriger a fait apparaître **8 findings `ERROR`
préexistants** sur lesquels la porte était aveugle depuis toujours.

---

### LES HUIT FORMES INTERDITES, ET LEUR REMÈDE

Chaque remède ci-dessous a été **vérifié en sortie** (mêmes octets, mêmes
verdicts) avant d'être adopté.

#### 1. Métacaractère dans une expansion de paramètre

Un `<`, `>`, `|`, `&` ou `(` écrit **dans la syntaxe** d'une expansion casse le
parse. Fais-le passer par la **valeur** d'une variable.

```bash
# NON                                   # OUI
echo "${prefix:-<root>}"                _racine='<root>'
                                        echo "${prefix:-$_racine}"

printf '%s' "${ROUTE:+$ROUTE | }"       _sep=' | '
                                        printf '%s' "${ROUTE:+$ROUTE$_sep}"

args="${args%%&&*}"                     _amp='&&'
                                        args="${args%%$_amp*}"
```

Le motif reste identique une fois la variable développée. Dans une fonction
RÉCURSIVE, déclare la variable `local`.

#### 2. Arithmétique parenthésée

```bash
# NON                                   # OUI
_min=$(( (_now - _epoch) / 60 ))        _delta=$(( _now - _epoch ))
                                        _min=$(( _delta / 60 ))
```

#### 3. `10#$X` — la notation de base forcée

Celle-ci ne produit pas un parse partiel mais un **`Syntax error` COMPLET**.

```bash
# NON                                   # OUI
(( 10#$RAW >= 1 && 10#$RAW <= 900 ))    [ "$RAW" -ge 1 ] && [ "$RAW" -le 900 ]
```

`[ … -ge … ]` compare en **décimal**, donc sans le piège de l'octal — vérifié
sur `08`, `09`, `007`, `60`, `900` : mêmes verdicts qu'avec `10#`.

#### 4. `!` devant un groupe d'accolades

La cause exacte est le `!` DEVANT les accolades. Sans le `!`, ou sans les
accolades, le parse passe. Le pipeline n'y est pour rien.

```bash
# NON                                   # OUI
if ! { have tar && tar -cf - . ; }; then   _ok=1
  ...                                      { have tar && tar -cf - . ; } || _ok=0
fi                                         if [ "$_ok" -eq 0 ]; then
                                             ...
                                           fi
```

Le groupe reste un groupe — **même shell, aucun sous-shell**. Seul le `!` sort.

#### 5. Heredoc en CONDITION de `if`

Vaut aussi pour un délimiteur quoté (`<<'MOT'`) et pour `<<-`.

```bash
# NON                                   # OUI
if "$PY" - <<PY                         "$PY" - <<PY
...                                     ...
PY                                      PY
then                                    _rc=$?
  ok                                    if [ "$_rc" -eq 0 ]; then
fi                                        ok
                                        fi
```

#### 6. Première clause collée au `case … in`

**Le `esac` n'y est POUR RIEN** : c'est la clause sur la même ligne que le `in`
qui casse. `case "$X" in` seul en fin de ligne parse ; suivi d'un commentaire
aussi.

```bash
# NON                                   # OUI
case "$X" in a) : ;; esac               case "$X" in
                                          a) : ;;
for t in $l; do case "$t" in            esac
  -*) ;; *) f "$t" ;; esac; done
                                        for t in $l; do
f() { case "$1" in *x*) return 0 ;;       case "$t" in
  *) return 1 ;; esac; }                    -*) ;;
                                            *) f "$t" ;;
case "$E" in *"DEGRADED"*) ok ;;          esac
  *) ko ;; esac                         done
```

**N'ÉCLATE PAS le corps sur `;;`** : un `;;` peut vivre dans une chaîne, et le
découper demanderait de parser les quotes — c'est-à-dire de réécrire le parseur
qu'on contourne. Trois lignes suffisent : `case … in`, le corps, `esac`.

#### 7. Espace ÉCHAPPÉ dans un motif de `case`

```bash
# NON                                   # OUI
set|set\ *)   return 0 ;;               set|"set "*)  return 0 ;;
cat\ *)       return 0 ;;               "cat "*)      return 0 ;;
\[\ *)        return 0 ;;               "[ "*)        return 0 ;;
```

L'espace **cité** dit exactement la même chose que l'espace échappé.

#### 8. Classe de caractères contenant un antislash

```bash
# NON                                   # OUI
/*|?:[\\/]*) target=... ;;              /*|?:/*|?:\\*) target=... ;;
```

---

### CE QUE TU FAIS AVANT DE PROPOSER DU SHELL

1. `bash -n <fichier>` — nécessaire, **jamais suffisant** : il accepte les huit
   formes ci-dessus.
2. `python3 -m pytest .agents/evals/test_no_compact_case.py -q` — deux étages :
   quatre motifs de ligne qui tiennent **sans semgrep**, et un relevé de parse
   repo-wide qui les attrape **toutes** quand semgrep est là.

Le relevé de parse se fait **un fichier à la fois**. Un scan groupé
SOUS-COMPTE : mesuré, `safe-bash.test.sh` rendait 0 erreur dans un lot de 121 et
1 erreur scanné seul. Et semgrep ne rend **qu'une erreur par fichier** — chaque
correction en découvre une autre, donc on **re-mesure après chaque geste**.

---

### AUTRES RÈGLES DE SHELL DU KIT

- **`set -uo pipefail`** est la forme du dépôt. `set -e` n'est PAS ajouté par
  défaut : les gardes relèvent leurs statuts explicitement, et un `-e` posé
  après coup change le sens de tout `&&` déjà écrit.
- **Un hook REFUSE, il ne demande pas** — et un hook qui échoue FERMÉ gèle
  l'hôte. Sur un événement `Stop`, un `exit 0` non désiré vaut mieux qu'un
  blocage accidentel. → `.agents/skills/guardrails/SKILL.md`
- **Une vérification n'est JAMAIS tronquée** par `| tail` ou `| head` : le
  statut rendu serait celui de `tail`, pas celui de la commande. Écris dans un
  fichier et relève `$?` séparément. → `.agents/skills/verification-discipline/SKILL.md`
- **Les ÉDITIONS de fichiers suivis passent par les outils d'édition**, jamais
  par un heredoc shell : sous Git Bash un heredoc mange un antislash final et
  corrompt un fichier en silence (L-00000197), et une écriture par le shell
  échappe aux gardes de chemins (T-00000244).
- **`eval` sur une valeur interpolée et `sh -c` sur une chaîne construite** sont
  des findings `ERROR` de classe 1, **non-waivables**. Passe la valeur en
  argument positionnel (`"$1"`), ou source un fichier.
- **Un commentaire ne COMMENCE jamais par le mot `shellcheck`.** `#  shellcheck :
  …` est lu comme une **DIRECTIVE** — **les DEUX formes, deux-points espacé ET
  deux-points collé (`# shellcheck: …`), mesurées sur 0.11.0** — et le fichier
  **entier** sort de l'analyse
  sur `SC1073`/`SC1072` — mesuré sur 0.10.0 comme sur 0.11.0, et payé le
  2026-09-13 sur `core-scripts/verify.sh`. Mets un mot devant : `# le paquet
  shellcheck : …`. Les seules formes valides sont `disable=`, `source=`,
  `shell=`, `enable=`, `external-sources=`. **Ce piège relève d'un AUTRE parseur
  que les huit formes ci-dessus** — celui de shellcheck, pas celui du SAST — et
  le filet qui l'attrape vit donc dans `.agents/security/shellcheck-scan.test.sh`
  (arm `(0)`), placé AVANT le test de présence de l'outil pour tenir aussi sur un
  hôte qui n'a pas shellcheck, c'est-à-dire là où le scanner est aveugle.
