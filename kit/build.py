#!/usr/bin/env python3
"""Assemble an explorable plan page: content + kit -> one self-contained HTML file.

Usage: python3 build.py [--fragment] <content.html> <output.html>
       python3 build.py --extract <page.html> <content.html>

By default the output is a complete HTML document (doctype, charset, viewport, title, description),
ready to open in a browser. With --fragment it is only what goes inside a document, for hosts that
add the skeleton themselves (such as the Claude Artifact tool). The output folder is created if it
does not exist. --extract reads either form, also a fragment inside a foreign skeleton.

The content file opens with a metadata comment, one key per line. A line that starts with a
space continues the previous key. An unknown or repeated key is an error.

    <!--plan
    title: Name of 2-4 words
    description: One sentence for the gallery card.
    masthead: PLAN · short topic
    date: 10 October 2026
    plan: path/to/PLAN-topic-YYYY-MM-DD.md
    commit: <hex sha, 7-40 characters, of the commit the page reflects>
    theme: neutral                 (a preset in kit/themes/, or custom; write neutral for the default)
    lang: en                       (optional: en or it; default en)
    theme-colors: light ink=#14213d paper=#fdf6e3 accent=#b4236a     (only with theme: custom)
      dark ink=#f1e9d2 paper=#101a2e accent=#f4a261
    theme-font: serif              (optional: sans, serif or mono; overrides the preset's font)
    sources: <p>...</p>            (optional, HTML)
      <p>...</p>                   (continuation)
    signature: Prepared on ...     (optional; empty by default)
    versions: 1 2026-10-08 1a2b3c4 First plan.          (optional; one line per version of the
      2 2026-10-10 5d6e7f8 Step 3 split in two.           PLAN, oldest first; the last commit is commit:)
    -->

Then the HTML body, usually `<main id="content">...</main>`. `<script>` blocks in the content are
moved after base.js and can use `window.Plan`. Write the output outside the repository. The input
file may start with a byte order mark.

The output keeps the content between two sentinel comments and re-emits the `<!--plan` block at
the end of the page. From a published page that was saved to a file, `--extract` rebuilds the
content file (metadata, body, scripts, theme and lang included) so the page can be rebuilt.

No overwrite: an output that already exists is replaced only if it holds the same version of the
same plan (rebuilding while you fix what check.py found). Another version, another plan, or a file
without a <!--plan block is left as it is and the build stops. A page without versions: is version 1.

Exit codes: 0 done; 1 on any error: a missing (theme included), unknown or repeated metadata key,
a commit that is not hexadecimal (upper or lower case, written in lower case), a malformed versions
list, an unknown theme, a custom theme without both a light and a dark row or with text/background
contrast below 4.5:1 in either mode, any %% left in the page, the same path for input and output,
an output that holds another version, another plan or no plan, or a file that cannot be found.
"""
import datetime
import html
import json
import pathlib
import re
import sys

KIT = pathlib.Path(__file__).resolve().parent
THEMES = KIT / "themes"
REQUIRED = ("title", "description", "masthead", "date", "plan", "commit", "theme")
OPTIONAL = ("sources", "signature", "lang", "theme-colors", "theme-font", "versions")
META = re.compile(r"<!--plan[ \t]*\n(.*?)-->", re.S)
CONTENT = ("<!--plan:content-->", "<!--/plan:content-->")
PAGE_JS = ("<!--plan:page-js-->", "<!--/plan:page-js-->")
MODES = ("light", "dark")
BASE_KEYS = ("ink", "paper", "accent")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
SCOPES = ("source", "text", "css")  # raw page source; source with HTML entities decoded; CSS only
MIN_CONTRAST = 4.5

# System font stacks only. Custom font files are out of scope for v1.
FONTS = {
    "sans": 'system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
    "serif": 'Georgia,"Iowan Old Style","Palatino Linotype",Palatino,"Times New Roman",serif',
    "mono": 'ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono","Courier New",monospace',
}
CODE_FONT = FONTS["mono"]

# Every string the kit itself writes into a page, per language. Content you write is not here.
UI = {
    "en": {
        "skip": "Skip to content",
        "open": "open",
        "close": "close",
        "to_decide": "to be decided.",
        "copied": "Copied.",
        "selected": "Selected: copy it with Ctrl+C or Cmd+C.",
        "decimal": ".",
        "date_fmt": "{d} {m} {y}",
        "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"],
        "footer": "This page presents the PLAN; it does not replace it. The source is the versioned "
                  "file {plan}; the page reflects commit {commit}. If the two differ, the file is canonical.",
        "version": "version {n}",
        "versions": "Versions of this plan, oldest first. Each one is the PLAN file at its commit: the file "
                    "only grows, so an earlier version is never rewritten.",
        "current": "this page",
    },
    "it": {
        "skip": "Vai al contenuto",
        "open": "apri",
        "close": "chiudi",
        "to_decide": "da decidere.",
        "copied": "Copiata.",
        "selected": "Selezionata: copiala con Ctrl+C o Cmd+C.",
        "decimal": ",",
        "date_fmt": "{d} {m} {y}",
        "months": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
                   "settembre", "ottobre", "novembre", "dicembre"],
        "footer": "Questa pagina presenta il PLAN, non lo sostituisce. La fonte è il file versionato "
                  "{plan}; la pagina riflette il commit {commit}. Se i due divergono, vale il file.",
        "version": "versione {n}",
        "versions": "Versioni di questo piano, dalla prima. Ognuna è il file PLAN al suo commit: il file "
                    "cresce soltanto, quindi una versione precedente non si riscrive.",
        "current": "questa pagina",
    },
}
JS_UI_KEYS = ("to_decide", "copied", "selected", "decimal", "date_fmt", "months")


class PlanError(Exception):
    """Any problem with the content, the theme or the files: reported once, exit code 1."""


def fail(msg):
    raise PlanError(msg)


# ---------------------------------------------------------------- colour maths

def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def mix(a, b, t):
    """Colour a moved toward colour b by the share t (0..1)."""
    return _hex(tuple(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b))))


def _lin(v):
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(h):
    r, g, b = (_lin(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _muted(bg, fg, wash, target):
    """Weakest mix of fg into bg that still reads at `target` on both bg and wash."""
    for i in range(40, 101):
        c = mix(bg, fg, i / 100.0)
        if contrast(c, bg) >= target + 0.05 and contrast(c, wash) >= target + 0.05:
            return c
    return fg


def derive(mode, base, target):
    """From ink, paper and accent to every token the CSS uses. One function for presets and custom."""
    ink, paper, accent = (base[k].lower() for k in BASE_KEYS)
    wash = mix(paper, ink, 0.05)
    t = {"ink": ink, "paper": paper, "accent": accent, "wash": wash,
         "rule": mix(paper, ink, 0.18), "selection": mix(paper, ink, 0.14),
         "muted": _muted(paper, ink, wash, target)}
    # the dark band is the ink colour in light mode and a deeper shade of the paper in dark mode
    band, band_ink = (ink, paper) if mode == "light" else (mix(paper, "#000000", 0.4), ink)
    band_wash = mix(band, band_ink, 0.08)
    t.update({"band_dark": band, "band_dark_ink": band_ink, "band_dark_wash": band_wash,
              "band_dark_rule": mix(band, band_ink, 0.25),
              "band_dark_muted": _muted(band, band_ink, band_wash, target)})
    return t


def validate_contrast(name, mode, t, target):
    pairs = [("ink", "paper"), ("accent", "paper"), ("ink", "wash"), ("accent", "wash"),
             ("muted", "paper"), ("muted", "wash"), ("band_dark_ink", "band_dark"),
             ("band_dark_muted", "band_dark"), ("band_dark_muted", "band_dark_wash")]
    for a, b in pairs:
        r = contrast(t[a], t[b])
        if r < target:
            fail(f"theme {name}: in {mode} mode {a.replace('_', '-')} {t[a]} on {b.replace('_', '-')} {t[b]} "
                 f"has contrast {r:.2f}:1, minimum {target:g}:1. Choose a darker ink or a lighter paper "
                 f"(or the reverse in dark mode), or a stronger accent.")


# ---------------------------------------------------------------- metadata

def read_meta(block):
    """Parse the `<!--plan` block. Syntax and key-level checks only; the theme is resolved apart."""
    meta, last = {}, None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t":
            if last is None:
                fail(f"continuation line before any key: {line!r}")
            meta[last] += "\n" + line.strip()
            continue
        k, sep, v = line.partition(":")
        k = k.strip()
        if not sep or k not in REQUIRED + OPTIONAL:
            fail(f"invalid metadata line: {line!r}. Allowed keys: {', '.join(REQUIRED + OPTIONAL)}; "
                 "a line that continues the previous one starts with a space")
        if k in meta:
            fail(f"repeated metadata key: {k}")
        meta[k], last = v.strip(), k
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        hint = ""
        if "theme" in missing:
            hint = (". theme is required: write `theme: neutral` for the default look "
                    "(or warm, cool, high-contrast, custom)")
        fail("missing metadata: " + ", ".join(missing) + hint)
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", meta["commit"]):
        fail(f"commit is not hexadecimal (7-40 characters): {meta['commit']!r}")
    meta["commit"] = meta["commit"].lower()
    if meta.get("lang", "en") not in UI:
        fail(f"lang must be one of {', '.join(sorted(UI))}, not {meta['lang']!r}")
    if meta.get("theme-font", "sans") not in FONTS:
        fail(f"theme-font must be one of {', '.join(FONTS)}, not {meta['theme-font']!r}")
    parse_versions(meta)
    return meta


def parse_versions(meta):
    """`versions:` as a list of (number, date, commit, what changed), oldest first; [] when absent.
    Numbers run 1..N, dates are valid and never go back, commits are distinct, the last is commit:."""
    out = []
    for line in meta.get("versions", "").splitlines():
        if not line.strip():
            continue
        m = re.fullmatch(r"(\d+)\s+(\d{4}-\d{2}-\d{2})\s+([0-9a-fA-F]{7,40})\s+(\S.*)", line.strip())
        if not m:
            fail(f"versions: bad line {line.strip()!r}; write `<number> <YYYY-MM-DD> <commit> <what changed>`")
        n, day, sha, what = int(m.group(1)), m.group(2), m.group(3).lower(), m.group(4).strip()
        try:
            date = datetime.date.fromisoformat(day)
        except ValueError:
            fail(f"versions: {day} is not a valid date (version {n})")
        if n != len(out) + 1:
            fail(f"versions: expected version {len(out) + 1}, found {n}; number them 1, 2, 3... oldest first")
        if out and date < out[-1][1]:
            fail(f"versions: version {n} is dated {day}, before version {n - 1} ({out[-1][1]})")
        if any(sha == v[2] for v in out):
            fail(f"versions: commit {sha} appears twice; each version reflects its own commit")
        out.append((n, date, sha, what))
    if "versions" in meta and not out:
        fail("versions: is empty; remove the key or write one line per version")
    if out and out[-1][2] != meta["commit"].lower():
        fail(f"versions: the last version ({out[-1][0]}) has commit {out[-1][2]}, but commit: is "
             f"{meta['commit'].lower()}; the page reflects the last version")
    return out


def version_of(meta):
    """The version a page or content file holds: the last of `versions:`, or 1 without the key."""
    versions = parse_versions(meta)
    return versions[-1][0] if versions else 1


def parse_theme_colors(value):
    """`light ink=#.. paper=#.. accent=#..` and the same for `dark`, on separate lines or after `;`."""
    out = {}
    for line in re.split(r"[;\n]", value):
        parts = line.split()
        if not parts:
            continue
        mode = parts[0]
        if mode not in MODES:
            fail(f"theme-colors: each line starts with light or dark, not {mode!r}")
        if mode in out:
            fail(f"theme-colors: {mode} given twice")
        cols = {}
        for kv in parts[1:]:
            k, sep, v = kv.partition("=")
            if not sep or k not in BASE_KEYS or not HEX.fullmatch(v) or k in cols:
                fail(f"theme-colors: bad entry {kv!r} in the {mode} line; use ink=#rrggbb paper=#rrggbb accent=#rrggbb")
            cols[k] = v.lower()
        if set(cols) != set(BASE_KEYS):
            fail(f"theme-colors: the {mode} line needs exactly ink, paper and accent")
        out[mode] = cols
    if set(out) != set(MODES):
        gone = [m for m in MODES if m not in out][0]
        if gone == "dark":
            line = "dark ink={paper} paper={ink} accent={accent}".format(**out["light"])
            how = ("This swaps ink and paper of the light line; lighten the accent until the contrast "
                   "is accepted.")
        else:
            line = "light ink=#rrggbb paper=#rrggbb accent=#rrggbb"
            how = "Use a dark ink on a light paper."
        fail(f"theme-colors: the {gone} line is missing, both a light and a dark line are required. "
             f"Add this line to the theme-colors value, as a continuation line that starts with a space: "
             f"`  {line}`. {how}")
    return out


def load_preset(name):
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        fail(f"invalid theme name: {name!r}")
    path = THEMES / f"{name}.json"
    if not path.is_file():
        have = sorted(p.stem for p in THEMES.glob("*.json")) + ["custom"]
        fail(f"unknown theme {name!r}. Available: {', '.join(have)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        fail(f"{path.name} is not valid JSON: {e}")
    try:
        colors = {m: {k: data["colors"][m][k] for k in BASE_KEYS} for m in MODES}
        font = data.get("font", "sans")
        target = float(data.get("min_contrast", MIN_CONTRAST))
        forbidden = data.get("forbidden", [])
    except (KeyError, TypeError, ValueError) as e:
        fail(f"{path.name}: missing or malformed field ({e!r})")
    for m in MODES:
        for k, v in colors[m].items():
            if not isinstance(v, str) or not HEX.fullmatch(v):
                fail(f"{path.name}: colors.{m}.{k} must be #rrggbb")
    if font not in FONTS:
        fail(f"{path.name}: font must be one of {', '.join(FONTS)}")
    if target < MIN_CONTRAST:
        fail(f"{path.name}: min_contrast cannot be below {MIN_CONTRAST:g}")
    if not isinstance(forbidden, list):
        fail(f"{path.name}: forbidden must be a list")
    for rule in forbidden:
        try:
            ok = rule["scope"] in SCOPES and rule["name"] and re.compile(rule["pattern"])
        except (KeyError, TypeError, re.error) as e:
            fail(f"{path.name}: bad forbidden rule {rule!r} ({e})")
        if not ok:
            fail(f"{path.name}: forbidden rules need name, pattern and scope in {', '.join(SCOPES)}: {rule!r}")
    return colors, font, target, forbidden


def resolve_theme(meta):
    """Theme from the metadata: tokens for both modes, font, and the forbidden list. Validates contrast."""
    name = meta["theme"]
    if name == "custom":
        if "theme-colors" not in meta:
            fail("theme: custom needs theme-colors")
        colors, font, target, forbidden = parse_theme_colors(meta["theme-colors"]), "sans", MIN_CONTRAST, []
    else:
        if "theme-colors" in meta:
            fail("theme-colors is only for theme: custom; a preset brings its own colours")
        colors, font, target, forbidden = load_preset(name)
    font = meta.get("theme-font", font)
    tokens = {m: derive(m, colors[m], target) for m in MODES}
    for m in MODES:
        validate_contrast(name, m, tokens[m], target)
    return {"name": name, "font": font, "min_contrast": target, "colors": tokens, "forbidden": forbidden}


# ---------------------------------------------------------------- output pieces

def css_string(text):
    """A CSS string token. Quote, backslash, `<` and anything outside printable ASCII become a CSS
    escape (`\\XXXXXX ` with its closing space), so the result does not depend on the page encoding."""
    out = []
    for ch in text:
        if ch in '"\\<' or not 0x20 <= ord(ch) < 0x7f:
            out.append("\\%x " % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def theme_css(theme, ui):
    def block(t):
        return "".join(f"--{k.replace('_', '-')}:{v};" for k, v in t.items())
    strings = f"--ui-open:{css_string(ui['open'])};--ui-close:{css_string(ui['close'])};"
    dark = block(theme["colors"]["dark"]) + "color-scheme:dark"
    # dark follows the reader's system, unless the host forces light with data-theme="light" on the
    # root; data-theme="dark" on the root forces dark whatever the system says
    return (":root{--font:" + FONTS[theme["font"]] + ";--mono:" + CODE_FONT + ";" + strings
            + block(theme["colors"]["light"]) + "color-scheme:light}\n"
            "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){" + dark + "}}\n"
            ":root[data-theme=\"dark\"]{" + dark + "}")


def ui_json(ui, lang):
    data = {k: ui[k] for k in JS_UI_KEYS}
    data["lang"] = lang
    return json.dumps(data, ensure_ascii=True).replace("</", "<\\/")


def ensure_distinct(src, out):
    """The output must not be the input: building onto the content file would destroy it."""
    if src == out or (src.exists() and out.exists() and src.samefile(out)):
        fail(f"input and output are the same file: {out}. Write the output to another path.")


def versioned_name(out, n):
    """The output path with `.v<n>` before the extension, replacing a `.v<k>` already there."""
    stem = re.sub(r"\.v\d+$", "", out.stem)
    return out.with_name(f"{stem}.v{n}{out.suffix}")


def ensure_no_overwrite(out, meta):
    """Never replace another version of the plan, another plan, or a file this kit did not write.
    The same version of the same plan may be rebuilt: that is fixing it, not overwriting it."""
    if not out.exists():
        return
    keep = " It is left as it is: choose another path, or remove the file yourself if you mean to replace it."
    if not out.is_file():
        fail(f"{out} exists and is not a file.{keep}")
    try:
        blocks = META.findall(out.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as e:
        fail(f"{out} exists and cannot be read ({e}).{keep}")
    if not blocks:
        fail(f"{out} exists and holds no <!--plan block, so this kit did not write it.{keep}")
    try:
        old = read_meta(blocks[-1])
    except PlanError as e:
        fail(f"{out} exists and its <!--plan block cannot be read ({e}).{keep}")
    if old["plan"] != meta["plan"]:
        fail(f"{out} holds another plan ({old['plan']}).{keep}")
    have, want = version_of(old), version_of(meta)
    if have != want:
        fail(f"{out} holds version {have} of this plan and this is version {want}: a version is never "
             f"overwritten. Write version {want} to {versioned_name(out, want)}.")


def write_out(out, text):
    """Write the output, creating its folder if needed."""
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    except OSError as e:
        fail(f"cannot write {out}: {e}")


def read_content(path):
    if not path.is_file():
        fail(f"file not found: {path}")
    text = path.read_text(encoding="utf-8-sig").lstrip()
    m = META.match(text)
    if not m:
        fail("the content must open with the <!--plan ... --> comment")
    block = m.group(1)
    meta = read_meta(block)
    body = text[m.end():]
    for s in CONTENT + PAGE_JS:
        if s in body:
            fail(f"the content contains a reserved sentinel comment: {s}")
    scripts = re.findall(r"<script\b[^>]*>.*?</script>", body, re.S)
    for s in scripts:
        body = body.replace(s, "")
    return block, meta, body.strip(), "\n".join(scripts)


def extract(page_path, out_path):
    """From a built page (also one read back from the publishing tool) to the content file to rebuild."""
    ensure_distinct(page_path, out_path)
    if not page_path.is_file():
        fail(f"file not found: {page_path}")
    text = page_path.read_text(encoding="utf-8")
    blocks = META.findall(text)
    if not blocks:
        fail("no <!--plan ... --> block in the page: it was not built with this kit")
    parts = []
    for a, b in (CONTENT, PAGE_JS):
        i = text.find(a)
        j = text.find(b, i + 1)
        if i < 0 or j < 0:
            fail(f"missing sentinel in the page: {a if i < 0 else b}")
        parts.append(text[i + len(a):j].strip("\n"))
    ensure_no_overwrite(out_path, read_meta(blocks[-1]))
    write_out(out_path, f"<!--plan\n{blocks[-1]}-->\n{parts[0]}\n{parts[1]}\n")
    print(f"extracted {out_path} from the <!--plan block at the end of {page_path.name}")


def build(src, out, fragment=False):
    ensure_distinct(src, out)
    block, meta, body, page_js = read_content(src)
    ensure_no_overwrite(out, meta)
    words = len(meta["title"].split())
    if not 2 <= words <= 4:
        fail(f"the title is a name of 2-4 words, not {words}: {meta['title']!r}")
    lang = meta.get("lang", "en")
    ui = UI[lang]
    theme = resolve_theme(meta)
    esc = lambda s: html.escape(s, quote=True)
    footer = ui["footer"].format(plan=f"<code>{esc(meta['plan'])}</code>", commit=f"<code>{esc(meta['commit'])}</code>")
    footer = f"<p data-canonical>{footer}</p>"
    date = esc(meta["date"])
    versions = parse_versions(meta)
    if versions:
        date += " · " + esc(ui["version"].format(n=versions[-1][0]))
        label = ui["version"][:1].upper() + ui["version"][1:]
        items = "".join(
            f"<li>{esc(label.format(n=n))} · {d.isoformat()} · <code>{sha}</code> · {esc(what)}"
            + (f" ({esc(ui['current'])})" if n == versions[-1][0] else "") + "</li>"
            for n, d, sha, what in versions)
        footer += f'\n<p>{esc(ui["versions"])}</p>\n<ol class="versions">{items}</ol>'
    signature = meta.get("signature", "")
    if fragment:
        doc_head = doc_body = doc_end = ""
    else:  # a complete document: standards mode, charset and viewport declared
        doc_head = ('<!doctype html>\n<html lang="' + esc(lang) + '">\n<head>\n<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">\n')
        doc_body, doc_end = "</head>\n<body>", "</body>\n</html>\n"
    subst = {
        "%%DOC_HEAD%%": doc_head,
        "%%DOC_BODY%%": doc_body,
        "%%DOC_END%%": doc_end,
        "%%TITLE%%": esc(meta["title"]),
        "%%DESCRIPTION%%": esc(meta["description"]),
        "%%LANG%%": esc(lang),
        "%%THEME%%": esc(theme["name"]),
        "%%THEME_CSS%%": theme_css(theme, ui),
        "%%SKIP%%": esc(ui["skip"]),
        "%%MASTHEAD%%": esc(meta["masthead"]),
        "%%DATE%%": date,
        "%%CONTENT%%": f"{CONTENT[0]}\n{body}\n{CONTENT[1]}",
        "%%FOOTER%%": footer,
        "%%SOURCES%%": meta.get("sources", ""),
        "%%SIGNATURE%%": f"<p>{esc(signature)}</p>" if signature else "",
        "%%UI%%": ui_json(ui, lang),
        "%%JS%%": (KIT / "base.js").read_text(encoding="utf-8"),
        "%%PAGE_JS%%": f"{PAGE_JS[0]}\n{page_js}\n{PAGE_JS[1]}",
        "%%META%%": f"<!--plan\n{block}-->",
    }
    # One pass over the template: substituted values are never re-read, so a %%X%% written in the
    # content stays as it is and trips the leftover check below instead of changing silently.
    template = (KIT / "base.html").read_text(encoding="utf-8")
    unknown = sorted(set(re.findall(r"%%[A-Z_]+%%", template)) - set(subst))
    if unknown:
        fail("template placeholders without a value: " + ", ".join(unknown))
    page = re.sub(r"%%[A-Z_]+%%", lambda m: subst[m.group(0)], template)
    if "%%" in page:
        seen = []
        for m in re.finditer("%%", page):
            around = page[max(0, m.start() - 15):m.end() + 15].replace("\n", " ")
            if around not in seen:
                seen.append(around)
        fail("%% left in the page (write a literal one as &#37;&#37; in the content): "
             + "; ".join(repr(a) for a in seen[:5]))
    write_out(out, page)
    print(f"wrote {out} · {len(page.encode()):,} bytes · theme: {theme['name']} · lang: {lang}"
          f" · {'fragment' if fragment else 'document'}")


def main(argv):
    args = [a for a in argv[1:] if a != "--fragment"]
    fragment = len(args) != len(argv) - 1
    try:
        if len(args) == 3 and args[0] == "--extract":
            if fragment:
                fail("--fragment is for building a page; --extract reads any form")
            extract(pathlib.Path(args[1]).resolve(), pathlib.Path(args[2]).resolve())
        elif len(args) == 2 and not args[0].startswith("--"):
            build(pathlib.Path(args[0]).resolve(), pathlib.Path(args[1]).resolve(), fragment)
        else:
            fail("usage: build.py [--fragment] <content.html> <output.html> "
                 "| build.py --extract <page.html> <content.html>")
    except PlanError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
