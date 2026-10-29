"""Aucun secret dans le CONTENU des exports de run suivis par git (T-00000677).

WHY THIS EXISTS
  Le binôme de clôture (verdict S-00001809, critic-opus) a nommé un CHEMIN DE
  RÉDACTION CONTOURNÉ : `agentic_v3/db/run_export.py:_ligne_export_historique`
  recopie `payload_json` BRUT, or les lignes backfillées (commit 1129030)
  datent d'AVANT l'invariant « aucun secret au ledger » (né le 2026-09-20,
  5432fa6), et le magasin d'export `runs/<auteur>/<copie>/<AAAA-MM>.jsonl` est
  VERSIONNÉ EN AJOUT SEUL. Le scanner du dépôt
  (`.agents/security/gitleaks-scan.sh`) tourne en mode `diff` — « changed +
  untracked vs HEAD, never the whole git history » (`:33-34`) — donc il ne
  relit JAMAIS une ligne déjà commitée et non modifiée : les lignes du backfill
  sont STRUCTURELLEMENT hors de son périmètre, et il est de toute façon absent
  en CI et chez un adoptant. Aucun banc ne scannait ce contenu : c'était le
  trou. Celui-ci le scanne, et il VOYAGE (il tourne dans la porte `verify.sh`).

WHAT IT ASSERTS
  1. NON-VACUITÉ À PLANCHER DÉRIVÉ PAR DEUX SOURCES GIT DISTINCTES —
     l'ensemble balayé est EXACTEMENT l'INDEX suivi sous `runs/`
     (`git ls-files -z`) ET inclut l'ARBRE de HEAD (`git ls-tree`, source
     INDÉPENDANTE) : deux commandes que git tire de deux endroits, donc une
     régression qui rétrécirait le balayage NE déplace PAS les deux côtés de
     l'égalité ensemble (C1 — le premier jet comparait `_git_ls_runs()` à
     lui-même, égalité vacante). Une égalité d'ENSEMBLES de chemins, jamais un
     compte figé (un plancher en dur se périmerait — ce dépôt l'a payé deux
     fois), qu'un fichier retiré OU substitué fait rougir ;
     `test_le_plancher_rougit_si_le_balayage_retrecit` le PROUVE par mutation.
     `-z` : `git ls-files` sépare sinon par LF et CITE (échappement octal) tout
     chemin non-ASCII — un espace serait découpé, un accent rendu inexistant
     (C2 mesuré). Balayage AGNOSTIQUE À L'EXTENSION (un résidu
     `<mois>.jsonl.borne.tmp` capté par `git add -- runs/` n'échappe à aucun
     filtre de nom). Chiffres mesurés RAPPORTÉS, jamais codés en dur. Chez un
     adoptant `runs/` est vide (`strip: runs/`) : `skipTest` motivé.
  2. REFUS — aucun secret des NEUF FAMILLES de `redaction.MOTIFS` (PEM, AWS,
     `gh[posur]_`, `github_pat_`, `glpat-`, JWT, `xox[baprs]-`, `AIza`, `sk-`)
     dans le contenu des exports suivis. Le vocabulaire de détection est celui
     du dépôt (`cadre.ledger.redaction`, importé — jamais recopié : une copie
     divergerait en silence). PORTÉE ÉCRITE (C4) : ce banc ne prouve PAS
     l'absence de TOUT secret — un mot de passe générique, une clé Azure, un
     compte de service GCP, un Basic auth ne sont dans AUCUN de ces neuf motifs
     et passeraient ; une borne écrite vaut mieux qu'une garantie supposée. Un
     échec nomme `fichier:ligne (famille)`, JAMAIS la valeur (précédent : le
     scanner journalise `--redact`).
  3. PREUVE PAR MUTATION — le contrôle PEUT échouer : une ligne d'export
     porteuse d'un faux secret (concaténé à l'exécution), écrite sous
     `tempfile`, passée au MÊME chemin de détection, DOIT rougir. Le même
     fichier prouve que l'exemption ci-dessous exempte la fixture et NON le
     faux secret.

DELIBERATELY NOT FLAGGED — la différence entre une FORME et un secret, LUE À LA
SOURCE, jamais recopiée.
  Le seul jeton que `redaction.MOTIFS` signale dans l'arbre réel est la fixture
  documentée du kit `AKIA` + `ABCDEF1234567890` (`.agents/bin/test_mcp_render.py:307`),
  citée EN PROSE dans l'événement `BOARD_TASK_OBSERVED` de `T-00000310`. Ce
  n'est PAS un secret : le vrai scanner du dépôt l'ignore parce que son alphabet
  base32 `[A-Z2-7]` exclut `0,1,8,9`, là où le motif de `redaction`
  (`[0-9A-Z]{16}`, volontairement large) mord.
  L'EXEMPTION N'EST PAS RECOPIÉE ICI. Elle est LUE dans `.gitleaks.toml`, table
  `[allowlist]`, clé `regexes` — la SOURCE UNIQUE qui porte déjà ce littéral
  (`:38`) à côté de deux autres fixtures. La recopier ferait un SECOND foyer de
  la même vérité — exactement l'argument par lequel `MOTIFS` est importé et non
  recopié : une liste dupliquée diverge en silence, et le jour où quelqu'un
  ajoute une fixture à `.gitleaks.toml`, ce banc rougirait sans raison.
  DEUX BORNES ÉCRITES :
    * une entrée d'allowlist est un MOTIF, pas forcément un littéral : chacune
      est COMPILÉE (`re`) ; une entrée qui ne compile pas est REFUSÉE en la
      nommant (témoin `test_toute_entree_d_allowlist_compile`), jamais un
      silence ;
    * `.gitleaks.toml` peut être ABSENT chez un adoptant : alors l'exemption est
      VIDE et le banc est plus STRICT (la fixture serait signalée), jamais plus
      permissif (témoin `test_l_absence_de_config_durcit_le_banc`).
"""

from __future__ import annotations

import functools
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Le paquet `cadre` de l'arbre (`.agents/vendor/cadre`, sinon `src/cadre`), chargé par chemin par
# le résolveur `vendor_paths.py` (S-01M5RJX5SB C9) — jamais par une entrée de `sys.path`.
_VP_SPEC = importlib.util.spec_from_file_location("_exports_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
_VP = sys.modules[_VP_SPEC.name] = importlib.util.module_from_spec(_VP_SPEC)
_VP_SPEC.loader.exec_module(_VP)
_VP.charger_paquet(ROOT, "cadre")

from cadre.ledger import redaction  # noqa: E402 — needs the package loaded above

#: Source UNIQUE de l'exemption : la table `[allowlist]` du gitleaks du dépôt.
GITLEAKS_TOML = ROOT / ".gitleaks.toml"


def _compiler_exemptions(chemin: Path) -> tuple[list["re.Pattern[str]"], list[tuple[str, str]]]:
    """Charge et COMPILE les motifs d'exemption depuis `.gitleaks.toml`
    (`[allowlist].regexes`). Rend `(patterns, erreurs)`.

    - Fichier ABSENT (cas adoptant) : `([], [])` — AUCUNE exemption, donc le
      banc est plus STRICT, jamais plus permissif.
    - Chaque entrée est un MOTIF, compilé par `re` (`tomllib` est stdlib depuis
      3.11, que le dépôt exige : « stdlib seule » tenu). Une entrée qui NE
      COMPILE PAS entre dans `erreurs` (nommée), jamais ignorée en silence."""
    if not chemin.exists():
        return [], []
    data = tomllib.loads(chemin.read_text(encoding="utf-8"))
    brut = data.get("allowlist", {}).get("regexes", [])
    patterns: list["re.Pattern[str]"] = []
    erreurs: list[tuple[str, str]] = []
    for entree in brut:
        try:
            patterns.append(re.compile(entree))
        except re.error as exc:
            erreurs.append((entree, str(exc)))
    return patterns, erreurs


@functools.lru_cache(maxsize=1)
def _exemptions() -> tuple[list["re.Pattern[str]"], list[tuple[str, str]]]:
    return _compiler_exemptions(GITLEAKS_TOML)


def _est_exempt(jeton: str, patterns: list["re.Pattern[str]"]) -> bool:
    """`True` si `jeton` est couvert par un motif d'allowlist — sémantique
    gitleaks : recherche NON ancrée sur la valeur du secret trouvé."""
    return any(p.search(jeton) for p in patterns)


def _echappe(entree: str) -> str:
    """`re.escape`, le TIRET rendu (T-01M54MWW5GH) : depuis Python 3.7 il est
    échappé, alors que hors d'une classe il n'élargit rien — un littéral à
    tirets (`temoin-zz-123456789abc`) était refusé à tort, ici et chez l'adoptant."""
    return re.escape(entree).replace("\\-", "-")


def _git_ls_runs() -> list[str]:
    """TOUT fichier de l'INDEX git sous `runs/`, quelle que soit son EXTENSION.
    La couverture du banc ne dépend d'AUCUN nom de fichier : un résidu
    `<mois>.jsonl.borne.tmp` que `git add -- runs/` capterait est ici balayé
    comme le reste. Un filtre `.endswith(".jsonl")` serait l'accident de
    `test_spec_citation_par_nom.py` (protégé « par accident » parce que son
    filtre d'extensions ignorait `.jsonl`) dans l'AUTRE sens.

    C'est cette fonction qui ALIMENTE le balayage (via `_tracked_run_exports`) ;
    elle N'EST PAS sa propre référence — sinon les deux côtés de l'égalité
    seraient la MÊME commande et une régression les déplacerait ENSEMBLE (C1
    mesuré). La référence indépendante est `_reference_independante` (arbre de
    HEAD), une AUTRE source git.

    `-z` : sans lui `git ls-files` sépare par LF et CITE (échappement octal)
    tout chemin non-ASCII — un chemin à espace serait découpé en deux, un chemin
    accentué rendu inexistant, et le banc ERREUR au lieu de refuser en nommant
    (C2 mesuré sur dépôt jetable). Seul `-z` rend des octets bruts NUL-séparés ;
    le `""` final du flux NUL-terminé est écarté."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "runs/"],
        capture_output=True, text=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def _reference_independante() -> list[str]:
    """SECONDE dérivation du plancher, par une AUTRE source git : l'ARBRE de
    HEAD (`git ls-tree`), JAMAIS l'index. `_git_ls_runs` (index) et ceci (arbre
    commité) sont deux commandes DISTINCTES : une régression qui rétrécirait
    `_git_ls_runs` ne déplace donc PAS les deux côtés de l'égalité ensemble — le
    défaut de fond mesuré par C1 (« deux appels de la MÊME fonction ») est fermé.
    Le témoin de mutation `test_le_plancher_rougit_si_le_balayage_retrecit` le
    PROUVE : il patche `_git_ls_runs`, cette source-ci reste intacte, le banc
    rougit.
    BORNE ÉCRITE : un fichier INDEXÉ et non commité est dans l'index et PAS dans
    HEAD ; le témoin exige donc l'INCLUSION (`arbre ⊆ balayé`) sur cet axe, et
    l'ÉGALITÉ seulement contre l'index. `-z` pour la même raison qu'au-dessus."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "-r", "-z", "--name-only",
         "HEAD", "--", "runs/"],
        capture_output=True, text=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def _tracked_run_exports() -> list[str]:
    """Les fichiers d'export que le banc BALAYE — `runs/` a quitté l'exemption
    « sans fichier suivi » depuis le backfill de T-00000677
    (`test_classification_complete.py:44-45,102-111`). On balaie les fichiers de
    l'INDEX, jamais des fixtures, et SANS filtre d'extension (cf. `_git_ls_runs`).
    Fonction de PRODUCTION : le témoin de non-vacuité recompte l'ensemble
    attendu par une source git INDÉPENDANTE (`_reference_independante`), pour
    qu'une régression ICI — ne plus balayer qu'un fichier sur trois, ou
    réintroduire un filtre de nom — ROUGISSE au lieu de déplacer les deux côtés
    ensemble."""
    return _git_ls_runs()


def _scan_fichier(
    path: Path, patterns: list["re.Pattern[str]"]
) -> tuple[int, list[tuple[int, list[str]]], list[tuple[str, str]]]:
    """Lit l'export à `path` et rend `(nb_lignes, offenders, jetons_bruts)`.

    - `offenders` = `(numéro, familles)` dont la ligne porte un secret reconnu
      NON couvert par l'allowlist. On parcourt ligne par ligne (JSONL : un objet
      par ligne physique) pour NOMMER la ligne sans jamais exposer la valeur.
    - `jetons_bruts` = `(famille, jeton)` distincts vus AVANT exemption — sert
      au témoin qui lie l'allowlist à ce que l'arbre porte VRAIMENT.
    - EXTENSION ET DÉCODABILITÉ : `path` est balayé quelle que soit son
      extension, et un octet non décodable en UTF-8 n'est PAS un motif d'oubli.
      `errors="replace"` le remplace et la ligne passe TOUT DE MÊME au
      détecteur : on préfère SUR-balayer qu'exempter en silence par le nom ou
      par un octet illisible.
    On lit le TEXTE brut sérialisé : un secret dans `payload_json` y apparaît
    (le motif PEM tolère `[\\s\\S]`, donc même les `\\n` échappés)."""
    offenders: list[tuple[int, list[str]]] = []
    jetons: set[tuple[str, str]] = set()
    nb = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for numero, ligne in enumerate(fh, start=1):
            nb = numero
            familles: set[str] = set()
            for famille, motif in redaction.MOTIFS:
                for trouve in motif.finditer(ligne):
                    jeton = trouve.group(0)
                    jetons.add((famille, jeton))
                    if not _est_exempt(jeton, patterns):
                        familles.add(famille)
            if familles:
                offenders.append((numero, sorted(familles)))
    return nb, offenders, sorted(jetons)


@functools.lru_cache(maxsize=1)
def _scan_tracked() -> tuple[
    tuple[str, ...], int,
    tuple[tuple[str, int, tuple[str, ...]], ...],
    tuple[tuple[str, str], ...],
]:
    """Balaye TOUS les exports suivis une seule fois (partagé par les témoins).
    Rend `(rels_balayés, nb_lignes_total, offenders, jetons_bruts)`.

    `rels_balayés` est l'ensemble EFFECTIVEMENT lu — construit dans la boucle,
    fichier par fichier, et NON recopié de `_tracked_run_exports()` : ainsi une
    régression qui rétrécirait le balayage (slice, `break`, filtre) est visible
    du témoin de non-vacuité, qui compare cet ensemble à `_git_ls_runs()`."""
    patterns, _ = _exemptions()
    total = 0
    scannes: list[str] = []
    offenders: list[tuple[str, int, tuple[str, ...]]] = []
    jetons: set[tuple[str, str]] = set()
    for rel in _tracked_run_exports():
        nb, off, jt = _scan_fichier(ROOT / rel, patterns)
        scannes.append(rel)
        total += nb
        offenders.extend((rel, numero, tuple(familles)) for numero, familles in off)
        jetons.update(jt)
    return tuple(scannes), total, tuple(offenders), tuple(sorted(jetons))


class RunsExportsPropres(unittest.TestCase):
    def test_le_balayage_a_vu_des_octets(self):
        """NON-VACUITÉ À PLANCHER DÉRIVÉ PAR DEUX SOURCES GIT DISTINCTES. Un banc
        qui balaye MOINS de fichiers qu'il ne croit et annonce « propre » est le
        défaut de fond du dépôt. Le plancher n'est pas un compte figé (il se
        périmerait) : l'ensemble BALAYÉ doit être EXACTEMENT l'INDEX suivi sous
        `runs/` (`git ls-files`) ET inclure l'ARBRE de HEAD (`git ls-tree`,
        source INDÉPENDANTE — C1). Sans cette seconde source, les deux côtés de
        l'égalité seraient la même commande et une régression les déplacerait
        ENSEMBLE. Chez un adoptant `runs/` est vide (`strip: runs/`) : on passe
        en le DISANT."""
        rels, total, _, _ = _scan_tracked()
        index, tete = set(_git_ls_runs()), set(_reference_independante())
        if not index and not tete:
            self.skipTest(
                "adoptant : `runs/` ne porte aucun export suivi "
                "(`strip: runs/` le retire du paquet qui voyage) — rien à "
                "balayer, le banc passe sans mesurer.")
        balayes = set(rels)
        self.assertEqual(
            balayes, index,
            "PLANCHER DÉRIVÉ ROMPU (index) : l'ensemble des fichiers BALAYÉS "
            "n'est pas EXACTEMENT l'index suivi sous `runs/` (`git ls-files`). "
            "Un fichier retiré du balayage — ou substitué, ou ignoré par son "
            "extension — passerait « propre » sans être lu.\n"
            f"  manquants (suivis mais NON balayés) : {sorted(index - balayes)}\n"
            f"  en trop  (balayés mais NON suivis)  : {sorted(balayes - index)}")
        self.assertTrue(
            tete and tete <= balayes,
            "PLANCHER DÉRIVÉ ROMPU (arbre de HEAD, source INDÉPENDANTE) : un "
            "fichier COMMITÉ sous `runs/` n'est PAS couvert par le balayage. "
            "Cette source ne suit PAS `_git_ls_runs`, donc une régression qui a "
            "rétréci le balayage la fait rougir SEULE — c'est ce que le premier "
            "jet (deux appels de la même fonction) ne pouvait pas détecter.\n"
            f"  commités NON balayés : {sorted(tete - balayes)}")
        self.assertGreater(
            total, 0,
            f"{len(rels)} export(s) suivi(s) mais 0 ligne balayée — balayage "
            "vacant, le vert serait faux.")

    def test_le_plancher_rougit_si_le_balayage_retrecit(self):
        """TÉMOIN DE NON-VACUITÉ DU PLANCHER (protocole exact d'opus, C1). On
        force `_git_ls_runs` (l'INDEX, qui ALIMENTE le balayage) à ne rendre
        qu'UN fichier ; l'ARBRE de HEAD (`_reference_independante`, source
        indépendante NON patchée) en porte plus.
        `test_le_balayage_a_vu_des_octets` DOIT alors ROUGIR (AssertionError) —
        sinon le plancher ne mord pas et un « clean » sur 1/3 du magasin
        passerait pour vrai, exactement le défaut que ce chantier ferme. Si la
        même fonction était des deux côtés de l'égalité, ce patch les
        déplacerait ENSEMBLE et le témoin resterait vert : c'est ce qui est
        interdit ici."""
        reels = _reference_independante()
        if len(reels) < 2:
            self.skipTest(
                "adoptant/HEAD : moins de deux exports commités sous `runs/` — "
                "impossible de démontrer un balayage qui rétrécit.")
        original = globals()["_git_ls_runs"]
        globals()["_git_ls_runs"] = lambda: reels[:1]
        try:
            _scan_tracked.cache_clear()
            with self.assertRaises(AssertionError):
                RunsExportsPropres(
                    "test_le_balayage_a_vu_des_octets"
                ).test_le_balayage_a_vu_des_octets()
        finally:
            globals()["_git_ls_runs"] = original
            _scan_tracked.cache_clear()

    def test_aucun_secret_dans_les_exports_suivis(self):
        """REFUS. Aucun secret des NEUF FAMILLES de `redaction.MOTIFS` dans le
        contenu des exports suivis (C4 : ce banc ne couvre QUE ces neuf motifs —
        ni mot de passe générique, ni Azure, ni GCP, ni Basic). Le message nomme
        `fichier:ligne (famille)`, JAMAIS la valeur."""
        rels, _, offenders, _ = _scan_tracked()
        if not rels:
            self.skipTest("adoptant : aucun export suivi à contrôler.")
        lignes = [f"{rel}:{numero} ({', '.join(familles)})"
                  for rel, numero, familles in offenders]
        self.assertEqual(
            lignes, [],
            "SECRET dans le CONTENU d'un export de run SUIVI (fichier:ligne, "
            "famille — jamais la valeur). Remède : le magasin est en AJOUT "
            "SEUL, donc retirer le secret exige de réécrire l'export (piste "
            "T-00000696) et de faire TOURNER le credential ; ne jamais se "
            "contenter de le tracer.\n  " + "\n  ".join(lignes))

    def test_toute_entree_d_allowlist_compile(self):
        """Une entrée d'allowlist est un MOTIF : chacune doit compiler. Une
        entrée invalide est REFUSÉE en la nommant, jamais ignorée en silence
        (sinon la fixture qu'elle couvre cesse d'être exemptée EN SILENCE)."""
        _, erreurs = _exemptions()
        self.assertEqual(
            erreurs, [],
            "entrée(s) `[allowlist].regexes` de `.gitleaks.toml` qui NE "
            "COMPILENT PAS (motif, erreur) : "
            + "; ".join(f"{motif!r} -> {err}" for motif, err in erreurs))

    def test_toute_entree_d_allowlist_est_un_litteral_long(self):
        """C3. Une entrée d'allowlist NEUTRALISE la détection sur tout ce
        qu'elle couvre : un motif court ou large (`ghp_`) exempterait un VRAI
        secret. Chaque entrée doit donc être un LITTÉRAL ÉTROIT — `re.escape(e)
        == e` (aucun métacaractère qui élargirait la portée) ET au moins 20
        caractères (un préfixe de famille seul ne suffit jamais). Coexiste avec
        `test_toute_entree_d_allowlist_compile`, qui exige un motif VALIDE : ici
        on exige EN PLUS qu'il soit étroit. `.gitleaks.toml` étant HORS
        PÉRIMÈTRE, une entrée fautive est RAPPORTÉE, jamais réécrite. Adoptant
        sans config : exemption vide, rien à durcir."""
        if not GITLEAKS_TOML.exists():
            self.skipTest("adoptant : `.gitleaks.toml` absent, exemption vide.")
        data = tomllib.loads(GITLEAKS_TOML.read_text(encoding="utf-8"))
        entrees = data.get("allowlist", {}).get("regexes", [])
        for entree in entrees:
            self.assertEqual(
                _echappe(entree), entree,
                "entrée d'allowlist NON littérale (un métacaractère élargit la "
                "portée, un vrai secret pourrait être exempté EN SILENCE) : "
                f"{entree!r}")
            self.assertGreaterEqual(
                len(entree), 20,
                "entrée d'allowlist trop courte (< 20 car. : un préfixe de "
                f"famille exempterait tout un type de secret) : {entree!r}")

    def test_la_regle_du_litteral_admet_le_tiret_et_refuse_les_metacaracteres(self):
        """TÉMOIN de `_echappe` (T-01M54MWW5GH) : `re.escape` échappe le tiret,
        qui hors d'une classe ne dit rien ; la règle le rend, et seulement lui."""
        self.assertEqual(_echappe("temoin-secret-123456"), "temoin-secret-123456")
        for large in ("a.b", "a*", "[a-b]", "a\\-b", "T-[0-9A-Z]{26}"):
            with self.subTest(entree=large):
                self.assertNotEqual(_echappe(large), large)

    def test_l_exemption_est_sourcee_et_vivante(self):
        """L'exemption est LUE dans `.gitleaks.toml` (source unique), pas
        recopiée. Chaque jeton que `redaction` signale dans l'arbre réel doit
        être (a) un secret RÉELLEMENT reconnu — sinon l'exemption est morte — et
        (b) COUVERT par un motif d'allowlist. Rouge si `.gitleaks.toml` cesse de
        couvrir ce que l'arbre porte."""
        rels, _, _, jetons_bruts = _scan_tracked()
        if not rels:
            self.skipTest("adoptant : aucun export suivi.")
        if not jetons_bruts:
            self.skipTest(
                "l'arbre réel ne porte aucun jeton signalé par `redaction` — "
                "rien à lier à l'allowlist ; le banc reste strict.")
        patterns, _ = _exemptions()
        non_reconnus = sorted({fam for fam, jeton in jetons_bruts
                               if not redaction.contient_secret(jeton)})
        self.assertEqual(
            non_reconnus, [],
            "familles prétendument signalées mais que `redaction` ne reconnaît "
            f"pas — exemption morte : {non_reconnus}")
        non_couvertes = sorted({fam for fam, jeton in jetons_bruts
                                if not _est_exempt(jeton, patterns)})
        self.assertEqual(
            non_couvertes, [],
            "l'arbre réel porte un jeton (famille — jamais la valeur) que "
            "`.gitleaks.toml` `[allowlist]` NE COUVRE PLUS : soit un vrai secret "
            "(le retirer + rotation), soit une fixture à déclarer À LA SOURCE "
            f"dans `.gitleaks.toml`. Familles : {non_couvertes}")

    def test_l_absence_de_config_durcit_le_banc(self):
        """BORNE ADOPTANT. `.gitleaks.toml` ABSENT ⇒ exemption VIDE ⇒ le banc
        est plus STRICT (la fixture serait signalée), jamais plus permissif."""
        with tempfile.TemporaryDirectory() as tmp:
            absent = Path(tmp) / "pas-de-gitleaks.toml"
            patterns, erreurs = _compiler_exemptions(absent)
        self.assertEqual(patterns, [], "config absente ⇒ aucun motif d'exemption")
        self.assertEqual(erreurs, [], "config absente ⇒ aucune erreur, juste le vide")
        fixture = "AKIA" + "ABCDEF1234567890"
        self.assertTrue(
            redaction.contient_secret(fixture),
            "sanity : la fixture est bien un secret RECONNU par `redaction`")
        self.assertFalse(
            _est_exempt(fixture, patterns),
            "config absente ⇒ la fixture N'EST PAS exemptée ⇒ le banc la "
            "SIGNALERAIT (plus strict, jamais plus permissif).")

    def test_le_controle_peut_echouer_sous_mutation(self):
        """PREUVE PAR MUTATION. On écrit sous `tempfile` un export porteur d'un
        faux secret (concaténé à l'exécution — le TEXTE du source reste propre
        pour le gitleaks/SAST du dépôt, formes de
        `test_cadre_ledger_redaction.py`) et on le passe au MÊME chemin de
        détection, avec les motifs d'exemption RÉELS lus dans `.gitleaks.toml`.
        Le fichier prouve DEUX choses : la fixture documentée (couverte à la
        source) reste EXEMPTE, un vrai faux secret ROUGIT."""
        patterns, _ = _exemptions()
        faux_aws = "AKIA" + "Z3XYQ7WNRT4KLMND"
        faux_ghp = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        fixture = "AKIA" + "ABCDEF1234567890"  # donnée de test ; exemptée PAR la source
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "auteur" / "copie" / "2026-09.jsonl"
            chemin.parent.mkdir(parents=True)
            lignes = [
                # ligne 1 : SEULE la fixture (couverte par `.gitleaks.toml`) -> EXEMPTE
                json.dumps({"event_type": "X",
                            "payload_json": json.dumps({"note": fixture})}),
                # ligne 2 : faux secrets réels (hors allowlist) -> DOIT rougir
                json.dumps({"event_type": "Y",
                            "payload_json": json.dumps({"aws": faux_aws,
                                                        "ghp": faux_ghp})}),
            ]
            chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
            nb, offenders, _ = _scan_fichier(chemin, patterns)

        self.assertEqual(nb, 2, "les deux lignes de mutation doivent être lues")
        signalees = {numero: familles for numero, familles in offenders}
        self.assertNotIn(
            1, signalees,
            "la fixture, couverte par `.gitleaks.toml`, ne doit PAS être "
            "signalée — sinon le banc rougit à l'arrivée sur l'arbre réel.")
        self.assertIn(
            2, signalees,
            "MÊME chemin de détection, faux secret concaténé HORS allowlist : le "
            "contrôle DOIT rougir, sinon il ne prouve rien.")
        self.assertIn("aws_access_key", signalees.get(2, []),
                      "le faux AKIA (hors fixture) doit rougir : l'exemption "
                      "couvre la fixture, pas la famille.")
        self.assertIn("github_token", signalees.get(2, []),
                      "le faux ghp_ doit rougir.")


if __name__ == "__main__":
    unittest.main()
