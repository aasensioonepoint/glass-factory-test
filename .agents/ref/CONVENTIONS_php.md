# PHP conventions — canonical (shared by Claude Code, Codex, Copilot)

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (PHP version, framework, Composer scripts, repo
layout) belong in a §2 of that project's own copy, each with its ledger id — not here.

**GUARANTEE — a §2 written by an adopting project SURVIVES a template refresh.**
Without this written down the invitation above is a trap: it asks you to write
something the next sync might erase, and nobody would find out until it was gone.
What holds, by relevé rather than by promise:

- **§1 belongs to the kit, §2 belongs to the project.** §1 is rewritten wholesale
  by kit-side syncs; nothing in the kit ever writes §2.
- **No kit mechanism writes this file inside an adopting project.**
  `sync_template.py` runs `main → template/starter-kit` INSIDE the kit repo only,
  and the docs-sync flow never touches `.agents/ref/` at all.
- **A consumer refresh is a MERGE, never a copy-overwrite** (L-015): a three-way
  merge keeps an added §2, or raises a conflict — it never deletes it silently.
- **The honest limit**: it is pinned by `.agents/evals/test_conventions_contract.py`.

**Framework layer: NO kit skill carries Laravel or Symfony.** The `## php` section of
`DOCS_REGISTRY.md` lists their versioned docs, fetched at need. This sheet is the SHORT gate layer,
and the language-wide rules below hold under any framework.

## Language & types

- `declare(strict_types=1);` at the top of every non-view file: without it PHP coerces `"12abc"` to a
  scalar parameter in silence, so a type hint documents a contract it does not enforce.
- Typed parameters, return types and typed properties on every new public method; a union type
  rather than `mixed` when the set is known: `mixed` switches the static analyser off for that value.
- `readonly` on promoted constructor properties never reassigned, `final` on a class not designed
  for inheritance: each closes a mutation or extension path nobody planned for.
- A DTO or value object, not an associative array, for data that crosses a service boundary: an
  array shape is checked by no runtime and drifts between producer and consumer unseen.

## Boundaries & validation

- Request input is validated at the framework edge (`FormRequest`, Symfony Validator, an explicit
  DTO) and only the validated payload goes further — never `$request->all()` into `create()`, which
  is mass assignment; models whitelist `$fillable`, never `$guarded = []`.
- Every dynamic query is parameterised (PDO prepared statements, query builder bindings);
  `DB::raw()` / `whereRaw()` never receive user input: interpolation is SQL injection.
- An exceptional state THROWS; `false`/`null` as a hidden error channel is refused in new code,
  because the caller that forgets the check proceeds with a wrong value.
- `catch (\Exception $e) {}` never stays empty: log and handle, or let it rise — a swallowed
  exception turns a failure into a silent wrong result.
- Refused outright: `eval`, `unserialize()` on untrusted data (object injection), `shell_exec` /
  `exec` / `system` on unvalidated input, raw `{!! !!}` output of user data, MD5/SHA1 for passwords
  (`password_hash()` / `password_verify()`), secrets in committed config.

## Guards & tests

- PHPUnit by default; Pest only where the project already configured it, and never both in one
  suite: two runners split the coverage and the CI command.
- At the gate the suite runs BARE, exactly as CI does (`vendor/bin/phpunit`). The dev and its
  judges run their `BANCS:` line (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`):
  `tests/Unit/FooTest.php::testBar` is `vendor/bin/phpunit tests/Unit/FooTest.php --filter '/::testBar( |$)/'`
  — the filter is a regex over `Class::method`, and the `( |$)` keeps `testBarBaz` out while letting
  a data-provider case (`testBar with data set #0`) in.
- Unit tests stay apart from framework/database integration tests, and fixtures come from factories
  or builders: a hand-written fixture array rots with the schema it mirrors.
- `dd()`, `dump()`, `var_dump()` never reach a commit: they print into a live response.

## Tooling

- One formatter (PHP-CS-Fixer or Laravel Pint, PSR-12) and one static analyser (PHPStan or Psalm),
  run through Composer scripts committed to the repo, so local and CI run the SAME command.
- `composer.lock` is committed for an application: without it two installs resolve two dependency
  sets and the build CI validated is not the one deployed.
- SCA: `composer.json` is NAMED as not covered by `sca-scan.sh` (`name_uncovered`, T-00000488) when
  it sits at the ROOT LOOKED AT, and is NOT scanned; a lone `composer.lock` without `composer.json`
  is not even named. `composer audit` is the pending work T-00000314. Do NOT read a GO verdict on a
  PHP project as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested php conventions.
