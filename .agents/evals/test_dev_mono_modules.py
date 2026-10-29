"""dev-mono lit les conventions du MODULE de son fichier cible (T-01M5DFN2Q956QKF0FVTSEMYZ7P, lot B).

Décision pilote S-01M5E5F9XNSBQ7DWNQ4H36H0FD. Le détecteur émet `modules[]` (chaque
entrée porte `test_runner`, `conventions_file`, `registry_sections`) ; avant ce lot,
dev-mono ne lisait que les champs RACINE : sur un dépôt Spring + Angular, un fichier
`frontend/…` recevait la feuille et le lanceur de tests du module dominant, en silence.

CE QUE CE BANC JUGE, sur les TROIS défs qui consomment `conventions_file`
(`.claude`, `.gemini`, `.kimi-code`) et sur le roster rendu de dev-mono :
  * la règle de module est écrite, à l'octet, identique sur les trois hôtes ;
  * l'étape 3 prend `test_runner` du module, plus de la racine seule ;
  * la règle compare par SEGMENTS de chemin, et son exemple est un vrai piège :
    `frontend-legacy/src/a.ts` commence par `frontend` en chaîne, jamais en dossier ;
  * le repli racine et « null means no sheet exists » restent dits.

BORNES (dites, pour ne pas être relues comme des garanties) :
  * C20 du plan : `.codex/agents/dev-mono.toml` et `.github/agents/dev-mono.agent.md`
    ne lisent ni `conventions_file` ni `test_runner` ; ils n'ont la lecture par module
    que par la doctrine (lot C, AGENTS.md et Copilot). Ce banc ne les juge PAS : un
    bras d'absence sur eux serait vert pour toujours.
  * Banc TEXTUEL : il prouve que la règle est écrite, jamais qu'un modèle l'applique.
  * Hors du kit (marqueur `.agents/IS_THE_KIT` absent), le bras roster SAUTE, annoncé.
"""
from pathlib import Path
import importlib.util
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import EST_LE_KIT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

HOSTS = {
    "claude": ".claude/agents/dev-mono.md",
    "gemini": ".gemini/agents/dev-mono.md",
    "kimi": ".kimi-code/agents/dev-mono.md",
}
# Le paquet `cadre` vit où le résolveur `vendor_paths.py` (chargé PAR CHEMIN) le désigne :
# `.agents/vendor/cadre` d'abord, `src/cadre` sinon (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot L).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_dev_mono_modules_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_CADRE = _VENDOR.dossier_paquet(ROOT, "cadre") or ROOT / _VENDOR.ANCIENS["cadre"]
ROSTER = (_CADRE / "data" / "roster" / "dev-mono.json").relative_to(ROOT.resolve()).as_posix()

RULE_HEAD = "- Module rule: when the language JSON carries a `modules[]` array"
FIELDS = "read `test_runner`, `conventions_file` and `registry_sections` from the entry"
PREFIX = "whose `path` is the LONGEST DIRECTORY PREFIX of the target file"
SEGMENTS = "compared by whole path segments"
OWNER, OWNED, FOREIGN = "frontend", "frontend/src/a.ts", "frontend-legacy/src/a.ts"
EXAMPLE = f"`{OWNER}` owns `{OWNED}`, never `{FOREIGN}`"
ROOT_FALLBACK = (
    "no `modules[]`, no matching entry, or a field absent from that entry "
    "→ the root field of the language JSON"
)
STEP3 = "type-check or lint (from the `test_runner` of the target file's module"
OLD_STEP3 = "from language JSON's `test_runner`"
CONSUMES_MODULE = "- Follow conventions from that `conventions_file` when it names a sheet"
NULL_FALLBACK = "null means no sheet exists"
AMBIGUOUS = ("path contains", "path starts with")

SAUT_ADOPTANT = (
    "SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) — "
    "le roster de cadre n'est jugé que dans le kit"
)


def lire(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def ligne_regle(texte: str, rel: str) -> str:
    lignes = [l for l in texte.splitlines() if l.startswith(RULE_HEAD)]
    assert len(lignes) == 1, f"{rel} : {len(lignes)} ligne(s) de règle de module, une attendue"
    return lignes[0]


def segment_prefix(dossier: str, fichier: str) -> bool:
    """La sémantique que la règle ÉCRIT : préfixe par segments entiers."""
    d, f = dossier.split("/"), fichier.split("/")
    return f[: len(d)] == d


def test_population_is_the_three_consumers() -> None:
    """Non-vacuité : les trois défs existent, sont dev-mono, et lisent le champ."""
    assert set(HOSTS) == {"claude", "gemini", "kimi"}
    for rel in HOSTS.values():
        texte = lire(rel)
        assert "\nname: dev-mono\n" in texte.split("---", 2)[1], f"{rel} n'est pas dev-mono"
        assert "conventions_file" in texte, f"{rel} ne lit plus `conventions_file`"


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_module_rule_is_written(host: str) -> None:
    """MUTATION : retirer la règle, son exemple ou son repli d'un hôte -> rouge."""
    rel = HOSTS[host]
    regle = ligne_regle(lire(rel), rel)
    for ancre in (FIELDS, PREFIX, SEGMENTS, EXAMPLE, ROOT_FALLBACK):
        assert ancre in regle, f"dev-mono/{host} : fragment absent de la règle de module : {ancre!r}"
    for flou in AMBIGUOUS:
        assert flou not in regle, f"dev-mono/{host} : règle ambiguë ({flou!r}), préfixe de DOSSIER exigé"


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_step3_reads_the_module_test_runner(host: str) -> None:
    """MUTATION : rendre à l'étape 3 la lecture racine seule -> rouge."""
    texte = lire(HOSTS[host])
    assert STEP3 in texte, f"dev-mono/{host} : l'étape 3 ne lit pas le `test_runner` du module"
    assert OLD_STEP3 not in texte, f"dev-mono/{host} : l'étape 3 lit encore la racine seule"


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_conventions_follow_the_module_and_keep_the_null_fallback(host: str) -> None:
    """La lecture des conventions VIENT APRÈS la règle et pointe sur son champ ;
    « null means no sheet exists » reste dit (A3 de test_conventions_contract)."""
    rel = HOSTS[host]
    texte = lire(rel)
    lignes = texte.splitlines()
    i_regle = lignes.index(ligne_regle(texte, rel))
    suivante = lignes[i_regle + 1]
    assert suivante.startswith(CONSUMES_MODULE), (
        f"dev-mono/{host} : la ligne qui suit la règle de module ne suit pas "
        "« that `conventions_file` » du module"
    )
    assert NULL_FALLBACK in suivante, f"dev-mono/{host} : repli null perdu"


def test_rule_is_identical_on_the_three_hosts() -> None:
    """Même règle, même octet, sur chaque hôte : un miroir à la traîne rougit."""
    regles = {h: ligne_regle(lire(rel), rel) for h, rel in HOSTS.items()}
    assert len(set(regles.values())) == 1, f"règles divergentes : {sorted(regles)}"


def test_the_example_is_a_real_trap_for_string_prefix() -> None:
    """L'exemple n'a de sens que si un `startswith` naïf se TROMPE sur lui et que la
    comparaison par segments le tranche. MUTATION : exemple `frontend/legacy/a.ts`
    ou `backend-legacy/…` -> rouge."""
    assert FOREIGN.startswith(OWNER), "l'exemple étranger ne piège plus le préfixe de chaîne"
    assert not segment_prefix(OWNER, FOREIGN), "l'exemple étranger est possédé par segments"
    assert segment_prefix(OWNER, OWNED), "l'exemple possédé ne l'est pas par segments"
    texte = lire(HOSTS["claude"])
    assert EXAMPLE in texte, "l'exemple épinglé n'est plus celui de la déf"


@pytest.mark.skipif(not EST_LE_KIT, reason=SAUT_ADOPTANT)
def test_roster_carries_the_module_rule() -> None:
    """Le roster rendu porte la règle (régénéré dans le même commit).
    MUTATION : déf modifiée sans `--regenerer` -> rouge ici et dans test_cadre_roster."""
    donnees = json.loads(lire(ROSTER))
    rendu = json.dumps(donnees, ensure_ascii=False)
    regle = ligne_regle(lire(HOSTS["claude"]), HOSTS["claude"])
    assert json.dumps(regle, ensure_ascii=False)[1:-1] in rendu, "roster sans la règle de module"
    assert OLD_STEP3 not in rendu, "roster encore sur l'étape 3 racine"
