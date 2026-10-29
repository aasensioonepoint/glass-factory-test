# Working language — the rule, its bench, and what the bench does not see

Source: pilot decision S-01M54GFZ9VTKTJ07AVZHKRA982, first slice delivered by T-01M54GEWXXDA6A2Z663G5SYGG0;
extended to EVERY agent def by S-01M5VCGTEBC76MKR63HJ2K67CE (pilot order of 2026-10-25,
T-01M5S9338BJP1B5RM3TG14AMYT). Benches: `.agents/evals/test_working_language.py` and
`.agents/evals/test_defs_anglais.py`.

## The rule

- Instructions, reasoning and exchanges between agents are written in English.
- Everything addressed to the pilot stays in French: what `communicator` writes, report blocks, gate
  questions, `angle mort:` questions, the text of the status banners. A def says it in one sentence
  of its own: "You answer in French.".
- Literals stay verbatim, whatever the language around them: code spans, numbers, CLI messages and
  help texts (S-01M53C64HEFE0YHKNMC5NE2A85 keeps them in French), verdict codes (`GO`, `NO_GO`,
  `REFUS`, `DEGRADED`, `DRY_RUN`…), plan keywords (`SEUILS:`, `LOT:`, `WRITE-SET:`…), and anything
  fenced or quoted between `«` and `»`. A banner line keeps its spans byte for byte; its
  instruction is English, the line it renders is French. In the PROSE of a def, a French phrase
  stays — byte for byte, in backticks where the syntax allows — only in five classes: (a) a
  literal the code emits or matches; (b) a plan-grammar line or a printed format a tool reads;
  (c) the name of a section of another surface it cites; (d) a text a travelling surface says to
  copy verbatim; (e) the headings the `communicator` prints to the pilot, and the kit terms
  (`binôme`, `fournée`, `plafond`, `chantier`, `HORS CHAÎNE`). Everything else in the prose is
  English.

## The unit of conversion

One role at a time, in ONE commit: its source `agents/<name>.md`, rendered to the five host defs
(`.claude`, `.codex`, `.github`, `.gemini`, `.kimi-code`) and the roster entry under
`.agents/vendor/cadre/data/roster/` by `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire`
(never by hand), and its skill. Each
rendered surface carries ONE pointer line to this sheet (the source: one per body). Converted: every
agent def of the kit (pilot order of 2026-10-25, S-01M5VCGTEBC76MKR63HJ2K67CE), and any def added
later is born converted; among the skills, only `load-test` — the other skills are unchanged; written
in English from the start: the `seo` skill (not judged by the bench). One exception, closed:
`language-detector` carries neither the pointer nor `You answer in French.` (it prints one JSON object,
never to the pilot, and its def is sha-pinned by 48 real host replays,
`.agents/evals/fixtures/detector_spring_angular.observed.json`); its prose is English all the same,
and both benches still judge it on French and on its printed regions. The general
doctrine (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.agents/ref/`,
the benches) and the language of plans, of the board and of SPECS change only on a decision of
the pilot.

## What the bench sees

- The sheet is tracked and carries the rule.
- Each converted surface points at this sheet exactly once and carries its rule sentence
  (defs: `You answer in French.`; skill: `**narrates** the verdict in French`), the closed
  `language-detector` exception above excepted (a tuple pinned to one entry). In the kit the defs
  are FOUND by glob — the five host directories and the sources `agents/*.md` (`README.md`
  excepted) — so a def added later is judged at birth; a source is judged body by body (each host
  body it carries, a `comme claude` reference excepted). In an adopting project only the shipped
  `load-tester` defs and the `load-test` skill are judged: the adopter's own defs stay free.
- French share at most 0.05: French function words over French plus English function words, on
  the whole file minus fenced blocks, code spans and «…». Lexicon: `de`, `un`, `et`, `en` count as
  French; `a` and `on` count as neither.
- Kit only, frozen on the bodies at 67bfe0d6 (frontmatter excluded), the table itself replayed
  against `git show 67bfe0d6:<path>`: each fenced block, each «…» (whitespace collapsed) and each
  banner line starting with `▸` hashed; PER SECTION, the multiset of code spans (a span may fold
  over two lines; a span folded over three lines or more is not seen), S-/T-/L- ids and bare
  numbers (a decimal comma read as a dot), minus one pointer span; the bullet count per section.
  This full table holds `load-tester` and the `load-test` skill.
- Kit only, for every OTHER def that existed at 8c74e8d55 (the French version the extension took
  its printed text from): what the agent prints to the pilot, compared byte for byte with
  `git show 8c74e8d55:<path>` — the fenced blocks in order, the «…» quotations as a multiset, the
  lines opening on `▸` and the code spans opening on `▸`; and, PER HOST SECTION (a source cut at its
  `<!-- hote: … -->` sentinels, a host file whole), the multiset of code spans of the prose (a span
  may fold over two lines, whitespace collapsed): every span of the base is still there, byte for
  byte — spans may be added, never altered or removed.
- A printed format the base left UNFENCED may be fenced: a block absent from the base is admitted
  only when its body is, byte for byte, a run of whole lines of the unfenced text of the SAME host
  section of the base, pinned by sha in the frozen `ADMITTED_FENCES` (shrunk, grown or moved: red);
  unfenced again for the comparison, the def must print what the base printed, host section by host
  section, and keep every span of it. A block whose
  body was translated or edited is not admitted, and the comparison goes red.
- A DELIBERATE change of a def's printed region or code span goes through ONE path: the change is
  made in its own commit, which descends from 8c74e8d55; a LATER commit maps the def's name to that
  commit's sha in `EXT_BASE_PAR_DEF` of `.agents/evals/test_working_language.py`, and the bench then
  compares that def with the mapped commit instead of 8c74e8d55. The bench refuses a mapping whose
  value is not a literal hex sha (`HEAD` or a branch name refused) or is HEAD's own commit, whose
  commit does not descend from 8c74e8d55 or is not in the history of `HEAD`
  (`git merge-base --is-ancestor`), or whose name no def carries. The mapping is the visible decision;
  a translation is never hidden behind it. Mapped today: `planner-sonnet` and
  `plan-critic-sonnet-max`, whose full plan-grammar clauses became pointers to
  `.agents/ref/PLAN_GRAMMAIRE.md` (§ 1, § 2, § 3), as `planner` and `plan-critic` already carried them.
- `.agents/evals/test_defs_anglais.py`: in the prose — outside fenced blocks, «…», lines opening
  on `▸` and code spans — no French tool-word of its closed list of 34, beyond a closed list of
  phrases kept by the five classes above.

## What the bench does NOT see

The lexical share proves the words are English, never that the sentence is right. Not seen, said
here so that nobody reads the bench as a guarantee:

- a wrong English sentence that keeps its atoms;
- a number written as a word, and a rule that carries no atom;
- a polarity inversion in prose (`never` turned into `always`, a negation dropped);
- a verdict code translated in prose (`REFUS` written `REFUSAL` outside a span or a block);
- the frontmatter, and the `description:` of a skill: French share only;
- for the defs other than `load-tester`, the ids, numbers and bullets of the prose: only their
  printed regions and their code spans are held, never these atoms; and a span ADDED is never
  judged;
- a def born after 8c74e8d55: no frozen base — pointer, rule sentence, French share and the
  tool-word count only;
- a printed format that stays OUTSIDE any fenced block in base and def alike: it is prose to the
  benches, so a translation of it is seen only through its code spans. Measured unfenced on
  2026-10-26, byte-identical to the base and held against translation by neither bench: the Codex bodies of
  `planner-sonnet` (its plan template), `design-review`, `seo-specialist` and `language-detector`,
  and the `FORECAST` header of the Codex `orchestrator` — fence one with its base bytes, as above,
  to bring it under the comparison.

These are seen only by the section-by-section re-reading of a conversion (base and translation
side by side, every obligation, prohibition, condition and bound found again). For the first
slice that method is written in the plan annex of T-01M54GEWXXDA6A2Z663G5SYGG0 (in the kit only:
`docs/tasks/T-01M54GEWXXDA6A2Z663G5SYGG0-annexe.md` § 4; it does not travel), which this sheet
does not own: the annex names the method, this list names the blind spots.

Known defect of the base, kept verbatim: in the `load-test` skill (§ Outputs and trace), the
sentence « é » reads there as `é` shows a literal `é` inside the code span, where an ASCII-escaped
JSON line shows `\u00e9` (six ASCII characters). It was already wrong at 67bfe0d6; the frozen fingerprints forbid
correcting it silently. Correct it only together with a re-freeze of FROZEN, decided and traced.

## Travel

This sheet and its benches travel. In an adopting project the sheet states the kit's rule,
bounded by S-01M54GFZ9VTKTJ07AVZHKRA982 and S-01M5VCGTEBC76MKR63HJ2K67CE — decisions of the kit's
pilot, not of yours — and every agent def and the `load-test` skill it ships are converted.
Without `.agents/IS_THE_KIT` the frozen fingerprints, their replay against the kit's history,
the glob over the defs and `.agents/evals/test_defs_anglais.py` are skipped, and the skip is
announced; the sheet, the pointer, the rule sentence and the French share of the shipped
`load-tester` defs and `load-test` skill are still judged on your copy. Your own defs stay free.
Whether the language of YOUR pilot replaces French is an open question for the kit's pilot.
