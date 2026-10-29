"""GLASS refonte (T-00001243) — what the SERVED bundle must hold, read off its bytes.

The React sources are judged by `npm test` (node, DEV-LOCAL, outside the gate:
T-505). This file is the part of the refonte that the GATE sees: it reads the
vendored `.agents/ui/` exactly as `dashboard.py` serves it, so a rebuild that
drops one of these properties turns `pytest` red without anyone running node.

Five properties, each one with the mutant that must turn it red:
  1. REDUCED MOTION WINS (C6). `@media (prefers-reduced-motion:reduce)` carries a
     universal `animation:none!important` — the per-selector rule it replaced lost
     to `.host.live .on` by specificity and the transport dot kept pulsing on all
     twelve routes. Mutant M3: rule removed.
  2. NO MAQUETTE SAMPLE DATA in the bundle (C2). The maquettes carry example
     figures in their `<script type="text/x-dc">`; none may ship. The list is
     CLOSED and named in the plan. Mutant M1: « 1 232 » hard-coded.
  3. TWO FONT ROUTES, BOTH GEIST, THE LICENCE BESIDE THEM AND NOT A ROUTE
     (S-00004649). Mutant M6 (a Geist route removed) is caught by
     `test_every_font_face_in_the_bundle_has_a_served_route` in test_dashboard.py;
     the shape of the table is pinned here.
  4. THE SWAP DOES NOT SHIFT THE LAYOUT (C10): the metric-matched local
     fallbacks ship in the stylesheet.
  5. THE SNAPSHOT NAMES `depends_on` (S-00004739, option b) and never rewrites
     TASKS.json. Mutant: the `board_serves` line removed from `build_snapshot`.

What it cannot see: anything that needs a browser (computed styles, focus, axe,
real motion) — that is `e2e/glass.spec.ts`, run by hand.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

import test_dashboard as td
from test_dashboard import _redirect  # noqa: F401 — autouse fixture: env and caches on tmp_path

dashboard = td.dashboard
UI = dashboard._UI_DIR
CSS = (UI / "assets" / "app.css").read_text(encoding="utf-8")
JS = (UI / "assets" / "app.js").read_text(encoding="utf-8")
HTML = (UI / "index.html").read_text(encoding="utf-8")

# The plan's CLOSED list (C2): sample figures and sentences of the maquettes.
MAQUETTE_SAMPLES = (
    "1 232", "1 811", "$449.69", "7 449", "1 353 M", "20 425 / 35 315", "$810.00",
    "261 PLANS", "6 agents", "T-00000305 · timeout socket SCA",
    # GLASS v2 frise (docs/design/2026-10-23-glass-frise/, annex § 5 C13)
    "×4,3", "×3,6", "×5,2", "5 lots démarrés sans journal chrono", "3 h 13", "2 h 29, est. 1 h 03",
    "8 tâches · 3 avec chrono",
)


def _spaces_variants(sample: str) -> set[str]:
    """A figure can ship with a plain, a no-break or a narrow no-break space —
    `toLocaleString("fr-FR")` emits U+202F — so each sample is searched in all
    three spellings, and in its NFKC form."""
    out = {sample}
    for sp in (" ", " "):
        out.add(sample.replace(" ", sp))
    return out | {unicodedata.normalize("NFKC", s) for s in out}


def test_reduced_motion_is_universal_and_important_in_the_served_css():
    rule = re.search(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{([^{}]*)\{([^}]*)\}", CSS)
    assert rule, "aucune règle @media (prefers-reduced-motion:reduce) dans le app.css servi"
    found = False
    for m in re.finditer(r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{([^{}]*)\{([^}]*)\}", CSS):
        selectors = {s.strip() for s in m.group(1).split(",")}
        body = m.group(2).replace(" ", "")
        if "*" in selectors and "animation:none!important" in body and "transition:none!important" in body:
            found = True
    assert found, ("la règle universelle `*{animation:none!important;transition:none!important}` sous "
                   "prefers-reduced-motion manque : un sélecteur plus spécifique (`.host.live .on`) "
                   "rallumerait la pulsation")


def test_no_maquette_sample_figure_ships_in_the_bundle():
    shipped = {name: text for name, text in (("app.js", JS), ("app.css", CSS), ("index.html", HTML))}
    leaks = []
    for sample in MAQUETTE_SAMPLES:
        for variant in _spaces_variants(sample):
            for name, text in shipped.items():
                if variant in text:
                    leaks.append(f"{name}: {variant!r}")
    assert not leaks, f"donnée d'exemple des maquettes dans le bundle servi : {sorted(set(leaks))}"


def test_font_routes_are_exactly_the_two_geist_files_and_the_licence_is_not_one():
    fonts = {route: segs for route, (segs, ct) in dashboard._ALLOWED_STATIC_ROUTES.items() if ct == "font/woff2"}
    assert sorted(fonts) == ["/fonts/geist-variable.woff2", "/fonts/geistmono-variable.woff2"], sorted(fonts)
    assert not any(route.endswith(".txt") for route in dashboard._ALLOWED_STATIC_ROUTES), \
        "la licence OFL est devenue une route — elle doit rester hors de la surface lue"
    licence = UI / "fonts" / "OFL-Geist.txt"
    text = licence.read_text(encoding="utf-8")
    assert text.startswith("Copyright (c) 2023 Vercel"), "OFL-Geist.txt n'est pas la licence du paquet geist"
    assert "SIL Open Font License, Version 1.1" in text
    # Exactly what ships beside the license: the two routed faces, nothing stale.
    on_disk = sorted(p.name for p in (UI / "fonts").iterdir())
    assert on_disk == ["OFL-Geist.txt", "geist-variable.woff2", "geistmono-variable.woff2"], on_disk


def test_the_stylesheet_declares_geist_variable_and_no_remote_font_host():
    faces = re.findall(r"@font-face\s*\{([^}]*)\}", CSS)
    families = {re.search(r"font-family:\s*['\"]?([^;'\"]+)", f).group(1).strip() for f in faces}
    assert {"Geist", "Geist Mono"} <= families, families
    for face in faces:
        if "/fonts/" in face:
            assert re.search(r"font-weight:\s*100 900", face), f"face non variable : {face[:80]}"
    for host in ("fonts.googleapis", "fonts.gstatic"):
        assert host not in CSS and host not in JS and host not in HTML, f"{host} dans le bundle servi"


def test_the_font_swap_has_metric_matched_local_fallbacks():
    fallbacks = {f for f in re.findall(r"@font-face\s*\{([^}]*)\}", CSS) if "local(" in f}
    assert len(fallbacks) == 2, f"{len(fallbacks)} face(s) de repli locale(s) — C10 en attend deux"
    for face in fallbacks:
        for prop in ("size-adjust", "ascent-override", "descent-override", "line-gap-override"):
            assert prop in face, f"repli sans {prop} : la bascule de police décalerait la mise en page"
    for token, family in (("--font", "Geist"), ("--mono", "Geist Mono")):
        stack = re.search(rf"{token}:\s*['\"]?{family}['\"]?\s*,\s*['\"]?{family} Fallback['\"]?", CSS)
        assert stack, f"la pile {token} ne passe pas par « {family} Fallback » juste après {family}"


def test_the_six_global_kpi_tiles_are_gone_from_the_served_bundle():
    # HANDOFF rule 2 — « supprimer la rangée des 6 KPI répétée sur chaque page ».
    assert not re.search(r"\.kpis?\b", CSS), "règle .kpi/.kpis encore servie"
    assert '"kpis"' not in JS and "`kpi " not in JS, "le composant KpiStrip est encore dans le bundle"


def test_the_snapshot_names_depends_on_and_never_rewrites_the_store(tmp_path):
    # S-00004739: the board's verbs DROP an emptied `depends_on` (tasks_verbes, tasks_graphe), so a
    # board with no dependency carries no key at all — the client could not tell it from a server that
    # does not serve the key. The server says it in `board_serves`; the board section stays the store.
    store = tmp_path / "project" / ".agents" / "state" / "board" / "TASKS.json"
    store.parent.mkdir(parents=True)
    stored = {"next_id": 3, "epics": [{"id": "E-01", "titre": "une epic"}], "tasks": [
        {"id": "T-00000001", "state": "pending", "task": "sans amont", "epic": "E-01"},
        {"id": "T-00000002", "state": "running", "task": "sans amont non plus", "epic": "E-01"},
    ]}
    store.write_text(json.dumps(stored), encoding="utf-8", newline="\n")
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    snap = dashboard.build_snapshot(tmp_path / "project")
    assert snap["board"]["status"] == "ok", snap["board"]
    assert snap.get("board_serves") == ["depends_on"], f"marqueur absent : {snap.get('board_serves')!r}"
    assert snap["board"]["data"]["tasks"] == stored["tasks"], "tâches servies autrement que stockées"
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before, "TASKS.json réécrit par le snapshot"
