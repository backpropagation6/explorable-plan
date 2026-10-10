#!/usr/bin/env python3
"""Smoke test of an explorable plan page before publishing: source checks and rendering in Chromium.

Usage: python3 check.py <page.html> [screenshot-folder]

It is a filter, not a gate: it finds the known faults, it does not prove the page is right. It does
not catch a readable colour outside the theme, overlapping elements or cut-off labels: look at the
screenshots before trusting an OK.

The page is tested as delivered: a file that starts with <!doctype> is loaded as it is; anything else
is a fragment (build.py --fragment) and is wrapped in a document skeleton, as a publishing tool does.

Source: <title> of 2-4 words and a meta description (in the head, or at the top of a fragment), no
%% placeholder, no external resource (stylesheet, @import, url(http...), src or href outside <a>)
except scripts from the allowed CDNs, under 16 MB, a footer element with a data-canonical attribute
holding a <code> with the hex commit that the metadata states, and every rule in the theme's
`forbidden` list (a preset in kit/themes/*.json; taste rules such as fonts, gradients or dashes
live there, not here).
Chromium: at 1280 and 390 px, light and dark: no JS error (after one, interaction is skipped), no
horizontal scroll, the background the theme expects, text/background contrast of at least 4.5:1 for
every visible text, one H1, no bar wider than its scale; with data-theme="dark" (or "light") set on
the root element the background is the theme's dark (or light) one whatever the system scheme says;
every tab and disclosure opens without error and the "next" button of the steps ends; in print every
panel is visible and after printing the state of before comes back; without JavaScript every panel
is visible, and the content wrapper carries the lang and data-plan-theme of the metadata. Each page
load and click has a 5 s timeout.
Screenshots go in the given folder (default: <page>-check/ next to the page).

Exit codes: 0 prints OK; 1 prints the list of problems; 2 usage error; 3 the browser checks did NOT
run (playwright or Chromium is missing): only the source checks ran, the result is incomplete, and
that is never reported as a pass. Exit 3 is also used when the source checks found problems, which
are printed before the notice.
"""
import html
import importlib.util
import pathlib
import re
import sys

try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:
    sync_playwright = None
    PlaywrightError = Exception


class BrowserUnavailable(Exception):
    """Chromium could not be started: the browser checks cannot run."""

HERE = pathlib.Path(__file__).resolve().parent
CDN = ("https://cdnjs.cloudflare.com/", "https://cdn.jsdelivr.net/npm/", "https://unpkg.com/",
       "https://code.jquery.com/", "https://cdn.tailwindcss.com")
MIN_RATIO = 4.5
TIMEOUT_MS = 5000
DOCTYPE = re.compile(r"[\s\ufeff]*<!doctype\b", re.I)
PANELS = "[role=tabpanel], .disc-body"
HIDDEN_IDS = """sel => [...document.querySelectorAll(sel)].filter(e => !e.getClientRects().length).map(e => e.id || e.className)"""
WIDE = """() => { const W = document.documentElement.clientWidth;
  return [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect();
    return r.right > W + 1 && getComputedStyle(e).position !== 'fixed'; })
  .slice(0, 6).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '') + ' ' + Math.round(e.getBoundingClientRect().right)); }"""
# declared bar widths (inline style, in %) that add up to more than the track: flexbox would shrink
# them silently, so the bar would look right and be wrong
BARS_OVER_SCALE = """() => [...document.querySelectorAll('.track')].filter(t =>
  [...t.querySelectorAll(':scope > .seg')].reduce((s, x) => s + (x.style.width.endsWith('%') ? parseFloat(x.style.width) : 0), 0) > 100.001
).length"""
# text/background contrast of every visible text node, form control and SVG text
CONTRAST = """min => {
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const over = (t, b) => ({r: t.r * t.a + b.r * (1 - t.a), g: t.g * t.a + b.g * (1 - t.a), b: t.b * t.a + b.b * (1 - t.a), a: 1});
  const bgOf = e => { const chain = [];
    for (let n = e; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { chain.push(c); if (c.a >= 1) break; } }
    let base = {r: 255, g: 255, b: 255, a: 1}; chain.reverse().forEach(c => { base = over(c, base); }); return base; };
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const bad = [], seen = new Set();
  for (const e of document.querySelectorAll('body *')) {
    if (e.closest('script,style,noscript,option') || e.closest(':disabled') || !e.getClientRects().length) continue;
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || e.getBoundingClientRect().right <= 0) continue;
    const control = e.matches('input,textarea,select') && !['checkbox', 'radio', 'range', 'hidden'].includes(e.type);
    const text = control || [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!text) continue;
    const fg = parse(e instanceof SVGElement ? cs.fill : cs.color);
    if (!fg) continue;
    const bg = bgOf(e), r = ratio(over(fg, bg), bg);
    if (r < min) {
      const label = e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : '') + ' "' + (e.textContent || e.value || '').trim().slice(0, 24) + '" ' + r.toFixed(2) + ':1';
      if (!seen.has(label)) { seen.add(label); bad.push(label); }
    }
  }
  return bad.slice(0, 6); }"""


# background of the body with data-theme set on the root; the attribute is put back afterwards
FORCE_THEME = """t => { const h = document.documentElement, prev = h.getAttribute('data-theme');
  h.setAttribute('data-theme', t); const bg = getComputedStyle(document.body).backgroundColor;
  if (prev === null) h.removeAttribute('data-theme'); else h.setAttribute('data-theme', prev); return bg; }"""


def load_build():
    """The parser and theme resolver live in build.py, so the two cannot disagree about the metadata."""
    spec = importlib.util.spec_from_file_location("explorable_plan_build", HERE / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rgb(hex_color):
    return "rgb(%d, %d, %d)" % tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def source_checks(src, theme):
    ko = []
    if DOCTYPE.match(src):  # a document: the pair is looked for in the head
        h = re.search(r"<head\b[^>]*>(.*?)</head>", src, re.S | re.I)
        head = h.group(1) if h else ""
        t = re.search(r"<title>(.*?)</title>", head, re.S | re.I)
        d = re.search(r"<meta\s+name=\"description\"\s+content=\"[^\"]+\"", head, re.I)
        m = t if t and d else None
        where = "the document head has no"
    else:  # a fragment: the pair opens the file
        m = re.match(r"\s*<title>(.*?)</title>\s*<meta name=\"description\" content=\"[^\"]+\">", src, re.S)
        where = "the page does not open with"
    if not m:
        ko.append(f"{where} <title> and <meta name=\"description\">")
    elif not 2 <= len(m.group(1).split()) <= 4:
        ko.append(f"title of {len(m.group(1).split())} words, 2-4 needed: {m.group(1)!r}")
    if "%%" in src:
        ko.append("a %% placeholder is left over")
    # taste rules come from the theme; each one says which part of the page it reads
    css = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", src, re.S | re.I)
                    + re.findall(r"\sstyle\s*=\s*\"([^\"]*)\"", src, re.I) + re.findall(r"\sstyle\s*=\s*'([^']*)'", src, re.I))
    scopes = {"source": src, "text": html.unescape(src), "css": css}
    for rule in theme["forbidden"]:
        flags = re.I if rule.get("ignorecase") else 0
        found = re.findall(rule["pattern"], scopes[rule["scope"]], flags)
        if found:
            ko.append(f"forbidden by theme {theme['name']!r}: {rule['name']} ({len(found)} match{'es' if len(found) != 1 else ''})")
    if re.search(r"<link[^>]+stylesheet", src, re.I):
        ko.append("external stylesheet: everything inline")
    if re.search(r"@import\b", css, re.I) or re.search(r"url\(\s*[\"']?(https?:)?//", css, re.I):
        ko.append("CSS that loads from outside (@import or url(http...)): everything inline")
    for tag, u in re.findall(r"<(\w+)\b[^>]*?\s(?:src|href|xlink:href)\s*=\s*[\"']?((?:https?:)?//[^\"'\s>]+)", src, re.I):
        if tag.lower() == "script" and u.startswith(CDN):
            continue
        if tag.lower() == "a":
            continue
        ko.append(f"external resource in <{tag}>: {u}" + (" (host not allowed)" if tag.lower() == "script" else ""))
    if len(src.encode()) > 16 * 1024 * 1024:
        ko.append("page over 16 MB")
    return ko


def footer_check(src, commit):
    """The footer is the element with data-canonical; its <code> must hold the commit of the metadata."""
    m = re.search(r"<(\w+)\b[^>]*\sdata-canonical\b[^>]*>(.*?)</\1>", src, re.S)
    codes = re.findall(r"<code>([^<]*)</code>", m.group(2)) if m else []
    if commit not in codes:
        return ["no footer: an element with data-canonical holding a <code> with the commit " + commit]
    return []


def browser_checks(url, out, theme, meta, ko):
    lang = meta.get("lang", "en")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # missing browser, missing system libraries, sandbox refusal
            raise BrowserUnavailable(str(e).strip().splitlines()[0][:200] + " (run: playwright install chromium)")
        for w in (1280, 390):
            for mode in ("light", "dark"):
                where = f"{w}px {mode}"
                ctx = b.new_context(viewport={"width": w, "height": 900}, color_scheme=mode)
                ctx.set_default_timeout(TIMEOUT_MS)
                pg = ctx.new_page()
                err = []
                pg.on("pageerror", lambda e, err=err: err.append(str(e)))
                pg.on("console", lambda m, err=err: err.append(m.text) if m.type == "error" else None)
                try:
                    pg.goto(url)
                    pg.wait_for_timeout(300)
                    if w == 1280 and mode == "light":
                        if (h1 := pg.evaluate("document.querySelectorAll('h1').length")) != 1:
                            ko.append(f"{h1} H1 in the page, one needed")
                        if pg.evaluate(BARS_OVER_SCALE):
                            ko.append("a bar is wider than its scale (segment widths add up to more than 100%)")
                    sw, cw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                    if sw > cw:
                        ko.append(f"{where}: horizontal scroll ({sw} > {cw}): {pg.evaluate(WIDE)}")
                    want = rgb(theme["colors"][mode]["paper"])
                    bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
                    if bg != want:
                        ko.append(f"{where}: background {bg}, the theme expects {want}")
                    if w == 1280:  # the host toggle: data-theme on the root beats the system scheme
                        other = "dark" if mode == "light" else "light"
                        forced = pg.evaluate(FORCE_THEME, other)
                        want_other = rgb(theme["colors"][other]["paper"])
                        if forced != want_other:
                            ko.append(f"{where}: with data-theme={other!r} on the root the background is {forced}, "
                                      f"the theme's {other} background is {want_other}")
                    low = pg.evaluate(CONTRAST, MIN_RATIO)
                    if low:
                        ko.append(f"{where}: text contrast under {MIN_RATIO}:1: {low}")
                    pg.screenshot(path=str(out / f"{w}-{mode}.png"), full_page=True)
                    if err:
                        # after an error at start the interaction is meaningless and may never end
                        ko.append(f"{where}: JS errors {err[:3]}" + (" (interaction skipped)" if w == 390 and mode == "light" else ""))
                    elif w == 390 and mode == "light":
                        interact(pg, ko)
                        if err:
                            ko.append(f"{where}: JS errors during interaction {err[:3]}")
                except PlaywrightError as e:
                    ko.append(f"{where}: browser step failed: {str(e).splitlines()[0][:200]}")
                ctx.close()
        ctx = b.new_context(viewport={"width": 390, "height": 900}, java_script_enabled=False)
        ctx.set_default_timeout(TIMEOUT_MS)
        pg = ctx.new_page()
        try:
            pg.goto(url)
            loc = pg.locator(PANELS)
            hidden = [loc.nth(i).get_attribute("id") for i in range(loc.count()) if not loc.nth(i).is_visible()]
            if hidden:
                ko.append(f"without JavaScript these stay hidden: {hidden}")
            wrap = pg.evaluate("""() => { const c = document.getElementById('content'); if (!c) return null;
              const l = c.closest('[lang]'), t = c.closest('[data-plan-theme]');
              return {lang: l && l.getAttribute('lang'), theme: t && t.getAttribute('data-plan-theme')}; }""")
            if wrap is None:
                ko.append("no element with id=\"content\"")
            elif wrap["lang"] != lang or wrap["theme"] != theme["name"]:
                ko.append(f"without JavaScript the content wrapper has lang={wrap['lang']!r} data-plan-theme={wrap['theme']!r}, "
                          f"the metadata says lang={lang!r} theme={theme['name']!r}")
        except PlaywrightError as e:
            ko.append(f"without JavaScript: browser step failed: {str(e).splitlines()[0][:200]}")
        ctx.close()
        b.close()


def interact(pg, ko):
    """Tabs, disclosures, the cap on 'next', print and back."""
    for t in pg.locator("[role=tab]").all():
        if t.is_visible():
            t.click()
            panel = t.get_attribute("aria-controls")
            if panel and not pg.locator(f"#{panel}").is_visible():
                ko.append(f"tab {t.inner_text()!r} does not show #{panel}")
    for d in pg.locator(".disc-btn").all():
        if d.is_visible():
            d.click()
            d.click()
    cap = pg.locator("[role=tab]").count()
    for n in pg.locator("[data-step=next]").all():
        for _ in range(cap):
            if not (n.is_visible() and n.is_enabled()):
                break
            n.click()
        if n.is_visible() and n.is_enabled():
            ko.append(f"the 'next' button is still enabled after {cap} clicks")
    before = pg.evaluate(HIDDEN_IDS, PANELS)
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pg.emulate_media(media="print")
    hidden = pg.evaluate(HIDDEN_IDS, PANELS)
    if hidden:
        ko.append(f"in print these stay hidden: {hidden}")
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")
    pg.emulate_media(media="screen")
    if (after := pg.evaluate(HIDDEN_IDS, PANELS)) != before:
        ko.append(f"after printing the hidden panels are not as before: {before} -> {after}")


def report(ko, shots):
    print("KO")
    for k in ko:
        print(" - " + k)
    print(f"screenshots: {shots}")


def main():
    if len(sys.argv) not in (2, 3):
        print("usage: check.py <page.html> [screenshot-folder]", file=sys.stderr)
        return 2
    page = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else page.with_name(page.stem + "-check")
    if not page.is_file():
        print(f"file not found: {page}", file=sys.stderr)
        return 2
    src = page.read_text(encoding="utf-8")
    build = load_build()
    blocks = build.META.findall(src)
    if not blocks:
        print("KO\n - no <!--plan block at the end of the page: it was not built with kit/build.py, so the theme is unknown")
        return 1
    try:
        meta = build.read_meta(blocks[-1])
        theme = build.resolve_theme(meta)
    except build.PlanError as e:
        print(f"KO\n - metadata or theme: {e}")
        return 1
    ko = source_checks(src, theme) + footer_check(src, meta["commit"])

    if sync_playwright is None:
        return not_run(ko, "playwright cannot be imported (pip install playwright && playwright install chromium)")
    out.mkdir(parents=True, exist_ok=True)
    if DOCTYPE.match(src):
        url = page.as_uri()  # a complete document is tested as it is
    else:
        # the publishing tool wraps the fragment in a document skeleton: simulate it
        wrapped = out / "wrapped.html"
        wrapped.write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
                           'content="width=device-width,initial-scale=1"></head><body>' + src + "</body></html>", encoding="utf-8")
        url = wrapped.as_uri()
    try:
        browser_checks(url, out, theme, meta, ko)
    except BrowserUnavailable as e:
        return not_run(ko, "Chromium could not be started: " + str(e))
    if ko:
        report(ko, out)
        return 1
    print(f"OK · screenshots to look at in {out}")
    return 0


def not_run(ko, why):
    print("BROWSER CHECKS NOT RUN: " + why)
    print("Only the source checks ran. This is not a pass: look at the page in a browser or install the dependencies.")
    if ko:
        print("Source checks found problems:")
        for k in ko:
            print(" - " + k)
    else:
        print("Source checks: no problems found.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
