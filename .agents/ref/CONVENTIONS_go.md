# Go conventions — canonical (shared by Claude Code, Codex, Copilot)

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (module path, framework version, repo layout)
belong in a §2 of that project's own copy, each with its ledger id — not here.

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

**Framework / idiom layer lives in the `go-idiomatic` skill and `## go` of `DOCS_REGISTRY.md` — the
rules here are NOT repeated there. Read both.** This sheet is the SHORT gate layer; the skill carries
errors-as-values, context propagation, goroutine ownership and table tests in full.

## Language & types

- `gofmt` and `go vet` are non-negotiable: `gofmt` settles form, `go vet` settles part of the
  substance, so neither is a matter of taste and CI runs both.
- `go.mod` carries the `go` directive and the build RESPECTS it: the directive changes language
  semantics, so a build on a different toolchain silently compiles a different language.

## Boundaries & validation

- An error is a VALUE, returned not thrown, and the decision is at the caller on the next line.
- Wrap with `%w` and match with `errors.Is`/`errors.As`: a string-formatted error (`%v`) severs the
  chain, so no caller upstream can branch on the cause it needs.

## Guards & tests

- At the gate, `go test ./...` runs BARE, exactly as CI does — never a hand-picked subset that
  green-lights a package the full run would fail. The dev and its judges run their `BANCS:` line
  (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`): `<pkg>/<f>_test.go::TestX` is
  `go test ./<pkg> -run '^TestX$'`.
- `-race` on any code that starts a goroutine: a data race is invisible to a serial test and rehearses
  as a production-only flake.

## Tooling

- `go.sum` is committed and `GOFLAGS=-mod=mod` is forbidden in CI: `-mod=mod` lets a build rewrite the
  module graph, so CI would validate a dependency set the commit never pinned.
- SCA: `go.mod` is NAMED as not covered by `sca-scan.sh` (T-00000488) when it sits at the ROOT LOOKED
  AT — bare form, the host hooks AND `/audit` — and is NOT scanned; a `go.mod` in a sub-folder that is
  not a discovered module is not even named; `govulncheck` is the pending work T-00000312. Do NOT read
  a GO verdict on a Go module as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested go conventions.
