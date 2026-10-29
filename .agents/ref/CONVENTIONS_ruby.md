# Ruby conventions — canonical (shared by Claude Code, Codex, Copilot)

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (Ruby and Rails versions, test runner, job
backend, repo layout) belong in a §2 of that project's own copy, each with its ledger id — not here.

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

**Framework layer: NO kit skill carries Rails.** The `## ruby` section of `DOCS_REGISTRY.md` lists
the Ruby and Rails guides, fetched at need. This sheet is the SHORT gate layer; the rules below hold
for Rails, Sinatra, Hanami or plain Ruby alike.

## Language & types

- `# frozen_string_literal: true` on every new file where the project already uses it, and mutable
  constants `.freeze`d: a shared mutable literal is state any caller can change for every other.
- Plain Ruby before metaprogramming; `method_missing` always ships with `respond_to_missing?`, and a
  core-class patch lives in a named refinement or initializer: dynamic dispatch hides the call graph
  from every reader and every tool.
- `rescue` names the exception it expects — never a bare `rescue => e` that logs nothing, never
  `rescue Exception`, never the `value rescue nil` modifier: each turns a failure into a silent nil.
- A `save`/`update` whose failure matters is checked, or written `save!`/`update!`: the non-bang form
  returns `false` and the caller proceeds as if it had persisted.

## Boundaries & validation

- Strong parameters with an explicit `permit` list before any mass assignment — never `permit!` and
  never raw `params` into `create`/`update`: one extra key writes a column nobody exposed.
- SQL is parameterised (hash conditions, `?` or named binds); no request, cookie, job or webhook value
  is ever interpolated into `where`, `order`, `find_by_sql` or `Arel.sql`.
- Refused on untrusted input: `send` / `public_send` / `constantize` / `Object.const_get` without an
  allowlist (unsafe reflection); backticks, `%x{}`, `system`, `Kernel#open` with interpolation
  (command injection — pass an argument array); `Marshal.load`, `YAML.load` / `YAML.unsafe_load`
  (use `YAML.safe_load` or JSON); `html_safe`, `raw`, `<%==` on user content; `redirect_to
  params[:url]` without a host check.
- CSRF protection stays on for browser routes, records are loaded through a scope or policy of the
  current user, and secrets live in Rails credentials or the environment — never in `config/*.yml`.
- A validation that matters is backed by a database constraint (unique index, `null: false`, foreign
  key): a model validation alone loses to two concurrent requests.

## Guards & tests

- One runner per feature area — Minitest (Rails default) or RSpec where already established, never
  both mixed without a migration reason: two runners split the CI command and the coverage.
- At the gate the suite runs BARE, exactly as CI does (`bin/rails test` or `bundle exec rspec`). The
  dev and its judges run their `BANCS:` line (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`):
  `test/models/user_test.rb::test_valid` is `bin/rails test test/models/user_test.rb -n '/^test_valid$/'`;
  an RSpec example is named by its line, `bundle exec rspec spec/models/user_spec.rb:42` — `-e`
  matches a SUBSTRING of the description and may run its neighbours too.
- No test reaches the network, depends on order or `sleep`s: stub HTTP (WebMock/VCR) and use time
  helpers, or the suite flakes on the machine that is not yours.
- `puts`, `pp`, `binding.pry`, `debugger`, `byebug` never reach a commit.

## Tooling

- RuboCop with the project's checked-in config, behind a binstub or script so local and CI run the
  SAME command; an inline `rubocop:disable` is narrow and says why.
- `Gemfile.lock` is committed for an application: without it two `bundle install` runs resolve two
  dependency sets and CI validates one that is not deployed.
- SCA: `Gemfile.lock` — or `Gemfile` when no lock is there — is NAMED as not covered by
  `sca-scan.sh` (`name_uncovered`, T-00000488) when it sits at the ROOT LOOKED AT, and is NOT
  scanned. `bundle-audit` (gem `bundler-audit`) is the pending work T-00000315; Brakeman is a SAST
  the project runs itself. Do NOT read a GO verdict on a Ruby project as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested ruby conventions.
