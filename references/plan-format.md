# The PLAN file

A PLAN is a versioned file written and committed before a non-trivial change is made. The explorable page
is a presentation of it; the file is what counts.

> **Process rule: the plan file is canonical; the page states the commit it reflects.** A decision taken
> on the page is carried back into the file, and if the two differ, the file wins.

## When a plan is worth writing

Write one before a change that touches production, a deploy or a migration; or that edits more than three
files; or that changes a prompt, a skill or a gate. Not for a typo, a small edit confined to three files
or fewer with no effect on production, or an emergency repair (repair first, write the post-mortem
afterwards).

## Name and place

`PLAN-<topic>-YYYY-MM-DD.md` at the root of the project the change belongs to. If a spec already exists,
the plan links to it and covers only execution: the spec says what and why, the plan says which files, in
what order, how it is verified and how to go back.

Commit the plan, on its own, before the first line of the implementation. A plan written after the code reduces no risk; it is documentation.

## The four sections

All four are required. A plan without the third is not a plan.

### 1. Files to touch
One path per line, from the project root, with one line saying what changes in each. It makes the blast
radius measurable before anything is opened, and gives the final commit its list of files.

### 2. Work order
The sequence, not the list. Say where there is a dependency ("the gate before the caller, otherwise the
caller fails halfway"). If the work can stop in the middle, say which intermediate state is safe, and mark
those steps.

### 3. Acceptance test
For every expected outcome: the command that checks it and the artifact you must see, at its destination.
Not valid as proof: an exit code, an HTTP 200, "I started it", a test the author wrote to pass. Valid: the
file read where the consumer reads it, the message found in the channel, the line in the log of whoever
receives it, the commit visible on the main branch. On the page, this section starts empty ("to be
measured") and never shows an expected result as if it were a measurement.

### 4. Risks and rollback
What can break, how you find out (who tells you, on which channel, how soon) and how to go back, with the
command. A rollback that exists only in words counts as no rollback and is written as such.

## Versions: the file only grows

The first commit of the plan is version 1. From then on nothing already committed is rewritten or deleted:
the four sections stay as they were approved, and everything new goes at the end of the file, in the order
it happened.

- **A change to the plan** (files, order, acceptance test, risks) is a new section at the end,
  `## Version N (YYYY-MM-DD)`: what changes, in which section, and why. It overrides the earlier text only
  where it says so. Commit it on its own, like version 1, before the work it changes.
- **Decisions** go in a dated `## Decisions (YYYY-MM-DD)` section at the end. An answer that only picks an
  option the plan offered is not a new version; an answer that changes the plan opens one.
- **The header is the only exception.** The lines above the first section may be updated: the current
  version and the link to the explorable page.
- **The current plan** is version 1 read together with the version sections, in order. When that gets hard
  to follow, do not rewrite: start a new PLAN file from the current state, link it to the old one, and leave
  the old one as it is.

A rewrite that happens anyway does not go unseen: `python3 kit/plan_history.py PLAN-<topic>-*.md` reads the
history of the file and fails on it. If the rewrite is not committed, put the text back. If it is, it cannot
be undone without rewriting history, so declare it: a later section names the commit and says what it
changed, and the earlier text stays readable in git.

The page lists the versions in its footer (number, date, commit, what changed), printed by
`plan_history.py --versions`. Each one can be read back with `git show <commit>:<plan file>`.

## Closing: the outcome section

When the work is done, add an `## Outcome` section at the end of the same file: what was actually done,
which acceptance test was observed (with the command and its real output), and what was left out. The plan
is not deleted and not rewritten afterwards; its use is the comparison between the intention and the result.

If the work stops halfway, `## Outcome` says where it stopped and what is missing.

When the reader answers the decisions of a plan, append them in a dated `## Decisions` section at the end of
the file (or in `## Outcome` if the work is closed) and commit it in the same session. An answer that stays
in the chat or on the page is not recorded.

## Three ways to cheat, and how to see them

1. **The plan written after the code.** Compare `git log --oneline --reverse -- PLAN-<topic>-*.md` with the
   implementation commits. If the plan came later, say so.
2. **The inflated plan.** A plan twice as long as the change it describes is a bad sign, not a good one. The
   four sections fit comfortably on one page for most changes.
3. **The rewritten plan.** After the first commit the file should only grow, apart from the header.
   `python3 kit/plan_history.py PLAN-<topic>-*.md` checks it commit by commit and names every rewrite, with
   the commit that still holds the text it replaced.

## What the explorable page shows

Only when the plan asks the reader for at least one decision, or estimates more than one session; whether
the Artifact tool is available does not change that. Before the page is written the reader is asked how it
should look, and the answer is the required `theme:` key of the content file (`theme: neutral` is the
default look). The page shows, in this order of importance:

1. status and effort;
2. the choices already made;
3. the mechanism in a diagram;
4. a manipulable example of the delicate point;
5. the acceptance test, simulable, starting empty;
6. the steps with their safe states;
7. costs and risks;
8. the open decisions, with an answer the reader can paste into the chat.

Every figure on the page exists in the plan with its label (source, measurement or estimate); the page adds
none. Every chart has its twin table; every verdict carries a glyph and a word, never colour alone; examples
you made up say so on the page.
