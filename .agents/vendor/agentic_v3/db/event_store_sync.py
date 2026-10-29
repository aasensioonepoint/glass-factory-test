"""Lecture des exports et sauvegarde préalable à la synchro V3.

Ce module ne porte pas de SQL : les requêtes et la transaction restent dans
``event_store.py``. Les chemins issus de runs/ ne sont jamais suivis.
"""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from agentic_v3.db import run_export


def obj_reconstruction_valide(obj: dict[str, Any]) -> bool:
    for cle in ("task_id", "agent_role", "event_type", "payload_json"):
        if not isinstance(obj.get(cle), str):
            return False
    try:
        int(obj.get("attempt", 0))
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def lire_exports(root: Path, resume: dict, chemins: dict,
                 parcourir: Callable, lire: Callable, json_module: Any) -> list[tuple]:
    """Lit les exports avec les mêmes compteurs et l'ordre inverse historique."""
    evenements: list[tuple] = []
    refuses: list[Path] = []
    erreurs: list[tuple[Path, OSError]] = []
    candidats = sorted(parcourir(root, refuses, erreurs), reverse=True)
    for chemin in refuses + [dossier for dossier, _exc in erreurs]:
        resume["fichiers_illisibles"] += 1
        chemins["fichiers_illisibles"].append(chemin)
    for chemin in candidats:
        verdict, brut = lire(chemin)
        if verdict == "trop_gros":
            resume["fichiers_trop_gros"] += 1
            chemins["fichiers_trop_gros"].append(chemin)
            continue
        if brut is None:
            resume["fichiers_illisibles"] += 1
            chemins["fichiers_illisibles"].append(chemin)
            continue
        for brute in brut.split(b"\n"):
            brute = brute.strip()
            if not brute:
                continue
            try:
                obj = json_module.loads(brute.decode("utf-8"))
            except json_module.JSONDecodeError:
                resume["lignes_illisibles"] += 1
                if chemin not in chemins["lignes_illisibles"]:
                    chemins["lignes_illisibles"].append(chemin)
                continue
            except (ValueError, RecursionError):
                resume["lignes_illisibles"] += 1
                if chemin not in chemins["lignes_illisibles"]:
                    chemins["lignes_illisibles"].append(chemin)
                continue
            if not isinstance(obj, dict) or not obj.get("ulid"):
                continue
            if not run_export.ulid_bien_forme(obj["ulid"]):
                resume["ignores"] += 1
                continue
            evenements.append((obj["ulid"], f"{chemin.parent.parent.name}/{chemin.parent.name}", obj))
    return evenements


def autorisee(partition: Path, racine: Path) -> bool:
    """Le kit demande un marqueur explicite pour chaque partition vivante."""
    if not (racine / ".agents" / "IS_THE_KIT").exists():
        return True
    marqueur = partition / "run" / "v3-auto-sync" / f"autorise-{partition.name}"
    return marqueur.is_file() and not marqueur.is_symlink()


def divergences(evenements: list[tuple], en_base: dict, champs: tuple,
                limite: int) -> tuple[int, list[str]]:
    """Nomme une fois chaque ULID dont une copie diffère de la base ou de la première ligne."""
    premiers: dict = {}
    divergents: set[str] = set()
    noms: list[str] = []
    def vue(obj: dict) -> dict:
        valeurs = {c: obj.get(c) for c in champs}
        try:
            valeurs["attempt"] = int(obj.get("attempt", 0))
        except (TypeError, ValueError, OverflowError):
            pass
        return valeurs
    for ulid, _tie, obj in evenements:
        precedent = premiers.setdefault(ulid, obj)
        if ulid in divergents:
            continue
        valeurs = vue(obj)
        precedent_vue = vue(precedent)
        if any(valeurs[c] != precedent_vue[c] for c in champs
               if c != "created_at" or (obj.get(c) is not None and precedent.get(c) is not None)) or (
            ulid in en_base and any(valeurs[c] != en_base[ulid][c] for c in champs
                                    if c != "created_at" or obj.get(c) is not None)
        ):
            divergents.add(ulid)
            if len(noms) < limite:
                noms.append(ulid)
    return len(divergents), noms


def _dossier_sans_lien(chemin: Path) -> None:
    """N'accepte que des dossiers réels sous la partition existante."""
    if chemin.is_symlink():
        raise OSError(f"lien refuse : {chemin}")
    chemin.mkdir(mode=0o700, exist_ok=True)
    if not stat.S_ISDIR(chemin.lstat().st_mode):
        raise OSError(f"dossier refuse : {chemin}")


def sauvegarder(partition: Path, base: Path, version: Callable[[sqlite3.Connection], int],
               identite: int) -> Path:
    """Copie SQLite cohérente avant première importation, avec contrôle de version.

    Une copie achevée est conservée même si la transaction d'import échoue ;
    une ouverture ultérieure peut ainsi reprendre sans effacer la sauvegarde.
    """
    dossier = partition / "run" / "v3-auto-sync"
    _dossier_sans_lien(dossier)
    backups = dossier / "backups"
    _dossier_sans_lien(backups)
    for orphelin in backups.glob(".v3-*.db.tmp"):
        try:
            if time.time() - orphelin.lstat().st_mtime > 3600:
                orphelin.unlink(missing_ok=True)
        except FileNotFoundError:
            pass  # Une autre session a déjà nettoyé cet orphelin.
    copies = sorted(p for p in backups.glob("v3-*.db")
                    if re.fullmatch(r"v3-\d+-\d{8}T\d{12}Z-[0-9a-f]{32}\.db", p.name))
    for copie in copies:
        if copie.is_symlink() or not stat.S_ISREG(copie.lstat().st_mode):
            raise OSError(f"sauvegarde refusee : {copie}")
    memes = [copie for copie in copies if copie.name.startswith(f"v3-{identite}-")]
    if memes:
        return memes[-1]
    horodate = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    cible = backups / f"v3-{identite}-{horodate}-{uuid.uuid4().hex}.db"
    tmp = backups / f".{cible.name}.tmp"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        for _ in range(3):
            source = run_export._ouvrir_base_sqlite(base)
            destination = sqlite3.connect(":memory:")
            try:
                avant = version(source)
                source.backup(destination)
                apres = version(source)
                octets = destination.serialize() if avant == apres else None
            finally:
                destination.close()
                source.close()
            if avant == apres:
                os.ftruncate(fd, 0)
                for offset in range(0, len(octets), 1024 * 1024):
                    bloc = memoryview(octets)[offset:offset + 1024 * 1024]
                    while bloc:
                        bloc = bloc[os.write(fd, bloc):]
                os.fsync(fd)
                os.close(fd)
                fd = -1
                verif = sqlite3.connect(tmp.as_uri() + "?mode=ro", uri=True)
                try:
                    if verif.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise OSError(f"sauvegarde illisible : {tmp}")
                finally:
                    verif.close()
                os.replace(tmp, cible)
                for ancienne in sorted(copies + [cible], key=lambda p: p.name.split("-")[-2])[:-3]:
                    ancienne.unlink(missing_ok=True)
                return cible
        raise OSError("base modifiee durant trois sauvegardes")
    finally:
        if fd >= 0:
            os.close(fd)
        tmp.unlink(missing_ok=True)
