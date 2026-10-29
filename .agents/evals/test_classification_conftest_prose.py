#!/usr/bin/env python3
"""LA PROSE DE CLASSEMENT VIT EN DEUX SURFACES — CE BANC LES CONFRONTE.

`classification_rules.py` (le CODE) et `docs/interne/classification.md` (la
DOC) portent chacun leur exemplaire de la meme prose. `test_classification_complete`
compare leurs TABLES — regles, mecanismes, consommateurs — et s'arrete la : sa
regex `_doc_mecanismes()` lit les QUATRE premieres cellules du § 3.4 et jamais la
cinquieme, `Raison`. Les deux proses pouvaient donc diverger — statut, date,
clause, critere de bascule — sans qu'aucun banc ne rougisse (T-00000737, mesure
du binome de T-00000635 : cellule reecrite, banc voisin VERT).

LA METHODE : LES DEUX SURFACES L'UNE CONTRE L'AUTRE, JAMAIS CONTRE UNE COPIE. Ce
banc ne recopie aucune des phrases qu'il surveille — une troisieme copie serait
une troisieme source de verite, qui rougirait le jour d'une bascule legitime
faite aux deux endroits. Il ne porte que des ANCRES courtes (le debut et la fin
de chaque segment) ; le segment entre elles est lu dans chaque surface, normalise
(accents, casse, gras Markdown, `§`, `#`, blancs), puis compare a l'autre. Une
ancre qui ne mord plus rougit sur la NON-VACUITE, jamais en silence.

CE QUE CE BANC NE PROUVE PAS : que la prose soit JUSTE. Il prouve qu'elle est la
MEME aux deux endroits ; la justesse reste a la revue et a la doctrine.

UNE SECONDE FAMILLE, SUR UNE SEULE SURFACE : `CardinauxEnProseTests` (T-00000637)
refuse tout cardinal d'enumeration recopie dans la prose du CODE — il se derive.

VOYAGE. Ses deux sujets sont `strip:` (`.template-exclude`) : chez un adoptant
ils manquent TOUS LES DEUX, et ce banc saute — nommement, jamais en silence. Un
seul des deux present est un ECHEC, pas un saut : c'est un renommage ici, pas un
arbre d'adoptant.
"""

from __future__ import annotations

import io
import re
import tokenize
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: sujet `strip:`, saute nommement quand les deux sujets manquent.
REGLES = ROOT / ".agents" / "evals" / "classification_rules.py"
# adopting-tree: sujet `strip:` (docs/interne/), meme saut que la ligne au-dessus.
DOC = ROOT / "docs" / "interne" / "classification.md"

DEBUT_MECA = "<!-- MECANISMES:DEBUT -->"
FIN_MECA = "<!-- MECANISMES:FIN -->"


def normer(texte: str) -> str:
    """Accents retires (NFKD), casse repliee, gras Markdown, `§` et blancs
    ecrases, apostrophe typographique ramenee a l'ASCII. Le code est ecrit sans
    accents et la doc avec : sans ce repli, chaque phrase divergerait a la
    premiere voyelle et le banc serait rouge sur du bruit."""
    t = unicodedata.normalize("NFKD", texte)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("’", "'").replace("**", "").replace("§", " ")
    return re.sub(r"\s+", " ", t).casefold().strip()


def _sauter_chez_l_adoptant() -> None:
    presents = [p.exists() for p in (REGLES, DOC)]
    if not any(presents):
        raise unittest.SkipTest(
            "arbre d'adoptant : classification_rules.py et docs/interne/ sont "
            "`strip:`, ce banc n'a pas de sujet ici")
    if not all(presents):
        raise AssertionError(
            f"un seul des deux sujets existe (regles={presents[0]}, "
            f"doc={presents[1]}) : renommage ou retrait, jamais un arbre d'adoptant")


def prose_du_code() -> str:
    """Le bloc de commentaires CONTIGU au-dessus de l'entree `conftest.py` de
    `MECANISME` — pas celle d'`EXACT`, qui vaut `CONTRAT` sans tuple."""
    lignes = REGLES.read_text(encoding="utf-8").splitlines()
    entrees = [i for i, l in enumerate(lignes)
               if re.match(r'\s*"conftest\.py":\s*\(', l)]
    if len(entrees) != 1:
        raise AssertionError(
            f"entree `conftest.py` de MECANISME introuvable ou dupliquee : {entrees}")
    bloc, i = [], entrees[0] - 1
    while i >= 0 and lignes[i].lstrip().startswith("#"):
        bloc.append(lignes[i].lstrip()[1:])
        i -= 1
    return normer(" ".join(reversed(bloc)))


def prose_de_la_doc() -> str:
    """La cinquieme cellule (`Raison`) de la ligne `conftest.py` du § 3.4."""
    texte = DOC.read_text(encoding="utf-8")
    debut, fin = texte.find(DEBUT_MECA), texte.find(FIN_MECA)
    if not 0 <= debut < fin:
        raise AssertionError("marqueurs du sous-tableau 3.4 absents ou inverses")
    lignes = [l for l in texte[debut:fin].splitlines()
              if re.match(r"\|\s*`conftest\.py`\s*\|", l)]
    if len(lignes) != 1:
        raise AssertionError(f"ligne `conftest.py` du § 3.4 : {len(lignes)} trouvee(s)")
    cellules = lignes[0].strip()[1:].rstrip("|").split("|", 4)
    if len(cellules) != 5:
        raise AssertionError(f"ligne `conftest.py` : {len(cellules)} cellules, 5 attendues")
    return normer(cellules[4])


def segment(prose: str, debut: str, fin: str) -> str | None:
    i = prose.find(debut)
    if i < 0:
        return None
    j = prose.find(fin, i)
    return None if j < 0 else prose[i:j + len(fin)]


#: Les ANCRES, et elles seules : debut et fin de chaque segment, normalises.
SEGMENTS = {
    "phrase de bascule": ("la bascule suit la plomberie", "`resolue_paquet`"),
    "critere de contenu": ("se rejuge au contenu", "`embarquee` sinon"),
    "statut de l'arbitrage": ("l'arbitrage pilote qui ouvre cette branche est", " ("),
}

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_IDENT = re.compile(r"\b[tsl]-\d{8}\b")  # la prose est deja repliee en minuscules
_CLAUSE = re.compile(r"«\s*([^»]+?)\s*»")


def citations(prose: str) -> dict[str, set[str]]:
    return {
        "dates": set(_DATE.findall(prose)),
        "identifiants": set(_IDENT.findall(prose)),
        "clauses": set(_CLAUSE.findall(prose)),
    }


class ProseDuConftestTests(unittest.TestCase):
    """Le classement de `conftest.py` : commentaire du code contre cellule
    `Raison` de la doc. Les deux disent la MEME bascule et le MEME critere."""

    @classmethod
    def setUpClass(cls):
        _sauter_chez_l_adoptant()
        cls.code, cls.doc = prose_du_code(), prose_de_la_doc()

    def test_les_deux_proses_sont_lues_et_parlent_du_meme_classement(self):
        for nom, prose in (("code", self.code), ("doc", self.doc)):
            with self.subTest(surface=nom):
                self.assertGreater(len(prose), 200, f"prose {nom} vide ou tronquee")
                self.assertIn("`resolue_paquet`", prose)
                self.assertIn("`conftest.py`", prose)

    def test_chaque_segment_existe_et_est_le_meme_dans_les_deux_surfaces(self):
        for nom, (debut, fin) in SEGMENTS.items():
            with self.subTest(segment=nom):
                code = segment(self.code, debut, fin)
                doc = segment(self.doc, debut, fin)
                self.assertIsNotNone(code, f"{nom} absente du commentaire du code")
                self.assertIsNotNone(doc, f"{nom} absente de la cellule Raison")
                self.assertEqual(
                    code, doc,
                    f"{nom} : le code et la doc ont diverge — corrige l'un sur "
                    "l'autre dans le MEME commit, jamais en retirant l'ancre")

    def test_dates_identifiants_et_clauses_cites_sont_les_memes(self):
        code, doc = citations(self.code), citations(self.doc)
        self.assertTrue(code["dates"] and code["identifiants"] and code["clauses"],
                        f"citations du code vides : la lecture ne mord plus ({code})")
        for cle in code:
            with self.subTest(citation=cle):
                self.assertEqual(
                    code[cle], doc[cle],
                    f"{cle} : code seul {sorted(code[cle] - doc[cle])}, "
                    f"doc seule {sorted(doc[cle] - code[cle])}")


_RELEVE = re.compile(
    r"releve du (\d{4}-\d{2}-\d{2}) a `?([0-9a-f]{7,40})`? : "
    r"`(git grep [^`]*cadre\.managed[^`]*)` rend (.{1,80}?)(?:,| —|\. )")


class ReleveCadreManagedTests(unittest.TestCase):
    """Le relevé daté de `cadre.managed` (docstring de `mecanisme()`, § 3.4 de
    la doc) : meme date, meme SHA, meme commande, meme resultat aux deux
    endroits. Il ne REJOUE pas la commande : un releve date dit l'etat A SA
    DATE, et le rejouer au tip rougirait chez la tache qui pose le marqueur,
    dont le write-set ne porte pas ces deux fichiers."""

    @classmethod
    def setUpClass(cls):
        _sauter_chez_l_adoptant()

    def _releve(self, chemin: Path) -> tuple[str, ...]:
        trouves = _RELEVE.findall(normer(chemin.read_text(encoding="utf-8")))
        self.assertEqual(
            len(trouves), 1,
            f"{chemin.name} : {len(trouves)} releve(s) date(s) de cadre.managed, "
            "un seul attendu — la regex ne mord plus, ou il a ete duplique")
        return trouves[0]

    def test_le_releve_date_est_le_meme_dans_les_deux_surfaces(self):
        self.assertEqual(self._releve(REGLES), self._releve(DOC))


def prose_des_regles() -> list[tuple[int, str]]:
    """(ligne, texte normalise) de chaque bloc de PROSE de `classification_rules.py` :
    commentaires pleine-ligne contigus (un bloc), commentaire de fin de ligne
    (seul : le joindre a son voisin fabriquerait « Phase 1 » + « plans »), et
    chaine triple (docstrings). Lu par `tokenize`, jamais par regex sur le
    source : un `#` dans une chaine n'est pas un commentaire."""
    source = REGLES.read_text(encoding="utf-8")
    lignes = source.splitlines()
    blocs: list[list] = []
    ouvert = None
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            plein = not lignes[tok.start[0] - 1][:tok.start[1]].strip()
            if plein and ouvert and ouvert[1] == tok.start[0] - 1:
                ouvert[1] = tok.start[0]
                ouvert[2].append(tok.string[1:])
                continue
            ouvert = [tok.start[0], tok.start[0], [tok.string[1:]]]
            blocs.append(ouvert)
            if not plein:
                ouvert = None
        elif tok.type == tokenize.STRING and re.match(r"[rRuU]?('''|\"\"\")", tok.string):
            blocs.append([tok.start[0], tok.end[0], [tok.string]])
            ouvert = None
        elif tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            ouvert = None
    return [(debut, normer(" ".join(morceaux))) for debut, _, morceaux in blocs]


#: Un CARDINAL ACCOLE A UNE ENUMERATION, trois formes. Le zero est hors grammaire
#: (`[1-9]`) : « rend 0 » est une ABSENCE mesuree, jamais le compte d'une liste.
CARDINAUX = {
    "repartition N/N/N": re.compile(r"(?<![\w.-])[1-9]\d*\s*/\s*\d+\s*/\s*\d+"),
    "N <objet compte>": re.compile(
        r"(?<![\w.,-])[1-9]\d*\s+(?:(?:surfaces?|entrees?|chemins?|prefixes?|scripts?"
        r"|plans?|lignes?)\b|`\.(?:md|toml|py)`)"),
    "les/des/aux N": re.compile(r"\b(?:les|des|aux)\s+[1-9]\d*(?![\w.,/-])"),
}

#: Un exemple qui DOIT mordre, par forme — la non-vacuite de la grammaire.
MORSURES = {
    "repartition N/N/N": "rendrait ~22/24/2 au lieu de 32/14/2",
    "N <objet compte>": "(29 `.md` par hote, 29 `.toml` sur Codex) ; les 14 entrees",
    "les/des/aux N": "LA SEULE DES 48 POUR LAQUELLE",
}

DERIVATION = ("python3 -c \"import sys,collections as k;sys.path.insert(0,'.agents/evals');"
              "import classification_rules as c;print(len(c.MECANISME),"
              "k.Counter(m for m,_ in c.MECANISME.values()))\"")


class CardinauxEnProseTests(unittest.TestCase):
    """AUCUN CARDINAL D'ENUMERATION DANS LA PROSE DE `classification_rules.py`.

    T-00000637, decision pilote S-00003970 (forme b) : on ne surveille pas un
    chiffre recopie, on cesse de le recopier. Le compte « 48 » a vecu 45, 46,
    48, et etait faux a 51 sans qu'aucun banc ne le lise : `ChiffresDeProseTests`
    est borne a `classification.md`. Ce fichier-ci n'ecrit plus ses cardinaux, il
    renvoie a la commande qui les derive (en-tete de la section 4).

    BORNE, ecrite plutot que decouverte (L-00000187) : la grammaire lit des
    CHIFFRES. Un cardinal en LETTRES (« quatre surfaces ») lui echappe, et une
    mesure DATEE d'une population de fichiers (`N fichiers`, absent des objets
    comptes) reste permise : elle dit l'etat a SA date et ne pretend pas au
    present.
    """

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        _sauter_chez_l_adoptant()
        cls.blocs = prose_des_regles()

    def test_la_lecture_et_la_grammaire_mordent(self):
        self.assertGreater(len(self.blocs), 50, "lecture des commentaires effondree")
        self.assertTrue(any("regles de classification" in t for _, t in self.blocs),
                        "la docstring du module n'est pas lue")
        for nom, rx in CARDINAUX.items():
            with self.subTest(forme=nom):
                self.assertRegex(normer(MORSURES[nom]), rx)

    def test_aucun_cardinal_accole_a_une_enumeration(self):
        trouves = [f":{debut} [{nom}] …{texte[max(0, m.start() - 25):m.end() + 15]}…"
                   for debut, texte in self.blocs
                   for nom, rx in CARDINAUX.items()
                   for m in rx.finditer(texte)]
        self.assertEqual(
            [], trouves,
            "cardinal recopie dans la prose de classification_rules.py — retire-le "
            f"et renvoie a la derivation : {DERIVATION}")


if __name__ == "__main__":
    unittest.main()
