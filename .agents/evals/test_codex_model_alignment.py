"""Codex role alignment and preservation of pinned models during mode changes."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib

import pytest

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from surface_kit import EST_LE_KIT, agents_du_kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# T-00000553: explicit pilot-approved role pins, outside the apply-mode lever.
EXPECTED_MODELS = {
    # Astra8
    "orchestrator": "gpt-6-astra",
    "planner": "gpt-6-astra",
    "modeler": "gpt-6-astra",
    "plan-critic": "gpt-6-astra",
    "exec-critic": "gpt-6-astra",
    "design-review": "gpt-6-astra",
    "security-code-review": "gpt-6-astra",
    "security-code-review-global": "gpt-6-astra",
    # T-01M5BZC1Y0T36EHTZY9AKZ650F (2026-10-21) — `seo-specialist` relit (lecture
    # seule, sandbox read-only) : tier des relecteurs, comme design-review. Choix de
    # l'exécutant sur la décision claude-opus-5-5/high de l'orchestrateur, à confirmer.
    "seo-specialist": "gpt-6-astra",
    # T-01M5HEJZ9XVXWQ61XMZYGA3YT0 (2026-10-22) — `reverse-engineer` fait du raisonnement
    # sur du code decompile hostile et ne produit pas de code : tier des juges et
    # planificateurs (contrat S-01M5HG8ZF5VY9T8DTV9TS86DT0). Hors EXCLUDED : son modele
    # n'est pas son identite.
    "reverse-engineer": "gpt-6-astra",
    # Sol4
    "dev-mono": "gpt-6-sol",
    "dev-multi": "gpt-6-sol",
    "frontend-fidelity": "gpt-6-sol",
    "optimizer": "gpt-6-sol",
    # T-01M4JC50S6CTJ5HJ697929E6N8 — `load-tester` produit du code (le scenario k6) : tier des defs
    # dev, decision pilote Q8 du 2026-10-08. Hors EXCLUDED : son modele n'est pas
    # son identite.
    "load-tester": "gpt-6-sol",
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19) — `terraform-deployer` produit du
    # code (l'IaC Terraform, slot dev d'une tache IaC) : tier des defs dev, comme
    # load-tester. Hors EXCLUDED : son modele n'est pas son identite.
    "terraform-deployer": "gpt-6-sol",
    # Terra8
    "analyzer": "gpt-5.6-terra",
    "custom-docs-curator": "gpt-5.6-terra",
    "documenter": "gpt-5.6-terra",
    "indexer": "gpt-5.6-terra",
    "skills-resolver": "gpt-5.6-terra",
    "security-orchestrator": "gpt-5.6-terra",
    "security-remediation": "gpt-5.6-terra",
    "security-sca": "gpt-5.6-terra",
    # Luna6
    "language-detector": "gpt-6-luna",
    "board-reporter": "gpt-6-luna",
    "communicator": "gpt-6-luna",
    "sca-java": "gpt-6-luna",
    "sca-mobile": "gpt-6-luna",
    "sca-npm": "gpt-6-luna",
    # T-012 — LE BINOME DE CLOTURE. Trois roles de CRITIQUE, nommes d apres le
    # modele qu ils portent SUR CLAUDE CODE ; ailleurs le role reste le meme et
    # le modele est celui de l hote. critic-sonnet-max est le REPLI de
    # critic-fable et porte l effort le plus haut des trois (max), a egalite
    # avec critic-fable depuis S-01M4N02D2KFYQVV92ZXGSXBG2G (2026-10-11).
    "critic-opus": "gpt-6-astra",
    "critic-fable": "gpt-6-sol",
    "critic-sonnet-max": "gpt-5.6-terra",
    # T-00000624 — LA PAIRE DE PLAN. Meme forme que le binome de cloture, un cran
    # plus tot dans la chaine : `plan-critic` (astra, max) garde le role de
    # Critique A et `plan-critic-sonnet-max` prend l angle B — les PREMISSES du
    # plan plutot que sa structure. `planner-sonnet` est le planner d ESCALADE,
    # invoque au PREMIER NO_GO de la paire et jamais au cas nominal.
    #
    # POURQUOI TERRA POUR LES DEUX, et c est la meme raison que pour
    # critic-sonnet-max : ces defs sont nommees d apres le modele qu elles
    # portent SUR CLAUDE CODE (sonnet), et terra en est l homologue ici. Les
    # trois sont EXCLUES du levier `apply-mode` pour cette raison exacte —
    # le levier echange les modeles, et echanger celui d une def nommee d apres
    # le sien detruirait la propriete qu elle existe pour porter.
    "plan-critic-sonnet-max": "gpt-5.6-terra",
    "planner-sonnet": "gpt-5.6-terra",
}

# T-01M5CYKCF6S7T5N2GCD6VXQTR7 — LA LISTE FERMÉE des slugs de rôle Codex, un par rang
# (luna < terra < sol < astra, CODEX_MODEL_RANK de test_golden_transcripts.py). Écrite ICI,
# jamais lue dans ~/.codex : le cache local du poste n'est pas celui du runner. Un slug que
# l'offre retire sort d'ici, et le roster embarqué qui le porterait encore rougit.
CODEX_MODELS_AUTORISES = frozenset({"gpt-6-luna", "gpt-5.6-terra", "gpt-6-sol", "gpt-6-astra"})
DEFS_CODEX = ROOT / ".codex/agents"


def _charger_par_chemin(nom: str, chemin: Path):
    """Un module chargé PAR CHEMIN sous un nom PRIVÉ, enregistré avant exécution (T-00000134) : `sys.path`
    intact, et pytest ne recollecte pas les classes de test qu'il porte."""
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def donnees_roster() -> Path:
    """`<paquet cadre>/data/roster`, le paquet résolu par `vendor_paths` (neuf `.agents/vendor/cadre`, sinon
    ancien `src/cadre`) : le banc suit le déplacement du paquet, il ne lit jamais un chemin en dur."""
    vendor_paths = _charger_par_chemin("_alignement_vendor_paths", ROOT / ".agents/bin/vendor_paths.py")
    paquet = vendor_paths.dossier_paquet(ROOT, "cadre")
    assert paquet is not None, f"paquet cadre introuvable sous {ROOT} (ni .agents/vendor ni src)"
    return paquet / "data" / "roster"


def rangs_codex() -> dict[str, int]:
    """`TierRelationTests.CODEX_MODEL_RANK` de `test_golden_transcripts.py`, lu, jamais recopié."""
    golden = _charger_par_chemin("_alignement_golden", EVALS / "test_golden_transcripts.py")
    return golden.TierRelationTests.CODEX_MODEL_RANK


def modeles_codex_embarques(donnees: Path) -> dict[str, str]:
    """Rôle -> modèle de l'entête Codex de chaque roster `<rôle>.json` (entrée en `.` ignorée)."""
    modeles = {}
    for chemin in sorted(donnees.glob("*.json")):
        if chemin.name.startswith("."):
            continue
        rendu = json.loads(chemin.read_text(encoding="utf-8"))["rendus"]["codex"]
        assert "entete" in rendu, f"{chemin.name} : rendu codex sans entete"
        modeles[chemin.stem] = tomllib.loads("\n".join(rendu["entete"]))["model"]
    assert modeles, f"aucun roster sous {donnees} : un ensemble vide serait vert par vacuite"
    return modeles


def ecarts_modeles_codex(donnees: Path, defs_codex: Path) -> list[str]:
    """Chaque modèle Codex du roster est dans la liste fermée ET égal à la déf du même rôle."""
    fautes = []
    for role, modele in modeles_codex_embarques(donnees).items():
        if modele not in CODEX_MODELS_AUTORISES:
            fautes.append(f"{role} : slug {modele!r} hors liste fermee {sorted(CODEX_MODELS_AUTORISES)}")
        definition = defs_codex / f"{role}.toml"
        if not definition.is_file():
            fautes.append(f"{role} : def codex absente ({definition.name})")
            continue
        vivant = tomllib.loads(definition.read_text(encoding="utf-8")).get("model")
        if vivant != modele:
            fautes.append(f"{role} : roster {modele!r} != def codex {vivant!r}")
    return fautes


def load_mode():
    spec = importlib.util.spec_from_file_location(
        "codex_alignment_mode", ROOT / "core-scripts/apply-mode.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_role_parity_and_effort_floor() -> None:
    claude = {p.stem: p for p in (ROOT / ".claude/agents").glob("*.md")}
    codex = {p.stem: p for p in (ROOT / ".codex/agents").glob("*.toml")}
    # T-01M54MWW5GH (S-01M54ZQ6WC) : les pins couvrent le roster EMBARQUÉ, partout ;
    # hors du kit, un agent AJOUTÉ par l'adoptant n'est pas jugé — ceux du kit, si.
    kit = agents_du_kit()
    assert EXPECTED_MODELS.keys() == kit, sorted(EXPECTED_MODELS.keys() ^ kit)
    assert set(EXPECTED_MODELS.values()) <= CODEX_MODELS_AUTORISES, sorted(
        set(EXPECTED_MODELS.values()) - CODEX_MODELS_AUTORISES)
    if not EST_LE_KIT:
        assert kit <= claude.keys() and kit <= codex.keys(), sorted(kit - (claude.keys() & codex.keys()))
        claude = {k: v for k, v in claude.items() if k in kit}
        codex = {k: v for k, v in codex.items() if k in kit}
        assert claude and codex, "filtre au roster vide"
    assert len(codex) == len(EXPECTED_MODELS)
    assert claude.keys() == codex.keys() == EXPECTED_MODELS.keys()
    ranks = {v: i for i, v in enumerate(("low", "medium", "high", "xhigh", "max", "ultra"))}
    for name, path in codex.items():
        config = tomllib.loads(path.read_text())
        header = claude[name].read_text().split("---", 2)[1]
        effort = re.search(r"^effort:\s*(\S+)", header, re.M).group(1)
        assert config["name"] == name
        assert config["model"] == EXPECTED_MODELS[name], name
        assert ranks[config["model_reasoning_effort"]] >= ranks[effort], name


def test_expert_restore_keeps_models_and_original_bytes(tmp_path, monkeypatch) -> None:
    mode = load_mode()
    for directory, *_ in mode.LEVER_HOSTS.values():
        shutil.copytree(ROOT / directory, tmp_path / directory)
    for directory, *_ in mode.INDICATIVE_HOSTS.values():
        shutil.copytree(ROOT / directory, tmp_path / directory)
    doc = tmp_path / ".agents/ref/MODEL_MODES.md"
    doc.parent.mkdir(parents=True)
    shutil.copyfile(mode.DOC, doc)
    monkeypatch.setattr(mode, "ROOT", tmp_path)
    monkeypatch.setattr(mode, "DOC", doc)
    monkeypatch.setattr(mode, "MODE_FILE", tmp_path / ".agents/state/local/MODEL_MODE")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    codex_paths = {p.stem: p for p in (tmp_path / ".codex/agents").glob("*.toml")}
    models_before = {
        name: tomllib.loads(before[path].decode("utf-8"))["model"]
        for name, path in codex_paths.items()
        if EST_LE_KIT or name in EXPECTED_MODELS
    }
    assert models_before == EXPECTED_MODELS
    communicator = codex_paths["communicator"]
    grid = mode.load_grid()
    assert grid == mode.capture_grid()
    assert mode.LEVER_HOSTS["codex"][2] == ("effort",)
    # T-012 — « AU ROSTER » ET « PILOTE PAR LE LEVIER » NE SONT PLUS LA MEME
    # CHOSE. Cette assertion les confondait, ce qui etait vrai tant qu'aucun
    # agent codex n'etait exclu. Le binome de cloture l'est sur les cinq hotes,
    # parce que le levier ECHANGE les modeles et que ces trois-la sont NOMMES
    # d'apres le leur. Le roster attendu est donc EXPECTED_MODELS moins les
    # exclus codex — derive de `mode.EXCLUDED`, jamais reecrit a la main.
    exclus_codex = {a for h, a in mode.EXCLUDED if h == "codex"}
    assert exclus_codex, "aucun exclu codex : cette soustraction serait un no-op"
    assert {(agent, axis) for host, agent, axis in grid if host == "codex"} == {
        (agent, "effort") for agent in EXPECTED_MODELS if agent not in exclus_codex
    }
    assert mode.cmd_apply(mode.EXPERT, False, True) == 0
    assert communicator.read_bytes() == before[communicator]
    touches = 0
    for path in (tmp_path / ".codex/agents").glob("*.toml"):
        if not EST_LE_KIT and path.stem not in models_before:
            continue  # hors du kit seulement : un agent de l'adoptant (filtre ci-dessus)
        config = tomllib.loads(path.read_text())
        assert config["model"] == models_before[path.stem], path.stem
        if path.stem in exclus_codex:
            # Un exclu n'a AUCUNE ligne de grille, et son octet ne bouge pas :
            # c'est ce que « exclu du levier » veut dire, et la seconde moitie
            # de l'assertion vaut mieux que l'absence de la premiere.
            assert path.read_bytes() == before[path], path.stem
            continue
        assert config["model_reasoning_effort"] == grid[("codex", path.stem, "effort")][mode.EXPERT]
        touches += 1
    assert touches == mode.EXPECTED_TOUCHED["codex"], touches
    assert mode.cmd_apply(mode.BASELINE, False, True) == 0
    assert not mode.MODE_FILE.exists()
    for path, content in before.items():
        assert path.read_bytes() == content, path


def test_embedded_codex_model_allowlist() -> None:
    """T-01M5CYKCF6S7T5N2GCD6VXQTR7 : tout modèle Codex du roster embarqué est dans la liste
    fermée et égal à la déf `.codex/agents/<rôle>.toml`. Dans le kit, le roster est EXACTEMENT celui des
    pins ; chez l'adoptant (`EST_LE_KIT` faux), il les couvre au moins — même tolérance que la parité."""
    donnees = donnees_roster()
    embarques = modeles_codex_embarques(donnees).keys()
    if EST_LE_KIT:
        assert embarques == EXPECTED_MODELS.keys(), sorted(embarques ^ EXPECTED_MODELS.keys())
    else:
        assert EXPECTED_MODELS.keys() <= embarques, sorted(EXPECTED_MODELS.keys() - embarques)
    assert ecarts_modeles_codex(donnees, DEFS_CODEX) == []


def test_liste_fermee_egale_aux_rangs_codex() -> None:
    """La liste fermée des slugs et les rangs du contrat de palier nomment les MÊMES modèles : un slug ajouté
    à l'une sans l'autre rougit ici, jamais au premier rôle qui le porterait."""
    assert CODEX_MODELS_AUTORISES == set(rangs_codex())


def _poser_roster(racine: Path, role: str, modele_roster: str, modele_def: str) -> tuple[Path, Path]:
    donnees, defs = racine / "roster", racine / "defs"
    donnees.mkdir()
    defs.mkdir()
    rendu = {"entete": [f'name = "{role}"', f'model = "{modele_roster}"'], "corps": []}
    (donnees / f"{role}.json").write_text(
        json.dumps({"version_format": 1, "nom": role, "rendus": {"codex": rendu}}), encoding="utf-8")
    (defs / f"{role}.toml").write_text(f'name = "{role}"\nmodel = "{modele_def}"\n', encoding="utf-8")
    return donnees, defs


def test_embedded_codex_model_allowlist_refuse_un_slug_hors_liste(tmp_path) -> None:
    # Slug SYNTHÉTIQUE : aucun slug retiré n'est écrit ici en témoin permanent.
    donnees, defs = _poser_roster(tmp_path, "alpha", "gpt-synthetique-hors-liste", "gpt-synthetique-hors-liste")
    fautes = ecarts_modeles_codex(donnees, defs)
    assert len(fautes) == 1 and "'gpt-synthetique-hors-liste' hors liste fermee" in fautes[0], fautes


def test_embedded_codex_model_allowlist_refuse_un_roster_desaccorde_de_sa_def(tmp_path) -> None:
    donnees, defs = _poser_roster(tmp_path, "alpha", "gpt-6-sol", "gpt-6-luna")
    assert ecarts_modeles_codex(donnees, defs) == ["alpha : roster 'gpt-6-sol' != def codex 'gpt-6-luna'"]


def test_embedded_codex_model_allowlist_refuse_un_roster_vide(tmp_path) -> None:
    (tmp_path / ".ignore.json").write_text("{}", encoding="utf-8")
    with pytest.raises(AssertionError, match="vacuite"):
        modeles_codex_embarques(tmp_path)
