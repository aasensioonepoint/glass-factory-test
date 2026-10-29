"""Closed document channel for the distributable template."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
import sys

SOURCE = ".agents/adopter-docs/"
DESTINATIONS = ("README.md", "CHANGELOG.md", "docs/usage.html")
TAG_RE = re.compile(
    r"template/v(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.dev[0-9]+)?)-"
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\Z"
)
REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


def doc_targets(paths: dict[str, str] | set[str]) -> dict[str, str]:
    """Map present adopter sources to their three public destinations."""
    sources = {path for path in paths if path.startswith(SOURCE)}
    allowed = {SOURCE + destination for destination in DESTINATIONS}
    unexpected = sorted(sources - allowed)
    if unexpected:
        raise ValueError(f"document source outside the closed set: {unexpected[0]}")
    return {destination: SOURCE + destination for destination in DESTINATIONS
            if SOURCE + destination in sources}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          check=False, timeout=20)


def _object(root: Path, ref: str, path: str) -> bytes | None:
    result = _git(root, "show", f"{ref}:{path}")
    return result.stdout if result.returncode == 0 else None


def _tagger_date(root: Path, tag_object: str) -> str | None:
    kind = _git(root, "cat-file", "-t", tag_object)
    if kind.returncode != 0:
        raise ValueError("objet du tag introuvable")
    if kind.stdout.strip() != b"tag":
        return None  # Lightweight tag: only the name and CHANGELOG dates exist.
    payload = _git(root, "cat-file", "-p", tag_object)
    if payload.returncode != 0:
        raise ValueError("objet du tag illisible")
    for line in payload.stdout.split(b"\n\n", 1)[0].splitlines():
        if line.startswith(b"tagger "):
            match = re.search(rb" ([0-9]+) ([+-])([0-9]{2})([0-9]{2})$", line)
            if match is None:
                raise ValueError("taggerdate illisible")
            seconds = int(match.group(1))
            sign = 1 if match.group(2) == b"+" else -1
            offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
            return datetime.fromtimestamp(seconds, timezone(sign * offset)).date().isoformat()
    raise ValueError("tag annoté sans taggerdate")


def fraicheur(root: Path, ref: str, tag: str, source: str,
              tag_object: str | None = None) -> tuple[int, str]:
    """Check the published commit and source branch against its sync anchor."""
    match = TAG_RE.fullmatch(tag.removeprefix("refs/tags/"))
    if match is None or REF_RE.fullmatch(ref) is None or REF_RE.fullmatch(source) is None:
        return 2, "nom de tag, référence ou branche source invalide"
    commit = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    source_ref = f"refs/heads/{source}"
    source_commit = _git(root, "rev-parse", "--verify", "--quiet", f"{source_ref}^{{commit}}")
    if commit.returncode != 0 or source_commit.returncode != 0:
        return 2, "commit publié ou branche source introuvable"
    published = commit.stdout.decode("ascii").strip()
    source_sha = source_commit.stdout.decode("ascii").strip()
    # Same first-parent anchor reader as sync_template.py, on the pushed commit.
    from sync_template import GitError, _last_synced_commit

    try:
        anchor = _last_synced_commit(root, published)
    except GitError as exc:
        return 2, f"historique de synchronisation illisible : {exc}"
    if anchor is None:
        return 2, "aucune ancre de synchronisation sur le commit publié"
    anchor_source = anchor[2]
    source_diff = _git(root, "diff", "--quiet", anchor_source, source_sha, "--", SOURCE)
    if source_diff.returncode == 1:
        return 1, f"sources adoptant modifiées depuis l'ancre {anchor_source[:8]} sur {source}"
    if source_diff.returncode != 0:
        return 2, "comparaison des sources adoptant impossible"
    for destination in DESTINATIONS:
        expected = _object(root, anchor_source, SOURCE + destination)
        actual = _object(root, published, destination)
        if expected is None or actual is None:
            return 1, f"document périmé : {destination} ou sa source absente à l'ancre"
        if actual != expected:
            return 1, f"document périmé : {destination} diffère de l'ancre {anchor_source[:8]}"
    changelog = _object(root, published, "CHANGELOG.md")
    assert changelog is not None
    heading = f"## {match.group('version')} — {match.group('date')}"
    first_version = next((line for line in changelog.decode("utf-8", errors="replace").splitlines()
                          if line.startswith("## ")), None)
    if first_version != heading:
        return 1, f"date/version du CHANGELOG : tête attendue {heading!r}"
    if tag_object is not None:
        if re.fullmatch(r"[0-9a-f]{40,64}", tag_object) is None:
            return 2, "objet du tag invalide"
        try:
            tagged = _tagger_date(root, tag_object)
        except ValueError as exc:
            return 2, str(exc)
        if tagged is not None and tagged != match.group("date"):
            return 1, f"taggerdate {tagged} différente de la date publiée {match.group('date')}"
    return 0, f"docs fraîches pour {tag} @ {published[:8]}"


def changelog_section(root: Path, section: str, version: str, date: str) -> str:
    """Render only reader facing entries from one kit CHANGELOG section."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:\.dev[0-9]+)?", version):
        raise ValueError("version invalide")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date) is None:
        raise ValueError("date invalide")
    try:
        datetime.fromisoformat(date).date()
    except ValueError as exc:
        raise ValueError("date invalide") from exc
    lines = (root / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    # A whole version (`## <section>`) keeps every `###` group; a `###` name keeps one.
    whole = f"## {section}" in lines
    heading = f"## {section}" if whole else f"### {section}"
    if heading not in lines:
        raise ValueError(f"section du kit absente : {section}")
    current: str | None = None if whole else section
    groups: dict[str, list[str]] = {}
    title: str | None = None
    for line in lines[lines.index(heading) + 1:]:
        if line.startswith("## ") or (line.startswith("### ") and not whole):
            break
        if line.startswith("### "):
            current, title = line[4:], None
        elif line.startswith("**") and line.endswith("**"):
            title = line
        elif line.startswith("Ce que ça change pour vous :"):
            if title is None or current is None:
                raise ValueError("entrée sans titre")
            groups.setdefault(current, []).extend((title, line, ""))
            title = None
    if not groups:
        raise ValueError(f"section sans entrée adoptant : {section}")
    body = [part for name, entries in groups.items() for part in (f"### {name}", "", *entries)]
    return "\n".join((f"## {version} — {date}", "", *body)).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    # T-01M5QC86XN : nom anglais en tête, ancien nom gardé en alias, `dest` ancien explicite.
    mode.add_argument("--freshness", "--fraicheur", dest="fraicheur", action="store_true",
                      help="check the published commit and source branch against the sync anchor "
                           "(alias: --fraicheur)")
    mode.add_argument("--changelog", action="store_true")
    parser.add_argument("--ref")
    parser.add_argument("--tag")
    parser.add_argument("--tag-object")
    parser.add_argument("--source", default="develop")
    parser.add_argument("--section")
    parser.add_argument("--version")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.fraicheur:
        if not args.ref or not args.tag:
            parser.error("--fraicheur exige --ref et --tag")
        code, message = fraicheur(root, args.ref, args.tag, args.source, args.tag_object)
        print(f"FRAICHEUR {code}: {message}")
        return code
    if not args.section or not args.version or not args.date:
        parser.error("--changelog exige --section, --version et --date")
    try:
        print(changelog_section(root, args.section, args.version, args.date), end="")
    except (OSError, ValueError) as exc:
        print(f"CHANGELOG REFUSÉ: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
