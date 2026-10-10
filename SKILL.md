---
name: explorable-plan
description: Write a PLAN file, then turn it into an explorable HTML page (tabs, steps, charts, a decisions form) after asking how the report should look. Build and check it in Chromium; publish it or hand over the file. Use for plans that need decisions or span several sessions.
license: MIT
compatibility: Any Agent Skills client that can run shell commands. Needs Python 3.8+ and git; Playwright with Chromium for the browser checks. A publishing tool (the Artifact tool in Claude Code) is optional.
---

# explorable-plan: write the plan, then the page when it earns one

The root is the folder that contains this file, not the working directory: call the scripts by absolute
path (`python3 <root>/kit/build.py ...`). If your agent did not tell you where this file is, find it with
`find -L . ~/.agents ~/.claude ~/.codex ~/.gemini ~/.copilot ~/.cursor ~/.config/opencode -path '*/explorable-plan/kit/build.py' 2>/dev/null | head -1`. The format of a PLAN is in [`references/plan-format.md`](references/plan-format.md).

**Any agent can follow this procedure.** Two tools in it carry Claude Code's names: AskUserQuestion (step 2)
and the Artifact tool (steps 5 to 7 and the rebuild). An agent without them uses its own equivalent, or the
fallback written next to each mention: the questions in the chat, the complete HTML file handed over. Another
publishing tool counts as the Artifact tool only if the page it publishes stays private until the user shares
it. If it adds the document skeleton itself (doctype, charset, viewport), build with `--fragment`; if it serves
your HTML as it is, build the complete document.

## Procedure

**1) Write the PLAN** as in `references/plan-format.md` and commit it. The page comes after the file, never
in place of it. That commit is version 1, and from then on the file only grows: a change is a new
`## Version N` section at the end, never an edit of what is already committed (§ Versions of the format).
After every commit of the plan run `python3 <root>/kit/plan_history.py <PLAN>`: it reads the file's history in
git and exits 1 on a rewrite, committed or not, naming the lines and the commit that still holds the text.

**2) Decide whether a page is needed.** Yes if the plan asks the reader for at least one decision or estimates
more than one session. The Artifact tool has no part in this decision. Otherwise summarise the plan in the
chat and stop here.

If a page is needed, **ask how the report should look before any content is written or built.**

- Ask exactly two questions, with the AskUserQuestion tool when it is available, otherwise in the chat as two
  numbered questions with the options listed. The default is the first option of each.
  1. **Palette:** neutral (black, white and greys; the default) / warm / cool / high contrast. "Other" means
     the user's own brand colours, given in hex.
  2. **Type:** system sans (the default) / system serif / system mono.
- Ask, then wait for the answer: end the turn with the questions, and never write the content or build in the
  same turn as the question. Only an explicit "no preference" ("you choose", "whatever") lets you go on
  without an answer: use `theme: neutral` and `theme-font: sans`. Silence is not an answer.
- Where nobody can answer (an unattended job) the questions cannot be asked: build no page and say so in the
  report.
- Light and dark mode (they follow the reader's system) and a single density are fixed defaults. They are not
  questions.
- Ask nothing if the user already named a theme, colours or a font, or if you are rebuilding a page whose
  metadata already has `theme:`: reuse what it says.
- Write the answer into the metadata block of the content (step 4). `theme:` is required: a preset becomes
  `theme: <name>` (`theme: neutral` is the default look); the type becomes `theme-font: sans|serif|mono`;
  brand colours become `theme: custom` plus `theme-colors:` (ink, paper and accent in hex, one line for
  `light` and one for `dark`; see the README). If the user gave only an accent, take ink and paper from the
  neutral theme and adjust the accent per mode (darker on light, lighter on dark). If the user gave only
  light colours, write the dark row yourself: swap ink and paper and lighten the accent until `build.py`
  accepts it. If the colours come as names (such as "navy"), ask once for hex codes, or propose hex values
  and get a yes. `build.py` rejects a custom theme whose text/background contrast is under 4.5:1 in either
  mode and names the pair; fix the colour and tell the user the value you used.
- `lang:` is `en` by default, or `it` when the conversation is in Italian. Write the content in that language.
  It is not a question.

**3) Re-read the plan file.** Every figure on the page already exists in the plan with its label (source,
measurement or estimate); the page adds no numbers. Examples you invent are declared as such on the page.

**4) Write the content** in a scratch file outside the repository, starting from
[`examples/minimal.html`](examples/minimal.html): the `<!--plan` metadata block first (including `theme:` and
`lang:` from step 2, `commit:` from `git rev-parse --short HEAD` after the plan commit, and `versions:`, one
line per version of the plan, oldest first, `<N> <YYYY-MM-DD> <commit> <what changed>`, the last one with the
same commit as `commit:`. Do not write it from memory: `python3 <root>/kit/plan_history.py --versions <PLAN>`
prints it from git), then
`<main id="content">`. Show the eight things a plan page needs: status and effort; the choices already made;
the mechanism in a diagram; a manipulable example of the delicate point; the acceptance test, simulable and
starting empty ("to be measured"); the steps with their safe states; costs and risks; the decisions, with an
answer the reader can paste into the chat. Every chart has its twin data table; every verdict carries a glyph
and a word (`✓`, `✕`), never colour alone. Page-specific interactions go in a `<script>` inside the content
and use `window.Plan`.

**5) Build and check.** The Artifact tool decides how the page is delivered, never whether it is built. With
the tool, build with `--fragment` (the tool adds the document skeleton) and publish in step 6. Without it,
build the default, a complete document, and hand the user the local file path in step 6.

```
python3 <root>/kit/build.py [--fragment] <content.html> <name>.v<N>.html
python3 <root>/kit/check.py <name>.v<N>.html <screenshot-folder>
```

Build only from a plan that `plan_history.py` passes. Name the page after its version. `build.py` never
overwrites another version: it rebuilds the same version
of the same plan in place (that is how you fix what `check.py` finds), and it stops, leaving the file as it
is, on a file that holds another version, another plan, or no plan at all. Do not delete that file to get
past the error: write to the name the error proposes.

Repeat until `check.py` prints `OK`. Exit code 3 means the browser checks did not run (playwright or Chromium
is missing): that is not a pass. The check is a smoke test, not a gate: it finds the faults listed at the top
of `kit/check.py`, not a readable colour outside the theme, overlaps or cut-off labels. Look at the
screenshots, light and dark, at 1280 and 390 px, before trusting an OK.

**6) Deliver.** With the Artifact tool: publish (private by default), after re-reading the whole file. Without
it: give the user the absolute path of the checked file and say to open it in a browser.

**7) If you published, put the link in the PLAN header** and commit:
`> **Explorable presentation:** [interactive page](<url>) (private; version <N>, reflects commit <sha>). If the two differ, the plan file is canonical.`
A file handed over has no link: there is nothing to put in the header.

**8) Tell the user** the link (or the file path) and the decisions you need from them; if step 2 ruled the page
out, say that.

**9) When the user answers,** the decisions are appended to the PLAN (a dated `## Decisions` section at the
end, or `## Outcome` if the work is closed) and committed in the same session: an answer that stays in the
chat or on the page is not recorded. If the answer changes the plan, it opens a new version: the section below
applies.

## When the plan changes after delivery

A change is a new version, never an overwrite: of the plan file, of the page file, or of the published page.

1. Append `## Version <N+1> (YYYY-MM-DD)` to the PLAN (what changes, in which section, why; its first sentence
   becomes the line on the page), commit it on its own, and run `plan_history.py`: it must print `OK`. If it
   finds a rewrite, put the text back; if the rewrite is already committed, say in the new section which
   commit it was and what it changed.
2. Get the content file of version N (in a new session it no longer exists: see below). Update the page where
   the new version changes it, replace `versions:` with what `plan_history.py --versions` prints, set `commit:` to the
   commit of version N+1 and `date:` to today. The page footer shows those lines as they are.
3. Build with the same flag as before into a new file, `<name>.v<N+1>.html`, and check it as in step 5. The
   file of version N stays where it is.
4. Republish at the same URL and update the version and the commit in the PLAN header. The Artifact tool keeps
   the earlier versions in the artifact's history, and the page lists every version in its footer. Without a
   publishing tool, hand over the new file next to the old one.

In a new session, read the page back (with the Artifact tool's read action, which saves the whole page to a
file, or from the file you handed over) and run
`python3 <root>/kit/build.py --extract <saved page> <content.html>`. `build.py` wraps the content between two
sentinel comments and repeats the `<!--plan` block at the end of the page, so `--extract` rebuilds metadata
(theme, lang and versions included), `<main>` and scripts untouched, from a complete document, a fragment, or
a fragment inside another skeleton. Do not ask the look again: go on from point 2 above, or from step 5 if you
are only rebuilding the same version.

## The kit

| File | What it does |
| --- | --- |
| [`kit/base.html`](kit/base.html) | Components (bands, tabs, disclosures, steps, bars, number tables, decisions), light and dark mode (the reader's system, or `data-theme="light"`/`"dark"` on the root element), print rules, masthead with the version, footer with the commit, the list of versions and "the file is canonical"; `lang` and `data-plan-theme` on the content wrapper, also without JavaScript. |
| [`kit/base.js`](kit/base.js) | The generic parts, exposed as `window.Plan`: keyboard tabs, steps with previous and next, disclosures, a composable answer with copy, print with everything open and then the state from before. UI strings come from a per-language dictionary. |
| [`kit/build.py`](kit/build.py) | Assembles content and kit into a complete HTML document (`--fragment`: only the part inside a document), resolves the theme, moves page scripts after `base.js`, wraps the content in sentinels and repeats the metadata at the end; `--extract` does the reverse. Fails on a missing (`theme` included), unknown or repeated key, a non-hex commit, a title outside 2-4 words, an unknown theme, a custom theme without both rows or under 4.5:1, any `%%` left in the page, the same path for input and output, a malformed `versions:` list, or an output that holds another version, another plan or no plan (it is never overwritten). |
| [`kit/plan_history.py`](kit/plan_history.py) | Reads the PLAN file's history in git, commit by commit and then the working copy: the header may change, the body may only grow at the end. Exits 1 on an uncommitted rewrite, on a committed one that no later section declares, or on `## Version N` headings out of order; 2 without git or without a first commit. `--versions` prints the `versions:` block for the page. |
| [`kit/check.py`](kit/check.py) | Smoke test of the page as delivered: source checks (external resources, size, footer, the theme's `forbidden` rules) and Chromium checks (JS errors, horizontal scroll, background, the light/dark switch on the root element, text contrast, bars, tabs and steps with a click cap, print and back, no-JavaScript view). |
| [`kit/themes/`](kit/themes) | The presets: `neutral`, `warm`, `cool`, `high-contrast`. |
| [`examples/`](examples) | An invented PLAN with every component, in the neutral theme and with a custom one. |

## What it does not do

- It does not replace the PLAN, ask for decisions the PLAN does not ask for, or add numbers.
- It does not commit the generated HTML: outputs go outside the repository, and the working copy of the
  content travels inside the page.
- It does not build a page where nobody can answer the questions of step 2 (an unattended job): there only
  step 1 applies.
- It ships no font files: system font stacks only.
