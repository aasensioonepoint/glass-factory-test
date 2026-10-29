# Symbols — 9 entries — built @ 0a91980 · updated 2026-10-29 · backend fallback · threshold 500 · kinds 846297bf · dirscope b2caece1
# grammar:  SYM-NNN  <path>:<start>-<end>  <name>  <kind>  uses[SYM-…]  :: <purpose ≤10 words>
# ids are fixed-width (3 digits) — find callers of SYM-020 with:  grep 'SYM-020' SYMBOLS*.md   (reverse edges are NOT stored)
# uses[] edges are APPROXIMATE (name-matched by build_index.py) — verify before relying on them

SYM-001  conftest.py:65-113  greffe_email_git_franchissable  function  uses[]  ::
SYM-002  conftest.py:117-138  _isolation_state_dir_session  function  uses[]  ::
SYM-003  conftest.py:160-162  git_herite  function  uses[]  ::
SYM-004  conftest.py:184-211  _portee  function  uses[]  ::
SYM-005  conftest.py:259-320  _marcher  function  uses[]  ::
SYM-006  conftest.py:342-406  _refuses  function  uses[SYM-004,SYM-005,SYM-007]  ::
SYM-007  conftest.py:409-496  _garde_1188  function  uses[SYM-003,SYM-006]  ::
SYM-008  conftest.py:502-505  pytest_terminal_summary  function  uses[]  ::
SYM-009  conftest.py:509-546  _isolation_git_session  function  uses[SYM-003]  ::
