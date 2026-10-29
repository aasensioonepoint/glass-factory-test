#!/usr/bin/env python3
"""Verdict commun des scanners de sécurité — contrat ``cadre.scan-verdict/1``.

Un verdict VERSIONNÉ et homogène par outil : findings normalisés, erreurs
d'outil sans leur texte, couverture partitionnée. Deux adaptateurs (semgrep,
gitleaks), un validateur, une CLI. Stdlib seule ; aucun sous-processus, aucun
réseau, aucun parcours d'arborescence : on ne lit que le rapport désigné et,
pour semgrep, la liste de candidats fournie par l'appelant.

BORNE V1 — À LIRE AVANT DE CONSOMMER UN VERDICT.
``coverage.complete`` ne vaut JAMAIS ``true`` en v1 : il vaut ``false`` quand
un trou est CONNU (fichier sauté hors politique, analyse incomplète) et
``null`` sinon. Une perte que l'outil ne rapporte pas reste invisible — mesuré
sur semgrep 1.175.0 : un script bash portant ``10#$X`` est listé « scanné »,
sans erreur, et la trouvaille qu'il contient est perdue. Un consommateur DOIT
donc lire ``complete`` ; ``status == "clean"`` SEUL NE PROUVE PAS la
couverture. ``validate`` refuse ``complete=true``.

Règle de version : l'identifiant reste ``cadre.scan-verdict/1``. TOUT champ
ajouté, retiré ou changé de sens — valeur d'énumération comprise — ouvre un
nouveau majeur ; il n'y a pas de mineur. ``validate`` refuse une clé inconnue
à tout niveau et un majeur inconnu. Cette règle court à partir du premier
producteur câblé (S1) ; avant lui, ``/1`` absorbe ses propres corrections
(S-01M4W0P3T3VBJVVRAFT2GRRWSH).

Un producteur câblé : ``semgrep-scan.sh`` (S1, T-01M4W80Q5C3F6G99G0JXJB3RH4), hors
hook, dans ``$OUT/semgrep-verdict.json``. ``gitleaks-scan.sh`` et la SCA ne
l'appellent pas encore (suites S3, S4, S5 du plan T-01M4V7R991WJNAMD8GAQZNG903).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA = "cadre.scan-verdict/1"
SCHEMA_FAMILY = "cadre.scan-verdict/"

# Énumérations fermées — tenues égales à scan-verdict.schema.json par le banc.
TOOL_CLASSES: dict[str, str] = {"semgrep": "sast", "gitleaks": "secrets"}
TOOL_NAMES: tuple[str, ...] = ("semgrep", "gitleaks")
CLASSES: tuple[str, ...] = ("sast", "secrets")
STATUSES: tuple[str, ...] = ("clean", "findings", "degraded")
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low", "unknown")
SKIPPED_SOURCES: tuple[str, ...] = ("paths.skipped", "complement", "unknown")
COMPLETE_VALUES: tuple[bool | None, ...] = (False, None)

# Catalogue FERMÉ des notes. Toutes, sauf la dernière, sont des causes de
# `degraded` ; la dernière ne naît qu'à côté de findings (désaccord rc/rapport).
NOTES: tuple[str, ...] = (
    "report_absent",
    "report_empty",
    "report_unreadable",
    "report_too_large",
    "tool_errors",
    "skipped_rules",
    "known_gap",
    "scanned_empty",
    "exit_code_absent",
    "exit_code_findings_without_findings",
    "exit_code_out_of_table",
    "exit_code_disagrees_with_report",
)

# Taille maximale d'un rapport lu (les deux adaptateurs) ; au-delà : note
# `report_too_large`, donc `degraded`. Constante du module, sans variable
# d'environnement : un rapport de 200 Mio coûtait ~654 Mo RSS (mesuré, ×3,2).
MAX_REPORT_BYTES = 64 * 1024 * 1024

# Raisons de `paths.skipped` qui relèvent d'une POLITIQUE (exclusion voulue,
# sans effet sur la couverture). Liste fermée et MESURÉE : on n'y ajoute une
# raison qu'avec une fixture capturée en direct, dans le même commit. Toute
# autre raison est un trou (fail-closed), recopiée verbatim.
POLICY_SKIP_REASONS: frozenset[str] = frozenset({"semgrepignore_patterns_match"})

# Sévérité native -> sévérité commune ; le reste -> "unknown". Une sévérité ne
# filtre JAMAIS le blocage : tout finding rend `findings`.
SEVERITY_TABLE: dict[str, str] = {
    "CRITICAL": "critical",
    "ERROR": "high",
    "HIGH": "high",
    "WARNING": "medium",
    "MEDIUM": "medium",
    "INFO": "low",
    "LOW": "low",
}

KEYS_TOP: tuple[str, ...] = (
    "schema", "tool", "status", "tool_exit_code", "findings", "tool_errors", "notes", "coverage",
)
KEYS_TOOL: tuple[str, ...] = ("name", "version", "class", "config")
KEYS_FINDING: tuple[str, ...] = ("rule", "path", "line", "severity", "tool_severity")
KEYS_TOOL_ERROR: tuple[str, ...] = ("type", "level", "rule_id")
KEYS_COVERAGE: tuple[str, ...] = (
    "candidates", "inspected", "analysis_incomplete", "skipped", "excluded",
    "not_reported", "skipped_source", "complete",
)
KEYS_INCOMPLETE: tuple[str, ...] = ("path", "type")
KEYS_SKIP: tuple[str, ...] = ("path", "reason")

# C0, DEL et C1 : retirés de TOUTE chaîne recopiée d'un rapport.
_CONTROLE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Fragment d'id de règle tel que semgrep l'assainit (rule_lang.py, 1.175.0).
_HORS_ID = re.compile(r"[^a-zA-Z0-9._-]")


def _texte(valeur: str) -> str:
    return _CONTROLE.sub("", valeur)


def _chaine(valeur: object) -> str | None:
    return _texte(valeur) if isinstance(valeur, str) else None


def _chemin(valeur: object) -> str | None:
    texte = _chaine(valeur)
    return texte.replace("\\", "/") if texte is not None else None


def _entier(valeur: object) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def _ligne(valeur: object) -> int | None:
    return valeur if _entier(valeur) and valeur >= 0 else None  # type: ignore[operator]


def _verifier_rc(nom: str, valeur: object, *, nullable: bool) -> None:
    if valeur is None and nullable:
        return
    if not _entier(valeur) or not 0 <= valeur <= 255:  # type: ignore[operator]
        raise ValueError(f"{nom} : entier 0..255 attendu, reçu {valeur!r}")


def _charger(rapport: str | os.PathLike[str]) -> tuple[Any, str | None]:
    """Rend (données, note). Une note non nulle = rapport inutilisable.

    Lit AU PLUS ``MAX_REPORT_BYTES + 1`` octets, sans jamais se fier à un ``stat``
    (``/dev/zero`` déclare une taille 0) ; au-delà de la borne : ``report_too_large``.
    """
    try:
        with open(rapport, "rb") as fh:
            brut = fh.read(MAX_REPORT_BYTES + 1)
    except FileNotFoundError:
        return None, "report_absent"
    except OSError:
        return None, "report_unreadable"
    if len(brut) > MAX_REPORT_BYTES:
        return None, "report_too_large"
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError:
        return None, "report_unreadable"
    if not texte.strip():
        return None, "report_empty"
    try:
        return json.loads(texte), None
    except (ValueError, RecursionError):
        return None, "report_unreadable"


def _couverture(*, candidats: int | None, source: str) -> dict[str, Any]:
    return {
        "candidates": candidats,
        "inspected": [],
        "analysis_incomplete": [],
        "skipped": [],
        "excluded": [],
        "not_reported": [],
        "skipped_source": source,
        "complete": None,
    }


def _assembler(
    tool: dict[str, Any],
    exit_code: int | None,
    findings: list[dict[str, Any]],
    tool_errors: list[dict[str, Any]],
    notes: list[str],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    """Statut par PRÉCÉDENCE : findings > degraded (toute note) > clean."""
    notes_uniques = [n for n in NOTES if n in notes]
    if findings:
        status = "findings"
    elif notes_uniques:
        status = "degraded"
    else:
        status = "clean"
    return {
        "schema": SCHEMA,
        "tool": tool,
        "status": status,
        "tool_exit_code": exit_code,
        "findings": findings,
        "tool_errors": tool_errors,
        "notes": notes_uniques,
        "coverage": coverage,
    }


def _notes_rc(nb_findings: int, findings_rc: int | None, exit_code: int | None) -> list[str]:
    """Lecture du rc. Sans finding, tout rc non nul dégrade (dont rc 2 de semgrep)."""
    if exit_code is None:
        return []
    if nb_findings:
        attendu = findings_rc if findings_rc is not None else 0
        return [] if exit_code == attendu else ["exit_code_disagrees_with_report"]
    if exit_code == 0:
        return []
    if findings_rc is not None and exit_code == findings_rc:
        return ["exit_code_findings_without_findings"]
    return ["exit_code_out_of_table"]


# --- semgrep -----------------------------------------------------------------

def _prefixe_semgrep(parties: Sequence[str]) -> str:
    """Préfixe que semgrep 1.175.0 accole à un id de règle (rule_lang.py:488-500)."""
    prefixe = ".".join(parties).lstrip("./").lstrip(".")
    if prefixe:
        prefixe += "."
    return _HORS_ID.sub("", prefixe)


def _prefixes_config(config: str | None) -> tuple[str, ...]:
    """Préfixes candidats dérivés du chemin de config, du plus long au plus court.

    semgrep relativise une config absolue au cwd du scan quand ce cwd en est un
    ancêtre ; l'adaptateur ignore ce cwd, il essaie donc chaque suffixe du
    dossier. Une config relative n'est jamais relativisée : un seul candidat.
    """
    if not config:
        return ()
    chemin = PurePath(config)
    dossiers = chemin.parts[:-1]
    if chemin.is_absolute():
        familles = [dossiers[k:] for k in range(len(dossiers))]
    else:
        familles = [dossiers]
    vus = {p for p in (_prefixe_semgrep(f) for f in familles) if p}
    return tuple(sorted(vus, key=lambda p: (-len(p), p)))


def _config_publique(config: str | None) -> str | None:
    r"""``tool.config`` du verdict. Une config ABSOLUE — POSIX ``/…``, lecteur ``X:\`` ou
    ``X:/``, UNC ``\\…`` (formes Windows lues par ``PureWindowsPath`` : sur un hôte POSIX,
    ``PurePath`` ne les reconnaît pas) — est réduite à son NOM : aucun chemin machine
    dans le verdict. Relative ou registre (``p/…``) : inchangée. Le chemin entier sert
    seul au retrait du préfixe (``_prefixes_config``) et reste au journal local
    ``audit-log.jsonl`` de semgrep-scan.sh (champ ``config``)."""
    texte = _chaine(config)
    if texte is None:
        return None
    for forme in (PureWindowsPath, PurePosixPath):
        chemin = forme(texte)
        if chemin.is_absolute():
            return chemin.name
    return texte


def _sans_prefixe(rule: str | None, prefixes: Sequence[str]) -> str | None:
    if rule is None:
        return None
    for prefixe in prefixes:
        if rule.startswith(prefixe) and len(rule) > len(prefixe):
            return rule[len(prefixe):]
    return rule


def _type_erreur(valeur: object) -> str:
    """Le type d'une erreur semgrep : la chaîne, ou le PREMIER élément d'une liste."""
    if isinstance(valeur, str):
        return _texte(valeur)
    if isinstance(valeur, list) and valeur and isinstance(valeur[0], str):
        return _texte(valeur[0])
    return "unknown"


def _chemins_erreur(erreur: dict[str, Any]) -> list[str]:
    """Chemins portés par une erreur : au sommet OU dans ``type[1][].path``."""
    chemins: list[str] = []
    sommet = _chemin(erreur.get("path"))
    if sommet:
        chemins.append(sommet)
    genre = erreur.get("type")
    if isinstance(genre, list) and len(genre) > 1 and isinstance(genre[1], list):
        for item in genre[1]:
            if isinstance(item, dict):
                imbrique = _chemin(item.get("path"))
                if imbrique:
                    chemins.append(imbrique)
    return chemins


def _forme_semgrep(data: object) -> bool:
    """Structure exploitable ? Toute anomalie = rapport illisible (fail-closed)."""
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("results"), list):
        return False
    if not all(isinstance(r, dict) for r in data["results"]):
        return False
    erreurs = data.get("errors")
    if erreurs is not None and not (isinstance(erreurs, list) and all(isinstance(e, dict) for e in erreurs)):
        return False
    regles = data.get("skipped_rules")
    if regles is not None and not isinstance(regles, list):
        return False
    paths = data.get("paths")
    if paths is None:
        return True
    if not isinstance(paths, dict):
        return False
    scanned = paths.get("scanned")
    if scanned is not None and not (isinstance(scanned, list) and all(isinstance(p, str) for p in scanned)):
        return False
    sautes = paths.get("skipped")
    if sautes is not None:
        if not isinstance(sautes, list):
            return False
        for item in sautes:
            if not (isinstance(item, dict) and isinstance(item.get("path"), str)
                    and isinstance(item.get("reason"), str)):
                return False
    return True


def _finding_semgrep(resultat: dict[str, Any], prefixes: Sequence[str]) -> dict[str, Any]:
    extra = resultat.get("extra")
    native = _chaine(extra.get("severity")) if isinstance(extra, dict) else None
    debut = resultat.get("start")
    return {
        "rule": _sans_prefixe(_chaine(resultat.get("check_id")), prefixes) or "?",
        "path": _chemin(resultat.get("path")) or "?",
        "line": _ligne(debut.get("line")) if isinstance(debut, dict) else None,
        "severity": SEVERITY_TABLE.get(native, "unknown") if native is not None else "unknown",
        "tool_severity": native,
    }


def _cle_finding(f: dict[str, Any]) -> tuple[str, int, str]:
    return (f["path"], f["line"] if f["line"] is not None else -1, f["rule"])


def from_semgrep(
    report: str | os.PathLike[str],
    *,
    findings_rc: int | None,
    exit_code: int | None = None,
    candidates: Sequence[str] | None = None,
    config: str | None = None,
) -> dict[str, Any]:
    """Verdict v1 d'un rapport ``semgrep --json``.

    Table des rc : 0 = aucun finding, ou findings sans ``--error`` ;
    ``findings_rc`` = findings avec ``--error`` (``None`` : lancé sans) ;
    2 = erreur de règle ou d'outil. Un rapport absent, vide ou illisible rend
    ``degraded``, jamais une exception.
    """
    _verifier_rc("findings_rc", findings_rc, nullable=True)
    _verifier_rc("exit_code", exit_code, nullable=True)
    cands = None if candidates is None else {c for c in (_chemin(x) for x in candidates) if c}
    tool = {"name": "semgrep", "version": None, "class": TOOL_CLASSES["semgrep"], "config": _config_publique(config)}
    data, note = _charger(report)
    if note is None and not _forme_semgrep(data):
        note = "report_unreadable"
    if note is not None:
        couverture = _couverture(candidats=None if cands is None else len(cands), source="unknown")
        return _assembler(tool, exit_code, [], [], [note], couverture)
    tool["version"] = _chaine(data.get("version"))
    prefixes = _prefixes_config(config)
    findings = sorted((_finding_semgrep(r, prefixes) for r in data["results"]), key=_cle_finding)

    paths = data.get("paths") or {}
    scanned = {c for c in (_chemin(p) for p in paths.get("scanned") or []) if c}
    sautes: dict[str, str] = {}
    exclus: dict[str, str] = {}
    for item in paths.get("skipped") or []:
        chemin = _chemin(item["path"]) or "?"
        raison = _texte(item["reason"])
        if raison in POLICY_SKIP_REASONS:
            exclus.setdefault(chemin, raison)
        else:
            sautes.setdefault(chemin, raison)

    incomplets: dict[str, str] = {}
    tool_errors: list[dict[str, Any]] = []
    for erreur in data.get("errors") or []:
        chemins = _chemins_erreur(erreur)
        if chemins:
            for chemin in chemins:
                incomplets.setdefault(chemin, _type_erreur(erreur.get("type")))
        else:
            tool_errors.append({
                "type": _type_erreur(erreur.get("type")),
                "level": _chaine(erreur.get("level")) or "unknown",
                "rule_id": _sans_prefixe(_chaine(erreur.get("rule_id")), prefixes),
            })

    # Un chemin, une place : skipped > analysis_incomplete > excluded > inspected.
    for chemin in sautes:
        incomplets.pop(chemin, None)
    for chemin in set(sautes) | set(incomplets):
        exclus.pop(chemin, None)
    places = set(sautes) | set(incomplets) | set(exclus)
    inspected = sorted(scanned - places)

    if "skipped" in paths:
        source, non_rapportes = "paths.skipped", []
    elif cands is not None:
        # Le complément est une BORNE (fichiers non ciblés ou non rapportés), jamais un trou.
        source, non_rapportes = "complement", sorted(cands - scanned - places)
    else:
        source, non_rapportes = "unknown", []

    trou = bool(sautes) or bool(incomplets)
    couverture = _couverture(candidats=None if cands is None else len(cands), source=source)
    couverture.update({
        "inspected": inspected,
        "analysis_incomplete": [{"path": p, "type": incomplets[p]} for p in sorted(incomplets)],
        "skipped": [{"path": p, "reason": sautes[p]} for p in sorted(sautes)],
        "excluded": [{"path": p, "reason": exclus[p]} for p in sorted(exclus)],
        "not_reported": non_rapportes,
        "complete": False if trou else None,
    })
    notes: list[str] = []
    if tool_errors:
        notes.append("tool_errors")
    if data.get("skipped_rules"):
        notes.append("skipped_rules")  # précaution fail-closed
    if trou:
        notes.append("known_gap")
    if cands and not scanned and cands - places:
        # Candidats fournis, rien de rapporté scanné, un candidat dans aucune case :
        # jamais clean (constat M1), quelle que soit la source du complément.
        notes.append("scanned_empty")
    notes.extend(_notes_rc(len(findings), findings_rc, exit_code))
    return _assembler(tool, exit_code, findings, tool_errors, notes, couverture)


# --- gitleaks ----------------------------------------------------------------

def from_gitleaks(
    report: str | os.PathLike[str],
    *,
    findings_rc: int,
    exit_code: int | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Verdict v1 d'un rapport ``gitleaks --report-format json``.

    Ne recopie QUE ``RuleID``, ``File`` et ``StartLine`` (sévérité
    ``critical``) : jamais ``Secret``, ``Match``, ``Line`` ni ``Email``.
    ``[]`` avec un ``exit_code`` rend ``clean`` ; sans ``exit_code``, ``[]``
    rend ``degraded`` (note ``exit_code_absent``) : un rapport propre ne prouve
    pas que l'outil a fini. « vide » = 0 octet ou blancs, et dégrade.
    Couverture inconnue : gitleaks ne rapporte pas son périmètre.
    """
    _verifier_rc("findings_rc", findings_rc, nullable=False)
    _verifier_rc("exit_code", exit_code, nullable=True)
    tool = {"name": "gitleaks", "version": _chaine(version), "class": TOOL_CLASSES["gitleaks"], "config": None}
    couverture = _couverture(candidats=None, source="unknown")
    data, note = _charger(report)
    if note is None and not (isinstance(data, list) and all(isinstance(e, dict) for e in data)):
        note = "report_unreadable"
    if note is not None:
        return _assembler(tool, exit_code, [], [], [note], couverture)
    findings = sorted(
        (
            {
                "rule": _chaine(e.get("RuleID")) or "?",
                "path": _chemin(e.get("File")) or "?",
                "line": _ligne(e.get("StartLine")),
                "severity": "critical",
                "tool_severity": None,
            }
            for e in data
        ),
        key=_cle_finding,
    )
    notes = _notes_rc(len(findings), findings_rc, exit_code)
    if not findings and exit_code is None:
        notes.append("exit_code_absent")  # constat M3 : une conclusion clean exige le rc
    return _assembler(tool, exit_code, findings, [], notes, couverture)


# --- validation ----------------------------------------------------------------

def _cles(obj: dict[str, Any], attendues: Sequence[str], ou: str, erreurs: list[str]) -> None:
    for cle in obj:
        if cle not in attendues:
            erreurs.append(f"{ou} : clé inconnue {cle!r}")
    for cle in attendues:
        if cle not in obj:
            erreurs.append(f"{ou} : clé manquante {cle!r}")


def _objet(valeur: object, attendues: Sequence[str], ou: str, erreurs: list[str]) -> dict[str, Any]:
    if not isinstance(valeur, dict):
        erreurs.append(f"{ou} : objet attendu")
        return {}
    _cles(valeur, attendues, ou, erreurs)
    return valeur


def _liste(valeur: object, ou: str, erreurs: list[str]) -> list[Any]:
    if not isinstance(valeur, list):
        erreurs.append(f"{ou} : liste attendue")
        return []
    return valeur


def _str(valeur: object, ou: str, erreurs: list[str], *, nullable: bool = False) -> None:
    if valeur is None and nullable:
        return
    if not isinstance(valeur, str):
        erreurs.append(f"{ou} : chaîne attendue")


def _enum(valeur: object, permis: Sequence[object], ou: str, erreurs: list[str]) -> None:
    if not any(valeur is p or (type(valeur) is type(p) and valeur == p) for p in permis):
        erreurs.append(f"{ou} : valeur hors énumération {valeur!r}")


def _entier_borne(valeur: object, ou: str, erreurs: list[str], *, maxi: int | None = None) -> None:
    if valeur is None:
        return
    if not _entier(valeur) or valeur < 0 or (maxi is not None and valeur > maxi):  # type: ignore[operator]
        erreurs.append(f"{ou} : entier attendu")


def validate(v: object) -> list[str]:
    """Erreurs du verdict ``v`` contre le contrat v1 ; liste vide = valide."""
    erreurs: list[str] = []
    top = _objet(v, KEYS_TOP, "verdict", erreurs)
    if not top:
        return erreurs
    schema = top.get("schema")
    if not isinstance(schema, str) or not schema.startswith(SCHEMA_FAMILY):
        erreurs.append(f"schema : identifiant inconnu {schema!r}")
    elif schema != SCHEMA:
        erreurs.append(f"schema : majeur inconnu {schema!r} (seul {SCHEMA!r} est lu)")

    tool = _objet(top.get("tool"), KEYS_TOOL, "tool", erreurs)
    if tool:
        _enum(tool.get("name"), TOOL_NAMES, "tool.name", erreurs)
        _enum(tool.get("class"), CLASSES, "tool.class", erreurs)
        _str(tool.get("version"), "tool.version", erreurs, nullable=True)
        _str(tool.get("config"), "tool.config", erreurs, nullable=True)
        nom, classe = tool.get("name"), tool.get("class")
        if isinstance(nom, str) and nom in TOOL_CLASSES and classe in CLASSES and classe != TOOL_CLASSES[nom]:
            erreurs.append(f"tool.class : {classe!r} n'est pas la classe de {nom!r} ({TOOL_CLASSES[nom]!r} attendu)")

    status = top.get("status")
    _enum(status, STATUSES, "status", erreurs)
    _entier_borne(top.get("tool_exit_code"), "tool_exit_code", erreurs, maxi=255)

    findings = _liste(top.get("findings"), "findings", erreurs)
    for i, f in enumerate(findings):
        f = _objet(f, KEYS_FINDING, f"findings[{i}]", erreurs)
        if f:
            _str(f.get("rule"), f"findings[{i}].rule", erreurs)
            _str(f.get("path"), f"findings[{i}].path", erreurs)
            _entier_borne(f.get("line"), f"findings[{i}].line", erreurs)
            _enum(f.get("severity"), SEVERITIES, f"findings[{i}].severity", erreurs)
            _str(f.get("tool_severity"), f"findings[{i}].tool_severity", erreurs, nullable=True)

    tool_errors = _liste(top.get("tool_errors"), "tool_errors", erreurs)
    for i, e in enumerate(tool_errors):
        e = _objet(e, KEYS_TOOL_ERROR, f"tool_errors[{i}]", erreurs)
        if e:
            _str(e.get("type"), f"tool_errors[{i}].type", erreurs)
            _str(e.get("level"), f"tool_errors[{i}].level", erreurs)
            _str(e.get("rule_id"), f"tool_errors[{i}].rule_id", erreurs, nullable=True)

    notes = _liste(top.get("notes"), "notes", erreurs)
    for i, n in enumerate(notes):
        if not isinstance(n, str) or n not in NOTES:
            erreurs.append(f"notes[{i}] : hors catalogue {n!r}")

    cov = _objet(top.get("coverage"), KEYS_COVERAGE, "coverage", erreurs)
    trou = False
    if cov:
        _entier_borne(cov.get("candidates"), "coverage.candidates", erreurs)
        for cle in ("inspected", "not_reported"):
            for i, p in enumerate(_liste(cov.get(cle), f"coverage.{cle}", erreurs)):
                _str(p, f"coverage.{cle}[{i}]", erreurs)
        incomplets = _liste(cov.get("analysis_incomplete"), "coverage.analysis_incomplete", erreurs)
        for i, item in enumerate(incomplets):
            item = _objet(item, KEYS_INCOMPLETE, f"coverage.analysis_incomplete[{i}]", erreurs)
            for cle in item:
                _str(item[cle], f"coverage.analysis_incomplete[{i}].{cle}", erreurs)
        sautes = _liste(cov.get("skipped"), "coverage.skipped", erreurs)
        for cle_liste, liste in (("skipped", sautes), ("excluded", _liste(cov.get("excluded"), "coverage.excluded", erreurs))):
            for i, item in enumerate(liste):
                item = _objet(item, KEYS_SKIP, f"coverage.{cle_liste}[{i}]", erreurs)
                for cle in item:
                    _str(item[cle], f"coverage.{cle_liste}[{i}].{cle}", erreurs)
        _enum(cov.get("skipped_source"), SKIPPED_SOURCES, "coverage.skipped_source", erreurs)
        complete = cov.get("complete")
        trou = bool(sautes) or bool(incomplets)
        if complete is True:
            erreurs.append("coverage.complete : true est interdit en v1 (une perte non rapportée reste invisible)")
        else:
            _enum(complete, COMPLETE_VALUES, "coverage.complete", erreurs)
        if complete is None and trou:
            erreurs.append("coverage.complete : null alors qu'un trou est connu (false attendu)")

    if status == "clean":
        if tool_errors:
            erreurs.append("status : clean avec des tool_errors")
        if trou:
            erreurs.append("status : clean avec un trou connu")
        if notes:
            erreurs.append("status : clean avec des notes")
        # Table propre : rc 0 ; null seulement pour semgrep (gitleaks : constat M3).
        rc = top.get("tool_exit_code")
        if rc is not None and rc != 0:
            erreurs.append(f"status : clean avec un rc hors table propre {rc!r} (0 attendu)")
        if rc is None and tool.get("name") == "gitleaks":
            erreurs.append("status : gitleaks clean sans rc (exit_code_absent attendu)")
    if status == "degraded" and not notes and not trou:
        erreurs.append("status : degraded sans note ni trou")
    if (status == "findings") != bool(findings):
        erreurs.append("status : findings si et seulement si la liste findings est non vide")
    return erreurs


# --- CLI ---------------------------------------------------------------------

def _serialize(verdict: dict[str, Any]) -> str:
    return json.dumps(verdict, ensure_ascii=True, indent=2) + "\n"


def _ecrire_atomique(cible: Path, verdict: dict[str, Any]) -> None:
    """Temporaire voisin puis ``os.replace`` : jamais de fichier partiel, et le
    temporaire est retiré en cas d'échec. L'ancien verdict n'est PAS préservé :
    ``main`` l'a retiré avant tout travail (constat M2)."""
    fd, temporaire = tempfile.mkstemp(dir=str(cible.parent), prefix=".scan-verdict-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_serialize(verdict))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporaire, cible)
    except BaseException:
        try:
            os.unlink(temporaire)
        except FileNotFoundError:
            pass
        raise


class _Usage(Exception):
    """Erreur d'usage : rc 2."""


def _rc_cli(texte: str, *, none_permis: bool, option: str) -> int | None:
    if texte == "none":
        if none_permis:
            return None
        raise _Usage(f"{option} none : refusé pour cet outil (un rc de findings est requis)")
    try:
        valeur = int(texte, 10)
    except ValueError:
        raise _Usage(f"{option} : entier 0..255 ou none attendu, reçu {texte!r}") from None
    if not 0 <= valeur <= 255:
        raise _Usage(f"{option} : entier 0..255 attendu, reçu {texte!r}")
    return valeur


def _lire_candidats(chemin: str) -> list[str]:
    try:
        texte = Path(chemin).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _Usage(f"--candidates illisible : {exc.__class__.__name__}") from None
    return [ligne.rstrip("\r") for ligne in texte.split("\n") if ligne.rstrip("\r")]


class _Unique(argparse.Action):
    """Option à valeur unique : la répéter est une erreur d'usage (rc 2), jamais « la
    dernière gagne » (mesuré : ``--report A --report B … --out A`` réécrivait A)."""

    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace,
                 values: Any, option_string: str | None = None) -> None:
        if getattr(namespace, self.dest, None) is not None:
            raise argparse.ArgumentError(self, "répétée : une seule valeur est permise")
        setattr(namespace, self.dest, values)


def _parser() -> argparse.ArgumentParser:
    # allow_abbrev=False sur CHAQUE parseur : un sous-parseur ne l'hérite pas de son parent (sondé).
    parser = argparse.ArgumentParser(
        prog="scan_verdict.py",
        description=f"Verdict {SCHEMA} d'un rapport semgrep ou gitleaks. rc 0 = verdict rendu (ce n'est PAS une porte).",
        allow_abbrev=False,
    )
    sous = parser.add_subparsers(dest="commande", required=True)
    for outil in TOOL_NAMES:
        p = sous.add_parser(outil, help=f"adapter un rapport {outil}", allow_abbrev=False)
        p.add_argument("--report", action=_Unique, required=True,
                       help="rapport JSON de l'outil (absent/vide/illisible/trop gros = degraded)")
        p.add_argument("--findings-exit-code", action=_Unique, required=True,
                       help="rc de l'outil quand il trouve (N ou none)")
        p.add_argument("--exit-code", action=_Unique, help="rc réel de l'outil")
        p.add_argument("--candidates", action=_Unique, help="semgrep : fichiers candidats, un chemin par ligne")
        p.add_argument("--tool-version", action=_Unique, help="gitleaks : version de l'outil")
        p.add_argument("--config", action=_Unique, help="semgrep : chemin de config passé à semgrep")
        p.add_argument("--out", action=_Unique, help="fichier de sortie, écrit atomiquement (défaut : stdout) ; "
                                                     "jamais le fichier d'un autre argument (rc 2)")
    v = sous.add_parser("validate", help="valider un verdict (rc 1 si invalide)", allow_abbrev=False)
    v.add_argument("fichier")
    return parser


def _valider_fichier(chemin: str) -> int:
    try:
        texte = Path(chemin).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise _Usage(f"validate : fichier absent {chemin!r}") from None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"invalide : illisible ({exc.__class__.__name__})", file=sys.stderr)
        return 1
    try:
        verdict = json.loads(texte)
    except (ValueError, RecursionError):
        print("invalide : JSON illisible", file=sys.stderr)
        return 1
    erreurs = validate(verdict)
    for erreur in erreurs:
        print(f"invalide : {erreur}", file=sys.stderr)
    if erreurs:
        return 1
    print("ok")
    return 0


def _adapter(args: argparse.Namespace) -> dict[str, Any]:
    exit_code = None if args.exit_code is None else _rc_cli(args.exit_code, none_permis=False, option="--exit-code")
    if args.commande == "semgrep":
        if args.tool_version is not None:
            raise _Usage("--tool-version : sans objet pour semgrep (la version est lue dans le rapport)")
        findings_rc = _rc_cli(args.findings_exit_code, none_permis=True, option="--findings-exit-code")
        candidats = None if args.candidates is None else _lire_candidats(args.candidates)
        return from_semgrep(args.report, findings_rc=findings_rc, exit_code=exit_code,
                            candidates=candidats, config=args.config)
    if args.candidates is not None or args.config is not None:
        raise _Usage("--candidates / --config : sans objet pour gitleaks")
    findings_rc = _rc_cli(args.findings_exit_code, none_permis=False, option="--findings-exit-code")
    return from_gitleaks(args.report, findings_rc=findings_rc, exit_code=exit_code, version=args.tool_version)


def _meme_fichier(a: str, b: str) -> bool:
    """Vrai si ``a`` et ``b`` désignent le même fichier : realpath égaux, ou même
    fichier sur disque (lien dur, système de fichiers insensible à la casse)."""
    try:
        if os.path.realpath(a) == os.path.realpath(b):
            return True
        return os.path.samefile(a, b)
    except (OSError, ValueError):
        return False


# Jeton qu'argparse prend pour une VALEUR après une option (Python 3.14, _parse_optional) :
# sans tiret initial, « - » seul, nombre négatif, ou porteur d'une espace.
_NEGATIF = re.compile(r"-\.?\d")


def _est_valeur(jeton: str) -> bool:
    return not jeton.startswith("-") or jeton == "-" or bool(_NEGATIF.match(jeton)) or " " in jeton


def _jetons(argv: Sequence[str]) -> tuple[list[str], list[tuple[str, str]]] | None:
    """Lecture par JETON d'une ligne d'adaptateur, acceptée ou refusée par argparse :
    (valeurs de ``--out``, puis chaque AUTRE argument avec l'option qui le porte, au
    mieux). La valeur de droite d'un ``--opt=valeur`` compte ; ``--out`` et ses valeurs
    non. Après ``--``, tout est argument. None hors adaptateur (``validate`` : rien)."""
    if not argv or argv[0] not in TOOL_NAMES:
        return None
    sorties: list[str] = []
    autres: list[tuple[str, str]] = []
    reste = list(argv[1:])
    porteur: str | None = None  # option qui attend peut-être le jeton suivant
    i, fin_options = 0, False
    while i < len(reste):
        jeton, i = reste[i], i + 1
        if fin_options or _est_valeur(jeton):
            autres.append((porteur or f"l'argument n°{i}", jeton))
            porteur = None
        elif jeton == "--":
            fin_options, porteur = True, None
        elif jeton == "--out":
            if i < len(reste) and _est_valeur(reste[i]):
                sorties.append(reste[i])
                i += 1
            porteur = None
        else:
            nom, egal, droite = jeton.partition("=")
            if nom == "--out" and egal:
                sorties.append(droite)
                porteur = None
                continue
            autres.append((nom, jeton))
            if egal:
                autres.append((nom, droite))
            porteur = None if egal else nom
    return [s for s in sorties if s], autres


def _collision(lecture: tuple[list[str], list[tuple[str, str]]]) -> str | None:
    """L'option (ou la position) de l'argument dont ``--out`` désigne le fichier, sinon
    None. Comparé à CHAQUE autre argument, option connue, inconnue ou future : la
    répétition d'une entrée (``--report A --report B --out A``) est couverte."""
    sorties, autres = lecture
    for sortie in sorties:
        for option, valeur in autres:
            if valeur and _meme_fichier(sortie, valeur):
                return _texte(option)
    return None


def _refus_collision(option: str) -> str:
    return f"--out désigne le fichier de {option} : refusé, rien n'est retiré (l'entrée serait détruite)"


def _retirer(cible: str) -> bool:
    """Retire un ancien verdict ; False (et dit sur stderr) s'il reste en place."""
    try:
        Path(cible).unlink(missing_ok=True)
    except OSError as exc:
        print(f"échec : --out non retirée ({exc.__class__.__name__}) : {cible!r}", file=sys.stderr)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """rc 0 = verdict rendu (rapport absent compris) ; validate invalide = 1 ; usage = 2.

    Avec ``--out``, la cible est RETIRÉE avant tout travail : un échec, quel
    qu'il soit (usage compris), ne laisse jamais un ancien verdict lisible.
    Seule exception, refusée en usage (rc 2) AVANT tout retrait, sur la ligne
    acceptée comme sur celle qu'argparse refuse, par la MÊME lecture par jeton :
    un ``--out`` qui désigne le fichier d'un autre argument, option connue ou non
    — le retirer détruirait l'entrée, donc la preuve (constat F7,
    S-01M4W2N4C5M27ZYAX4X12GET98 ; étendu à tout argument par S1). Une option
    répétée ou abrégée est refusée (rc 2) ; sans collision, chaque ``--out``
    nommé est retiré.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 2
        lecture = _jetons(argv) if rc else None
        if lecture:
            option = _collision(lecture)
            if option:
                print(f"usage : {_refus_collision(option)}", file=sys.stderr)
            else:
                for sortie in lecture[0]:
                    _retirer(sortie)
        return rc
    try:
        if args.commande == "validate":
            return _valider_fichier(args.fichier)
        lecture = _jetons(argv)
        option = _collision(lecture) if lecture else None
        if option:
            raise _Usage(_refus_collision(option))
        if args.out and not _retirer(args.out):
            return 2
        verdict = _adapter(args)
        if args.out:
            _ecrire_atomique(Path(args.out), verdict)
        else:
            sys.stdout.write(_serialize(verdict))
        return 0
    except _Usage as exc:
        print(f"usage : {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError) as exc:
        print(f"échec : {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
