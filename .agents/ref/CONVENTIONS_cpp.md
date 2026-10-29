# C++ conventions — canonical (shared by Claude Code, Codex, Copilot)

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (C++ standard, compilers, build system, package
manager, naming) belong in a §2 of that project's own copy, each with its ledger id — not here.

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

**Idiom layer: NO kit skill carries C++.** The `## c / c++ / cpp` section of `DOCS_REGISTRY.md`
lists the language and library references, fetched at need. This sheet is the SHORT gate layer; the
rules below hold for CMake, Bazel or Meson builds alike, and for the C++ side of a mixed C/C++ tree.
A pure C tree is NOT covered: no sheet carries C.

## Language & types

- The standard is the one the build declares (`CMAKE_CXX_STANDARD` or its equivalent), read BEFORE
  writing: a C++20 construct in a C++17 build compiles on your compiler and not on CI's.
- RAII for every resource: no raw `new`/`delete`, no `malloc`/`free` — `std::unique_ptr` by default,
  `std::shared_ptr` only for genuinely shared ownership: a manual release is skipped by the first
  early return or exception.
- Rule of Zero first; a class that defines one of destructor, copy or move operations defines or
  deletes all five: a half-defined set copies a handle and frees it twice.
- Every variable is initialized at declaration and no `reinterpret_cast` or C-style cast without a
  comment: reading an uninitialized value is undefined behaviour, not a wrong number.
- Errors follow ONE scheme per module — exceptions, `std::optional`, or `std::expected`/a result
  type — and a returned error is never ignored (`[[nodiscard]]` on functions whose result matters).
- `const` on what does not change, and no `using namespace` in a header: a header leaks its
  namespace into every file that includes it.

## Boundaries & validation

- No `strcpy`, `strcat`, `sprintf`, `gets` or C array indexed by untrusted input — `std::string`,
  `std::array`/`std::vector`, `std::span`, bounds-checked access where the index comes from outside.
- No user input as a `printf`-family format string, and arithmetic on untrusted sizes is checked
  before it allocates or indexes: an overflowed length is the classic buffer overflow.
- `system()` and `popen()` never receive interpolated input — an argument vector API instead; a
  user-supplied path is canonicalized and checked against its allowed root.
- Threads are joined or owned (`std::jthread`), locks are scoped (`std::scoped_lock`,
  `std::lock_guard`) and taken in one documented order: a manual `unlock()` is skipped by an
  exception, and two orders are a deadlock.
- An iterator, pointer or reference into a container is not used after the container may have
  reallocated: a `push_back` invalidates it silently.
- No secret as a literal in source: a shipped binary gives its strings to `strings`.

## Guards & tests

- `clang-format` with the project's checked-in config settles form; `clang-tidy` (and `cppcheck`
  where the project has it) runs with the project's config and the warnings the build already treats
  as errors; a `NOLINT` or `#pragma` suppression is narrow and says why.
- CI runs the suite at least once under AddressSanitizer and UndefinedBehaviorSanitizer: most memory
  and UB defects pass a plain test run and fail only in production.
- At the gate the suite runs BARE, exactly as CI does (`cmake --build build && ctest --test-dir
  build --output-on-failure`, or the project's equivalent). The dev and its judges run their `BANCS:`
  line (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`): `tests/user_test.cpp::UserTest.Creates`
  is `ctest --test-dir build -R '^UserTest\.Creates$' --output-on-failure` when GoogleTest cases are
  registered one by one (`gtest_discover_tests`), otherwise the test binary with
  `--gtest_filter=UserTest.Creates` — `-R` is a REGEX, and unanchored it runs its neighbours too.

## Tooling

- The dependency set is pinned — `vcpkg.json` with its baseline, a Conan lockfile, or vendored
  sources at a recorded revision: an unpinned fetch builds a different library on CI than on yours.
- SCA: NO C/C++ manifest — `conanfile.txt`, `conanfile.py`, `vcpkg.json`, `CMakeLists.txt` — is
  scanned by `sca-scan.sh`, and none is NAMED either: unlike Go or Rust, C++ gets no "not covered"
  line, no DEGRADED status, and no key in the per-ecosystem status map. A pure C++ tree reads
  `SCA: no known ecosystem detected.`; next to another ecosystem, C++ is not mentioned at all. Do
  NOT read a GO verdict on a C++ project as an absence of CVEs; the project audits its own.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested cpp conventions.
