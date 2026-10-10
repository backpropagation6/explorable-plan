#!/usr/bin/env python3
"""Track the versions of a PLAN file in git and catch rewrites.

Usage: python3 plan_history.py <PLAN.md>
       python3 plan_history.py --versions <PLAN.md>

A PLAN only grows. The header (the lines before the first `## ` heading) may change; the body may
only grow at the end. This script reads every commit of the file, oldest first, and then the
working copy, and checks each step against that rule.

- A rewrite that is not committed yet fails: put the text back and add the change at the end of the
  file as `## Version N`.
- A rewrite already committed cannot be undone without rewriting history, so it has to be declared:
  it fails until a later section of the PLAN names that commit (7 or more characters of its hash)
  and says what it changed. The text before it stays in git, and the report says at which commit.
- `## Version N` headings run 2, 3, 4... in order.

Version 1 is the first commit of the file; version N is the commit that added `## Version N`.
`--versions` prints them as the `versions:` block of the page content (number, date, commit, the
first sentence of the section), so the history on the page comes from git, not from memory.

Exit codes: 0 append-only (declared rewrites included); 1 an undeclared or uncommitted rewrite, or
version headings out of order; 2 usage error, no git, or a file with no commit yet.
"""
import pathlib
import re
import subprocess
import sys

VERSION_H = re.compile(r"^##\s+Versione?\s+(\d+)\b")


class Usage(Exception):
    """Wrong arguments, no git, or a file git does not track: exit code 2."""


def git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Usage(f"git {' '.join(args)}: {r.stderr.strip() or 'failed'}")
    return r.stdout


def split(text):
    """(header, body) as lists of lines. The header ends at the first `## ` heading."""
    lines = [l.rstrip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("## "):
            return lines[:i], lines[i:]
    return lines, []


def trimmed(body):
    while body and not body[-1]:
        body = body[:-1]
    return body


def changed_lines(old, new, offset):
    """Lines of the old body that the new body does not keep in place, as (line number, was, now)."""
    return [(offset + k + 1, line, new[k] if k < len(new) else None)
            for k, line in enumerate(old) if k >= len(new) or new[k] != line]


def step(old_text, new_text):
    """[] when new only grows old at the end (header aside), else the changed lines of old."""
    old_head, old_body = split(old_text)
    _, new_body = split(new_text)
    old_body = trimmed(old_body)
    if new_body[:len(old_body)] == old_body:
        return []
    return changed_lines(old_body, new_body, len(old_head))


def first_sentence(body, start):
    """The first sentence of the section that starts at body[start], for the versions line."""
    words = []
    for line in body[start + 1:]:
        if line.startswith("## "):
            break
        if not line.strip():
            if words:
                break
            continue
        words.append(line.strip())
    text = re.sub(r"[*_`]", "", " ".join(words))
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    text = (m.group(1) if m else text).strip()
    return text if len(text) <= 120 else text[:117].rstrip() + "..."


def history(path):
    path = pathlib.Path(path).resolve()
    if not path.is_file():
        raise Usage(f"file not found: {path}")
    cwd = path.parent
    rel = git(cwd, "ls-files", "--full-name", "--", path.name).strip()
    if not rel:
        raise Usage(f"{path.name} is not tracked by git: commit version 1 of the plan first")
    log = git(cwd, "log", "--reverse", "--format=%H %ad", "--date=short", "--", path.name).split("\n")
    commits = [tuple(l.split(" ", 1)) for l in log if l.strip()]
    if not commits:
        raise Usage(f"{path.name} has no commit yet: commit version 1 of the plan first")
    shallow = git(cwd, "rev-parse", "--is-shallow-repository").strip() == "true"
    texts = [git(cwd, "show", f"{sha}:{rel}") for sha, _ in commits]
    return path, rel, commits, texts, path.read_text(encoding="utf-8-sig"), shallow


def analyse(path):
    path, rel, commits, texts, work, shallow = history(path)
    notes, errors, versions = [], [], []
    if shallow:
        notes.append("shallow clone: the history may start after the first commit of the plan; "
                     "only the commits present are checked")
    _, cur_body = split(work)
    cur_text = "\n".join(cur_body)

    # versions from git: v1 is the first commit, vN the commit that added `## Version N`
    seen = set()
    for (sha, day), text in zip(commits, texts):
        body = split(text)[1]
        if not versions:
            versions.append((1, day, sha[:7], "First plan."))
        for i, line in enumerate(body):
            m = VERSION_H.match(line)
            if m and int(m.group(1)) not in seen:
                seen.add(int(m.group(1)))
                versions.append((int(m.group(1)), day, sha[:7], first_sentence(body, i)))

    # headings in the working copy run 2, 3, 4...
    found = [int(m.group(1)) for m in (VERSION_H.match(l) for l in cur_body) if m]
    if found != list(range(2, len(found) + 2)):
        errors.append(f"version headings are {found or 'none'}; they run 2, 3, 4... in the order "
                      "they were added")

    # each committed step, then the working copy
    def short(s):
        return repr(s if len(s) <= 80 else s[:77] + "...")

    def describe(changes):
        out = [f"    line {n}: was {short(was)}, " + (f"now {short(now)}" if now is not None else "now gone")
               for n, was, now in changes[:5]]
        if len(changes) > 5:
            out.append(f"    ... and {len(changes) - 5} more")
        return out

    for k in range(1, len(texts)):
        changes = step(texts[k - 1], texts[k])
        if not changes:
            continue
        sha, day = commits[k]
        before = commits[k - 1][0][:7]
        declared = sha[:7] in cur_text
        head = (f"rewrite in commit {sha[:7]} ({day}): the text before it is at {before} "
                f"(git show {before}:{rel})")
        if declared:
            notes.append(head + ", declared in the plan")
        else:
            errors.append(head + ", not declared. Add a section at the end that names "
                          f"{sha[:7]} and says what it changed.")
            errors.extend(describe(changes))
    changes = step(texts[-1], work)
    if changes:
        errors.append("rewrite not committed: put these lines back as they are in the last commit "
                      f"({commits[-1][0][:7]}) and add the change at the end of the file as "
                      f"## Version {len(found) + 2}.")
        errors.extend(describe(changes))
    return path, versions, notes, errors


def main(argv):
    args = argv[1:]
    as_block = "--versions" in args
    args = [a for a in args if a != "--versions"]
    try:
        if len(args) != 1 or args[0].startswith("--"):
            raise Usage("usage: plan_history.py [--versions] <PLAN.md>")
        path, versions, notes, errors = analyse(args[0])
    except Usage as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if as_block:
        lines = [f"{n} {day} {sha} {what}" for n, day, sha, what in versions]
        print("versions: " + "\n  ".join(lines))
    else:
        print(f"{path.name} · version {versions[-1][0]} · {len(versions)} version(s) in git")
        for n, day, sha, what in versions:
            print(f"  v{n}  {day}  {sha}  {what}")
        for note in notes:
            print(f"note: {note}")
    for e in errors:
        print(e if e.startswith("    ") else f"FAIL: {e}", file=sys.stderr)
    if errors:
        return 1
    if not as_block:
        print("OK · the plan only grew")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
