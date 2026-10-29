r"""Le marqueur `cadre.managed` — pose, lecture, dépouillement, vérification.

Clause de spec « marquage des fichiers générés » (`docs/PROMPT-refonte-packaging-
cadre.md`) : un COMMENTAIRE, jamais une clé d'en-tête (décision pilote
S-00002846) — lignes `# cadre.…` dans le frontmatter d'un Markdown qui en a un,
`<!-- cadre.… -->` en tête d'un Markdown qui n'en a pas, `# cadre.…` en tête
d'un TOML —, avec `managed`, la version du kit et le checksum du contenu.
Décisions pilote S-00001602 (le marqueur est POSÉ dans le fichier et DÉRIVÉ de
l'arbre) et S-00001608 (fixture d'abord, dogfooding en dernier — ce module ne
touche aucun fichier de ce dépôt, T-00000736 le fait).

POURQUOI UN COMMENTAIRE (S-00002846, mesures S-00002854 et T-00000786). Des
clés `cadre.*` dans un frontmatter rendent une déf Gemini INCHARGEABLE : le
schéma de gemini-cli 0.57 est strict et refuse toute clé inconnue. Un `#` dans
un frontmatter est un commentaire YAML : la déf se charge sans erreur et le
modèle ne le voit pas (mesuré sur gemini-cli 0.57.0 et Claude Code 2.1.283).
`<!-- … -->` est le seul commentaire Markdown, mais il vit dans le CORPS : là
où l'hôte injecte le corps comme prompt, le modèle le VOIT (mesuré sur les
deux). Et une ligne AVANT le premier `---` casse le chargeur de frontmatter
(S-00002854) : un en-tête HTML suivi d'un frontmatter refermé est un refus.

L'ÉNUMÉRATION SE FAIT EN DEUX TEMPS, et le premier ne suffit pas :
`git grep -l -F cadre.managed` rend un SUR-ENSEMBLE — les fichiers qui CITENT
le jeton, une doc qui explique ce format ou une déf Codex qui le cite dans une
chaîne compris —, que l'appelant filtre par `lire(texte, forme_de(chemin)) is
not None`. Seule la lecture BORNÉE (frontmatter réel, lignes de TÊTE) dit
qu'un fichier est marqué ; le grep ne dit que par où commencer. L'ancienne
phrase « `git grep -F` suffit » était fausse (binôme final du lot vague A,
S-00002727).

UNE GRAMMAIRE, TROIS PORTEURS. La ligne est `cadre.<clé>: <valeur>`, clés
FERMÉES, valeurs quotées ; seule son ENVELOPPE change, choisie par
`forme_de(relatif)` sur le suffixe, puis, en Markdown, par le texte.

* `.md` À FRONTMATTER (`---` en ligne 1, refermé) → `Forme.MARKDOWN`, trois
  lignes `# ` en colonne 0 insérées juste avant le `---` fermant ; région
  lue : le frontmatter seul —

      # cadre.managed: true
      # cadre.version: "<cadre.__version__>"
      # cadre.checksum: "sha256:<64 hex>"

* `.md` SANS frontmatter → `Forme.MARKDOWN`, les trois mêmes lignes en tête
  (lignes 1-3), enveloppées `<!-- cadre.managed: true -->` ; région lue : la
  suite de lignes de TÊTE qui ouvrent sur `<!-- cadre.`. `poser` ne CRÉE
  jamais de frontmatter.

* `.toml` → `Forme.TOML`, les trois lignes `# ` en tête (lignes 1-3) : un
  commentaire TOML 1.0, que `tomllib` ignore ; région lue : la suite de lignes
  de TÊTE qui ouvrent sur `# cadre.`.

* tout autre suffixe → `FormeInconnue`, `.py` compris. C'est le POINT
  D'EXTENSION nommé : shims `.py`/`.sh` (T-00000736), YAML et JSON
  (T-00000776). Un `.py`/`.sh` exécutable garde son shebang en ligne 1
  (mesuré : 80 `.py` sur 238 et 82 `.sh` sur 83 ouvrent sur `#!`) : son site,
  et l'écart avec `shim_grammar.MARQUEUR` (`#cadre.` accepté, fenêtre de 10
  lignes), sont tranchés par T-00000736. YAML entier prendra l'enveloppe `#`
  en tête ; JSON n'a pas de commentaire, son porteur reste à T-00000776.

Des lignes lisibles SANS parseur YAML — la stdlib n'en a pas. Le jeton littéral
`cadre.managed` rend l'ensemble dérivable par `git grep -F` sur les trois
porteurs. Valeurs quotées : la forme la plus conservatrice (`1.0` nu serait un
flottant pour qui parserait la ligne). Trois lignes et non une : le même
lecteur (clés fermées, doublons, valeurs validées) sert les trois porteurs, et
la reprise d'une ligne garde sa forme écrite.

LA FORME D'AVANT EST REFUSÉE, jamais lue ni migrée (S-00002846). Une clé
`cadre.*` NUE dans un frontmatter, ou une table `[cadre]` portant `managed`
dans la vraie structure TOML, lève `MarqueurIllisible` en nommant le remède —
écrire `# cadre.managed: …`. Aucun fichier de ce dépôt ne la porte (mesuré au
BASE de T-00000786) : rien à migrer, et une migration devinée serait pire qu'un
refus.

LES CLÉS SONT FERMÉES (précédent `kitlock.CLES`). Une clé `cadre.<inconnue>`
rend le marqueur `MarqueurIllisible` — et `poser` comme `depouiller` refusent
AVANT de retirer quoi que ce soit : aucune ligne étrangère n'est perdue en
silence.

ET L'ENSEMBLE EST FERMÉ DANS LE TEMPS AUSSI, sans décision prise. Ce module ne
porte AUCUNE version de FORMAT — `version` est la version de KIT. Une évolution
du format (une quatrième clé, une autre empreinte) a deux issues, et ce lot
n'en tranche AUCUNE : geler les clés (un lecteur N lit tout marqueur, le format
ne bouge jamais), ou tolérer N-1 derrière une clé de version de format (le
lecteur N lit N-1 et le DIT). Question OUVERTE, portée par T-00000752
(`--upgrade`), et BLOQUANTE pour le scénario N-1→N de T-00000741 : tant qu'elle
n'est pas tranchée, une clé de plus est un refus `MarqueurIllisible`, jamais
une migration devinée.

`version` = `cadre.__version__`, version de KIT, INFORMATIVE — même doctrine que
`version_kit` de `kitlock` : aucune comparaison ne la lit, le lockstep lit
`kit.lock`. Elle n'est jamais vide, et se LIT sous la forme même où elle se
pose (voir les bornes).

CHECKSUM = `sha256:` + hexdigest SHA-256 de l'UTF-8 de `depouiller(texte)` : le
texte SANS les lignes du marqueur, donc TOUT le reste — frontmatter
`name:`/`model:` compris —, fins de ligne normalisées `\r\n` → `\n` (un checkout
`autocrlf` n'est pas une reprise par l'adoptant). Par construction, une
modification qui ne touche QUE les lignes du marqueur (une `version` éditée à la
main) est invisible au checksum : `cadre doctor` (Phase 6) nomme ce cas, pas ce
module.

`managed: false` ⇒ REPRIS, et REPRIS N'EST PAS ABSENT : c'est la reprise
EXPLICITE par l'adoptant (« une GENEREE peut ne pas l'être si l'adoptant l'a
reprise », S-00001602), et elle se voit. `lire` rend un `Marqueur` dont
`managed` est faux — `None` ne dit que l'ABSENCE ; `verifier` rend
`Etat.REPRIS` sans comparer d'empreinte (la reprise prime sur le corps) ; et
`poser` REFUSE de re-marquer une reprise (`MarqueurIllisible`, « repris ») —
l'adoptant a écrit `false` pour ne plus être régénéré, un poseur qui écraserait
ce `false` par `true` annulerait sa décision en silence. `depouiller` retire
les lignes d'une reprise comme celles d'un marqueur : ce sont des lignes du
marqueur, pas du corps. `Marqueur.managed` vaut `True` par défaut parce que
c'est la seule valeur que `poser` écrit. Toute autre valeur que `true`/`false`
⇒ `MarqueurIllisible`.

LA FORME MINIMALE D'UNE REPRISE EST UNE SEULE LIGNE (décision S-00002731),
dans l'enveloppe de son porteur et À SA PLACE : `# cadre.managed: false` dans
un frontmatter ou en ligne 1 d'un TOML, `<!-- cadre.managed: false -->` en
ligne 1 d'un Markdown sans frontmatter — où un `# …` en tête est un titre.
Un adoptant qui reprend un fichier l'écrit ainsi, et une reprise sort le
fichier de la gestion —
l'empreinte n'y sert plus. `version` et `checksum` y sont donc FACULTATIFS,
mais VALIDÉS s'ils sont présents, AVANT que `managed` compte : un marqueur
repris n'est pas un marqueur mutilé, et `managed: false` avec un checksum de
63 hex reste un refus, pas une reprise. Un marqueur POSÉ (`managed: true`),
lui, porte les trois clés, et le refus d'une clé manquante NOMME le remède
(« une reprise peut s'écrire `# cadre.managed: false` seule »).
`Marqueur.version` et `Marqueur.checksum` valent `None` sur une reprise qui ne
les porte pas — jamais sur un marqueur posé.

CE QUE REPRIS NE COMPARE PAS, ET QUI EN DÉCOULE (critic-opus F5, S-00002731).
`verifier` rend `Etat.REPRIS` SANS comparer l'empreinte : un contrôle
d'intégrité du socle (`check_socle_integrity`, Phase 3bis) qui voudrait savoir
si un fichier repris a AUSSI divergé du rendu doit comparer LUI-MÊME
`empreinte(depouiller(t, forme))` au checksum qu'il attend, reprise comprise —
`verifier` ne le fera pas pour lui. Et parce que le checksum couvre TOUT le
frontmatter non-cadre (`model:`, `effort:` compris), `core-scripts/apply-mode.py`,
qui réécrit ces clés, rend MODIFIE toute déf marquée qu'il touche : c'est une
décision ouverte (ré-empreindre après `apply-mode`, ou exclure ces clés du
dépouillé), portée par T-00000752, jamais prise ici.

LA RÉGION LUE EST BORNÉE. Frontmatter : du `---` en ligne 1 au `---` fermant,
et seules les lignes qui OUVRENT sur `# cadre.` ou `cadre.` y sont jugées —
`name:`, `description:` et les autres clés ne le sont JAMAIS. Tête HTML ou
TOML : la suite de lignes consécutives, depuis la ligne 1, qui ouvrent sur
`<!-- cadre.` ou `# cadre.`. Chaque ligne jugée doit être la ligne enveloppée
EXACTE (`# ` puis la ligne, ou `<!-- ` + la ligne + ` -->`), sinon refus.
UNE REPRISE MAL ESPACÉE NE SE LIT PAS ABSENTE (exec-critic, T-00000786 ;
garde S-00001602) : dans la région, une ligne en colonne 0 qui ouvre sur
l'enveloppe de son porteur SANS blanc ou avec PLUSIEURS, devant `managed`,
`version` ou `checksum` — `#cadre.managed: false`, `#  cadre.version`,
`<!--cadre.managed: false -->` — est un refus qui nomme la forme exacte :
lue absente, `poser` la marquerait `true` par-dessus. Une clé hors des trois
ainsi enveloppée (`#cadre.colle`), ou une ligne indentée, reste du corps. Tout
le reste est CORPS, donc empreint et gardé à l'octet : un
`<!-- cadre.managed: true -->` plus bas dans un Markdown, un
`# cadre.managed: true` après la tête ou dans une chaîne TOML multi-ligne (une
déf Codex qui cite le format) ne sont ni lus ni dépouillés.

UNE REPRISE MAL PLACÉE N'EST PAS ÉCRASÉE (critic-opus F1, T-00000786). Hors
région, elle n'est pas lue (`verifier` dit NON_MARQUE), mais `poser` la
cherche dans la ZONE DE REPRISE — les lignes du frontmatter refermé qui
ouvrent, blancs de tête retirés, sur `#` ou `<!--`, puis la suite de tête
des lignes vides ou qui ouvrent ainsi (`#` seul en TOML) — et REFUSE en
nommant la place : `cadre.managed` puis `: false` ou `= false`, quoté ou non,
casse de `false` ignorée. Au-delà (après un paragraphe, dans un commentaire
HTML multi-ligne, un blanc insécable avant `false`), elle n'est pas vue.

LE COÛT DE CETTE LECTURE EST BORNÉ, et la borne est écrite. Chaque ligne jugée
est lue une fois, sans rebroussement : l'enveloppe est retirée à l'octet, puis
la ligne `cadre.` passe par une expression sans quantificateur paresseux. En
TOML, le fichier n'est chargé par `tomllib` que s'il porte une ligne candidate
`[cadre]` — pour juger la forme d'avant sur la VRAIE structure, une citation
dans une chaîne restant du corps —, et alors UNE fois : illisible ou trop
imbriqué ⇒ refus, rien ne pouvant être décidé.

LE REFUS EST UN TYPE, JAMAIS UNE VALEUR PAR DÉFAUT (patron `kitlock`) : clés
partielles, dupliquées ou inconnues, ligne `cadre.` mal enveloppée, enveloppe
mal espacée d'une des trois clés, checksum hors `sha256:[0-9a-f]{64}`, version
vide ou hors `[0-9A-Za-z.+-]+`, `managed` ni `true` ni `false` (`"true"` quoté
est une chaîne), forme d'avant, TOML illisible à candidate,
frontmatter ouvert et jamais fermé qui porte des lignes `cadre.`, en-tête HTML
devant un frontmatter refermé ou juste sous un frontmatter refermé qui n'en
porte pas, reprise passée à `poser`, bien ou mal placée — tout lève
`MarqueurIllisible`. Seule l'ABSENCE (aucune ligne du marqueur dans la région
lue) rend `None`.

`poser` est IDEMPOTENT (il retire le marqueur existant avant de poser), REFUSE avant
tout rendu une version hors `[0-9A-Za-z.+-]+`, une reprise, et un corps TOML illisible
ou à clé `cadre.managed` ; exige en TOML que son rendu se charge EXACTEMENT comme le
corps (`tomllib.loads(rendu) == tomllib.loads(corps)`) ; et RELIT son rendu — `lire`
puis `verifier` — avant de le rendre : ce module ne produit jamais un texte qu'il
refuserait de lire ou dirait modifié.

BORNES ÉCRITES, pour ne pas être découvertes — et les ÉCARTS documentés, qui
sont des choix, pas des oublis.
* Un frontmatter est reconnu par un `---` en LIGNE 1 exactement ; une ligne
  vide avant, ou `...` comme fermeture ne le sont pas. Un `---` en ligne 1
  jamais refermé et sans ligne `# cadre.`/`cadre.` est une règle horizontale,
  pas un frontmatter : `poser` pose l'en-tête HTML au-dessus, et la relecture
  l'accepte (le refus ne vise qu'un frontmatter REFERMÉ).
* Un BOM initial (U+FEFF) est retiré à la normalisation, comme un `\r` : il
  n'est ni corps ni marqueur. Un `.md` ou un `.toml` marqué puis rouvert avec un
  BOM est INTACT, et `poser` d'un texte à BOM rend les MÊMES octets que sans.
  Conséquence dite : `poser` rend TOUJOURS un texte sans BOM — un poseur qui
  réécrit un fichier à BOM le lui retire.
* Un frontmatter VIDE (`---` suivi de `---`) est un frontmatter : `poser` y met
  le marqueur et `depouiller` le rend TEL QUEL, délimiteurs compris. L'ÉCART 1
  d'avant (le frontmatter vide traité comme absent, ses délimiteurs retirés)
  est retiré avec la création de frontmatter qui le motivait.
* ÉCART 2 — `forme_de` lit le suffixe SANS tenir compte de la casse (`X.MD` et
  `x.md` ouvrent un seul fichier sur NTFS comme sur APFS) : un `.Md` est un
  Markdown ici, là où un hôte sensible à la casse pourrait l'ignorer.
* L'enveloppe HTML est VUE du modèle là où l'hôte injecte le corps d'un `.md`
  sans frontmatter (mesuré, T-00000786) : c'est le prix d'un Markdown qui n'a
  pas d'autre commentaire. Les défs d'agents, à frontmatter, n'y sont pas
  exposées. Une ligne HTML dont l'intérieur porte `-->` ou `--!>` (HTML5
  referme aussi sur celui-ci, en erreur de parse) est refusée : le
  commentaire s'y refermerait avant sa fin.
* Un corps qui OUVRE lui-même sur `# cadre.` (TOML) ou `<!-- cadre.` (Markdown
  sans frontmatter) ne peut pas recevoir de marqueur : sa première ligne entre
  dans la suite de tête, et elle est refusée en LECTURE, avant tout rendu.
* Un frontmatter ajouté AU-DESSUS d'un marqueur posé en tête HTML est un refus
  s'il ne porte pas de marqueur et que la tête est juste sous son `---`
  fermant ; séparée par une ligne vide, elle est du corps. Une ligne ajoutée
  AU-DESSUS d'une tête HTML ou TOML la fait lire NON_MARQUE : une nouvelle
  pose empile un second bloc (épinglé T32).
* Même borne qu'avant sur une chaîne YAML multi-ligne du frontmatter : une
  ligne en colonne 0 qui ouvre sur `# cadre.` ou `cadre.` y est jugée comme une
  ligne du frontmatter — ce lecteur n'est pas un parseur YAML.
* TOML — la forme d'avant n'est LUE que sous un en-tête `[cadre]` : la clé
  pointée `cadre.managed = …` au niveau racine, ou une table en ligne `cadre =
  { managed = … }`, sont lues NON_MARQUE — mais `poser` les REFUSE (clé TOML,
  critic-fable F1) : un `false` ainsi écrit n'est jamais marqué `true`. Aucun
  fichier de ce dépôt ne porte l'une ou l'autre (mesuré au BASE de T-00000786).
* TOML — `tomllib` laisse remonter `RecursionError` sur un tableau imbriqué de
  quelques centaines de niveaux, et un `ValueError` NU sur un entier de plus de
  4 300 chiffres (limite de conversion de Python) : capturés, ce sont des
  refus, en lecture (fichier à candidate) comme au chargement du corps par
  `poser`. Les flottants se chargent en TEXTE (`parse_float=str`) : aucune
  décision de ce module ne lit leur valeur, et l'égalité de chargement de
  `poser` tient ainsi sur `nan` et `inf`. `poser` garde le corps TOML à
  l'octet, sans lui ajouter de fin de ligne.
* La version est bornée à `[0-9A-Za-z.+-]+`, POSÉE comme LUE : ni guillemet,
  ni antislash, ni blanc, ni saut de ligne — les trois porteurs la portent nue,
  sans échappement. À la LECTURE c'est une borne de sécurité
  (security-code-review, T-00000786) : une ligne du marqueur est HORS
  empreinte, donc une version libre y ferait passer un texte arbitraire — un
  séparateur de ligne Unicode U+2028 ou NEL U+0085, un `--!>` qui refermerait
  l'en-tête HTML — sous un `verifier` qui dirait INTACT.
* ÉCART 3 — le découpage se fait par `split("\n")` et non `splitlines()`, qui
  coupe aussi sur `\x0c`, `\x1c`, `\u2028`… et dont la rejointure altérerait
  le corps. Les valeurs sont lues nues ou entre guillemets doubles, blancs de
  queue retirés ; `cadre.managed` se lit nu seulement (`"true"` quoté est une
  chaîne YAML).

PURETÉ. Aucune fonction ne prend de chemin, aucune E/S, aucun import de
`Workspace` ni de `kitlock` : les poseurs (T-00000736, renderers de 3bis.A)
lisent et écrivent par la couture. La normalisation passe par `re.sub`, et
l'enveloppe se retire par `removeprefix`/`removesuffix`, jamais par
`str.replace` — le filet de pureté juge les NOMS de méthode, pas leurs
récepteurs.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from enum import Enum

from cadre import __version__

#: Les trois clés FERMÉES du marqueur, les MÊMES sur les trois porteurs. Une
#: quatrième dans une enveloppe EXACTE est un refus ; MAL enveloppée
#: (`_PRESQUE`), seule une de ces trois l'est, une autre reste du corps.
CLES = frozenset({"cadre.managed", "cadre.version", "cadre.checksum"})

#: `sha256:` puis EXACTEMENT 64 chiffres hexadécimaux minuscules — la forme que
#: `hexdigest()` rend. Utilisé en `fullmatch` : ni préfixe ni suffixe tolérés.
_CHECKSUM = re.compile(r"sha256:[0-9a-f]{64}")
#: `\r\n` et `\r` seul → `\n`. Un seul site de normalisation, appelé partout.
_FINS_DE_LIGNE = re.compile(r"\r\n?")
#: U+FEFF, le BOM — écrit par `chr` et non par un échappement `\u`, parce
#: qu'un outil d'édition peut rendre l'échappement en caractère BRUT, invisible
#: dans la source (mesuré ; T23 du banc le refuse).
_BOM = chr(0xFEFF)
_DELIMITEUR = "---"
#: La ligne `cadre.<clé>: <valeur>`, une fois son enveloppe retirée : la clé,
#: `:` suivi d'au moins un blanc puis la valeur (ou rien : valeur vide). Ses
#: blancs de queue sont retirés APRÈS, par `rstrip`, et non par un `[ \t]*$`
#: derrière un `.*?` paresseux, qui rebrousse en O(n²) (mesuré : une valeur de
#: 40 000 blancs suivis d'une lettre = 3 s). `re.ASCII` : `\w` ne doit
#: connaître que les lettres ASCII.
_LIGNE_CADRE = re.compile(r"(cadre\.[\w.-]*)[ \t]*:(?:[ \t]+(.*))?$", re.ASCII)
#: Une ligne candidate `[cadre]` : blancs tolérés, clé nue ou quotée — `"cadre"`
#: et `'cadre'` sont la MÊME table pour TOML —, commentaire de fin de ligne
#: toléré. C'est le PRÉ-FILTRE de la forme d'avant : sans candidate, un TOML
#: n'est jamais chargé ; avec, sa vraie structure dit si la table existe.
_ENTETE_CADRE = re.compile(r"""[ \t]*\[[ \t]*(?:cadre|"cadre"|'cadre')[ \t]*\][ \t]*(?:#.*)?$""")
#: La version que `poser` accepte, et la seule que `lire` accepte : ni guillemet,
#: ni antislash, ni blanc, ni saut de ligne — les trois porteurs la portent nue,
#: sans échappement.
_VERSION = re.compile(r"[0-9A-Za-z.+-]+")
#: L'enveloppe MAL ESPACÉE d'une des trois clés, en colonne 0 : `#` ou `<!--`,
#: aucun blanc ou plusieurs (espace, tabulation), puis la clé, suivie d'un
#: caractère hors `[\w.-]` ou de la fin (`#cadre.managedx` n'est pas
#: `cadre.managed`). Jugée APRÈS l'enveloppe exacte, qui n'y entre jamais.
_PRESQUE = re.compile(
    r"(#|<!--)[ \t]*(cadre\.(?:"
    + "|".join(sorted(re.escape(c.removeprefix("cadre.")) for c in CLES))
    + r"))(?![\w.-])", re.ASCII)
#: Une reprise écrite N'IMPORTE OÙ dans une ligne de la zone de reprise :
#: `cadre.managed`, `:` ou `=`, puis `false` nu ou quoté, casse ignorée, borné
#: à droite. Cherchée (`search`) par `poser` seul, jamais par `lire`.
_REPRISE_LIBRE = re.compile(
    r"""cadre\.managed[ \t]*[:=][ \t]*["']?(?i:false)(?![\w.-])""", re.ASCII)


class Forme(Enum):
    """La forme du marqueur, choisie par le suffixe du chemin relatif. En
    Markdown, le porteur (frontmatter ou tête HTML) se choisit sur le texte."""

    MARKDOWN = "markdown"
    TOML = "toml"


class Etat(Enum):
    """Le verdict de `verifier` : absent, repris par l'adoptant (`managed:
    false`, S-00001602), intact, ou modifié depuis la pose."""

    NON_MARQUE = "non_marque"
    REPRIS = "repris"
    INTACT = "intact"
    MODIFIE = "modifie"


class MarqueurIllisible(ValueError):
    """Le texte porte un marqueur que ce noyau ne sait pas lire : clés
    partielles, dupliquées ou inconnues, ligne mal enveloppée, valeur hors
    forme, forme d'avant, TOML illisible. Jamais de valeur par défaut : un
    marqueur illisible est refusé, pas complété."""


class FormeInconnue(ValueError):
    """Le suffixe n'a pas de forme de marqueur ici — point d'extension nommé
    (shims `.py`/`.sh` : T-00000736 ; YAML et JSON : T-00000776)."""


@dataclass(frozen=True)
class Marqueur:
    """Ce qu'un marqueur LU porte : la version de kit qui l'a posé
    (informative), le checksum du contenu dépouillé, et `managed` — `False`
    sur une reprise explicite de l'adoptant (`managed: false`), `True` par
    défaut parce que c'est la seule valeur que `poser` écrit. Un `Marqueur`
    repris n'est pas un marqueur absent : `lire` ne rend `None` que pour
    l'absence. `version` et `checksum` ne valent `None` que sur une reprise
    qui ne les porte pas (S-00002731) — un marqueur posé porte les deux."""

    version: str | None
    checksum: str | None
    managed: bool = True


@dataclass(frozen=True)
class _Porteur:
    """L'enveloppe d'une ligne `cadre.<clé>: <valeur>` et le nom de sa région
    dans les refus. `ferme` vide : l'enveloppe est un préfixe seul."""

    ou: str
    ouvre: str
    ferme: str = ""

    def envelopper(self, ligne: str) -> str:
        """`ligne` dans cette enveloppe — la forme que `poser` écrit."""
        return f"{self.ouvre}{ligne}{self.ferme}"


#: Les trois porteurs du tableau de la docstring.
_FRONTMATTER = _Porteur("frontmatter", "# ")
_TETE_HTML = _Porteur("en-tête HTML", "<!-- ", " -->")
_TETE_TOML = _Porteur("en-tête TOML", "# ")


def forme_de(relatif: str) -> Forme:
    """La forme du marqueur pour `relatif` (chemin POSIX relatif, en texte), par
    son suffixe, casse ignorée — `X.MD` et `x.md` ouvrent un seul fichier sur
    NTFS comme sur APFS. `.md` → MARKDOWN, `.toml` → TOML, tout autre — `.py`
    compris — → `FormeInconnue`."""
    bas = relatif.lower()
    if bas.endswith(".md"):
        return Forme.MARKDOWN
    if bas.endswith(".toml"):
        return Forme.TOML
    raise FormeInconnue(
        f"{relatif!r} : aucune forme de marqueur pour ce suffixe (formes connues : "
        "`.md` — `# cadre.…` au frontmatter ou `<!-- cadre.… -->` en tête —, "
        "`.toml` — `# cadre.…` en tête ; shims `.py`/`.sh` : T-00000736, YAML et "
        "JSON : T-00000776)")


def _normaliser(texte: str) -> str:
    """Fins de ligne `\\r\\n` (et `\\r` seul) → `\\n`, et un BOM initial (U+FEFF)
    retiré : ni corps ni marqueur. L'unique site."""
    return _FINS_DE_LIGNE.sub("\n", texte.removeprefix(_BOM))


def empreinte(texte: str) -> str:
    """`sha256:` + hexdigest SHA-256 de l'UTF-8 de `texte`, fins de ligne
    normalisées. C'est la valeur que `checksum` porte quand `texte` est le
    dépouillé du fichier (`empreinte(depouiller(m)) == lire(m).checksum`)."""
    return "sha256:" + hashlib.sha256(_normaliser(texte).encode("utf-8")).hexdigest()


# --- une ligne du marqueur, dans son enveloppe -------------------------------

def _extrait(ligne: str) -> str:
    """`repr` d'une ligne citée par un refus, bornée à 80 caractères."""
    return f"{ligne[:80]!r}{' (tronquée)' if len(ligne) > 80 else ''}"


def _deballer(ligne: str, i: int, porteur: _Porteur) -> tuple[int, str, str]:
    """`(indice, clé, valeur)` d'une ligne qui OUVRE sur l'enveloppe de
    `porteur` suivie de `cadre.` — `MarqueurIllisible` si elle n'est pas
    EXACTEMENT `porteur.envelopper("cadre.<clé>: <valeur>")` : une ligne qui
    ouvre ainsi ne peut pas être « pas le marqueur ». L'enveloppe se retire à
    l'octet, jamais par une expression qui rebrousserait ; l'intérieur passe
    par `_LIGNE_CADRE`, puis ses blancs de queue par `rstrip`."""
    brute = ligne.rstrip(" \t") if porteur.ferme else ligne
    trouve = None
    if brute.endswith(porteur.ferme):
        interieur = brute.removeprefix(porteur.ouvre).removesuffix(porteur.ferme)
        # `-->` DANS l'intérieur refermerait le commentaire HTML avant sa fin,
        # et `--!>` aussi : HTML5 le traite en fermeture (erreur de parse).
        if not (porteur.ferme and ("-->" in interieur or "--!>" in interieur)):
            trouve = _LIGNE_CADRE.match(interieur)
    if trouve is None:
        raise MarqueurIllisible(
            f"{porteur.ou}, ligne {i + 1} : {_extrait(ligne)} ouvre sur `{porteur.ouvre}cadre.` "
            f"sans être de la forme `{porteur.envelopper('cadre.<clé>: <valeur>')}`")
    return i, trouve.group(1), (trouve.group(2) or "").rstrip(" \t")


def _mal_enveloppee(ligne: str, porteur: _Porteur) -> str | None:
    """La clé d'une ligne qui enveloppe MAL une des trois clés fermées dans la
    famille de `porteur` — `#` ou `<!--` en colonne 0, sans blanc ou avec
    plusieurs —, ou `None`. L'enveloppe exacte n'y entre jamais ; une clé hors
    des trois (`#cadre.colle`) ni une ligne indentée non plus : du corps."""
    trouve = _PRESQUE.match(ligne)
    if (trouve is None or ligne.startswith(porteur.ouvre + "cadre.")
            or trouve.group(1) != porteur.ouvre.rstrip(" ")):
        return None
    return trouve.group(2)


def _refus_enveloppe(ligne: str, i: int, porteur: _Porteur, cle: str) -> MarqueurIllisible:
    """Le refus d'une enveloppe mal espacée : lue ABSENTE, une reprise presque
    écrite (`#cadre.managed: false`) serait marquée `true` par `poser` — la
    décision de l'adoptant écrasée en silence (garde S-00001602)."""
    return MarqueurIllisible(
        f"{porteur.ou}, ligne {i + 1} : {_extrait(ligne)} — enveloppe malformée de {cle}, écrire "
        f"`{porteur.envelopper(cle + ': …')}` (une espace après `{porteur.ouvre.rstrip(' ')}`)")


# --- régions : frontmatter, tête HTML, tête TOML -----------------------------

def _fermeture(lignes: list[str], debut: int = 0) -> int | None:
    """L'indice du `---` qui referme un frontmatter ouvert par la ligne
    `debut`, ou `None` : `lignes[debut]` n'est pas `---`, ou n'est jamais
    refermé."""
    if debut >= len(lignes) or lignes[debut].rstrip() != _DELIMITEUR:
        return None
    return next(
        (i for i in range(debut + 1, len(lignes)) if lignes[i].rstrip() == _DELIMITEUR), None)


def _bloc_frontmatter(lignes: list[str]) -> tuple[int | None, list[tuple[int, str, str]]]:
    """`(fermeture, cadre)` : l'indice du `---` fermant (`None` sans frontmatter)
    et les lignes `# cadre.*` du bloc — et de lui seul — en `(indice, clé,
    valeur)`.

    Seules les lignes qui OUVRENT sur `# cadre.` ou `cadre.` sont jugées, plus
    une enveloppe `#` mal espacée d'une des trois clés (`#cadre.managed`) ;
    `name:`, `description:` et les autres ne le sont jamais. Une clé `cadre.*`
    NUE est la forme d'avant : refus nommé, avec le remède. Un texte ouvert par
    `---` mais jamais refermé n'a pas de frontmatter ; s'il porte pourtant de
    telles lignes, il est illisible — un marqueur à moitié écrit se refuse, il
    ne se devine pas."""
    if not lignes or lignes[0].rstrip() != _DELIMITEUR:
        return None, []
    fermeture = _fermeture(lignes)
    borne = len(lignes) if fermeture is None else fermeture
    jugees = [i for i in range(1, borne) if lignes[i].startswith(("# cadre.", "cadre."))
              or _mal_enveloppee(lignes[i], _FRONTMATTER) is not None]
    if fermeture is None:
        if jugees:
            raise MarqueurIllisible(
                "frontmatter ouvert en ligne 1 et jamais refermé, mais il porte des "
                f"lignes cadre. (lignes {[i + 1 for i in jugees]})")
        return None, []
    cadre: list[tuple[int, str, str]] = []
    for i in jugees:
        if lignes[i].startswith("cadre."):
            raise MarqueurIllisible(
                f"frontmatter, ligne {i + 1} : {_extrait(lignes[i])} est une clé d'en-tête "
                "`cadre.*` NUE — forme d'avant, refusée (S-00002846) : écrire "
                "`# cadre.managed: …`, un commentaire YAML")
        cle = _mal_enveloppee(lignes[i], _FRONTMATTER)
        if cle is not None:
            raise _refus_enveloppe(lignes[i], i, _FRONTMATTER, cle)
        cadre.append(_deballer(lignes[i], i, _FRONTMATTER))
    return fermeture, cadre


def _tete(lignes: list[str], porteur: _Porteur, debut: int = 0) -> list[tuple[int, str, str]]:
    """Les lignes du marqueur en TÊTE : la suite consécutive, depuis l'indice
    `debut` (la ligne 1 par défaut), des lignes qui ouvrent sur l'enveloppe de
    `porteur` suivie de `cadre.` — chacune enveloppée EXACTEMENT, sinon refus ;
    une enveloppe mal espacée d'une des trois clés (`#cadre.managed`,
    `<!--  cadre.version`) est un refus aussi, jamais une fin de région. La
    première ligne qui n'est ni l'une ni l'autre clôt la région."""
    jeton = porteur.ouvre + "cadre."
    cadre: list[tuple[int, str, str]] = []
    for i in range(debut, len(lignes)):
        ligne = lignes[i]
        cle = _mal_enveloppee(ligne, porteur)
        if cle is not None:
            raise _refus_enveloppe(ligne, i, porteur, cle)
        if not ligne.startswith(jeton):
            break
        cadre.append(_deballer(ligne, i, porteur))
    return cadre


def _charger_toml(texte: str, ou: str) -> dict[str, object]:
    """`tomllib.loads(texte)`, flottants en TEXTE, échecs → `MarqueurIllisible` :
    TOML illisible (`TOMLDecodeError`, et le `ValueError` NU d'un entier de
    plus de 4 300 chiffres, que `tomllib` n'enveloppe pas) ou trop imbriqué
    (`RecursionError`) — une erreur nue serait une panne, pas un refus.
    `parse_float=str` : l'égalité de chargement de `poser` tient sur `nan`."""
    try:
        return tomllib.loads(texte, parse_float=str)
    except ValueError as exc:  # `TOMLDecodeError` en hérite
        raise MarqueurIllisible(f"{ou} : TOML illisible : {exc}") from exc
    except RecursionError as exc:
        raise MarqueurIllisible(f"{ou} : TOML trop imbriqué pour être lu") from exc


def _forme_d_avant_toml(lignes: list[str]) -> None:
    """Refuse la forme d'avant : une table `[cadre]` portant `managed` dans la
    VRAIE structure TOML. Sans ligne candidate `[cadre]`, le fichier n'est pas
    chargé ; avec, il l'est UNE fois — illisible ou trop imbriqué ⇒ refus, rien
    ne pouvant être décidé ; une candidate dans une chaîne reste du corps. La
    clé racine pointée ou en ligne n'est pas lue ici : `poser` la refuse."""
    if not any(_ENTETE_CADRE.match(ligne) for ligne in lignes):
        return
    table = _charger_toml("\n".join(lignes), "fichier entier").get("cadre")
    if isinstance(table, dict) and "managed" in table:
        raise MarqueurIllisible(
            "table [cadre] portant `managed` : forme d'avant, refusée (S-00002846) — "
            "écrire `# cadre.managed: …`, un commentaire TOML, en tête du fichier")


def _region(lignes: list[str], forme: Forme) -> tuple[list[tuple[int, str, str]], _Porteur]:
    """Les lignes du marqueur et leur porteur, lues dans la région BORNÉE de
    `forme` — refus sur une ligne mal enveloppée, sur la forme d'avant, sur un
    en-tête HTML qui précède un frontmatter refermé (une ligne avant le premier
    `---` casse le chargeur de l'hôte, S-00002854), et sur un en-tête HTML
    juste sous un frontmatter refermé qui n'en porte pas (critic-fable F1 :
    lu NON_MARQUE, un fichier modifié échapperait à `--upgrade`). Une liste
    vide dit l'ABSENCE."""
    if forme is Forme.MARKDOWN:
        fermeture, cadre = _bloc_frontmatter(lignes)
        if fermeture is not None:
            if not cadre and _tete(lignes, _TETE_HTML, fermeture + 1):
                raise MarqueurIllisible(
                    f"{_TETE_HTML.ou} : juste sous le `---` fermant (ligne {fermeture + 2}) — "
                    "un frontmatter a été ajouté au-dessus d'un marqueur posé en tête : "
                    "le déplacer en `# cadre.…` DANS le frontmatter")
            return cadre, _FRONTMATTER
        cadre = _tete(lignes, _TETE_HTML)
        if cadre and _fermeture(lignes, len(cadre)) is not None:
            raise MarqueurIllisible(
                f"{_TETE_HTML.ou} : les lignes 1-{len(cadre)} précèdent un frontmatter "
                "refermé — une ligne avant le premier `---` casse le chargeur de l'hôte "
                "(S-00002854) : le marqueur d'un Markdown à frontmatter s'écrit "
                "`# cadre.…` DANS le frontmatter")
        return cadre, _TETE_HTML
    if forme is Forme.TOML:
        cadre = _tete(lignes, _TETE_TOML)
        _forme_d_avant_toml(lignes)
        return cadre, _TETE_TOML
    raise FormeInconnue(f"forme {forme!r} inconnue")


def _reprise_hors_region(lignes: list[str], forme: Forme) -> None:
    """Refuse une reprise MAL PLACÉE (critic-opus F1) : `cadre.managed: false`
    dans la ZONE DE REPRISE sans être dans la région — lue NON_MARQUE,
    `poser` la marquerait `true` par-dessus. Zone : les lignes du frontmatter
    refermé qui ouvrent, blancs de tête retirés, sur `#` ou `<!--` ; puis la
    suite de tête des lignes vides ou qui ouvrent ainsi (`#` seul en TOML),
    sous le `---` fermant ou depuis la ligne 1. Appelé sur un texte SANS
    marqueur lu : une ligne de région n'y est donc jamais."""
    ouvrants = ("#", "<!--") if forme is Forme.MARKDOWN else ("#",)
    fermeture = _fermeture(lignes) if forme is Forme.MARKDOWN else None
    zone = [] if fermeture is None else [
        i for i in range(1, fermeture) if lignes[i].lstrip().startswith(ouvrants)]
    for i in range(0 if fermeture is None else fermeture + 1, len(lignes)):
        if lignes[i].strip() and not lignes[i].lstrip().startswith(ouvrants):
            break
        zone.append(i)
    porteur = (_TETE_TOML if forme is Forme.TOML
               else _TETE_HTML if fermeture is None else _FRONTMATTER)
    for i in zone:
        if _REPRISE_LIBRE.search(lignes[i]):
            raise MarqueurIllisible(
                f"reprise mal placée, ligne {i + 1} : {_extrait(lignes[i])} — hors de la "
                "région du marqueur, elle n'est pas lue et `poser` la marquerait `true` "
                f"par-dessus : l'écrire `{porteur.envelopper('cadre.managed: false')}` "
                f"({porteur.ou}), ou la retirer pour rendre le fichier à la génération")


# --- le lecteur commun -------------------------------------------------------

def _dequoter(valeur: str) -> str:
    if len(valeur) >= 2 and valeur[0] == '"' and valeur[-1] == '"':
        return valeur[1:-1]
    return valeur


def _marqueur_lu(cadre: list[tuple[int, str, str]], porteur: _Porteur) -> Marqueur | None:
    """Le lecteur COMMUN des trois porteurs : le `Marqueur` des lignes `cadre.*`
    lues (`managed` faux sur `cadre.managed: false`), `None` s'il n'y en a
    aucune ; `MarqueurIllisible` sinon. La seule ligne `cadre.managed: false`
    est une reprise complète (S-00002731) ; `cadre.managed: true` exige les
    trois clés."""
    if not cadre:
        return None
    champs: dict[str, str] = {}
    for i, cle, valeur in cadre:
        if cle not in CLES:
            raise MarqueurIllisible(
                f"{porteur.ou}, ligne {i + 1} : clé {cle!r} inconnue ; clés connues "
                f"{sorted(CLES)}")
        if cle in champs:
            raise MarqueurIllisible(f"{porteur.ou}, ligne {i + 1} : clé {cle!r} dupliquée")
        champs[cle] = valeur
    if "cadre.managed" not in champs:
        raise MarqueurIllisible(
            f"{porteur.ou} : clé cadre.managed manquante (présentes : {sorted(champs)}) — "
            "un marqueur posé porte cadre.managed, cadre.version et cadre.checksum ; "
            f"une reprise peut s'écrire `{porteur.envelopper('cadre.managed: false')}` seule")
    brut = champs["cadre.managed"]
    if brut not in ("true", "false"):
        raise MarqueurIllisible(
            f"{porteur.ou} : cadre.managed doit valoir true ou false, pas {brut!r}")
    version = champs.get("cadre.version")
    checksum = champs.get("cadre.checksum")
    return _marqueur(
        brut == "true",
        None if version is None else _dequoter(version),
        None if checksum is None else _dequoter(checksum),
        porteur,
    )


def _marqueur(managed: bool, version: str | None, checksum: str | None,
              porteur: _Porteur) -> Marqueur:
    """Les trois valeurs déjà extraites → `Marqueur`, `managed` faux sur une
    reprise explicite ; `None` pour une clé ABSENTE. Version et checksum sont
    validés AVANT que `managed` compte, dans les deux cas : un marqueur repris
    n'est pas un marqueur mutilé. Puis seulement : un marqueur POSÉ exige les
    deux, une reprise s'en passe (S-00002731) — et le refus cite la forme
    COMMENTAIRE du porteur lu. La version LUE est tenue à la forme de la
    version POSÉE : une ligne du marqueur est hors empreinte, donc une valeur
    libre y ferait passer un texte arbitraire sous un `verifier` INTACT."""
    ou = porteur.ou
    if version is not None and not version:
        raise MarqueurIllisible(f"{ou} : version vide")
    if version is not None and not _VERSION.fullmatch(version):
        raise MarqueurIllisible(
            f"{ou} : version {version[:60]!r}{' (tronquée)' if len(version) > 60 else ''} "
            "hors de la forme [0-9A-Za-z.+-]+ — celle où elle se pose : la ligne est hors "
            "empreinte, une valeur libre y échapperait au checksum")
    if checksum is not None and not _CHECKSUM.fullmatch(checksum):
        raise MarqueurIllisible(
            f"{ou} : checksum {_extrait(checksum)} hors de la forme sha256:<64 hex minuscules>")
    if managed and (version is None or checksum is None):
        manquantes = [f"cadre.{cle}" for cle, valeur in (("version", version),
                                                         ("checksum", checksum))
                      if valeur is None]
        raise MarqueurIllisible(
            f"{ou} : clé(s) manquante(s) {manquantes} pour un marqueur posé "
            f"(`{porteur.envelopper('cadre.managed: true')}`) — une reprise, elle, peut "
            f"s'écrire `{porteur.envelopper('cadre.managed: false')}` seule")
    return Marqueur(version=version, checksum=checksum, managed=managed)


def lire(texte: str, forme: Forme) -> Marqueur | None:
    """Le marqueur porté par `texte` — `managed` faux sur une reprise
    (`managed: false`) —, ou `None` s'il est ABSENT, et seulement alors. Tout
    autre cas est un refus `MarqueurIllisible`. La lecture est BORNÉE : le
    frontmatter réel, ou la suite de lignes de tête (HTML, TOML)."""
    return _marqueur_lu(*_region(_normaliser(texte).split("\n"), forme))


def depouiller(texte: str, forme: Forme) -> str:
    """Le texte SANS les lignes du marqueur — reprise comprise : ce sont des
    lignes du marqueur, pas du corps —, fins de ligne normalisées — la matière
    du checksum. Refuse (`MarqueurIllisible`) un marqueur qu'il ne lirait pas,
    AVANT tout retrait : rien n'est retiré à l'aveugle. Rien d'autre ne part —
    un frontmatter vidé garde ses délimiteurs. Sans marqueur, rend le texte
    normalisé tel quel."""
    lignes = _normaliser(texte).split("\n")
    cadre, porteur = _region(lignes, forme)
    _marqueur_lu(cadre, porteur)
    retirees = {i for i, _, _ in cadre}
    return "\n".join(ligne for i, ligne in enumerate(lignes) if i not in retirees)


def poser(texte: str, forme: Forme, version: str | None = None) -> str:
    """`texte` avec le marqueur posé — `version=None` → `cadre.__version__`,
    résolue dans le corps par convention (un défaut d'argument s'évalue à
    l'import) ; `None` garde le signal « non fournie », à l'appelant la sienne.

    Le SITE : Markdown à frontmatter → trois lignes `# ` juste avant le `---`
    fermant ; sans frontmatter → trois lignes `<!-- … -->` en tête (aucun
    frontmatter créé) ; TOML → trois lignes `# ` en tête. Rien d'autre.

    IDEMPOTENT : un marqueur existant est retiré d'abord, `poser(poser(x)) == poser(x)`.
    REFUSE avant tout rendu : une version hors `[0-9A-Za-z.+-]+` ; un marqueur illisible —
    c'est `lire` qui le dit ; une REPRISE (`managed: false`, S-00001602), lue ou MAL PLACÉE
    (`_reprise_hors_region`) — ce `false` ne se réécrit pas `true` en silence ; en TOML, un
    corps illisible ou à clé racine `cadre.managed` (pointée ou en ligne : même motif, F1),
    ou un rendu qui ne se charge pas EXACTEMENT comme lui. Puis RELIT son rendu : relu, le
    marqueur doit être celui posé et `verifier` dire INTACT, sinon `MarqueurIllisible`,
    avant toute écriture."""
    version_kit = __version__ if version is None else version
    if not isinstance(version_kit, str) or not _VERSION.fullmatch(version_kit):
        raise MarqueurIllisible(
            f"version {version_kit!r} hors de la forme [0-9A-Za-z.+-]+ : ni guillemet, "
            "ni antislash, ni blanc, ni saut de ligne ne se posent")
    existant = lire(texte, forme)
    if existant is not None and not existant.managed:
        raise MarqueurIllisible(
            "marqueur repris (managed: false, S-00001602) : ce fichier a été repris "
            "par l'adoptant et ne se re-marque pas — retirer la reprise à la main "
            "pour le rendre à la génération")
    if existant is None:
        _reprise_hors_region(_normaliser(texte).split("\n"), forme)
    corps = depouiller(texte, forme)
    checksum = empreinte(corps)
    marqueur = (
        "cadre.managed: true",
        f'cadre.version: "{version_kit}"',
        f'cadre.checksum: "{checksum}"',
    )
    if forme is Forme.MARKDOWN:
        lignes = corps.split("\n")
        fermeture = _fermeture(lignes)
        if fermeture is None:
            rendu = "\n".join([*map(_TETE_HTML.envelopper, marqueur), corps])
        else:
            rendu = "\n".join([*lignes[:fermeture], *map(_FRONTMATTER.envelopper, marqueur),
                               *lignes[fermeture:]])
    elif forme is Forme.TOML:
        avant = _charger_toml(corps, "corps")
        if isinstance(avant.get("cadre"), dict) and "managed" in avant["cadre"]:
            raise MarqueurIllisible(
                "corps : `cadre.managed` y est une clé TOML (pointée ou en ligne), que `poser` "
                "n'écrase pas : reprendre par `# cadre.managed: false` en tête, ou la retirer")
        rendu = "\n".join([*map(_TETE_TOML.envelopper, marqueur), corps])
        if _charger_toml(rendu, "rendu") != avant:
            raise MarqueurIllisible(
                "rendu : il ne se charge pas comme le corps — l'en-tête posé doit être "
                "un commentaire TOML inerte")
    else:
        raise FormeInconnue(f"forme {forme!r} inconnue")
    attendu = Marqueur(version=version_kit, checksum=checksum)
    relu = lire(rendu, forme)
    if relu != attendu or verifier(rendu, forme) is not Etat.INTACT:
        raise MarqueurIllisible(
            f"rendu relu ≠ marqueur posé ({relu!r} contre {attendu!r}) : le texte "
            "n'est pas rendu — version ou corps que cette forme ne sait pas porter")
    return rendu


def verifier(texte: str, forme: Forme) -> Etat:
    """`NON_MARQUE` sans marqueur, `REPRIS` sur `managed: false` (bien formé,
    et sans lire le corps : la reprise prime), `INTACT` si le checksum posé
    égale l'empreinte du dépouillé, `MODIFIE` sinon. Un marqueur illisible n'a
    pas d'état : `MarqueurIllisible` remonte."""
    marqueur = lire(texte, forme)
    if marqueur is None:
        return Etat.NON_MARQUE
    if not marqueur.managed:
        return Etat.REPRIS
    if empreinte(depouiller(texte, forme)) == marqueur.checksum:
        return Etat.INTACT
    return Etat.MODIFIE
