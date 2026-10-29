# Rust conventions — canonical (shared by Claude Code, Codex, Copilot)

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (edition, MSRV, async runtime, workspace layout)
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

**Idiom layer: NO kit skill carries Rust.** The `## rust` section of `DOCS_REGISTRY.md` lists the
book, `std`, Cargo and Clippy references, fetched at need. This sheet is the SHORT gate layer; the
rules below hold for a library, a CLI or an async service alike.

## Language & types

- The `edition` and `rust-version` of `Cargo.toml` are read BEFORE writing: the edition changes
  idioms and lints, and syntax newer than the declared MSRV compiles on your toolchain and not on CI's.
- Borrow by default — `&str` over `String`, `&[T]` over `Vec<T>` in parameters — and a `.clone()`
  added to quiet the borrow checker states why: a clone that hides a lifetime problem moves it.
- `Result` and `?` on every recoverable path; `unwrap()`, `expect()`, `panic!`, `todo!` stay in tests
  and truly unreachable states: a panic in a request path takes the whole worker thread down.
- A library returns a typed error (`thiserror`); an application may use `anyhow` with
  `.context(...)`: a `Box<dyn Error>` in a public API leaves the caller nothing to match on.
- `let _ = <must_use value>;` is refused unless a comment says why the result is irrelevant: it is
  the one-token way to drop an error on the floor.
- A `match` on a domain enum lists its variants — no `_ =>` catch-all: a new variant must break the
  build, not fall silently into the default arm.

## Boundaries & validation

- Parse at the boundary into a typed value (newtype with a fallible constructor): an invariant held
  by the type cannot be forgotten by the next caller, a validated `String` can.
- SQL is bound (`sqlx::query(...).bind`, diesel, sea-orm) — never `format!` into a query string.
- `std::process::Command` takes arguments one by one, never a shell string; a user-supplied path is
  canonicalized and checked against its allowed root: both are injection by another name.
- Untrusted input to `serde` carries a size limit: an unbounded payload is a memory exhaustion away.
- Every `unsafe` block carries a `// SAFETY:` comment naming the invariants it relies on, and
  `unsafe` never works around a borrow-checker error: an unstated invariant is an unreviewable one.
- In async code, no blocking call (`std::thread::sleep`, `std::fs`, a sync mutex held across
  `.await`) and channels are bounded unless a comment says why: both stall the executor under load.
- Secrets come from the environment and fail fast at startup when absent; errors returned to a
  client are generic, the detail goes to `tracing` server-side.

## Guards & tests

- `cargo fmt --check` and `cargo clippy -- -D warnings` (with `--all-targets` where the project
  already does) are non-negotiable; an `#[allow(...)]` is narrow and says why.
- At the gate, `cargo test` runs BARE (with `--workspace` on a workspace), exactly as CI does. The
  dev and its judges run their `BANCS:` line (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`):
  `tests/api.rs::creates_user` is `cargo test --test api creates_user -- --exact`; a unit test in
  `src/user.rs` is `cargo test --lib user::tests::creates_user -- --exact` — without `--exact` the
  name is a SUBSTRING filter and may run its neighbours too.
- Async tests use the runtime's test macro (`#[tokio::test]`), never a hand-built runtime per test.

## Tooling

- `Cargo.lock` is committed for a binary or a service: without it two builds resolve two dependency
  sets and CI validates one that is not deployed.
- SCA: `Cargo.toml` is NAMED as not covered by `sca-scan.sh` (`name_uncovered`, T-00000488) when it
  sits at the ROOT LOOKED AT, and is NOT scanned. The hook throttle (`SCA_CHANGED_ONLY=1`) does not
  list `Cargo.toml` or `Cargo.lock`, so when they are the only files changed the hook skips the scan.
  `cargo audit` is the pending work T-00000313; `cargo deny check` is a gate the project runs
  itself. Do NOT read a GO verdict on a Rust crate as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested rust conventions.
