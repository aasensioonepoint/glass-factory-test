import re
import subprocess

from _common import ROOT, additional_context, emit_event, lecture_copilot, read_payload


# `git diff --check` reports one `path:line: <what>` header per offending hunk,
# followed by the offending line itself. Only the header's PATH is ever read
# here — the line body is file content, which has no business in the event
# stream (same rule the class-0 gate exists for).
CHECK_LOCATION = re.compile(r"^(?P<path>[^\s:][^:]*):\d+:", re.M)


def first_offending_path(output):
    """The first path `git diff --check` complained about, or "".

    One event per hook run carries one path, matching the Claude homologue's
    single `path` field (there, the edited file). A whole location list would
    need `locations`, which events.py does not allowlist for this kind.
    """
    match = CHECK_LOCATION.search(output or "")
    return match.group("path") if match else ""


def main():
    payload = read_payload()
    # Une LECTURE LOCALE identifiée positivement sous Copilot sort ici, avant le
    # `git diff --check` de tout l'arbre (T-01M4RWC6VHHN479J2A9RRY1BE3) ;
    # partout ailleurs, inerte.
    if lecture_copilot(payload):
        return
    try:
        result = subprocess.run(
            ["git", "diff", "--check"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        additional_context(f"Post-edit check skipped: {exc}", event_name="PostToolUse")
        return
    if result.returncode != 0:
        additional_context(
            "git diff --check found whitespace issues:\n" + result.stdout[:4000],
            event_name="PostToolUse",
        )
        # hook.check_fail{guard,rule,path} — same kind and same field NAMES as
        # .claude/hooks/post-edit-check.sh. The `rule` VALUE is deliberately NOT
        # made to look alike: that hook runs a per-language toolchain on the file
        # that was just edited and labels the rule with its extension, whereas
        # this host runs `git diff --check` over the worktree, so the only honest
        # rule id is the check that actually ran. `path` is omitted rather than
        # sent empty when the output carries no location.
        fields = {"guard": "post-edit-check", "rule": "whitespace"}
        offending = first_offending_path(result.stdout)
        if offending:
            fields["path"] = offending
        emit_event("hook.check_fail", **fields)


if __name__ == "__main__":
    main()
