# Third-party notices

This kit includes material adapted from, or vendored from, the third-party works listed below. Each notice is reproduced as its licence requires.

## ECC — affaan-m/ECC

- Source: https://github.com/affaan-m/ECC, commit `6f1881ae` (v2.2.3).
- Licence: MIT.
- What is adapted (rewritten, never copied verbatim):
  - the convention sheets `.agents/ref/CONVENTIONS_{java,kotlin,dotnet,php,ruby,dart,rust,swift,cpp}.md`, from ECC's `agents/*-reviewer.md`, `agents/*-build-resolver.md` and `rules/<lang>/` ;
  - `.agents/security/unicode_scan.py`, inspired by ECC's `affaan-m/ECC/scripts/ci/check-unicode-safety.js` ;
  - `.agents/bin/config_qualite_guard.py`, inspired by ECC's `affaan-m/ECC/scripts/hooks/config-protection.js` ;
  - the git hook-bypass guard in `.codex/hooks/safe_bash_hooks.py` (and its Gemini twin and Claude counterpart), inspired by ECC's `affaan-m/ECC/scripts/hooks/block-no-verify.js` ;
  - the single-source agent layout (`agents/` rendered to each host by `.agents/bin/render_hosts.py`), inspired by ECC's `scripts/lib/install-targets/` ;
  - the `seo-specialist` agent (`agents/seo-specialist.md`) and the `seo` skill (`.agents/skills/seo/SKILL.md`), from ECC's `agents/seo-specialist.md` and `skills/seo/SKILL.md` — the review scope and the `[SEV] Location / Issue / Fix` report shape are adapted; the deterministic measure they run first, `.agents/bin/seo_mesure.py`, is this kit's own.

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Not taken from ECC, on purpose: `skills/osint-investigation` (CC-BY-SA 4.0, ShareAlike), and the skills marked `origin: community` (provenance not verified).

## Vendored skills

These keep their own licence file next to them; nothing is changed in their terms.

| Path | Licence | Holder | Licence file |
|---|---|---|---|
| `.agents/skills/vendor/composition-patterns/` | MIT | Vercel Labs | `LICENSE`, `NOTICE` |
| `.agents/skills/vendor/react-best-practices/` | MIT | Vercel Labs | `LICENSE`, `NOTICE` |
| `.agents/skills/vendor/web-interface-guidelines/` | MIT | Vercel Labs (2025) | `LICENSE` |
| `.agents/skills/vendor/playwright-best-practices/` | MIT-style | Currents Software Inc. (2026) | `LICENSE.md` |

## The kit itself

The kit declares no licence of its own (`pyproject.toml`, pilot decision of 2026-09-14). This file only covers third-party material.
