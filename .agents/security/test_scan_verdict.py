#!/usr/bin/env python3
"""Banc de scan_verdict.py — contrat cadre.scan-verdict/1 (T-01M4V7R991WJNAMD8GAQZNG903).

Lancer : python3 -m pytest -q -p no:cacheprovider .agents/security/test_scan_verdict.py

Chaque fixture est MESURÉE (outil, version, date, commande) ou déclarée
SYNTHÉTIQUE. Les bras live (`BrasLive*`) ne tournent que si semgrep / gitleaks
sont sur le PATH : ils ne tournent pas en CI (job `tests` sans scanners).
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import scan_verdict as sv  # noqa: E402

SCHEMA_JSON = ICI / "scan-verdict.schema.json"
CANARI = "CANARI-0001"
CONTROLE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# --- fixtures semgrep ---------------------------------------------------------

# MESURÉ — semgrep 1.175.0, 2026-10-13, plan-critic it.2 (E4) : règle lente, sans
# --verbose, rc 0 ; erreur Timeout de niveau warn qui porte un chemin, heavy.py
# reste dans `scanned`, pas de clé `skipped`. Bloc `time` retiré ; `rule_id` et
# `message` portaient un chemin machine : id neutre (plan, ligne 11).
E4 = {
    "version": "1.175.0",
    "results": [],
    "errors": [{"code": 2, "level": "warn", "type": "Timeout", "rule_id": "heavy",
                "message": "Timeout when running heavy on heavy.py:\n ", "path": "heavy.py"}],
    "paths": {"scanned": ["heavy.py", "small.py"]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}

# MESURÉ — semgrep 1.175.0, 2026-10-13, plan-critic it.2 (A5) : --verbose, un
# fichier de plus de 1 Mo et un .semgrepignore ; rc 0. Bloc `time` retiré.
A5 = {
    "version": "1.175.0",
    "results": [],
    "errors": [],
    "paths": {"scanned": ["small.py"],
              "skipped": [{"path": "big.py", "reason": "exceeded_size_limit"},
                          {"path": "ignored.py", "reason": "semgrepignore_patterns_match"}]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}

# MESURÉ — semgrep 1.175.0, 2026-10-13 (m1b, bad2) : regex invalide dans une
# règle, rc 2, erreur SANS chemin. Bloc `time` retiré ; chemin machine de
# `rule_id` et `message` remplacé par un id neutre.
BAD2 = {
    "version": "1.175.0",
    "results": [],
    "errors": [{"code": 2, "level": "error", "type": "Rule parse error", "rule_id": "bad-re",
                "message": "Rule parse error in rule bad-re:\n invalid regex '([a-z': missing terminating ]"}],
    "paths": {"scanned": ["clean1.py"]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}

# MESURÉ — semgrep 1.175.0, 2026-10-14, ce dev : `semgrep scan --config
# rules-local.yml --json --verbose --metrics=off --disable-version-check .` dans
# un dossier dont le .semgrepignore liste ignored.py et rules-local.yml ; rc 0.
# notes.txt (non ciblé) n'apparaît nulle part. Bloc `time` retiré.
SEMGREPIGNORE_SEUL = {
    "version": "1.175.0",
    "results": [],
    "errors": [],
    "paths": {"scanned": ["small.py"],
              "skipped": [{"path": "ignored.py", "reason": "semgrepignore_patterns_match"},
                          {"path": "rules-local.yml", "reason": "semgrepignore_patterns_match"}]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}

# MESURÉ — même cible, même commande SANS --verbose (2026-10-14) : rc 0, pas de
# clé `skipped`. Bloc `time` retiré.
SANS_VERBOSE = {
    "version": "1.175.0",
    "results": [],
    "errors": [],
    "paths": {"scanned": ["small.py"]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}

# MESURÉ — semgrep 1.175.0, 2026-10-13, plan-critic it.3 (rel.json) : config
# relative au cwd, `check_id` sans préfixe, une trouvaille ERROR. `time` retiré.
REL = {
    "version": "1.175.0",
    "results": [{"check_id": "py-eval", "path": "t/small.py",
                 "start": {"line": 1, "col": 1, "offset": 0}, "end": {"line": 1, "col": 10, "offset": 9},
                 "extra": {"message": "eval of \"1\"", "metadata": {}, "severity": "ERROR",
                           "fingerprint": "requires login", "lines": "requires login",
                           "validation_state": "NO_VALIDATOR", "engine_kind": "OSS"}}],
    "errors": [],
    "paths": {"scanned": ["t/small.py"]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}

# SYNTHÉTIQUE (plan-critic it.3, réserve C1) : le SEUL trou est une raison
# inventée ; la politique (semgrepignore) est à côté, sans effet.
RAISON_INCONNUE = {
    "version": "1.175.0",
    "results": [],
    "errors": [],
    "paths": {"scanned": [],
              "skipped": [{"path": "ignored.py", "reason": "semgrepignore_patterns_match"},
                          {"path": "small.py", "reason": "zz_raison_future"}]},
    "engine_requested": "OSS", "skipped_rules": [], "profiling_results": [],
}


def _semgrep_avec_erreurs(erreurs: list, scanned: list[str]) -> dict:
    """SYNTHÉTIQUE : rapport propre (forme mesurée) auquel on greffe des erreurs."""
    return {"version": "1.175.0", "results": [], "errors": erreurs, "paths": {"scanned": scanned},
            "engine_requested": "OSS", "skipped_rules": [], "profiling_results": []}


# --- fixtures gitleaks --------------------------------------------------------

# MESURÉ — gitleaks 8.30.1, 2026-10-14, ce dev : `gitleaks dir gl --report-format
# json --report-path … --redact --exit-code 7 --no-banner`, rc 7. Jeton
# assemblé par fragments, valeur caviardée par --redact.
GITLEAKS_ROUGE = [{
    "RuleID": "github-pat",
    "Description": "Uncovered a GitHub Personal Access Token, potentially leading to unauthorized "
                   "repository access and sensitive content exposure.",
    "StartLine": 1, "EndLine": 1, "StartColumn": 10, "EndColumn": 49,
    "Match": "REDACTED", "Secret": "REDACTED", "File": "gl/app.py", "SymlinkFile": "",
    "Commit": "", "Entropy": 5.121928, "Author": "", "Email": "", "Date": "", "Message": "",
    "Tags": [], "Fingerprint": "gl/app.py:github-pat:1",
}]

# MESURÉ — même commande sur un dossier sans secret : rc 0, rapport de 3 octets.
GITLEAKS_PROPRE = "[]\n"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dossier = Path(self._tmp.name)
        self._n = 0

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def rapport(self, contenu: object) -> Path:
        self._n += 1
        chemin = self.dossier / f"rapport-{self._n}.json"
        if isinstance(contenu, bytes):
            chemin.write_bytes(contenu)
        elif isinstance(contenu, str):
            chemin.write_bytes(contenu.encode("utf-8"))
        else:
            chemin.write_bytes(json.dumps(contenu).encode("utf-8"))
        return chemin

    def valide(self, verdict: dict) -> dict:
        self.assertEqual(sv.validate(verdict), [], verdict)
        return verdict

    def semgrep(self, data: object, **kw: object) -> dict:
        kw.setdefault("findings_rc", None)
        return self.valide(sv.from_semgrep(self.rapport(data), **kw))

    def gitleaks(self, data: object, **kw: object) -> dict:
        kw.setdefault("findings_rc", 1)
        return self.valide(sv.from_gitleaks(self.rapport(data), **kw))

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = sv.main([str(a) for a in argv])
        return rc, out.getvalue(), err.getvalue()

    def batterie(self) -> list[dict]:
        """Verdicts de toutes les fixtures, pour les propriétés universelles."""
        with mock.patch.object(sv, "MAX_REPORT_BYTES", 8):  # note report_too_large (S1, étape 1)
            trop_gros = [self.semgrep(SEMGREPIGNORE_SEUL), self.gitleaks(GITLEAKS_ROUGE, findings_rc=7, exit_code=7)]
        return [
            *trop_gros,
            self.semgrep(E4), self.semgrep(A5), self.semgrep(BAD2), self.semgrep(SEMGREPIGNORE_SEUL),
            self.semgrep(SANS_VERBOSE, candidates=["small.py", "notes.txt"]), self.semgrep(REL),
            self.semgrep(RAISON_INCONNUE), self.semgrep(SEMGREPIGNORE_SEUL, exit_code=2),
            self.gitleaks(GITLEAKS_ROUGE, findings_rc=7, exit_code=7), self.gitleaks(GITLEAKS_PROPRE),
            self.gitleaks(GITLEAKS_PROPRE, exit_code=0), self.gitleaks(""), self.semgrep("{pas du json"),
            self.semgrep({**SANS_VERBOSE, "paths": {"scanned": []}}, candidates=["small.py"]),
        ]


def _cles_schema(noeud: dict) -> list[str]:
    return list(noeud["properties"])


# Mots-clés d'application conditionnelle : leurs sous-schémas ne décrivent pas un
# objet du verdict, ils contraignent les champs déjà décrits.
_CONDITIONNELS = ("allOf", "anyOf", "oneOf", "not", "if", "then", "else")

# Mots-clés que _conforme sait évaluer. Un autre mot-clé dans le schéma serait
# IGNORÉ par _conforme : le banc le refuse (test_schema_json_egal_constantes).
_MOTS_CLES = {"$schema", "$id", "title", "description", "type", "additionalProperties", "required",
              "properties", "items", "enum", "const", "minimum", "maximum", "minItems", "maxItems",
              "allOf", "anyOf", "if", "then", "else"}


def _mots_cles(sch: dict) -> set[str]:
    """Mots-clés employés par un schéma, sous-schémas compris."""
    vus = set(sch)
    for sous in sch.get("properties", {}).values():
        vus |= _mots_cles(sous)
    for cle in ("items", "if", "then", "else"):
        if isinstance(sch.get(cle), dict):
            vus |= _mots_cles(sch[cle])
    for cle in ("allOf", "anyOf"):
        for sous in sch.get(cle, []):
            vus |= _mots_cles(sous)
    return vus


def _objets_schema(noeud: object, ou: str = "$") -> list[tuple[str, dict]]:
    """Nœuds objet STRUCTURELS du schéma (récursion sur le document JSON, pas sur le disque)."""
    trouves: list[tuple[str, dict]] = []
    if isinstance(noeud, dict):
        if "properties" in noeud:
            trouves.append((ou, noeud))
        for cle, valeur in noeud.items():
            if cle not in _CONDITIONNELS:
                trouves.extend(_objets_schema(valeur, f"{ou}.{cle}"))
    elif isinstance(noeud, list):
        for i, valeur in enumerate(noeud):
            trouves.extend(_objets_schema(valeur, f"{ou}[{i}]"))
    return trouves


_TYPES = {
    "string": lambda x: isinstance(x, str),
    "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
    "null": lambda x: x is None,
    "object": lambda x: isinstance(x, dict),
    "array": lambda x: isinstance(x, list),
    "boolean": lambda x: isinstance(x, bool),
}


def _conforme(inst: object, sch: dict, ou: str = "$") -> list[str]:
    """Sous-ensemble draft 2020-12 utilisé par le schéma (stdlib : pas de jsonschema).

    Couvre exactement _MOTS_CLES ; le banc refuse un schéma qui en emploie un autre.
    """
    err: list[str] = []
    if "const" in sch and not (type(inst) is type(sch["const"]) and inst == sch["const"]):
        err.append(f"{ou}: const")
    if "enum" in sch and not any(type(inst) is type(e) and inst == e for e in sch["enum"]):
        err.append(f"{ou}: enum {inst!r}")
    if "type" in sch:
        types = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_TYPES[t](inst) for t in types):
            err.append(f"{ou}: type")
    if _TYPES["integer"](inst):
        if "minimum" in sch and inst < sch["minimum"]:
            err.append(f"{ou}: minimum")
        if "maximum" in sch and inst > sch["maximum"]:
            err.append(f"{ou}: maximum")
    if isinstance(inst, dict):
        err.extend(f"{ou}: requis {k}" for k in sch.get("required", []) if k not in inst)
        if "properties" in sch:
            if sch.get("additionalProperties") is False:
                err.extend(f"{ou}: clé inconnue {k}" for k in inst if k not in sch["properties"])
            for cle, valeur in inst.items():
                if cle in sch["properties"]:
                    err.extend(_conforme(valeur, sch["properties"][cle], f"{ou}.{cle}"))
    if isinstance(inst, list):
        if "minItems" in sch and len(inst) < sch["minItems"]:
            err.append(f"{ou}: minItems")
        if "maxItems" in sch and len(inst) > sch["maxItems"]:
            err.append(f"{ou}: maxItems")
        if "items" in sch:
            for i, valeur in enumerate(inst):
                err.extend(_conforme(valeur, sch["items"], f"{ou}[{i}]"))
    for sous in sch.get("allOf", []):
        err.extend(_conforme(inst, sous, ou))
    if "anyOf" in sch and all(_conforme(inst, sous, ou) for sous in sch["anyOf"]):
        err.append(f"{ou}: anyOf")
    if "if" in sch:
        branche = sch.get("else") if _conforme(inst, sch["if"], ou) else sch.get("then")
        if branche is not None:
            err.extend(_conforme(inst, branche, ou))
    return err


def _chaines(valeur: object) -> list[str]:
    if isinstance(valeur, str):
        return [valeur]
    if isinstance(valeur, dict):
        return [s for k, v in valeur.items() for s in (_chaines(k) + _chaines(v))]
    if isinstance(valeur, list):
        return [s for v in valeur for s in _chaines(v)]
    return []


class Contrat(_Base):
    def test_version_epinglee(self) -> None:
        self.assertEqual(sv.SCHEMA, "cadre.scan-verdict/1")
        for verdict in self.batterie():
            self.assertEqual(verdict["schema"], "cadre.scan-verdict/1")
        schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema"]["const"], "cadre.scan-verdict/1")
        autre = copy.deepcopy(self.semgrep(SEMGREPIGNORE_SEUL))
        autre["schema"] = "cadre.scan-verdict/2"
        self.assertTrue(any("majeur inconnu" in e for e in sv.validate(autre)))

    def test_cle_inconnue_refusee(self) -> None:
        clean = self.semgrep(SEMGREPIGNORE_SEUL)
        avec_tout = self.semgrep({**A5, "results": REL["results"],
                                  "errors": E4["errors"] + BAD2["errors"]})
        lieux = {
            "verdict": lambda v: v,
            "tool": lambda v: v["tool"],
            "findings[0]": lambda v: v["findings"][0],
            "tool_errors[0]": lambda v: v["tool_errors"][0],
            "coverage": lambda v: v["coverage"],
            "coverage.analysis_incomplete[0]": lambda v: v["coverage"]["analysis_incomplete"][0],
            "coverage.skipped[0]": lambda v: v["coverage"]["skipped"][0],
            "coverage.excluded[0]": lambda v: v["coverage"]["excluded"][0],
        }
        self.assertEqual(sv.validate(clean), [])
        for lieu, acces in lieux.items():
            v = copy.deepcopy(avec_tout)
            acces(v)["message"] = "x"
            erreurs = sv.validate(v)
            self.assertIn(f"{lieu} : clé inconnue 'message'", erreurs, lieu)
        schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        objets = _objets_schema(schema)
        self.assertEqual(len(objets), 8, [ou for ou, _ in objets])
        for ou, noeud in objets:
            self.assertIs(noeud.get("additionalProperties"), False, ou)
            self.assertEqual(noeud.get("type"), "object", ou)
            self.assertEqual(noeud.get("required"), _cles_schema(noeud), ou)

    def test_complete_jamais_true_v1(self) -> None:
        for verdict in self.batterie():
            self.assertIn(verdict["coverage"]["complete"], (False, None))
            self.assertIsNot(verdict["coverage"]["complete"], True)
        self.assertIs(self.semgrep(E4)["coverage"]["complete"], False)
        self.assertIsNone(self.semgrep(SEMGREPIGNORE_SEUL)["coverage"]["complete"])
        v = copy.deepcopy(self.semgrep(SEMGREPIGNORE_SEUL))
        v["coverage"]["complete"] = True
        self.assertTrue(any("true est interdit" in e for e in sv.validate(v)))

    def test_schema_json_egal_constantes(self) -> None:
        s = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        p = s["properties"]
        self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(s["title"], sv.SCHEMA)
        self.assertEqual(p["schema"]["const"], sv.SCHEMA)
        self.assertEqual(_cles_schema(s), list(sv.KEYS_TOP))
        self.assertEqual(_cles_schema(p["tool"]), list(sv.KEYS_TOOL))
        self.assertEqual(_cles_schema(p["findings"]["items"]), list(sv.KEYS_FINDING))
        self.assertEqual(_cles_schema(p["tool_errors"]["items"]), list(sv.KEYS_TOOL_ERROR))
        cov = p["coverage"]
        self.assertEqual(_cles_schema(cov), list(sv.KEYS_COVERAGE))
        self.assertEqual(_cles_schema(cov["properties"]["analysis_incomplete"]["items"]), list(sv.KEYS_INCOMPLETE))
        self.assertEqual(_cles_schema(cov["properties"]["skipped"]["items"]), list(sv.KEYS_SKIP))
        self.assertEqual(_cles_schema(cov["properties"]["excluded"]["items"]), list(sv.KEYS_SKIP))
        self.assertEqual(p["tool"]["properties"]["name"]["enum"], list(sv.TOOL_NAMES))
        self.assertEqual(p["tool"]["properties"]["class"]["enum"], list(sv.CLASSES))
        self.assertEqual(p["status"]["enum"], list(sv.STATUSES))
        self.assertEqual(p["findings"]["items"]["properties"]["severity"]["enum"], list(sv.SEVERITIES))
        self.assertEqual(p["notes"]["items"]["enum"], list(sv.NOTES))
        self.assertEqual(sv.NOTES[sv.NOTES.index("report_unreadable") + 1], "report_too_large")
        self.assertEqual(cov["properties"]["skipped_source"]["enum"], list(sv.SKIPPED_SOURCES))
        self.assertEqual(cov["properties"]["complete"]["enum"], list(sv.COMPLETE_VALUES))
        self.assertEqual(sorted(sv.TOOL_CLASSES), sorted(sv.TOOL_NAMES))
        self.assertEqual(sorted(set(sv.TOOL_CLASSES.values())), sorted(sv.CLASSES))
        classes = {c["if"]["properties"]["name"]["const"]: c["then"]["properties"]["class"]["const"]
                   for c in p["tool"].get("allOf", [])}
        self.assertEqual(classes, sv.TOOL_CLASSES)
        self.assertLessEqual(_mots_cles(s), _MOTS_CLES, "mot-clé que _conforme ignorerait")
        self.assertTrue(set(sv.SEVERITY_TABLE.values()) < set(sv.SEVERITIES))
        # Le schéma ACCEPTE chaque verdict produit, et refuse une clé ajoutée.
        for verdict in self.batterie():
            self.assertEqual(_conforme(verdict, s), [], verdict)
        intrus = copy.deepcopy(self.semgrep(E4))
        intrus["coverage"]["analysis_incomplete"][0]["message"] = "x"
        self.assertTrue(_conforme(intrus, s))

    def _refus(self) -> list[tuple[str, object]]:
        """(message attendu, verdict) : au moins un cas par contrôle de validate."""
        clean = self.semgrep(SEMGREPIGNORE_SEUL)
        trou = self.semgrep(E4)
        trouvaille = self.semgrep(REL)
        erreur_outil = self.semgrep(BAD2)
        propre_gl = self.gitleaks(GITLEAKS_PROPRE, exit_code=0)
        cas: list[tuple[str, object]] = [("verdict : objet attendu", "pas un objet")]

        def refuse(base: dict, retouche, attendu: str) -> None:
            v = copy.deepcopy(base)
            retouche(v)
            cas.append((attendu, v))

        def poser(*chemin_et_valeur):
            *chemin, valeur = chemin_et_valeur

            def faire(v):
                for cle in chemin[:-1]:
                    v = v[cle]
                v[chemin[-1]] = valeur
            return faire

        refuse(clean, lambda v: v.pop("notes"), "clé manquante 'notes'")
        refuse(clean, poser("schema", "cadre.scan-verdict/2"), "majeur inconnu")
        refuse(clean, poser("schema", "autre/1"), "identifiant inconnu")
        refuse(clean, poser("coverage", "complete", True), "true est interdit")
        refuse(trou, poser("coverage", "complete", None), "null alors qu'un trou est connu")
        refuse(clean, poser("tool_errors", [{"type": "x", "level": "error", "rule_id": None}]),
               "clean avec des tool_errors")
        refuse(clean, poser("coverage", "skipped", [{"path": "a", "reason": "b"}]), "clean avec un trou connu")
        refuse(clean, poser("notes", ["known_gap"]), "clean avec des notes")
        refuse(clean, poser("status", "findings"), "si et seulement si")
        refuse(trouvaille, poser("status", "degraded"), "si et seulement si")
        refuse(clean, poser("status", "ok"), "status : valeur hors énumération")
        refuse(clean, poser("tool", "name", "trivy"), "tool.name : valeur hors énumération")
        refuse(clean, poser("tool", "class", "sca"), "tool.class : valeur hors énumération")
        refuse(clean, poser("coverage", "skipped_source", "deviné"), "skipped_source : valeur hors énumération")
        refuse(trouvaille, lambda v: v["findings"][0].update(severity="grave"), "severity : valeur hors énumération")
        refuse(trouvaille, lambda v: v["findings"][0].update(line="1"), "findings[0].line : entier attendu")
        refuse(clean, poser("tool_exit_code", 300), "tool_exit_code : entier attendu")
        refuse(clean, poser("coverage", "candidates", -1), "coverage.candidates : entier attendu")
        refuse(clean, poser("notes", ["note libre"]), "hors catalogue")
        refuse(clean, poser("coverage", "inspected", [3]), "coverage.inspected[0] : chaîne attendue")
        refuse(clean, poser("findings", "x"), "findings : liste attendue")
        refuse(clean, poser("tool", None), "tool : objet attendu")
        # LOW 4 (S-01M4VYXNW9) : cohérence rc/statut ; mineurs exec-critic (S-01M4VZER7Y).
        refuse(clean, poser("tool_exit_code", 2), "clean avec un rc hors table propre")
        refuse(clean, poser("tool_exit_code", 1), "clean avec un rc hors table propre")
        refuse(propre_gl, poser("tool_exit_code", None), "gitleaks clean sans rc")
        refuse(clean, poser("status", "degraded"), "degraded sans note ni trou")
        refuse(clean, poser("tool", "class", "secrets"), "tool.class : 'secrets' n'est pas la classe de 'semgrep'")
        refuse(propre_gl, poser("tool", "class", "sast"), "tool.class : 'sast' n'est pas la classe de 'gitleaks'")
        refuse(erreur_outil, lambda v: v["tool_errors"][0].update(type=None), "tool_errors[0].type : chaîne attendue")
        refuse(erreur_outil, lambda v: v["tool_errors"][0].update(type=3), "tool_errors[0].type : chaîne attendue")
        return cas

    def _acceptes(self) -> list[dict]:
        """Verdicts valides aux frontières des contrôles de cohérence."""
        sans_note = copy.deepcopy(self.semgrep(E4))
        sans_note["notes"] = []  # degraded porté par un trou seul : accepté
        return [*self.batterie(), self.semgrep(SEMGREPIGNORE_SEUL, exit_code=0), sans_note]

    def test_validateur_refuse(self) -> None:
        self.assertEqual(sv.validate("pas un objet"), ["verdict : objet attendu"])
        for attendu, v in self._refus():
            erreurs = sv.validate(v)
            self.assertTrue(any(attendu in e for e in erreurs), (attendu, erreurs))
        for v in self._acceptes():
            self.assertEqual(sv.validate(v), [], v)
        self.assertEqual(sv.validate({**self.semgrep(SEMGREPIGNORE_SEUL), "tool": {"name": [], "version": None,
                                                                             "class": "sast", "config": None}}),
                         ["tool.name : valeur hors énumération []"])

    def test_schema_egal_validate(self) -> None:
        # Mineur exec-critic (S-01M4VZER7Y) : le schéma (if/then compris) refuse chaque
        # cas que validate refuse et accepte chaque verdict qu'il accepte.
        s = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        for attendu, v in self._refus():
            self.assertTrue(_conforme(v, s), attendu)
        for v in self._acceptes():
            self.assertEqual(_conforme(v, s), [], v)

    def test_notes_catalogue_ferme(self) -> None:
        produites = {n for verdict in self.batterie() for n in verdict["notes"]}
        self.assertTrue(produites)
        self.assertLessEqual(produites, set(sv.NOTES))
        for libre in ("note libre", "report_absent ", 7):
            v = copy.deepcopy(self.semgrep(E4))
            v["notes"] = ["known_gap", libre]
            self.assertTrue(any("hors catalogue" in e for e in sv.validate(v)), libre)


class Semgrep(_Base):
    def test_erreur_a_chemin_est_un_trou(self) -> None:
        v = self.semgrep(E4, exit_code=0)
        self.assertEqual(v["status"], "degraded")
        self.assertEqual(v["coverage"]["analysis_incomplete"], [{"path": "heavy.py", "type": "Timeout"}])
        self.assertEqual(v["coverage"]["inspected"], ["small.py"])
        self.assertEqual(v["tool_errors"], [])
        self.assertIs(v["coverage"]["complete"], False)
        self.assertEqual(v["notes"], ["known_gap"])

    def test_partialparsing_chemin_au_sommet(self) -> None:
        # SYNTHÉTIQUE : le chemin est au sommet de l'erreur, la liste imbriquée n'en porte pas.
        erreur = {"code": 3, "level": "warn", "type": ["PartialParsing", [{"start": {"line": 2}}]],
                  "path": "partial.sh", "message": "Syntax error"}
        v = self.semgrep(_semgrep_avec_erreurs([erreur], ["partial.sh", "ok.sh"]))
        self.assertEqual(v["coverage"]["analysis_incomplete"], [{"path": "partial.sh", "type": "PartialParsing"}])
        self.assertEqual(v["coverage"]["inspected"], ["ok.sh"])
        self.assertEqual(v["tool_errors"], [])

    def test_partialparsing_chemin_imbrique(self) -> None:
        # SYNTHÉTIQUE, forme mesurée (plan-critic it.2, a_sans_path_sommet) : chemin
        # SEULEMENT dans type[1][].path ; type = premier élément de la liste (réserve C4).
        erreur = {"code": 3, "level": "warn",
                  "type": ["PartialParsing", [{"path": "partial.sh", "start": {"line": 2, "col": 6, "offset": 0},
                                               "end": {"line": 2, "col": 17, "offset": 11}}]],
                  "message": "Syntax error at line partial.sh:2"}
        v = self.semgrep(_semgrep_avec_erreurs([erreur], ["partial.sh", "ok.sh"]))
        self.assertEqual(v["coverage"]["analysis_incomplete"], [{"path": "partial.sh", "type": "PartialParsing"}])
        self.assertEqual(v["coverage"]["inspected"], ["ok.sh"])
        self.assertEqual(v["tool_errors"], [])

    def test_un_chemin_une_place(self) -> None:
        # SYNTHÉTIQUE : a.py sauté ET en erreur, b.py en erreur, d.py exclu ET en erreur,
        # c.py propre, e.py exclu seul, f.py candidat non rapporté (sans clé skipped).
        data = {"version": "1.175.0", "results": [],
                "errors": [{"type": "Timeout", "level": "warn", "path": p} for p in ("a.py", "b.py", "d.py")],
                "paths": {"scanned": ["a.py", "b.py", "c.py", "d.py"],
                          "skipped": [{"path": "a.py", "reason": "exceeded_size_limit"},
                                      {"path": "d.py", "reason": "semgrepignore_patterns_match"},
                                      {"path": "e.py", "reason": "semgrepignore_patterns_match"}]},
                "skipped_rules": []}
        c = self.semgrep(data)["coverage"]
        places = {
            "inspected": c["inspected"],
            "analysis_incomplete": [x["path"] for x in c["analysis_incomplete"]],
            "skipped": [x["path"] for x in c["skipped"]],
            "excluded": [x["path"] for x in c["excluded"]],
            "not_reported": c["not_reported"],
        }
        self.assertEqual(places, {"inspected": ["c.py"], "analysis_incomplete": ["b.py", "d.py"],
                                  "skipped": ["a.py"], "excluded": ["e.py"], "not_reported": []})
        tous = [p for liste in places.values() for p in liste]
        self.assertEqual(len(tous), len(set(tous)))
        sans_cle = copy.deepcopy(data)
        del sans_cle["paths"]["skipped"]
        c = self.semgrep(sans_cle, candidates=["a.py", "b.py", "c.py", "d.py", "f.py"])["coverage"]
        self.assertEqual(c["not_reported"], ["f.py"])
        self.assertEqual(c["inspected"], ["c.py"])

    def test_saute_taille_degrade(self) -> None:
        v = self.semgrep(A5, exit_code=0)
        self.assertEqual(v["status"], "degraded")
        self.assertEqual(v["coverage"]["skipped"], [{"path": "big.py", "reason": "exceeded_size_limit"}])
        self.assertEqual(v["coverage"]["excluded"], [{"path": "ignored.py", "reason": "semgrepignore_patterns_match"}])
        self.assertEqual(v["coverage"]["skipped_source"], "paths.skipped")
        self.assertIs(v["coverage"]["complete"], False)
        self.assertEqual(v["notes"], ["known_gap"])

    def test_raison_inconnue_fail_closed(self) -> None:
        v = self.semgrep(RAISON_INCONNUE, exit_code=0)
        self.assertEqual(v["status"], "degraded")
        self.assertEqual(v["coverage"]["skipped"], [{"path": "small.py", "reason": "zz_raison_future"}])
        self.assertEqual([x["path"] for x in v["coverage"]["excluded"]], ["ignored.py"])
        self.assertIs(v["coverage"]["complete"], False)

    def test_semgrepignore_exclu_clean(self) -> None:
        v = self.semgrep(SEMGREPIGNORE_SEUL, exit_code=0)
        self.assertEqual(v["status"], "clean")
        self.assertEqual([x["path"] for x in v["coverage"]["excluded"]], ["ignored.py", "rules-local.yml"])
        self.assertEqual(v["coverage"]["skipped"], [])
        self.assertIsNone(v["coverage"]["complete"])
        self.assertEqual(v["notes"], [])

    def test_complement_est_une_borne(self) -> None:
        v = self.semgrep(SANS_VERBOSE, exit_code=0, candidates=["small.py", "notes.txt", "notes.txt"])
        self.assertEqual(v["status"], "clean")
        self.assertEqual(v["coverage"]["skipped_source"], "complement")
        self.assertEqual(v["coverage"]["not_reported"], ["notes.txt"])
        self.assertEqual(v["coverage"]["candidates"], 2)
        self.assertIsNone(v["coverage"]["complete"])
        sans = self.semgrep(SANS_VERBOSE)
        self.assertEqual(sans["coverage"]["skipped_source"], "unknown")
        self.assertIsNone(sans["coverage"]["candidates"])

    def test_rien_de_scanne_degrade(self) -> None:
        # Constat M1 (S-01M4VYXNW9). SYNTHÉTIQUE, forme mesurée SANS_VERBOSE : candidats
        # fournis, `paths.scanned` absent ou vide, un candidat dans aucune case -> jamais clean.
        sans_paths = {k: v for k, v in SANS_VERBOSE.items() if k != "paths"}
        for data in (sans_paths, {**SANS_VERBOSE, "paths": {}}, {**SANS_VERBOSE, "paths": {"scanned": []}}):
            v = self.semgrep(data, exit_code=0, candidates=["small.py", "notes.txt"])
            self.assertEqual((v["status"], v["notes"]), ("degraded", ["scanned_empty"]), data)
            self.assertEqual(v["coverage"]["skipped_source"], "complement")
            self.assertEqual(v["coverage"]["not_reported"], ["notes.txt", "small.py"])
            self.assertIsNone(v["coverage"]["complete"])
        # Même faux clean en mode paths.skipped : `not_reported` y est vide par construction.
        v = self.semgrep({**SANS_VERBOSE, "paths": {"scanned": [], "skipped": []}}, exit_code=0,
                         candidates=["small.py"])
        self.assertEqual((v["status"], v["notes"]), ("degraded", ["scanned_empty"]))
        # Non-déclencheurs : sans candidats ; tout candidat exclu par politique ; un fichier scanné.
        self.assertEqual(self.semgrep({**SANS_VERBOSE, "paths": {"scanned": []}}, exit_code=0)["status"], "clean")
        exclu = {"scanned": [], "skipped": [{"path": "small.py", "reason": "semgrepignore_patterns_match"}]}
        self.assertEqual(self.semgrep({**SANS_VERBOSE, "paths": exclu}, exit_code=0,
                                      candidates=["small.py"])["status"], "clean")
        self.assertEqual(self.semgrep(SANS_VERBOSE, exit_code=0, candidates=["small.py", "notes.txt"])["status"],
                         "clean")

    def test_erreur_sans_chemin_degrade(self) -> None:
        v = self.semgrep(BAD2)
        self.assertEqual(v["status"], "degraded")
        self.assertEqual(v["tool_errors"], [{"type": "Rule parse error", "level": "error", "rule_id": "bad-re"}])
        self.assertEqual(v["notes"], ["tool_errors"])
        self.assertIsNone(v["tool_exit_code"])
        self.assertEqual(v["coverage"]["inspected"], ["clean1.py"])
        warn = self.semgrep(_semgrep_avec_erreurs([{"type": "Timeout", "level": "warn", "rule_id": "r"}], ["a.py"]))
        self.assertEqual(warn["status"], "degraded")

    def test_skipped_rules_degrade(self) -> None:
        # SYNTHÉTIQUE : rapport propre mesuré + une règle sautée.
        data = {**SEMGREPIGNORE_SEUL, "skipped_rules": [{"rule_id": "r", "details": "x", "position": {}}]}
        v = self.semgrep(data, exit_code=0)
        self.assertEqual(v["status"], "degraded")
        self.assertEqual(v["notes"], ["skipped_rules"])

    def test_rc2_sans_finding_degrade(self) -> None:
        # SYNTHÉTIQUE (réserve C1) : rapport PROPRE mesuré + rc 2 — le rc est la seule cause.
        self.assertEqual(self.semgrep(SEMGREPIGNORE_SEUL, exit_code=0)["status"], "clean")
        v = self.semgrep(SEMGREPIGNORE_SEUL, exit_code=2)
        self.assertEqual(v["status"], "degraded")
        self.assertEqual(v["notes"], ["exit_code_out_of_table"])
        self.assertEqual(v["tool_exit_code"], 2)
        v = self.semgrep(SEMGREPIGNORE_SEUL, findings_rc=1, exit_code=1)
        self.assertEqual((v["status"], v["notes"]), ("degraded", ["exit_code_findings_without_findings"]))
        v = self.semgrep(SEMGREPIGNORE_SEUL, findings_rc=1, exit_code=5)
        self.assertEqual((v["status"], v["notes"]), ("degraded", ["exit_code_out_of_table"]))

    def test_rc2_et_finding_rend_findings(self) -> None:
        v = self.semgrep(REL, exit_code=2)
        self.assertEqual(v["status"], "findings")
        self.assertEqual(v["notes"], ["exit_code_disagrees_with_report"])
        self.assertEqual(self.semgrep(REL, findings_rc=1, exit_code=1)["notes"], [])
        self.assertEqual(self.semgrep(REL, exit_code=0)["notes"], [])
        # findings > 0 l'emporte sur tout ; les autres faits restent écrits.
        tout = self.semgrep({**A5, "results": REL["results"], "errors": BAD2["errors"]}, exit_code=2)
        self.assertEqual(tout["status"], "findings")
        self.assertEqual(tout["notes"], ["tool_errors", "known_gap", "exit_code_disagrees_with_report"])
        self.assertIs(tout["coverage"]["complete"], False)

    def test_prefixe_config_retire(self) -> None:
        # Réserve C2. Forme MESURÉE (semgrep 1.175.0, 2026-10-14, ce dev) : config
        # absolue hors de l'ascendance du cwd -> check_id préfixé des dossiers absolus
        # pointés (m3) ; absolue SOUS le cwd -> préfixe relatif (m4) ; relative -> préfixe
        # relatif (m5). Chemins ci-dessous SYNTHÉTIQUES (aucun chemin machine).
        def avec(check_id: str) -> dict:
            return {**REL, "results": [{**REL["results"][0], "check_id": check_id}]}
        cas = [
            ("regles/sous/rules.yml", "regles.sous.py-eval"),
            ("rules.yml", "py-eval"),
            ("../regles/sous/rules.yml", "regles.sous.py-eval"),
        ]
        if os.name != "nt":
            cas += [("/opt/kit/regles/sous/rules.yml", "opt.kit.regles.sous.py-eval"),
                    ("/opt/kit/regles/sous/rules.yml", "regles.sous.py-eval"),
                    ("/home/user/.agents/security/semgrep.yml", "agents.security.py-eval")]
        for config, check_id in cas:
            v = self.semgrep(avec(check_id), config=config)
            self.assertEqual(v["findings"][0]["rule"], "py-eval", (config, check_id))
            # S1, étape 2 : une config absolue n'entre au verdict que par son nom.
            self.assertEqual(v["tool"]["config"], config.rsplit("/", 1)[-1] if config.startswith("/") else config)
        self.assertEqual(self.semgrep(avec("regles.sous.py-eval"))["findings"][0]["rule"], "regles.sous.py-eval")
        self.assertEqual(self.semgrep(avec("autre.py-eval"), config="regles/sous/rules.yml")["findings"][0]["rule"],
                         "autre.py-eval")
        erreur = {**BAD2["errors"][0], "rule_id": "regles.bad-re"}
        v = self.semgrep(_semgrep_avec_erreurs([erreur], ["a.py"]), config="regles/rules.yml")
        self.assertEqual(v["tool_errors"][0]["rule_id"], "bad-re")
        # Mutant O2 (exec-critic) : un id ÉGAL au préfixe n'est jamais réduit à rien.
        v = self.semgrep(avec("regles.sous."), config="regles/sous/rules.yml")
        self.assertEqual(v["findings"][0]["rule"], "regles.sous.")
        erreur = {**BAD2["errors"][0], "rule_id": "regles."}
        v = self.semgrep(_semgrep_avec_erreurs([erreur], ["a.py"]), config="regles/rules.yml")
        self.assertEqual(v["tool_errors"][0]["rule_id"], "regles.")

    def test_config_absolue_reduite_au_nom(self) -> None:
        # S1, étape 2 : une config ABSOLUE n'entre au verdict que par son NOM, sous les formes
        # POSIX, lecteur et UNC quel que soit l'hôte ; le retrait du préfixe lit, lui, le chemin
        # ENTIER. Chemins SYNTHÉTIQUES.
        formes = [("/opt/kit/r/rules.yml", "rules.yml"), (r"C:\kit\rules.yml", "rules.yml"),
                  ("C:/kit/rules.yml", "rules.yml"), (r"\\srv\r\rules.yml", "rules.yml"),
                  ("//srv/r/rules.yml", "rules.yml"), ("rules.yml", "rules.yml"), ("p/default", "p/default"),
                  ("../regles/rules.yml", "../regles/rules.yml"), ("co\x85nf.yml", "conf.yml"), (None, None)]
        for config, attendu in formes:
            self.assertEqual(self.semgrep(REL, config=config)["tool"]["config"], attendu, config)
        if os.name != "nt":  # préfixe d'une config absolue POSIX : forme mesurée sur hôte POSIX (m3)
            v = self.semgrep({**REL, "results": [{**REL["results"][0], "check_id": "opt.kit.r.py-eval"}]},
                             config="/opt/kit/r/rules.yml")
            self.assertEqual((v["tool"]["config"], v["findings"][0]["rule"]), ("rules.yml", "py-eval"))
        rc, out, err = self.cli("semgrep", "--report", self.rapport(REL), "--findings-exit-code", "none",
                                "--config", "/Users/someone/rules/semgrep.yml")  # CA5
        self.assertEqual((rc, json.loads(out)["tool"]["config"] if rc == 0 else err), (0, "semgrep.yml"))

    def test_skipped_vide_est_rapporte(self) -> None:
        # SYNTHÉTIQUE (mutant O3 d'exec-critic) : `skipped: []` PRÉSENT = semgrep a rapporté
        # ses sauts (aucun) ; la source reste paths.skipped, aucun complément n'est calculé.
        data = {**SANS_VERBOSE, "paths": {"scanned": ["small.py"], "skipped": []}}
        v = self.semgrep(data, exit_code=0, candidates=["small.py", "notes.txt"])
        self.assertEqual(v["coverage"]["skipped_source"], "paths.skipped")
        self.assertEqual(v["coverage"]["not_reported"], [])
        self.assertEqual(v["status"], "clean")

    def test_antislash_normalise(self) -> None:
        # SYNTHÉTIQUE (mutant O1 d'exec-critic) : un chemin Windows prend '/' partout,
        # candidats compris, pour que les cases et le complément se recoupent.
        data = {"version": "1.175.0", "results": [{**REL["results"][0], "path": "t\\small.py"}],
                "errors": [{"type": "Timeout", "level": "warn", "path": "t\\lent.py"}],
                "paths": {"scanned": ["t\\small.py", "t\\lent.py"],
                          "skipped": [{"path": "t\\gros.py", "reason": "exceeded_size_limit"}]},
                "skipped_rules": []}
        v = self.semgrep(data, candidates=["t\\small.py", "t/lent.py", "t\\gros.py"])
        self.assertEqual(v["findings"][0]["path"], "t/small.py")
        self.assertEqual(v["coverage"]["inspected"], ["t/small.py"])
        self.assertEqual(v["coverage"]["analysis_incomplete"], [{"path": "t/lent.py", "type": "Timeout"}])
        self.assertEqual(v["coverage"]["skipped"], [{"path": "t/gros.py", "reason": "exceeded_size_limit"}])
        self.assertEqual(v["coverage"]["candidates"], 3)
        v = self.semgrep({**data, "errors": [], "paths": {"scanned": ["t\\small.py"]}},
                         candidates=["t/small.py", "t\\autre.py"])
        self.assertEqual(v["coverage"]["not_reported"], ["t/autre.py"])
        g = self.gitleaks([{"RuleID": "r", "File": "gl\\app.py", "StartLine": 1}], exit_code=1)
        self.assertEqual(g["findings"][0]["path"], "gl/app.py")

    def test_table_severites(self) -> None:
        attendu = {"CRITICAL": "critical", "ERROR": "high", "HIGH": "high", "WARNING": "medium",
                   "MEDIUM": "medium", "INFO": "low", "LOW": "low", "EXPERIMENTAL": "unknown",
                   "error": "unknown", "": "unknown"}
        for native, commune in attendu.items():
            data = {**REL, "results": [{**REL["results"][0], "extra": {"severity": native}}]}
            f = self.semgrep(data)["findings"][0]
            self.assertEqual((f["severity"], f["tool_severity"]), (commune, native), native)
        sans = self.semgrep({**REL, "results": [{"check_id": "r", "path": "a.py"}]})["findings"][0]
        self.assertEqual((sans["severity"], sans["tool_severity"], sans["line"]), ("unknown", None, None))
        self.assertEqual(self.gitleaks(GITLEAKS_ROUGE)["findings"][0]["severity"], "critical")


class Gitleaks(_Base):
    def test_gitleaks_exit_code_7(self) -> None:
        v = self.gitleaks(GITLEAKS_ROUGE, findings_rc=7, exit_code=7, version="8.30.1")
        self.assertEqual(v["status"], "findings")
        self.assertEqual(v["notes"], [])
        self.assertEqual(v["findings"], [{"rule": "github-pat", "path": "gl/app.py", "line": 1,
                                          "severity": "critical", "tool_severity": None}])
        self.assertEqual(v["tool"], {"name": "gitleaks", "version": "8.30.1", "class": "secrets", "config": None})
        self.assertEqual(self.gitleaks(GITLEAKS_ROUGE, findings_rc=7, exit_code=1)["notes"],
                         ["exit_code_disagrees_with_report"])
        self.assertEqual(self.gitleaks(GITLEAKS_ROUGE, findings_rc=1, exit_code=1)["notes"], [])
        sans = self.gitleaks(GITLEAKS_PROPRE, findings_rc=7, exit_code=7)
        self.assertEqual((sans["status"], sans["notes"]), ("degraded", ["exit_code_findings_without_findings"]))

    def test_rapport_propre_clean(self) -> None:
        v = self.gitleaks(GITLEAKS_PROPRE, findings_rc=7, exit_code=0)
        self.assertEqual((v["status"], v["notes"], v["findings"]), ("clean", [], []))
        self.assertEqual(v["coverage"]["skipped_source"], "unknown")
        self.assertIsNone(v["coverage"]["complete"])
        # Constat M3 (S-01M4VYXNW9) : sans rc, `[]` ne conclut pas clean (API et CLI).
        v = self.gitleaks(GITLEAKS_PROPRE, findings_rc=7)
        self.assertEqual((v["status"], v["notes"], v["findings"]), ("degraded", ["exit_code_absent"], []))
        rc, out, _ = self.cli("gitleaks", "--report", self.rapport(GITLEAKS_PROPRE), "--findings-exit-code", "7")
        sortie = json.loads(out)
        self.assertEqual((rc, sortie["status"], sortie["notes"]), (0, "degraded", ["exit_code_absent"]))
        # Avec findings, le statut reste findings et la note n'est pas posée.
        self.assertEqual(self.gitleaks(GITLEAKS_ROUGE, findings_rc=7)["notes"], [])

    def test_findings_rc_requis(self) -> None:
        # Réserve C3, côté API : gitleaks exige un rc de findings entier.
        chemin = self.rapport(GITLEAKS_PROPRE)
        for mauvais in (None, True, -1, 256, "7"):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                sv.from_gitleaks(chemin, findings_rc=mauvais)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            sv.from_semgrep(chemin, findings_rc=None, exit_code=False)  # type: ignore[arg-type]


class Transverse(_Base):
    def test_rapport_absent_vide_illisible_degrade(self) -> None:
        cas = [
            ("semgrep", None, "report_absent"),
            ("semgrep", b"", "report_empty"),
            ("semgrep", " \n\t", "report_empty"),
            ("semgrep", "{pas du json", "report_unreadable"),
            ("semgrep", "[]", "report_unreadable"),
            ("semgrep", json.dumps({"results": "x"}), "report_unreadable"),
            ("semgrep", json.dumps({"results": [], "paths": {"skipped": [{"path": "a"}]}}), "report_unreadable"),
            ("semgrep", b"\xff\xfe{}", "report_unreadable"),
            ("semgrep", "[" * 100000, "report_unreadable"),
            ("gitleaks", None, "report_absent"),
            ("gitleaks", b"", "report_empty"),
            ("gitleaks", "\n", "report_empty"),
            ("gitleaks", "{}", "report_unreadable"),
            ("gitleaks", "[1]", "report_unreadable"),
            ("gitleaks", "nope", "report_unreadable"),
        ]
        for outil, contenu, note in cas:
            rapport = self.dossier / "absent.json" if contenu is None else self.rapport(contenu)
            sortie = self.dossier / "verdict.json"
            rc, _, err = self.cli(outil, "--report", rapport, "--findings-exit-code", "7", "--out", sortie)
            self.assertEqual(rc, 0, (outil, contenu, err))
            v = json.loads(sortie.read_text(encoding="utf-8"))
            self.assertEqual(sv.validate(v), [])
            self.assertEqual((v["status"], v["notes"]), ("degraded", [note]), (outil, contenu))
            self.assertEqual(v["findings"], [])
        dossier = self.dossier / "un-dossier"
        dossier.mkdir()
        self.assertEqual(sv.from_gitleaks(dossier, findings_rc=1)["notes"], ["report_unreadable"])

    def test_report_trop_gros_degrade(self) -> None:
        # S1, étape 1 : borne ramenée à 64 octets. Rapports VALIDES complétés par des blancs :
        # sans la borne, 65 octets rendraient clean, jamais report_too_large ; 64 sont lus.
        semgrep = '{"results": [], "paths": {"scanned": ["a.py"]}}'
        with mock.patch.object(sv, "MAX_REPORT_BYTES", 64):
            for taille, attendu in ((64, ("clean", [])), (65, ("degraded", ["report_too_large"]))):
                v = self.semgrep(semgrep.encode("utf-8").ljust(taille, b" "), exit_code=0)
                self.assertEqual((v["status"], v["notes"]), attendu, ("semgrep", taille))
                g = self.gitleaks(b"[]".ljust(taille, b" "), exit_code=0)
                self.assertEqual((g["status"], g["notes"]), attendu, ("gitleaks", taille))
            # Un stat qui ment (taille 0, comme /dev/zero) ne lève pas la borne : la lecture la tient.
            rapport = self.rapport(semgrep.encode("utf-8").ljust(65, b" "))
            vrai = os.stat(rapport)
            faux = os.stat_result((*vrai[:6], 0, *vrai[7:10]))
            with mock.patch.object(sv.os, "stat", return_value=faux), \
                    mock.patch.object(sv.os, "fstat", return_value=faux), \
                    mock.patch.object(sv.Path, "stat", return_value=faux):
                v = sv.from_semgrep(rapport, findings_rc=None, exit_code=0)
            self.assertEqual((v["status"], v["notes"]), ("degraded", ["report_too_large"]))

    @unittest.skipUnless(Path("/dev/zero").exists(), "/dev/zero absent : flux sans taille non sondé")
    def test_report_dev_zero_borne(self) -> None:
        # CA4 : /dev/zero déclare une taille 0 et ne finit jamais ; la borne réelle rend
        # report_too_large par la CLI. Sous-processus et timeout COURT : une lecture non bornée
        # pendrait (et gonflerait la mémoire) au lieu de rougir ; le chemin borné prend ~0,05 s.
        for outil, rc_trouve in (("semgrep", "none"), ("gitleaks", "1")):
            r = subprocess.run([sys.executable, str(ICI / "scan_verdict.py"), outil, "--report", "/dev/zero",
                                "--findings-exit-code", rc_trouve], capture_output=True, text=True,
                               timeout=20, check=False)
            self.assertEqual(r.returncode, 0, r.stderr)
            v = json.loads(r.stdout)
            self.assertEqual(sv.validate(v), [])
            self.assertEqual((v["status"], v["notes"]), ("degraded", ["report_too_large"]), outil)

    def test_anti_fuite(self) -> None:
        # SYNTHÉTIQUE, formes mesurées (semgrep a_sans_path_sommet + rel ; gitleaks 8.30.1,
        # clés relevées + `Line` des versions antérieures) : le canari dans CHAQUE champ
        # hors liste blanche.
        semgrep = {
            "version": "1.175.0", "canari": CANARI,
            "results": [{"check_id": "py-eval", "path": "a.py", "start": {"line": 1, "col": 1, "offset": 0},
                         "end": {"line": 1, "col": 9, "offset": 8, "canari": CANARI},
                         "extra": {"message": CANARI, "lines": CANARI, "metavars": {"$X": {"abstract_content": CANARI}},
                                   "fix": CANARI, "metadata": {"canari": CANARI}, "severity": "ERROR",
                                   "fingerprint": CANARI, "dataflow_trace": CANARI}}],
            "errors": [{"code": 3, "level": "warn", "message": CANARI, "spans": [{"file": CANARI}],
                        "type": ["PartialParsing", [{"path": "p.sh", "canari": CANARI}]]},
                       {"code": 2, "level": "error", "type": "Rule parse error", "rule_id": "r",
                        "message": CANARI, "details": CANARI}],
            "paths": {"scanned": ["a.py", "p.sh"], "skipped": [], "canari": CANARI},
            "skipped_rules": [], "interfile_languages_used": [CANARI], "time": {"canari": CANARI},
        }
        v = self.semgrep(semgrep, exit_code=1)
        self.assertNotIn(CANARI, json.dumps(v))
        self.assertEqual(len(v["findings"]), 1)
        self.assertEqual(len(v["tool_errors"]), 1)
        champs = ("Description", "Match", "Secret", "Line", "Email", "Author", "Message",
                  "Commit", "Fingerprint", "Date", "SymlinkFile", "Link")
        gitleaks = [{**GITLEAKS_ROUGE[0], **{c: CANARI for c in champs}, "Tags": [CANARI], "Entropy": CANARI}]
        v = self.gitleaks(gitleaks, findings_rc=1, exit_code=1)
        self.assertNotIn(CANARI, json.dumps(v))
        self.assertEqual(len(v["findings"]), 1)

    def test_controle_c0_del_c1(self) -> None:
        data = {
            "version": "1.\x00175",
            "results": [{"check_id": "r\x00g\x1fl\x7fe\x85", "path": "a\x01b\x9f.py", "start": {"line": 3},
                         "extra": {"severity": "ERR\x7fOR"}}],
            "errors": [{"type": "Time\x00out", "level": "wa\x9brn", "rule_id": "id\x7f"},
                       {"type": ["Partial\x85Parsing", [{"path": "p\x1b[31m.sh"}]], "level": "warn"}],
            "paths": {"scanned": ["a\x01b\x9f.py", "c\x7f.py"], "skipped": [{"path": "d\x85.py", "reason": "too\x07_big"}]},
        }
        v = self.semgrep(data, config="co\x85nf.yml")
        self.assertEqual(v["findings"][0], {"rule": "rgle", "path": "ab.py", "line": 3, "severity": "high",
                                            "tool_severity": "ERROR"})
        self.assertEqual(v["tool_errors"], [{"type": "Timeout", "level": "warn", "rule_id": "id"}])
        self.assertEqual(v["coverage"]["analysis_incomplete"], [{"path": "p[31m.sh", "type": "PartialParsing"}])
        self.assertEqual(v["coverage"]["skipped"], [{"path": "d.py", "reason": "too_big"}])
        self.assertEqual(v["coverage"]["inspected"], ["ab.py", "c.py"])
        self.assertEqual((v["tool"]["version"], v["tool"]["config"]), ("1.175", "conf.yml"))
        g = self.gitleaks([{"RuleID": "gen\x85eric", "File": "x\x7f.env", "StartLine": 2}], version="8.\x9b30")
        for verdict in (v, g):
            for chaine in _chaines(verdict):
                self.assertIsNone(CONTROLE.search(chaine), repr(chaine))
        self.assertEqual((g["findings"][0]["rule"], g["findings"][0]["path"], g["tool"]["version"]),
                         ("generic", "x.env", "8.30"))

    def test_cli_rc(self) -> None:
        trouvaille = self.rapport(REL)
        rc, out, _ = self.cli("semgrep", "--report", trouvaille, "--findings-exit-code", "1", "--exit-code", "1")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["status"], "findings")
        rc, out, _ = self.cli("gitleaks", "--report", self.rapport(GITLEAKS_ROUGE), "--findings-exit-code", "7",
                              "--exit-code", "7", "--tool-version", "8.30.1")
        self.assertEqual((rc, json.loads(out)["status"]), (0, "findings"))
        bon = self.dossier / "bon.json"
        bon.write_text(out, encoding="utf-8")
        self.assertEqual(self.cli("validate", bon)[:2], (0, "ok\n"))
        mauvais = self.dossier / "mauvais.json"
        mauvais.write_text(out.replace('"findings"', '"degraded"', 1), encoding="utf-8")
        self.assertEqual(self.cli("validate", mauvais)[0], 1)
        illisible = self.rapport("{")
        self.assertEqual(self.cli("validate", illisible)[0], 1)
        usage = [
            ("validate", self.dossier / "absent.json"),
            ("inconnu",),
            ("gitleaks", "--report", trouvaille, "--findings-exit-code", "none"),
            ("semgrep", "--report", trouvaille, "--findings-exit-code", "none", "--tool-version", "1"),
            ("gitleaks", "--report", trouvaille, "--findings-exit-code", "1", "--config", "r.yml"),
            ("gitleaks", "--report", trouvaille, "--findings-exit-code", "1", "--candidates", "c.txt"),
            ("semgrep", "--report", trouvaille, "--findings-exit-code", "1", "--exit-code", "300"),
            ("semgrep", "--report", trouvaille, "--findings-exit-code", "abc"),
            ("semgrep", "--report", trouvaille, "--findings-exit-code", "1", "--exit-code", "none"),
            ("semgrep", "--findings-exit-code", "1"),
            ("semgrep", "--report", trouvaille, "--findings-exit-code", "none", "--candidates",
             self.dossier / "absent.txt"),
            ("semgrep", "--report", trouvaille, "--findings-exit-code", "none", "--out",
             self.dossier / "pas-de-dossier" / "v.json"),
        ]
        for argv in usage:
            self.assertEqual(self.cli(*argv)[0], 2, argv)
        candidats = self.dossier / "cand.txt"
        candidats.write_text("t/small.py\r\nautre.py\n\n", encoding="utf-8")
        rc, out, _ = self.cli("semgrep", "--report", trouvaille, "--findings-exit-code", "none",
                              "--candidates", candidats, "--config", "rules.yml")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["coverage"]["not_reported"], ["autre.py"])
        r = subprocess.run([sys.executable, str(ICI / "scan_verdict.py"), "semgrep", "--report", str(trouvaille),
                            "--findings-exit-code", "1", "--exit-code", "1"],
                           capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "findings")

    def test_out_atomique(self) -> None:
        # Constat M2 (S-01M4VYXNW9) : un échec avec --out RETIRE l'ancien verdict ; ni
        # fichier partiel ni temporaire. La panne de os.replace prouve l'écriture atomique.
        sortie = self.dossier / "sortie"
        sortie.mkdir()
        cible = sortie / "verdict.json"
        rapport = self.rapport(SEMGREPIGNORE_SEUL)
        argv = ("semgrep", "--report", rapport, "--findings-exit-code", "none", "--exit-code", "0", "--out", cible)

        def panne_serialiseur(_verdict: dict) -> str:
            raise ValueError("sérialiseur forcé à lever")

        def panne_replace(*_args: object, **_kw: object) -> None:
            raise OSError("os.replace forcé à lever")

        for panne in (mock.patch.object(sv, "_serialize", panne_serialiseur),
                      mock.patch.object(sv.os, "replace", panne_replace)):
            cible.write_text("ANCIEN\n", encoding="utf-8")
            with panne:
                rc, _, err = self.cli(*argv)
            self.assertEqual(rc, 2, err)
            self.assertEqual(sorted(p.name for p in sortie.iterdir()), [], err)
        cible.write_text("ANCIEN\n", encoding="utf-8")
        rc, _, _ = self.cli(*argv)
        self.assertEqual(rc, 0)
        self.assertEqual(sv.validate(json.loads(cible.read_text(encoding="utf-8"))), [])
        self.assertEqual(sorted(p.name for p in sortie.iterdir()), ["verdict.json"])

    def test_out_retire_sur_echec(self) -> None:
        # Constat M2 : toute erreur d'usage, argparse comprise, rend 2 ET retire la cible.
        cible = self.dossier / "verdict.json"
        rapport = self.rapport(SEMGREPIGNORE_SEUL)
        echecs = [
            ("semgrep", "--report", rapport, "--findings-exit-code", "1", "--exit-code", "300", "--out", cible),
            ("semgrep", "--report", rapport, "--findings-exit-code", "abc", "--out", cible),
            ("semgrep", "--report", rapport, "--findings-exit-code", "none", "--tool-version", "1", "--out", cible),
            ("semgrep", "--report", rapport, "--findings-exit-code", "none",
             "--candidates", self.dossier / "absent.txt", "--out", cible),
            ("gitleaks", "--report", rapport, "--findings-exit-code", "none", "--out", cible),
            ("semgrep", "--findings-exit-code", "1", "--out", cible),
            ("semgrep", "--report", rapport, "--findings-exit-code", "1", "--inconnue", "--out", cible),
            ("gitleaks", f"--out={cible}", "--report", rapport),
            # Option d'entrée PENDANTE : le pré-parseur de F7 ne doit pas perdre --out.
            ("semgrep", "--out", cible, "--report"),
            ("semgrep", "--out", cible, "--findings-exit-code", "1", "--candidates"),
            ("semgrep", "--out", cible, "--config"),
            # « --c » abrège --candidates ET --config : l'ambiguïté ne doit pas perdre --out.
            ("semgrep", "--report", rapport, "--findings-exit-code", "1", "--c", self.dossier / "x", "--out", cible),
        ]
        for argv in echecs:
            cible.write_text("ANCIEN\n", encoding="utf-8")
            rc, _, err = self.cli(*argv)
            self.assertEqual(rc, 2, (argv, err))
            self.assertFalse(cible.exists(), argv)
        # validate n'a pas d'option --out : rien n'est retiré.
        cible.write_text("ANCIEN\n", encoding="utf-8")
        self.assertEqual(self.cli("validate", "--out", cible)[0], 2)
        self.assertTrue(cible.exists())
        # Cible non retirable (un dossier ; un unlink qui échoue) : rc 2, dit sur stderr,
        # aucun verdict écrit — même quand l'écriture, elle, aurait réussi.
        rc, out, err = self.cli("semgrep", "--report", rapport, "--findings-exit-code", "none", "--out", self.dossier)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("non retirée", err)
        cible.write_text("ANCIEN\n", encoding="utf-8")
        with mock.patch.object(sv.Path, "unlink", side_effect=PermissionError("unlink forcé à échouer")):
            rc, out, err = self.cli("semgrep", "--report", rapport, "--findings-exit-code", "none", "--out", cible)
        self.assertEqual((rc, out), (2, ""), err)
        self.assertIn("non retirée", err)
        self.assertEqual(cible.read_text(encoding="utf-8"), "ANCIEN\n")

    def test_out_egal_a_une_entree_refuse_sans_rien_retirer(self) -> None:
        # Constat F7 (S-01M4W2N4C5M27ZYAX4X12GET98) : un --out qui désigne le fichier de
        # --report ou de --candidates détruisait la preuve. Refus d'usage (rc 2) AVANT tout
        # retrait, sur les DEUX sites de retrait (ligne acceptée, ligne refusée par argparse).
        octets = json.dumps(SEMGREPIGNORE_SEUL).encode("utf-8")
        rapport = self.rapport(octets)
        candidats = self.dossier / "candidats.txt"
        candidats.write_bytes(b"a.py\n")
        config = self.dossier / "regles.yml"  # --config est une entrée protégée (C3, revue BIS E-36)
        config.write_bytes(b"rules: []\n")
        autre_graphie = f"{rapport.parent}/./{rapport.name}"  # chaîne : pathlib effacerait le « . »
        self.assertNotEqual(autre_graphie, str(rapport))
        cas = [
            ("semgrep", "--report", rapport, "--findings-exit-code", "none", "--out", rapport),
            ("semgrep", "--report", rapport, "--findings-exit-code", "none", "--out", autre_graphie),
            ("gitleaks", "--report", rapport, "--findings-exit-code", "1", "--exit-code", "0", "--out", rapport),
            ("semgrep", "--report", rapport, "--findings-exit-code", "none",
             "--candidates", candidats, "--out", candidats),
            ("semgrep", "--report", rapport, "--findings-exit-code", "1", "--inconnue", "--out", rapport),
            ("semgrep", "--report", rapport, "--out", rapport),
            ("semgrep", "--report", rapport, "--candidates", candidats, "--inconnue", f"--out={candidats}"),
            ("semgrep", "--report", rapport, "--findings-exit-code", "none", "--config", config, "--out", config),
            ("semgrep", "--report", rapport, "--config", config, "--inconnue", "--out", config),
            ("gitleaks", "--report", rapport, "--findings-exit-code", "1", "--config", config, "--out", config),
            ("semgrep", "--report", rapport, "--c", config, "--out", config),
            ("semgrep", "--report", rapport, f"--c={candidats}", "--out", candidats),
        ]
        for argv in cas:
            rc, out, err = self.cli(*argv)
            self.assertEqual((rc, out), (2, ""), (argv, err))
            self.assertIn("--out désigne le fichier de", err, argv)
            self.assertEqual(rapport.read_bytes(), octets, argv)
            self.assertEqual(candidats.read_bytes(), b"a.py\n", argv)
            self.assertEqual(config.read_bytes(), b"rules: []\n", argv)
        # Témoin vert : un --out distinct des entrées reste retiré puis écrit.
        cible = self.dossier / "verdict.json"
        cible.write_text("ANCIEN\n", encoding="utf-8")
        rc, _, err = self.cli("semgrep", "--report", rapport, "--findings-exit-code", "none",
                              "--candidates", candidats, "--out", cible)
        self.assertEqual(rc, 0, err)
        self.assertEqual(sv.validate(json.loads(cible.read_text(encoding="utf-8"))), [])

    def test_option_repetee_refusee(self) -> None:
        # S1, étape 3 (mesuré) : argparse gardait la DERNIÈRE valeur d'une option répétée et la
        # collision ne comparait qu'elle : A, une entrée, était réécrit (rc 0) ou supprimé (rc 2).
        a, b = self.rapport(SEMGREPIGNORE_SEUL), self.rapport(REL)
        octets_a, octets_b = a.read_bytes(), b.read_bytes()
        for extra in ((), ("--bogus",)):
            rc, out, err = self.cli("semgrep", "--report", a, "--report", b, "--findings-exit-code", "none",
                                    *extra, "--out", a)
            self.assertEqual((rc, out), (2, ""), (extra, err))
            self.assertIn("--out désigne le fichier de --report ", err, extra)
            self.assertEqual((a.read_bytes(), b.read_bytes()), (octets_a, octets_b), extra)
        # Chaque option à valeur unique, répétée, sans collision : rc 2 et la cible est retirée (M2).
        c, cand = self.dossier / "c.json", self.dossier / "cand.txt"
        repetitions = [("--report", b), (f"--report={b}",), ("--findings-exit-code", "1"),
                       ("--exit-code", "0", "--exit-code", "0"), ("--candidates", cand, "--candidates", cand),
                       ("--tool-version", "1", "--tool-version", "1"), ("--config", "r.yml", "--config", "r.yml"),
                       ("--out", self.dossier / "d.json")]
        for outil, rc_trouve in (("semgrep", "none"), ("gitleaks", "1")):
            for extra in repetitions:
                c.write_text("ANCIEN\n", encoding="utf-8")
                rc, out, err = self.cli(outil, "--report", a, "--findings-exit-code", rc_trouve, *extra, "--out", c)
                self.assertEqual((rc, out), (2, ""), (outil, extra, err))
                self.assertIn("répétée", err, (outil, extra))
                self.assertFalse(c.exists(), (outil, extra))
        self.assertEqual((a.read_bytes(), b.read_bytes()), (octets_a, octets_b))

    def test_abreviation_refusee(self) -> None:
        # S1, étape 3 : allow_abbrev=False sur CHAQUE parseur ; un sous-parseur ne l'hérite pas.
        rapport = self.rapport(SEMGREPIGNORE_SEUL)
        cas = [("semgrep", "--rep", rapport, "--findings-exit-code", "none"),
               ("semgrep", f"--rep={rapport}", "--findings-exit-code", "none"),
               ("semgrep", "--report", rapport, "--findings", "none"),
               ("gitleaks", "--rep", rapport, "--findings-exit-code", "1"),
               ("gitleaks", "--report", rapport, "--findings", "1"),
               ("validate", "--he"), ("--he",)]
        for argv in cas:
            rc, out, err = self.cli(*argv)
            self.assertEqual((rc, out), (2, ""), (argv, err))

    def test_collision_par_jeton(self) -> None:
        # S1, étape 3 : --out comparé à CHAQUE autre argument — option inconnue, abrégée ou
        # future, droite de --opt=valeur, positionnel — sur la ligne refusée comme acceptée.
        octets = b"rules: []\n"
        f = self.dossier / "f.yml"
        f.write_bytes(octets)
        rapport = self.rapport(SEMGREPIGNORE_SEUL)
        for outil, rc_trouve in (("semgrep", "none"), ("gitleaks", "1")):
            base = (outil, "--report", rapport, "--findings-exit-code", rc_trouve)
            for queue, porteur in ((("--zzz", f, "--out", f), "--zzz"), (("--conf", f, "--out", f), "--conf"),
                                   ((f"--zzz={f}", "--out", f), "--zzz"), ((f, "--out", f), "l'argument n°5"),
                                   (("--out", f, "--", f), "l'argument n°8")):
                rc, out, err = self.cli(*base, *queue)
                self.assertEqual((rc, out), (2, ""), (outil, queue, err))
                self.assertIn(f"--out désigne le fichier de {porteur} :", err, (outil, queue))
                self.assertEqual(f.read_bytes(), octets, (outil, queue))
        octets_rapport = rapport.read_bytes()
        rc, out, err = self.cli("semgrep", f"--report={rapport}", "--findings-exit-code", "none", "--out", rapport)
        self.assertEqual((rc, out), (2, ""), err)
        self.assertIn("--out désigne le fichier de --report :", err)
        self.assertEqual(rapport.read_bytes(), octets_rapport)
        # Témoin : un jeton qui ne désigne pas la cible ne bloque pas son retrait (ligne refusée).
        cible = self.dossier / "verdict.json"
        cible.write_text("ANCIEN\n", encoding="utf-8")
        rc, _, err = self.cli("semgrep", "--report", rapport, "--findings-exit-code", "none", "--zzz", f,
                              "--out", cible)
        self.assertEqual(rc, 2, err)
        self.assertFalse(cible.exists())
        self.assertEqual(f.read_bytes(), octets)
        # Après « -- », argparse lit « --out X » comme positionnel : rien n'est désigné, rien retiré.
        cible.write_text("ANCIEN\n", encoding="utf-8")
        rc, _, err = self.cli("semgrep", "--report", rapport, "--findings-exit-code", "none", "--", "--out", cible)
        self.assertEqual(rc, 2, err)
        self.assertEqual(cible.read_text(encoding="utf-8"), "ANCIEN\n")


def _sans_gitleaks_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_")}


@unittest.skipUnless(shutil.which("semgrep"), "semgrep absent du PATH : bras live sauté (ne tourne pas en CI)")
class BrasLiveSemgrep(_Base):
    REGLE = ("rules:\n  - id: sonde-puits\n    pattern: probe_sink(...)\n    message: sonde\n"
             "    languages: [python]\n    severity: WARNING\n")

    def _scan(self, cible: Path, config: str, sortie: Path) -> int:
        r = subprocess.run(
            [shutil.which("semgrep") or "semgrep", "scan", "--config", config, "--json", "--output", str(sortie),
             "--verbose", "--metrics=off", "--disable-version-check", "--error", "."],
            cwd=str(cible), capture_output=True, text=True, timeout=600, check=False)
        return r.returncode

    def test_live_semgrep_config_relative_et_absolue(self) -> None:
        racine = self.dossier.resolve()
        cible, regles = racine / "cible", racine / "regles" / "sous"
        cible.mkdir()
        regles.mkdir(parents=True)
        (regles / "rules.yml").write_text(self.REGLE, encoding="utf-8")
        (cible / "app.py").write_text("probe_sink(1)\n", encoding="utf-8")
        (cible / "propre.py").write_text("x = 1\n", encoding="utf-8")
        for config, prefixe in (("../regles/sous/rules.yml", "regles.sous."), (str(regles / "rules.yml"), None)):
            sortie = racine / "rapport.json"
            rc = self._scan(cible, config, sortie)
            brut = json.loads(sortie.read_text(encoding="utf-8"))["results"][0]["check_id"]
            self.assertNotEqual(brut, "sonde-puits", "témoin vide : semgrep n'a préfixé aucun id")
            if prefixe:
                self.assertEqual(brut, prefixe + "sonde-puits")
            v = self.valide(sv.from_semgrep(sortie, findings_rc=1, exit_code=rc, config=config))
            self.assertEqual(rc, 1)
            self.assertEqual((v["status"], v["notes"]), ("findings", []))
            self.assertEqual(v["findings"], [{"rule": "sonde-puits", "path": "app.py", "line": 1,
                                              "severity": "medium", "tool_severity": "WARNING"}])
            self.assertEqual(v["coverage"]["inspected"], ["app.py", "propre.py"])
            self.assertEqual(v["coverage"]["skipped_source"], "paths.skipped")
            self.assertEqual(v["tool"]["version"], json.loads(sortie.read_text(encoding="utf-8"))["version"])


@unittest.skipUnless(shutil.which("gitleaks"), "gitleaks absent du PATH : bras live sauté (ne tourne pas en CI)")
class BrasLiveGitleaks(_Base):
    def _scan(self, cible: Path, sortie: Path) -> int:
        r = subprocess.run(
            [shutil.which("gitleaks") or "gitleaks", "dir", str(cible), "--report-format", "json",
             "--report-path", str(sortie), "--redact", "--exit-code", "7", "--no-banner"],
            cwd=str(self.dossier), env=_sans_gitleaks_env(), capture_output=True, text=True, timeout=300, check=False)
        return r.returncode

    def test_live_gitleaks_redact(self) -> None:
        # La clé live est assemblée par fragments : ce fichier ne la porte jamais entière.
        jeton = "".join(["gh", "p_", "Zx9Kq2Lm7N", "p4Rt8Vw3Yb", "6Cd1Fg5Hj0", "Sa2Qe7"])
        rouge, propre = self.dossier / "rouge", self.dossier / "propre"
        rouge.mkdir()
        propre.mkdir()
        (rouge / "app.py").write_text('jeton = "' + jeton + '"\n', encoding="utf-8")
        (propre / "app.py").write_text("x = 1\n", encoding="utf-8")
        sortie = self.dossier / "rouge.json"
        rc = self._scan(rouge, sortie)
        self.assertEqual(rc, 7)
        self.assertNotIn(jeton, sortie.read_text(encoding="utf-8"))
        v = self.valide(sv.from_gitleaks(sortie, findings_rc=7, exit_code=rc, version="live"))
        self.assertEqual((v["status"], v["notes"]), ("findings", []))
        self.assertEqual([(f["rule"], f["line"]) for f in v["findings"]], [("github-pat", 1)])
        self.assertNotIn(jeton, json.dumps(v))
        sortie = self.dossier / "propre.json"
        rc = self._scan(propre, sortie)
        v = self.valide(sv.from_gitleaks(sortie, findings_rc=7, exit_code=rc))
        self.assertEqual((rc, v["status"]), (0, "clean"))


if __name__ == "__main__":
    unittest.main()
