# C# / .NET conventions — canonical (shared by Claude Code, Codex, Copilot)

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. Facts specific to ONE project (target framework, DI container, repo layout) belong in a
§2 of that project's own copy, each with its ledger id — not here.

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

**REACHABILITY, said without euphemism.** This is THE C# sheet as well: there is no
`CONVENTIONS_csharp.md`, by design. The REGISTRY routes here, by the `conventions:` key of its
`## c# / .net` section (wired by lot D of T-01M5BZC4DV3XT5AVZ6F388P78K): `dotnet`, `c#` and `.net`
resolve to that section, a bare `csharp` resolves to none (measured), and the title stays intact
because the `dotnet` alias points at it. The DETECTOR
does not: `language-detector` emits no `.NET`/`c#` token, so no detector run points a dev agent here.
Wiring the token is the pending residue b1 → **T-00000449** (NOT T-00000436, which is CLOSED —
routing a debt to a closed task buries it). If T-00000449 does not cover the .NET token, that work is
still "to open", never a closed identifier.

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

## Language & types

- `<Nullable>enable</Nullable>` and warnings-as-errors: nullability is a compile-time contract, so a
  warning left as a warning is a `NullReferenceException` deferred to production.
- No `dynamic` and no reflection where a type or a generic will do: both move a type error from the
  compiler to the first unlucky request.
- The null-forgiving `!` is a suppression, not a proof: each one carries the reason it holds, or the
  nullability contract above is switched off one expression at a time.
- `obj is T t` rather than a bare `(T)obj` cast: the pattern makes the failing case a branch you
  write, where the cast makes it an `InvalidCastException` nobody handles.
- Value-like models are `record` (or `record struct`) and a class not designed for inheritance is
  `sealed`: an immutable value cannot be seen half-updated, and a sealed class keeps its invariants.

## Boundaries & validation

- `async` end to end — never `.Result`, `.Wait()` or `.GetAwaiter().GetResult()`: blocking on a task
  deadlocks a captured synchronization context and, at load, starves the thread pool.
- No `async void` outside event handlers: its exception escapes to the synchronization context and
  can take the process down, where a returned `Task` lets the caller observe it.
- A public async API takes a `CancellationToken` and passes it down: without it a cancelled request
  keeps consuming database and network time for an answer nobody reads.
- `using`/`await using` for every `IDisposable`/`IAsyncDisposable`: a disposal left to the caller's
  memory is skipped on the first exception path.
- SQL takes PARAMETERS (EF Core LINQ, `FromSql` with an interpolated value, Dapper `@name`), never a
  string built from input — `FromSqlRaw` fed an interpolated string is an injection.
- No `BinaryFormatter`, and no Newtonsoft `TypeNameHandling` other than `None` on untrusted input:
  both let the payload choose the type to instantiate, i.e. remote code execution.
- A user-supplied path goes through `Path.GetFullPath` then a check that it stays under its base
  directory: without the check `..` walks out of it.
- Secrets come from user-secrets locally and a secret store in production, never from source or a
  committed `appsettings*.json`; a client error carries no stack trace, SQL text or file path.
- `IOptions<T>` is validated AT STARTUP (`ValidateOnStart`): a bad configuration must fail the boot,
  not the first request that happens to read the option.

## Guards & tests

- At the gate, `dotnet test` runs BARE, exactly as CI does — never a hand-picked subset that
  green-lights a project the full run would fail. The dev and its judges run their `BANCS:` line
  (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`): `<proj>/<F>Tests.cs::TestX` is
  `dotnet test <proj> --filter 'FullyQualifiedName~TestX'`.
- ASP.NET Core integration tests go through HTTP (`WebApplicationFactory<TEntryPoint>`): calling
  the handler directly bypasses the middleware where auth, validation and serialization live.
- A gate is fail-closed: an unreadable file or an I/O error makes it fail loudly, never turn green.

## Tooling

- `HttpClientFactory` for every outbound call: a hand-newed `HttpClient` exhausts sockets under load.
- `dotnet format --verify-no-changes` plus the analyzers in CI, so form and a slice of substance are
  settled off the review.
- SCA: `*.csproj`/`*.sln` are NAMED as not covered by `sca-scan.sh` (T-00000488, its
  `name_uncovered`), down to depth 3 from the root looked at, and are NOT scanned; `dotnet list package --vulnerable` is the pending work
  T-00000316. Do NOT read a GO verdict on a .NET project as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested c# / .net conventions.
