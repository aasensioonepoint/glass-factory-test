---
name: seo
description: Technical SEO review of a page or a site — measure first with the deterministic .agents/bin/seo_mesure.py (JSON-LD against schema.org, title, description, h1, canonical, noindex, lang, and Lighthouse SEO only when the project installed it), then advise; report as [SEV] Location / Issue / Fix, MEASURED kept apart from ADVICE, unmeasured legs said. Read before a technical SEO review, or before citing any SEO number.
---

# seo — technical SEO, measured before it is advised

Working language: `.agents/ref/WORKING_LANGUAGE.md` — this page is English;
what goes to the pilot stays French, literals verbatim.

This is a reference and a measuring contract, not a marketing method. The review
workflow lives in the `seo-specialist` agent; `design-review` calls it when a task
touches public pages. The `[SEV] Location / Issue / Fix` report shape is adapted
from ECC (MIT, see `THIRD_PARTY_NOTICES.md`); the measurement is this kit's own.

## READ WHEN

- a task touches a public page: HTML templates, SSR routes, `sitemap.xml`,
  `robots.txt`, `<head>` metadata, JSON-LD;
- before writing ANY SEO number (a score, a length, a threshold) — read the
  honesty section first.

## Where there is no official number — do not invent one

- **`<title>` length**: Google publishes no character limit; the snippet is cut
  by rendered width, not by a count. The kit's `60` (`TITRE_MAX` in
  `seo_mesure.py`) is a HEURISTIC that raises a `LOW`, never a defect of
  indexing. Say "heuristic" when citing it.
- **Meta description length**: no official limit either; the script does not
  judge it.
- **One `<h1>`**: a convention for a readable outline. The script reports a
  second `<h1>` as `LOW`, no `<h1>` at all as `MEDIUM`; neither blocks indexing.
- **Required JSON-LD fields**: the script checks the KIT's closed subset (below).
  Google's rich-result eligibility differs per type and lives on its page —
  read it there (`.agents/ref/DOCS_REGISTRY.md` § seo) before claiming a page is
  "eligible".
- **Core Web Vitals**: the thresholds are NOT restated here. Cite them from
  `.agents/skills/frontend-fidelity/SKILL.md` § Core Web Vitals — one source,
  never a second copy that drifts.
- **Rankings, traffic, "SEO score" promises**: out of scope. Nothing here
  measures them, so nothing here may claim them.

## Measure first

```
python3 .agents/bin/seo_mesure.py <file.html | directory> [--json <out.json>] [--delai-lighthouse <s>]
```

Exit codes: `0` no HIGH finding · `1` at least one HIGH · `2` usage or refusal
(missing target, symbolic link, directory without HTML, refused `--json` path),
or NOTHING read (every file too large or unreadable — nothing measured is never
green). Measure the RENDERED output (the built `dist/`, a saved SSR response),
not a template with placeholders: a client-rendered page is judged on its
skeleton only.

Three legs, each stated in the output as `jambe <name> : mesuré … | non mesuré : <why>`:

| Leg | What it checks | Severity |
|---|---|---|
| `jsonld` | each `<script type="application/ld+json">` parses (`NaN`/`Infinity` refused); `@context` is schema.org; `@type` present; required fields of the closed subset | invalid, no context, no type, missing field: HIGH · type outside the subset: INFO "non vérifié" · no JSON-LD on the page: INFO |
| `balises` | `<title>` absent/empty (HIGH), several (MEDIUM), over 60 chars (LOW, heuristic); `<meta name="description">` absent/empty (MEDIUM); `<h1>` none (MEDIUM) or several (LOW); `<link rel="canonical">` absent (LOW), several or empty (MEDIUM); `noindex`/`none` in `<meta name="robots|googlebot">` (HIGH); `lang` missing on `<html>` (MEDIUM) | as listed |
| `lighthouse` | Lighthouse category SEO, score and failed audits | below 50: MEDIUM · 50–89: LOW · 90+: INFO |

The closed subset of the `jsonld` leg (`TYPES_REQUIS`): `Organization` name ·
`WebSite` name, url · `Article` and `BlogPosting` headline, datePublished ·
`Product` name · `BreadcrumbList` itemListElement · `FAQPage` mainEntity. Nodes
of a `@graph` are checked; nested nodes (an `author` inside an `Article`) are not.

**Lighthouse bound.** Lighthouse category SEO is played only if the PROJECT
installed it (a `lighthouse` executable on the `PATH`): `npx lighthouse` is a
network access, forbidden to the kit. Otherwise the leg is `non mesuré :
lighthouse absent du PATH`, and the report SAYS so — never a score from memory.
It runs on ONE file (a directory leaves the leg `non mesuré`), under a time bound
(`--delai-lighthouse`, default 180 s). Chrome then loads the page, including the
remote resources it references — that load is Chrome's, not the script's.

Reading bounds, said by the script: a file over 4 MiB is not read; a symbolic
link is never followed; `node_modules/` and `.git/` are not walked; past 500
HTML files the rest is not read.

## Checklist — what the measure does not cover, read by hand

`source: à vérifier` — the points below were written on 2026-10-21 without
re-opening the registry pages (no network on that task). Open the page named in
the registry before quoting one of them as Google's rule.

Indexability:
- `robots.txt` at the site root: no `Disallow` over the public pages; the
  sitemap is declared there. A `robots.txt` block is not a `noindex` — a
  blocked URL can still be indexed from links.
- `sitemap.xml`: absolute canonical URLs only, no redirected or `noindex` URL.
- HTTP: the public pages answer `200`; moved pages `301`; no redirect chain.
  Read status codes from a served build when the project can serve one; never
  from memory.
- The canonical points at itself or at the true original, absolute URL.

Tags:
- `hreflang`: each language version lists every other one AND itself, with
  absolute URLs; a missing return link voids the pair.
- Open Graph: `og:title`, `og:description`, `og:image` (absolute URL), `og:url`.

Structured data:
- JSON-LD only describes what is VISIBLE on the page; marking up content the
  user cannot see is the classic cause of a manual action.
- Validate with the schema.org definition of the type and Google's structured
  data pages (registry § seo).

Performance:
- Core Web Vitals at p75: the thresholds and the "measure the field, not only
  the lab" rule are in `.agents/skills/frontend-fidelity/SKILL.md`.

## Report format

```
MESURÉ (seo_mesure.py, rc <n>, <date>)
[HIGH] site/blog/post.html:12 — `<meta name="robots">` interdit l'indexation (noindex) — retirer noindex d'une page publique
[MEDIUM] site/index.html — `lang` absent de `<html>` — déclarer la langue
CONSEIL (lecture, non mesuré)
[MEDIUM] public/robots.txt:3 — Disallow: /blog/ masque les billets — lever la règle pour /blog/
NON MESURÉ
lighthouse — absent du PATH ; hreflang — aucune variante de langue fournie
```

Every finding carries its severity, a `file:line` or a URL, the issue, and a
concrete fix. MEASURED lines quote the script's output; ADVICE lines are the
reviewer's reading and say so; the NON MESURÉ block is never omitted — an
unmeasured leg left out turns a clean report into a lie.

## Sources

`.agents/ref/DOCS_REGISTRY.md` § seo — schema.org, Google Search Central
(structured data, robots meta, canonical), Lighthouse SEO audits. Fetch the page
at need; never paste it.
