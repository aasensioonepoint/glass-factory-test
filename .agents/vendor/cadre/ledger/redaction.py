"""RÉDACTION DES SECRETS À L'ÉCRITURE — un secret reconnu n'entre pas au magasin.

Phase 2 de T-012, étape D (point 7, `T-00000641`), invariant « aucun secret au
ledger » (spec §3 : « Aucun secret n'atterrit dans les logs ni au
ledger »). Le besoin est MESURÉ et grave : `.agents/state/events/` est git-ignoré
par décision pilote du 2026-07-28, motif SECRET — un record `hook.deny` a porté
1 171 octets de shell brut, et « gitleaks never scans a hook's own append » : un
secret entre à `.agents/state/events/` par un canal que le scanner de secrets ne
regarde pas. C'est le CONTEXTE qui rend l'invariant grave, PAS le périmètre de ce
module.

COUVERTURE, ÉLARGIE PAR `T-00000641`. Ce module rédige à la SOURCE le magasin de
leçons `src/cadre/ledger/` : le texte libre d'une leçon est rédigé AVANT l'insert,
jamais nettoyé après coup (un magasin append-only ne se nettoie pas). Depuis
`T-00000641` ses motifs sont AUSSI chargés PAR CHEMIN par les deux écrivains du
RUN, qui appellent `rediger`/`rediger_arbre` à l'écriture :
  * `agentic_v3/db/event_store.py` — store V3 : `events_ledger.payload_json`, les
    projections (`code_diff`, `current_assignee`) et `board_sync_outbox.last_error` ;
  * `.agents/bin/events.py` — spool JSONL des hooks sous `.agents/state/events/`,
    charge ET enveloppe ; en voie DÉGRADÉE l'enveloppe est NEUTRALISÉE (littéral),
    pas rédigée, et le composant host du NOM de day-file l'est par le même moyen.
CE MODULE N'EST PAS LE SEUL RÉDACTEUR DU DÉPÔT (A-T3, mesuré) : `.agents/bin/
otel_receiver.py` en porte un SECOND — `redact`, drop-list forme-consciente
(`L-00000040`) — sur un AUTRE spool durable (le récepteur OTLP). Deux mécanismes
distincts, deux surfaces. BRAS « LOGS » : il n'est affirmé, pour CET invariant,
que sur le spool JSONL des hooks ci-dessus ; le spool OTLP a sa PROPRE rédaction
dans `otel_receiver.py`, hors de ce module, et aucun autre écrivain de journal
durable n'existe sous `src/cadre/`.
CE QUI RESTE NON COUVERT, et se lit sans deviner : `board_sync_outbox.payload_json`
reste EN CLAIR sans borne de temps (arbitrage `T-00000641` étape 4, inscrit au
registre) ; les champs d'IDENTITÉ (jointures, baux) ne sont pas rédigés — les
rédiger ferait dériver une clé. Les CLÉS de dict d'un arbre passé à
`rediger_arbre`, elles, le SONT depuis `T-00001131` : cela ne touche que la forme
ÉCRITE ou COMPARÉE, l'appelant gardant l'arbre BRUT pour son contrôle de flux
(`event_store.py`). La CLÉ SECRÈTE AWS (40 car. base64, sans préfixe fixe) reste
non reconnue (voir plus bas).

RECONNAISSANCE PAR MOTIFS STDLIB (`re` SEUL). Les formes couvertes sont celles
qu'un scanner reconnaît RÉELLEMENT — calibrées UNE FOIS par P-H1 (`gitleaks`
8.30.1, 2026-09-17, qui a détecté un faux secret des formes `aws-access-token`,
`github-pat`, `private-key`) puis FIGÉES ici : clé d'ACCÈS AWS (`AKIA…` + 16,
bornée `(?<![A-Z0-9])…(?![A-Z0-9])` pour mordre même collée à du texte), jeton
GitHub classique (`ghp_`/`gho_`/`ghs_`/`ghu_`/`ghr_` + 36+) et fine-grained
(`github_pat_…`), jeton GitLab (`glpat-…`), bloc de clé privée PEM TOLÉRANT (types
`RSA`/`EC`/`OPENSSH`/`ENCRYPTED`, reconnu MÊME tronqué sans marqueur END), JWT
(`eyJ….….…`), plus des jetons génériques évidents (Slack `xox…`, Google `AIza…`,
`sk-…` avec ses préfixes `proj-`/`ant-api…`/`svcacct-`).

NON COUVERT, ÉCRIT PLUTÔT QUE SOUS-ENTENDU : la CLÉ SECRÈTE AWS (40 caractères
base64, jamais un préfixe fixe) n'est PAS reconnue — sans contexte elle est
indiscernable d'un jeton base64 quelconque, et un motif assez lâche pour la
prendre rédigerait du texte innocent. `task-ABC…` NE matche AUCUN motif (le
faux positif nommé du check) : la tête `(?<![0-9A-Za-z])` l'exclut.

FRONTIÈRES DE MOT ET SOULIGNÉ (`T-00001144`). `\\b` tient `_` pour un caractère de
mot : `foo_` devant un jeton, ou `_suite` derrière un jeton à corps alphanumérique,
le laissaient ENTIER en clair (mesuré à 645846e8, sept familles en tête, trois en
queue). La TÊTE des sept motifs qui ouvrent en minuscule ou par `AIza` (`gh?_`,
`github_pat_`, `glpat-`, `eyJ`, `xox?-`, `AIza`, `sk-`) est donc `(?<![0-9A-Za-z])`.
La QUEUE de `gh?_`, `xox?-` et `AIza` (`_QUEUE`) accepte de finir devant un `_`, SAUF
quand le corps vient d'avaler l'ouverture `gh?` ou `github` d'un jeton COLLÉ
(`(?<=gh[posur])_(?=[0-9A-Za-z]{36})`, `(?<=github)_(?=pat_)`). Ce garde mord dans la
PROJECTION : un jeton, un `Cf` seul, puis un jeton `gh?_` ou `github_pat_` lui-même
coupé — le `Cf` retiré, le corps du premier avale l'ouverture `ghs` du second, et sans
le garde il finissait devant son `_` : `ghs_<36><U+202E>ghs_<16><U+200E><20>` sortait
`[…]_<16><U+200E><20>` (98 cas du corpus, rouges au mutant « sans garde »). Celle de
`glpat-` (`_QUEUE_GLPAT`) admet un corps fini par `-` (en clair dès 645846e8). La
queue de `github_pat_` (corps à `_`) est `(?![0-9A-Za-z_])` : son ancien `\\b`, Unicode
en Python 3, tenait `é` pour un caractère de mot, et `github_pat_<22>é` sortait ENTIER en
clair (645846e8 de même ; 69 cas du fuzz du critique) ; `sk-` et `jwt` n'ont pas de queue.
SUR-RÉDACTION NOMMÉE, sens sûr : puisque tête et queue admettent `_`, un identifiant
LÉGITIME de forme `…_sk-<20+>` ou `AIza<35>_…` est rédigé ici et ne l'était pas à
645846e8 (`my_sk-<20>` sort `my_[SECRET RÉDIGÉ:openai_key]`, `AIza<35>_x` sort
`[SECRET RÉDIGÉ:google_api_key]_x`) — environ 227 identifiants tirés sur 100 000 au
relevé de l'exec-critic. Le texte perd une valeur innocente, aucun secret ne sort.

AUCUN appel à gitleaks : gitleaks n'a servi qu'à CALIBRER la forme, il n'est PAS
le mécanisme du check. La reconnaissance reste stdlib pur, comme l'exigent
l'invariant « stdlib seule » et le banc de pureté du service ledger
(`test_cadre_ledger_purete`) — d'où l'absence de tout verbe d'E/S et de
`str.replace` (dans `IO_PAR_METHODE` du banc), la substitution passant par découpe
et `"".join`. `re` et `unicodedata` seuls, aucune syntaxe postérieure à 3.9 (ni
possessif, ni groupe atomique) : le module se charge sous Python 3.9.
PAS de backtracking EXPONENTIEL : aucun motif ne porte de quantificateur imbriqué ;
< 1 s sur les 100 Ko adversariaux du banc `test_cadre_ledger_redaction`, Cf compris.
JWT LINÉAIRE, SANS BORNE DE LONGUEUR (`T-00001143`). Le motif nu `eyJ…\\.…\\.…` est
QUADRATIQUE sur une suite de départs `-eyJ` sans point, chaque départ relisant la
suite jusqu'au bout — `"eyJ" + ("a"*8 + "-eyJ")*k` : 240 Ko en 3,3 s et 480 Ko en
13 s à 645846e8. `_MotifLineaire` rend les MÊMES correspondances (équivalence
`finditer`/`search`/`sub` au motif nu, tenue au banc) mais saute, après un départ
raté, le reste de la suite de corps (preuve : sa docstring). Mesuré (minimum de 3
essais, 240 / 480 Ko) : cette suite 0,015 / 0,029 s, la même avec `_` au lieu de `-`
0,014 / 0,028 s, précédée de 9 jetons coupés par un `Cf` 0,08 / 0,15 s (645846e8 :
4,2 / 17,0 s). AUCUN en-tête ni aucune charge n'est borné : des en-têtes de 4 096,
4 097 et 100 000 caractères, une charge de 100 000, sont rédigés.

CARACTÈRES DE FORMAT (`T-00001130`). Un caractère de catégorie Unicode `Cf`
(U+200B, ZWJ U+200D, U+2060, BOM U+FEFF, marques bidi, trait d'union conditionnel
U+00AD…) glissé dans un jeton défaisait TOUS les motifs — mesuré sur la BASE
645846e8 : les huit motifs de jeton, et le bloc PEM coupé dans son en-tête.
`rediger` joue donc un TOUR de deux passes : (1) les motifs sur une PROJECTION du
texte privée de ses `Cf`, chaque correspondance ramenée à son empan d'origine ;
(2) les motifs sur le texte BRUT, où un `Cf` fait frontière. LA PROJECTION D'ABORD
(binôme F2) : jouée en second, elle arrivait après que le brut avait pris le PRÉFIXE
d'un jeton à longueur variable coupé APRÈS sa longueur minimale, et la QUEUE restait
en clair — mesuré à la BASE 63f63f35 : `sk-ant-api03-…` coupé, 70 caractères en clair.
UNION AVEC LE BRUT (binôme bis, S-00004005) : jouée seule, la projection SOUDAIT deux
jetons ENTIERS séparés par un `Cf` seul — le corps du premier avalait l'ouverture du
second, dont la queue sortait en clair (`ghp_<36><U+200B>sk-ant-api03-<30>` rendait
`…]-ant-api03-<30>` à 0dc39b67 ; vert à 645846e8). L'empan d'origine de chaque
correspondance projetée est donc UNI, de proche en proche, aux correspondances
BRUTES (`_bruts`) qui le chevauchent, et ce GROUPE est remplacé ENTIER par le
marqueur du motif projeté : les `Cf` INTÉRIEURS disparaissent avec lui, jamais
réinjectés ; ceux qui le BORDENT restent.
LES CORRESPONDANCES BRUTES SONT UNE DOUBLE UNION (`_bruts`, S-00004011 puis r4 du plan) :
les INDÉPENDANTES (chaque motif sur le texte brut) ET les SÉQUENTIELLES (chaque motif
cherché là où ceux qui le précèdent dans `MOTIFS` sont masqués par des `]`, comme le
ferait leur marqueur). Les séquentielles voient le jeton COLLÉ derrière une clé AWS
(`ghp_…<U+200B>AKIA…xoxb-<10>` sortait `[…]-<10>` à 95df5a87, où elles manquaient) ;
les indépendantes voient le jeton qu'un masque précédent a coupé de sa frontière. La
passe BRUTE (2) prend la MÊME double union, groupée de même : prise sur les seules
indépendantes, `k=github_pat_<24>AKIA<16>xoxa-<12>` laissait `-<12>` en clair (le corps
du premier traverse la clé AWS jusqu'au `xoxa`) — fermé SEULEMENT si `<24>` finit par
`[a-z_]` : s'il finit par `[A-Z0-9]`, le lookbehind AWS `(?<![A-Z0-9])` refuse la clé dans
toutes les passes, aucun masque ne rend au slack sa frontière, et `-<12>` reste en clair
comme à 645846e8 (borne (c1), comptée en (xi) du banc frère) ; sur les seules
séquentielles, un jeton soudé par un masque précédent laissait sa queue. Chaque union a son témoin, rouge sur
son mutant (`test_cadre_ledger_redaction_cf`, `UnionsTests`). Deux effets NOMMÉS, sens sûr :
SUR-ÉTIQUETTE — un groupe prend le nom de son premier élément, donc le second jeton
prend le nom du premier (`ghp_…<U+200B>sk-…` sort `[SECRET RÉDIGÉ:github_token]`
seul) ; SUR-ABSORPTION — un jeton suivi d'un `Cf` puis d'un mot avale ce mot, que la
projection soude à son corps (`Key ghp_…<U+200B>suite fin` sort
`Key [SECRET RÉDIGÉ:github_token] fin` ; 645846e8 gardait `suite`). Jugé sur un corpus
adversarial construit d'abord, par classe, corps tirés dans l'ALPHABET RÉEL de chaque
famille (`test_cadre_ledger_redaction_cf`) : aucun cas rouge là où 645846e8 est vert —
`test_aucune_regression_vs_645846e8` le tient contre une base FIGÉE, fuzz compris. Puis
le tour se RÉPÈTE jusqu'au POINT FIXE : un marqueur crée une frontière qui ouvre un
jeton jusque-là soudé à son voisin (docstring de `rediger`).
TERMINAISON, prouvée : chaque motif ouvre par un littéral d'une liste fermée
(`-----BEGIN `, `AKIA`/`ASIA`/…, `gh[posur]_`, `github_pat_`, `glpat-`, `eyJ`,
`xox[baprs]-`, `AIza`, `sk-`) sans `Cf`, sans `[` ni `]`, et sous-chaîne d'aucun
marqueur. Une substitution remplace un empan qui CONTIENT l'ouverture d'au moins une
correspondance (projetée ou brute) ; la projection du nouveau texte est celle de ce
qui précède l'empan, le marqueur, puis celle de ce qui le suit — un préfixe et un
suffixe de l'ancienne — et aucun littéral ne chevauche le marqueur. Chaque
substitution détruit donc au moins une occurrence de ces littéraux dans la projection
sans en créer : un texte qui en porte P connaît au plus P + 1 tours.
COÛT, MESURÉ ET ACCEPTÉ (S-01M53V66EY, « sécurité d'abord », réversible). Un texte
ASCII sans secret coûte un balayage par motif, comme à 645846e8 : sans
correspondance indépendante il n'y a pas de séquentielle, la passe brute s'arrête
là (1 Mo : 0,06 s contre 0,04 s). Un texte NON-ASCII paie en plus la projection (une
catégorie Unicode par caractère) : 1 Mo sans `Cf` 0,10 s contre 0,04 s (×2,4), 1 Mo à
`Cf` dispersés (un tous les 42 caractères) 0,17 s contre 0,05 s (×3,5 ; 0,150 s contre
0,043 s au relevé de l'exec-critic). Le pire mesuré est un texte dense en jetons
coupés : 50 000 jetons `ghp_`, la moitié coupés par un `Cf` (2 Mo), 0,64 s contre
0,08 s à 645846e8, qui ne lisait pas à travers les `Cf` — ×8 ici, ×15 au relevé du
critique de plan (0,62 s contre 0,04 s), au-delà du ×2 de S-00004007 Q4 : coût
ACCEPTÉ et nommé par S-01M53V66EY. 1 Mo adversarial (PEM sans END, `sk-` sans fin,
`AKIA` répété, `eyJ` sans point) en 0,05 à 0,11 s, `AKIA<U+200B>` répété en 0,15 s.
Retirer d'abord les `Cf` du texte entier était écarté sur MESURE :
`x<U+200B>ghp_…` ne matche que grâce à la frontière que
porte le `Cf` (même chose pour le lookbehind AWS), et un texte SAIN perdrait ses
`Cf` — un emoji composé par ZWJ, un BOM, une marque bidi ressortent ici à
l'identique, ce qui garde aussi la forme canonique des charges déjà stockées
(comparaisons d'identité d'`event_store.py`). `Cf` est la catégorie que rend le
`unicodedata` de l'interpréteur courant (Unicode 16.0.0 sous Python 3.14.7,
mesuré). BORNES MESURÉES, NON COUVERTES : (a) des caractères HORS `Cf` défont
encore les motifs, notamment U+034F et U+FE0F (`Mn`), U+115F et U+3164 (`Lo`),
U+2800 (`So`) et les `Cc` (U+007F, U+0080–U+009F, comme les C0 U+0000–U+001F) —
les couvrir est un choix pilote non rendu ; (b) un `Cf` qui SÉPARE un caractère
de mot d'un jeton LUI-MÊME coupé (`a<U+200B>ghp_…<U+200B>…`,
`Q<U+200B>AK<U+200B>IA…`) n'est pris par aucune passe si la coupure tombe AVANT
la longueur minimale : le brut ne porte aucun jeton entier, la projection soude
`aghp_…` sans frontière ;
APRÈS la longueur minimale, le brut rédige le préfixe et la QUEUE reste en clair
(`x<U+200B>ghp_<36><U+200B><10>` : les 10 derniers caractères) ; (b′) un jeton
ENTIER suivi d'un `Cf` seul (ou de `Cf-`) puis d'un jeton LUI-MÊME coupé : AVANT la
longueur minimale du second, la projection soude son ouverture alphanumérique (`xoxb`,
`glpat`, `eyJ<8>`, `sk`) au corps du premier, le second n'a aucune correspondance
brute à unir, et sa suite reste en clair (`ghp_<36><U+200B>xoxb-11<U+200B><8>` sort
`[…]-11<U+200B><8>`) ; APRÈS elle, la correspondance brute de son préfixe rejoint le
groupe et sa QUEUE, au-delà du `Cf`, reste en clair
(`ghp_<36><U+200B>glpat-<20><U+200B><12>` sort `[…]<U+200B><12>`) — rouge aussi à
645846e8, qui laissait le second ENTIER en clair, ou la même queue ; (b″) un jeton
COUPÉ après sa longueur minimale, suivi d'un `Cf` seul puis d'un jeton qui porte un `_`
dans son ouverture (`gh?_`, `github_pat_`) : la QUEUE du premier reste en clair
(`ghp_<36><U+200B><10><U+200B>ghp_<36>` sort `[…]<U+200B><10><U+200B>[…]`) : dans la
projection, le `_` du second arrête le corps du premier sans y poser de frontière, et seul
le brut prend le préfixe du premier — sortie identique à
645846e8 et à 95df5a87 (mesuré) ; (c) deux jetons COLLÉS, qu'un `Cf` coupe le premier
ou non : (c1) SANS séparateur, selon les familles, le premier avale le préfixe du second
et en laisse la QUEUE (`ghp_<36>xoxb-<10>` : `-<10>` en clair), ou leurs bornes se
bloquent l'une l'autre et AUCUN n'est rédigé (`AKIA<16>AIza<35>`) ; (c2) collés par `_`
quand le PREMIER admet `_` dans son corps (`eyJ…_eyJ…`) : ce corps avale l'ouverture du
second, dont la suite reste en clair ; (c3) un jeton à LONGUEUR FIXE COLLÉ à ce qui
prolongerait son corps — `AIza` + 35 devant un alphanumérique (`…x`, `…9`, `…hello`),
une clé AWS + 16 devant une majuscule ou un chiffre — n'est PAS rédigé, par conception :
il est indiscernable d'une chaîne plus longue — tous rouges aussi à
645846e8 et 63f63f35 ; HORS de (c), une clé AWS suivie d'un jeton COLLÉ qui ouvre en
minuscule est rédigée, comme à 645846e8. Les rouges du corpus, bornes comprises, sont
COMPTÉS par classe par `FUITES_CONNUES` du banc frère, fuzz compris : une borne qui
tombe ou qui grossit fait rougir ce compte.
SUR-ABSORPTION NOMMÉE, sens sûr, comme à 645846e8 : un bloc PEM dont le marqueur END
porte un `Cf` n'est pas fermé par lui dans le texte brut — sa correspondance brute court
jusqu'à la fin du texte, le groupe aussi, et tout ce qui suit le bloc est rédigé avec lui
(un bloc RSA fermé par `-----E<U+200B>ND …`, suivi d'une ligne `suite`, sort le marqueur
seul ; 645846e8 de même).

MARQUEUR. Un secret reconnu est remplacé par `[SECRET RÉDIGÉ:<type>]` — le texte
brut n'est JAMAIS écrit. Le `<type>` NOMME la famille retirée (`aws_access_key`,
`github_token`, `private_key`, …) pour qu'un relecteur sache CE QUI a disparu sans
jamais le voir.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Iterator, Union

__all__ = ["rediger", "rediger_arbre", "contient_secret", "MOTIFS"]


def _marqueur(type_: str) -> str:
    """Le marqueur qui remplace un secret reconnu — jamais le texte brut."""
    return "[SECRET RÉDIGÉ:" + type_ + "]"


#: L'étiquette d'un bloc PEM, FERMÉE aux types attendus (spec P-H1) : un seul
#: groupe optionnel, JAMAIS `(?:[A-Z0-9]+ )*` qui, sur une suite `RSA RSA …` sans
#: `PRIVATE KEY`, backtrackerait (forme ReDoS). Bornée, elle ne peut pas.
_PEM_LABEL = r"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?"

#: TÊTE des sept motifs à ouverture minuscule ou `AIza` (`T-00001144`) : aucun
#: alphanumérique devant, mais `_` admis (`\b` refusait `foo_` devant le jeton).
_TETE = r"(?<![0-9A-Za-z])"

#: QUEUE de `gh?_`, `xox?-` et `AIza` (`T-00001144`, docstring du module) : une frontière
#: de mot, OU aucun alphanumérique derrière et pas de `_` qui suive l'ouverture `gh?` ou
#: `github` d'un jeton collé dont le corps vient d'avaler cette ouverture.
_QUEUE = r"(?:\b|(?![0-9A-Za-z]|(?<=gh[posur])_(?=[0-9A-Za-z]{36})|(?<=github)_(?=pat_)))"

#: QUEUE de `glpat-` : son corps admet `-`, et un corps fini par `-` doit être pris.
_QUEUE_GLPAT = r"(?:\b|(?![0-9A-Za-z]))"


class _MotifLineaire:
    """Le motif `jwt`, LINÉAIRE sans borne de longueur (`T-00001143`) : mêmes
    correspondances que `motif` nu, mais les départs d'une même suite de corps échouent
    ENSEMBLE, et après un départ raté le reste de la suite est sauté.

    PREUVE. Les trois segments sont pris dans S = `[A-Za-z0-9_-]`, et `.` n'est pas dans
    S. Soit un départ p dans une suite maximale de S : le segment 1 court jusqu'à la fin
    r1 de cette suite, et seul r1 peut être suivi du `.` exigé (un retour arrière ne fait
    que raccourcir le segment). Les conditions sont donc : r1 - (p + 3) >= 8,
    `texte[r1] == "."`, un segment 2 de 8 au moins suivi de `.`, un segment 3 de 8 au
    moins. Toutes sauf la première sont COMMUNES aux départs de la suite, et la première
    est monotone en p : un départ raté condamne les suivants de la même suite. Chaque
    caractère n'est relu qu'une fois par suite. `depart` est la tête du motif (lookbehind
    compris) et `suite` la classe S : l'un ou l'autre changé casse l'équivalence, que le
    banc tient au motif nu ; les deux entrent dans l'empreinte des `MOTIFS` du banc frère.

    Rend de VRAIS `re.Match` (`test_runs_exports_propres` lit `group(0)`) et expose ce
    que les appelants lisent : `pattern`, `finditer`, `search`, `fullmatch`, `sub` (avec
    un remplacement APPELABLE seulement, la seule forme employée ici)."""

    def __init__(self, motif: re.Pattern[str], depart: re.Pattern[str],
                 suite: re.Pattern[str]) -> None:
        self._motif, self.depart, self.suite = motif, depart, suite
        self.pattern = motif.pattern

    def finditer(self, texte: str) -> Iterator[re.Match[str]]:
        pos = saut = 0
        for d in self.depart.finditer(texte):
            p = d.start()
            if p < pos or p < saut:
                continue
            m = self._motif.match(texte, p)
            if m is not None:
                yield m
                pos = m.end()
            else:
                saut = self.suite.match(texte, d.end()).end()

    def search(self, texte: str) -> re.Match[str] | None:
        return next(self.finditer(texte), None)

    def fullmatch(self, texte: str) -> re.Match[str] | None:
        return self._motif.fullmatch(texte)

    def sub(self, remplacement: Callable[[re.Match[str]], str], texte: str) -> str:
        morceaux, curseur = [], 0
        for m in self.finditer(texte):
            morceaux += [texte[curseur:m.start()], remplacement(m)]
            curseur = m.end()
        return "".join(morceaux) + texte[curseur:]


#: `(type, motif)`. Formes CALIBRÉES UNE FOIS par P-H1 puis figées ; frontières revues
#: par `T-00001144` (tête et queue), jwt rendu linéaire par `T-00001143`. Le bloc PEM
#: vient EN PREMIER : il englobe des sous-chaînes (base64) qui pourraient sinon matcher
#: un autre motif au milieu de la clé. Les lookarounds bornent chaque jeton pour qu'il ne
#: morde pas au milieu d'un mot (`task-…` ne matche pas `sk-…`), et les longueurs sont
#: celles d'un vrai credential — un motif trop lâche rédigerait du texte innocent. AUCUN
#: motif ne porte de quantificateur imbriqué : le PEM tronqué utilise `[\s\S]*?` lazy
#: fermé par une alternation `(…END…|\Z)`, linéaire, jamais catastrophique.
MOTIFS: tuple[tuple[str, Union[re.Pattern[str], _MotifLineaire]], ...] = (
    # PEM TOLÉRANT : reconnu même TRONQUÉ (sans marqueur END, une clé coupée reste
    # un secret). Le corps `[\s\S]*?` est lazy ; l'alternation le ferme soit sur le
    # marqueur END, soit sur la fin de chaîne `\Z` — linéaire.
    ("private_key", re.compile(
        r"-----BEGIN " + _PEM_LABEL + r"PRIVATE KEY-----"
        r"[\s\S]*?"
        r"(?:-----END " + _PEM_LABEL + r"PRIVATE KEY-----|\Z)")),
    # AWS ACCESS KEY ID : bornes lookaround plutôt que `\b`, pour mordre même
    # COLLÉ à du texte (`xAKIA…`, `…KLMNDsuffixe`).
    ("aws_access_key", re.compile(
        r"(?<![A-Z0-9])(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)"
        r"[0-9A-Z]{16}(?![A-Z0-9])")),
    ("github_token", re.compile(_TETE + r"gh[posur]_[0-9A-Za-z]{36,}" + _QUEUE)),
    ("github_token", re.compile(_TETE + r"github_pat_[0-9A-Za-z_]{22,}(?![0-9A-Za-z_])")),
    ("gitlab_token", re.compile(_TETE + r"glpat-[0-9A-Za-z_-]{20,}" + _QUEUE_GLPAT)),
    ("jwt", _MotifLineaire(
        re.compile(_TETE + r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        re.compile(_TETE + r"eyJ"), re.compile(r"[A-Za-z0-9_-]*"))),
    ("slack_token", re.compile(_TETE + r"xox[baprs]-[0-9A-Za-z-]{10,}" + _QUEUE)),
    ("google_api_key", re.compile(_TETE + r"AIza[0-9A-Za-z_-]{35}" + _QUEUE)),
    # `sk-…` avec préfixes optionnels OpenAI/Anthropic. Tête `(?<![0-9A-Za-z])` :
    # `task-ABC…` contient `sk-ABC…` mais le `s` y suit un `a`, donc il ne matche
    # pas — le faux positif nommé du check.
    ("openai_key", re.compile(
        _TETE + r"sk-(?:proj-|ant-api\d{2}-|svcacct-)?[A-Za-z0-9_-]{20,}")),
)


def _projection(texte: str) -> tuple[str, list[int]] | None:
    """`texte` privé de ses caractères `Cf`, avec la position d'ORIGINE de chaque
    caractère gardé ; `None` s'il n'en porte aucun (chemin rapide : un texte ASCII
    n'en porte jamais, le premier `Cf` étant U+00AD)."""
    if texte.isascii():
        return None
    gardes = [i for i, c in enumerate(texte) if unicodedata.category(c) != "Cf"]
    if len(gardes) == len(texte):
        return None
    return "".join([texte[i] for i in gardes]), gardes


def _groupes(empans: list[tuple[int, int]],
             bruts: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    """Les empans à remplacer : composantes connexes, par CHEVAUCHEMENT strict et de
    proche en proche, des `empans` projetés d'un motif et des correspondances BRUTES
    `bruts` (`_bruts`, leur rang ignoré) ; seules restent celles qui contiennent un empan
    projeté (une composante purement brute revient à la passe BRUTE du même tour)."""
    groupes: list[tuple[int, int]] = []
    debut = fin = -1
    projete = False
    for d, f, p in sorted([(d, f, True) for d, f in empans] + [(d, f, False) for d, f, _ in bruts],
                          key=lambda e: (e[0], not e[2], e[1])):
        if d < fin:
            fin, projete = max(fin, f), projete or p
            continue
        if projete:
            groupes.append((debut, fin))
        debut, fin, projete = d, f, p
    if projete:
        groupes.append((debut, fin))
    return groupes


def _bruts(texte: str) -> list[tuple[int, int, int]]:
    """Les correspondances BRUTES de `texte`, `(début, fin, rang dans MOTIFS)` : l'UNION
    des INDÉPENDANTES (chaque motif sur le texte tel quel) et des SÉQUENTIELLES (chaque
    motif, dans l'ordre de `MOTIFS`, sur le texte où celles des motifs précédents sont
    masquées par des `]` de même longueur — les frontières que poseraient leurs
    marqueurs, binôme ter S-00004011). Pourquoi les deux : docstring du module.

    Tant qu'aucun masque n'est posé, les séquentielles d'un motif SONT ses
    indépendantes : elles ne sont ni recherchées ni ajoutées deux fois. Sans aucune
    indépendante, aucun masque n'est jamais posé : la liste est vide, en un balayage."""
    independantes = [[m.span() for m in motif.finditer(texte) if m.end() > m.start()]
                     for _, motif in MOTIFS]
    empans = [(d, f, k) for k, liste in enumerate(independantes) for d, f in liste]
    masque, masque_pose = texte, False
    for k, (_, motif) in enumerate(MOTIFS):
        if not empans:
            break
        if masque_pose:
            sequentielles = [m.span() for m in motif.finditer(masque) if m.end() > m.start()]
            empans += [(d, f, k) for d, f in sequentielles]
        else:
            sequentielles = independantes[k]
        if sequentielles:
            morceaux, curseur = [], 0
            for d, f in sequentielles:
                morceaux += [masque[curseur:d], "]" * (f - d)]
                curseur = f
            masque, masque_pose = "".join(morceaux) + masque[curseur:], True
    return empans


def _rediger_a_travers_le_format(texte: str) -> str:
    """Passe PROJECTION, la première d'un tour de `rediger` (`T-00001130`, docstring
    du module) : chaque motif est cherché dans la projection sans `Cf` ; l'empan
    d'ORIGINE de chaque correspondance — `Cf` intérieurs compris — est UNI aux
    correspondances BRUTES (`_bruts`) qui le chevauchent (`_groupes`), et le groupe est
    remplacé ENTIER par le marqueur du motif projeté. La projection et les
    correspondances brutes ne sont recalculées qu'après une substitution."""
    projection = _projection(texte)
    for type_, motif in MOTIFS:
        if projection is None:
            # Plus aucun `Cf` : la projection EST le texte, et les motifs sautés ici
            # sont rejoués par la passe BRUTE qui suit, dans le MÊME tour.
            break
        plat, origine = projection
        empans = [(origine[m.start()], origine[m.end() - 1] + 1)
                  for m in motif.finditer(plat) if m.end() > m.start()]
        if not empans:
            continue
        bruts = _bruts(texte)
        morceaux: list[str] = []
        curseur = 0
        for debut, fin in _groupes(empans, bruts):
            morceaux += [texte[curseur:debut], _marqueur(type_)]
            curseur = fin
        texte = "".join(morceaux) + texte[curseur:]
        projection = _projection(texte)
    return texte


def _rediger_brut(texte: str) -> str:
    """Passe BRUTE, la seconde d'un tour : les correspondances BRUTES (`_bruts`,
    indépendantes ET séquentielles), triées par `(début, fin, rang)` ; les chevauchements
    stricts sont fusionnés de proche en proche, et chaque groupe reçoit le marqueur de son
    PREMIER élément (sur-étiquette, docstring du module)."""
    morceaux, curseur, debut, fin, k0 = [], 0, -1, -1, 0
    for d, f, k in sorted(_bruts(texte)):
        if d < fin:
            fin = max(fin, f)
            continue
        if fin >= 0:
            morceaux += [texte[curseur:debut], _marqueur(MOTIFS[k0][0])]
            curseur = fin
        debut, fin, k0 = d, f, k
    if fin < 0:
        return texte
    morceaux += [texte[curseur:debut], _marqueur(MOTIFS[k0][0])]
    return "".join(morceaux) + texte[fin:]


def rediger(texte: str | None) -> str | None:
    """Rend `texte` débarrassé de tout secret reconnu, chaque occurrence remplacée
    par `[SECRET RÉDIGÉ:<type>]`. Un TOUR joue la passe À TRAVERS les caractères de
    format `Cf` (projection, `T-00001130`) PUIS la passe sur le texte BRUT ; les tours
    se répètent jusqu'au POINT FIXE (ordre, terminaison, coût : docstring du module).

    `None` en entrée rend `None` : un champ texte libre OPTIONNEL absent (une
    `forme_generalisee` non fournie) le reste, et l'appelant garde sa sémantique.

    IDEMPOTENT PAR CONSTRUCTION : le résultat est un point fixe du tour, donc un
    second appel s'arrête au premier tour sans rien changer — propriété qui rend sûr
    de l'appliquer sans savoir si le texte est déjà passé par ici. Ce n'est PAS le
    marqueur qui la donne : il ne matche aucun motif, mais il CRÉE une frontière (`]`
    devant `xoxb-…`) qui ouvre un jeton jusque-là soudé à son voisin — mesuré à la
    BASE 63f63f35, un seul tour ne rédigeait le slack de `AKIA…<U+202E>OPxoxb-…`
    qu'au SECOND appel. La boucle a son témoin : mutée en « un seul tour », elle fait
    rougir `test_la_boucle_de_point_fixe_est_necessaire` (`test_cadre_ledger_redaction_cf`).
    """
    if texte is None:
        return None
    resultat = texte
    while True:
        precedent = resultat
        resultat = _rediger_brut(_rediger_a_travers_le_format(resultat))
        if resultat == precedent:
            return resultat


def _cle(cle: Any) -> Any:
    """Une CLÉ de dict rédigée comme une feuille (`T-00001131`). Inchangée par la
    rédaction, c'est l'OBJET d'origine qui est rendu : une clé sous-classe de `str`
    (un `Enum` à mixin `str`) reste le MÊME objet, de même type."""
    redigee = rediger_arbre(cle)
    return cle if redigee == cle else redigee


def rediger_arbre(valeur: Any) -> Any:
    """Rédige récursivement toute feuille `str` ET toute CLÉ de dict d'une
    structure `dict`/`list`/`tuple`, en appelant `rediger` — résolu comme GLOBAL de
    module, JAMAIS via un alias local : c'est ce qui permet à un contrôle négatif de
    neutraliser la rédaction par une seule substitution de `rediger`.

    TOTALE par conception : une feuille non-`str` (y compris `None`, un `int`, un
    `bool`) est rendue INTACTE, jamais passée à `rediger` (qui lève `TypeError` sur
    un non-`str`/`None`). Le chemin d'écriture appelle donc `rediger_arbre` sur
    toute valeur non typée, jamais `rediger`.

    CLÉS (`T-00001131`) : une clé passe par la même règle qu'une feuille — une clé
    `str` est rédigée, une clé `tuple` reste un `tuple` (ses `str` rédigées), donc
    HASHABLE ; une clé d'un autre type (`int`, `None`…) reste intacte. COLLISION,
    choix ÉCRIT : deux clés DISTINCTES qui se rédigent en la MÊME valeur (deux jetons
    d'une même famille, ou un jeton à côté d'un marqueur déjà présent) FUSIONNENT —
    seule reste la valeur de la clé d'ORIGINE de plus grand `repr`, les autres sont
    PERDUES, et aucun jeton n'est écrit. Le départage ne dépend PAS de l'ordre
    d'insertion (binôme F2) : `{A: 1, B: 2}` et `{B: 2, A: 1}` s'écrivent pareil, ce
    qu'exige le rejeu d'`event_store.apply_run_step` — départagée par l'ordre, la
    forme rédigée levait « same durable identity, DIFFERENT content ». BORNE : `repr`
    est injectif sur `str` ; deux clés distinctes de MÊME `repr` (un `__repr__`
    surchargé) qui entrent en collision gardent la DERNIÈRE insérée.

    Les conteneurs conservent leur TYPE (un `tuple` reste un `tuple`), pour que
    `json.dumps(..., sort_keys=True)` d'une entrée SANS secret produise une chaîne
    IDENTIQUE à celle de l'entrée brute — la rédaction est alors l'identité.
    """
    if isinstance(valeur, str):
        return rediger(valeur)
    if isinstance(valeur, dict):
        sortie: dict = {}
        origines: dict = {}  # clé rédigée -> clé d'ORIGINE retenue (départage des collisions)
        for cle, sous in valeur.items():
            redigee = _cle(cle)
            if redigee in origines and repr(origines[redigee]) > repr(cle):
                continue
            origines[redigee] = cle
            sortie[redigee] = rediger_arbre(sous)
        return sortie
    if isinstance(valeur, list):
        return [rediger_arbre(sous) for sous in valeur]
    if isinstance(valeur, tuple):
        return tuple(rediger_arbre(sous) for sous in valeur)
    return valeur


def contient_secret(texte: str | None) -> bool:
    """`True` si `texte` porte au moins un secret reconnu. Appelé sur le CHEMIN
    D'ÉCRITURE : `lessons.ecrire_lecon` (contrôle C6) REFUSE par `ValueError` une
    MÉTADONNÉE qui porte un secret reconnu — clé ou énumération, jamais rédigée ; le
    texte libre, lui, passe par `rediger` (rédigé plutôt que refusé : une leçon n'est
    jamais perdue parce qu'elle contenait un secret, elle est écrite épurée). Lu aussi
    par les bancs (`test_runs_exports_propres`). Même portée que `rediger`
    (`T-00001130`) : un motif matche le texte BRUT ou sa projection sans `Cf` SSI le
    premier tour change le texte, donc SSI `rediger(texte) != texte` (une séquentielle
    n'existe pas sans indépendante, `_bruts`) ; la sortie de `rediger`, point fixe, rend
    toujours `False` (fuzz de `test_cadre_ledger_redaction`, corpus de
    `test_cadre_ledger_redaction_cf`)."""
    if texte is None:
        return False
    if any(m.search(texte) for _, m in MOTIFS):
        return True
    projection = _projection(texte)
    return projection is not None and any(m.search(projection[0]) for _, m in MOTIFS)
