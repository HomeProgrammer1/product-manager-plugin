#!/usr/bin/env python3
"""sdd-product charts: turn a product validation data file (data.json) into
editorial SVG charts, a review dashboard (index.html) and a manifest.

data.json is the single source of truth. Everything written here is generated,
stamped with the hash of the data it was drawn from, and never edited by hand.

Charts (each drawn only when its data is present):
  market       TAM / SAM / SOM as nested circles, area to scale
  trend        market size by year, actual vs projected
  pricing      entry price per competitor, normalised to one period
  features     competitor feature matrix (full / partial / none / unknown)
  positioning  2x2 positioning map
  assumptions  impact x uncertainty map of risky assumptions
  scorecard    validation scorecard with verdict and confidence
  experiments  experiment timeline in weeks

Usage:
  product_charts.py check <data.json> [--strict]
  product_charts.py build <data.json> [--out DIR] [--tokens FILE] [--theme FILE]
  product_charts.py verdict <data.json>
  product_charts.py verify <data.json>
  product_charts.py provenance <data.json>

check writes nothing; it reports schema, consistency and evidence problems.
Exit 1 on errors (and on warnings with --strict).
verify opens every source and writes signed verification records into data.json.
provenance prints a table of every number the verdict uses and what it rests on.

Standard library only. verify needs network; PDF sources also need pdftotext.
"""
import argparse
import hashlib
import html
import json
import math
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------- theme
# Same semantic roles as sdd-diagrams, plus the data roles a chart needs.

DEFAULT_THEME = {
    "paper": "#fafaf9",
    "paper2": "#f1f0ee",
    "ink": "#1f2430",
    "muted": "#4a5468",
    "soft": "#5f6b80",
    "rule": "#d6d3ce",
    "grid": "#e7e5e1",
    "accent": "#b4400f",
    "accentTint": "#f6e7df",
    "link": "#1f4fb8",
    "series": "#2a78d6",
    "seriesLight": "#86b6ef",
    "seriesTint": "#dbe8f8",
    "critical": "#d03b3b",
    "font": "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
}

DARK_THEME = {
    "paper": "#1a1a19",
    "paper2": "#242422",
    "ink": "#f0efec",
    "muted": "#c3c2b7",
    "soft": "#a9a79f",
    "rule": "#45443f",
    "grid": "#2c2c2a",
    "accent": "#f08a55",
    "accentTint": "#3d2619",
    "link": "#8fb4ff",
    "series": "#3987e5",
    "seriesLight": "#256abf",
    "seriesTint": "#1d2a3b",
    "critical": "#e66767",
}

TOKEN_CANDIDATES = {
    "paper": ["chart.paper", "diagram.paper", "color.background", "color.bg", "color.surface", "color.neutral.0"],
    "paper2": ["chart.paper2", "diagram.paper2", "color.surface-2", "color.surface.subtle", "color.neutral.50"],
    "ink": ["chart.ink", "diagram.ink", "color.text", "color.text.primary", "color.foreground", "color.neutral.900"],
    "muted": ["chart.muted", "diagram.muted", "color.text-muted", "color.text.secondary", "color.neutral.600"],
    "soft": ["chart.soft", "diagram.soft", "color.text-subtle", "color.text.tertiary", "color.neutral.500"],
    "rule": ["chart.rule", "diagram.rule", "color.border", "color.border.default", "color.neutral.200"],
    "accent": ["chart.accent", "diagram.accent", "color.accent", "color.primary", "color.brand", "color.primary.600"],
    "accentTint": ["chart.accentTint", "diagram.accentTint", "color.accent-subtle", "color.primary.50"],
    "series": ["chart.series", "color.data.1", "color.chart.1", "color.info", "color.blue.600"],
    "font": ["chart.font", "diagram.font", "font.family.sans", "typography.fontFamily.sans", "font.sans"],
    "mono": ["chart.mono", "diagram.mono", "font.family.mono", "typography.fontFamily.mono", "font.mono"],
}

COLOR_ROLES = [k for k in DEFAULT_THEME if k not in ("font", "mono")]


def flatten_tokens(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        if "$value" in obj or "value" in obj:
            out[prefix] = obj.get("$value", obj.get("value"))
            return out
        for k, v in obj.items():
            if k.startswith("$"):
                continue
            out.update(flatten_tokens(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = obj
    return out


def resolve_token(flat, value, depth=0):
    if isinstance(value, str):
        m = re.fullmatch(r"\{([^}]+)\}", value.strip())
        if m and depth < 10:
            return resolve_token(flat, flat.get(m.group(1)), depth + 1)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


def load_theme(theme_path=None, tokens_path=None):
    theme = dict(DEFAULT_THEME)
    if tokens_path:
        flat = flatten_tokens(json.loads(Path(tokens_path).read_text(encoding="utf-8")))
        for role, keys in TOKEN_CANDIDATES.items():
            for key in keys:
                val = resolve_token(flat, flat.get(key))
                if isinstance(val, str) and val:
                    theme[role] = val
                    break
    if theme_path:
        theme.update(json.loads(Path(theme_path).read_text(encoding="utf-8")))
    return theme


def _luminance(hex_colour):
    h = str(hex_colour).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h[:6]):
        return None
    chans = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    if la is None or lb is None:
        return None
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def contrast_issues(theme, name="theme"):
    """Text roles reach WCAG AA 4.5:1 on paper; data marks reach 3:1."""
    issues = []
    for fg, need in (("ink", 4.5), ("muted", 4.5), ("soft", 4.5), ("series", 3.0), ("accent", 3.0)):
        for bg in ("paper", "paper2"):
            r = contrast(theme[fg], theme[bg])
            if r is None:
                issues.append(f"{name}: cannot read colours {fg}={theme[fg]} / {bg}={theme[bg]} (use hex)")
            elif r < need:
                issues.append(f"{name}: {fg} on {bg} is {r:.2f}:1, below {need}:1")
    return issues


# --------------------------------------------------------------------- words

WORDS = {
    "en": {
        "market": "Market size", "trend": "Market trend", "pricing": "Entry price",
        "features": "Feature coverage", "positioning": "Positioning map", "assumptions": "Riskiest assumptions",
        "scorecard": "Validation scorecard", "experiments": "Experiment plan",
        "sourced": "sourced", "estimated": "estimated", "assumed": "assumed", "tested": "your data",
        "projected": "projected", "actual": "actual", "you": "you", "free": "free",
        "full": "full", "partial": "partial", "none": "none", "unknown": "unknown",
        "impact": "Impact", "uncertainty": "Uncertainty", "test_first": "Test first",
        "watch": "Watch", "accept": "Accept for now", "monitor": "Monitor",
        "week": "week", "weeks": "Weeks", "threshold": "go threshold", "weighted": "Weighted score",
        "confidence": "Confidence", "red_flag": "red flag", "not_to_scale": "SOM drawn at minimum size, not to scale",
        "per": "per", "month": "month", "year": "year", "user": "user", "seat": "seat", "one-time": "one-time",
        "go": "GO", "pivot": "PIVOT", "kill": "KILL", "low": "low", "medium": "medium", "high": "high",
        "table": "Data table", "sources": "Sources", "generated": "Generated from", "no_price": "price not public",
        "dashboard": "Product validation", "verdict": "Verdict",
        "illustrative": "Illustrative data for the example. These are not research results.",
        "verified": "verified source", "resolved": "page found, quote not", "unverified": "unverified",
        "capped": "capped by evidence", "fragile": "Fragile: ±0.5 on {dims} flips the verdict",
        "profile": "Profile", "side": "side project", "bootstrapped": "bootstrapped", "venture": "venture",
        "sources_checked": "Sources checked", "unproven": "UNPROVEN",
        "grounded": "Grounded in", "grounded_parts": "your data {t}% · checked, about your segment {v}% · checked, indirect {p}% · guesses {a}%",
        "proxy": "indirect source", "prov": ("What", "Value", "Rests on"), "price_of": "price",
    },
    "uk": {
        "market": "Розмір ринку", "trend": "Динаміка ринку", "pricing": "Вхідна ціна",
        "features": "Покриття функцій", "positioning": "Карта позиціонування", "assumptions": "Найризиковіші припущення",
        "scorecard": "Оцінка ідеї", "experiments": "План експериментів",
        "sourced": "з джерела", "estimated": "оцінка", "assumed": "припущення", "tested": "ваші дані",
        "projected": "прогноз", "actual": "факт", "you": "ви", "free": "безкоштовно",
        "full": "є", "partial": "частково", "none": "немає", "unknown": "невідомо",
        "impact": "Вплив", "uncertainty": "Невизначеність", "test_first": "Перевірити першими",
        "watch": "Стежити", "accept": "Поки прийняти", "monitor": "Моніторити",
        "week": "тиж.", "weeks": "Тижні", "threshold": "поріг GO", "weighted": "Зважена оцінка",
        "confidence": "Впевненість", "red_flag": "червоний прапорець", "not_to_scale": "SOM показано мінімальним розміром, не в масштабі",
        "per": "за", "month": "місяць", "year": "рік", "user": "користувача", "seat": "місце", "one-time": "разово",
        "go": "GO", "pivot": "PIVOT", "kill": "KILL", "low": "низька", "medium": "середня", "high": "висока",
        "table": "Таблиця даних", "sources": "Джерела", "generated": "Згенеровано з", "no_price": "ціна не публічна",
        "dashboard": "Валідація продукту", "verdict": "Вердикт",
        "illustrative": "Ілюстративні дані для прикладу. Це не результати дослідження.",
        "verified": "перевірене джерело", "resolved": "сторінка є, цитати нема", "unverified": "не перевірено",
        "capped": "обрізано доказами", "fragile": "Крихкий: ±0,5 у «{dims}» змінює вердикт",
        "profile": "Профіль", "side": "підробіток", "bootstrapped": "бутстреп", "venture": "венчур",
        "sources_checked": "Перевірено джерел", "unproven": "НЕ ДОВЕДЕНО",
        "grounded": "Спирається на", "grounded_parts": "ваші дані {t}% · перевірене про ваш сегмент {v}% · перевірене непряме {p}% · припущення {a}%",
        "proxy": "непряме джерело", "prov": ("Що", "Значення", "На чому тримається"), "price_of": "ціна",
    },
}

EVIDENCE = ("tested", "sourced", "estimated", "assumed")
CURRENCY = {"USD": "$", "EUR": "€", "GBP": "£", "UAH": "₴", "PLN": "zł ", "JPY": "¥"}
SCALE = {
    "en": [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")],
    "uk": [(1e12, " трлн"), (1e9, " млрд"), (1e6, " млн"), (1e3, " тис.")],
}


def words(data):
    lang = (data.get("meta", {}).get("language") or "en").lower()[:2]
    return WORDS.get(lang, WORDS["en"]), lang if lang in WORDS else "en"


def money(v, cur="USD", lang="en", compact=True):
    if v is None:
        return "?"
    sym = CURRENCY.get(cur, "")
    tail = "" if sym else f" {cur}"
    if compact:
        for div, suf in SCALE.get(lang, SCALE["en"]):
            if abs(v) >= div:
                n = v / div
                s = f"{n:.1f}" if n < 100 else f"{n:.0f}"
                s = s.rstrip("0").rstrip(".") if "." in s else s
                if lang == "uk":
                    s = s.replace(".", ",")
                return f"{sym}{s}{suf}{tail}"
    s = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    if lang == "uk":
        s = s.replace(",", " ").replace(".", ",")
    return f"{sym}{s}{tail}"


# --------------------------------------------------------------------- text metrics

NARROW = set("iljtfr.,:;|!'`()[] ")
WIDE = set("mwMWЖШЩЮФМ@%")


def text_width(text, size):
    w = 0.0
    for ch in str(text):
        if ch in NARROW:
            w += 0.32
        elif ch in WIDE:
            w += 0.86
        elif ch.isupper():
            w += 0.66
        elif ch.isdigit():
            w += 0.57
        else:
            w += 0.55
    return w * size


def wrap(text, size, max_w, max_lines=3):
    words_ = str(text).split()
    lines, cur = [], ""
    for wd in words_:
        cand = f"{cur} {wd}".strip()
        if cur and text_width(cand, size) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines or [""]


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------- SVG frame

MARGIN = 24


class Svg:
    """Collects marks; every fill is a theme role so dark mode can re-colour it."""

    def __init__(self, w, h, uid, title, desc, theme, eyebrow, source_hash):
        self.w, self.h, self.uid, self.t = w, h, uid, theme
        self.title, self.desc, self.eyebrow, self.hash = title, desc, eyebrow, source_hash
        self.body = []

    def fill(self, role):
        return f'fill="{self.t[role]}" class="f-{role}"'

    def stroke(self, role):
        return f'stroke="{self.t[role]}" class="s-{role}"'

    def text(self, x, y, s, size=12, role="ink", weight=None, anchor="start", mono=False, tip=None, extra=""):
        fam = self.t["mono"] if mono else self.t["font"]
        wt = f' font-weight="{weight}"' if weight else ""
        inner = esc(s) + (f"<title>{esc(tip)}</title>" if tip else "")
        self.body.append(f'<text x="{fmt(x)}" y="{fmt(y)}" font-family="{esc(fam)}" font-size="{size}"{wt} '
                         f'text-anchor="{anchor}" {self.fill(role)}{extra}>{inner}</text>')

    def raw(self, s):
        self.body.append(s)

    @staticmethod
    def merge_classes(markup):
        """fill() and stroke() each add a class; one element may carry only one class attribute."""
        def fix(m):
            tag = m.group(0)
            found = re.findall(r' class="([^"]*)"', tag)
            if len(found) < 2:
                return tag
            tag = re.sub(r' class="[^"]*"', "", tag)
            end = -2 if tag.endswith("/>") else -1
            return tag[:end] + f' class="{" ".join(found)}"' + tag[end:]
        return re.sub(r"<[a-z][^<>]*>", fix, markup)

    def render(self):
        t = self.t
        dark_rules = []
        for role in COLOR_ROLES:
            if role in DARK_THEME:
                dark_rules.append(f".f-{role}{{fill:{DARK_THEME[role]}}}.s-{role}{{stroke:{DARK_THEME[role]}}}")
        head = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
            f'role="img" aria-labelledby="{self.uid}-title {self.uid}-desc" data-source-sha1="{self.hash}">',
            f'<title id="{self.uid}-title">{esc(self.title)}</title>',
            f'<desc id="{self.uid}-desc">{esc(self.desc)}</desc>',
            f'<style>@media (prefers-color-scheme: dark){{{"".join(dark_rules)}}}</style>',
            f'<rect width="{self.w}" height="{self.h}" {self.fill("paper")}/>',
        ]
        head.append(f'<text x="{MARGIN}" y="24" font-family="{esc(t["mono"])}" font-size="10.5" letter-spacing="0.08em" '
                    f'{self.fill("soft")}>{esc(self.eyebrow.upper())}</text>')
        head.append(f'<text x="{MARGIN}" y="44" font-family="{esc(t["font"])}" font-size="17" font-weight="600" '
                    f'{self.fill("ink")}>{esc(self.title)}</text>')
        return self.merge_classes("\n".join(head + self.body + ["</svg>"])) + "\n"


def tag_text(W, basis, sources):
    label = W.get(basis, basis or "?")
    return f"{label}" + (f" · {', '.join(sources)}" if sources else "")


def nice_ticks(vmax, n=4):
    if vmax <= 0:
        return [0, 1]
    raw = vmax / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10 * mag)
    ticks, v = [], 0.0
    while v < vmax + step * 0.999:
        ticks.append(v)
        v += step
    return ticks


# --------------------------------------------------------------------- charts


def chart_market(data, theme, W, lang, h):
    m = data["market"]
    cur = data.get("meta", {}).get("currency", "USD")
    tiers = [k for k in ("tam", "sam", "som") if isinstance(m.get(k), dict) and m[k].get("value") is not None]
    vals = {k: float(m[k]["value"]) for k in tiers}
    R = 140.0
    top = max(vals.values())
    radii, tiny = {}, False
    for k in tiers:
        r = R * math.sqrt(vals[k] / top) if top > 0 else 0
        if r < 10:
            r, tiny = 10.0, True
        radii[k] = r
    cx, base = MARGIN + R + 8, 76 + 2 * R
    w, hgt = 760, int(base + (56 if tiny else 32))
    desc = "; ".join(f"{k.upper()} {money(vals[k], cur, lang)} ({m[k].get('basis', '?')})" for k in tiers)
    s = Svg(w, hgt, "market", W["market"], desc, theme, m.get("unit") or W["market"], h)
    roles = {"tam": ("paper2", "rule"), "sam": ("seriesTint", "series"), "som": ("accentTint", "accent")}
    label_x = cx + R + 56
    slots = {"tam": 96, "sam": 96 + 2 * R * 0.42, "som": base - 30}
    for k in tiers:
        r = radii[k]
        cy = base - r
        f, st = roles[k]
        tip = f"{k.upper()}: {money(vals[k], cur, lang, compact=False)} ({W.get(m[k].get('basis'), '?')})"
        s.raw(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" {s.fill(f)} {s.stroke(st)} stroke-width="1.5">'
              f'<title>{esc(tip)}</title></circle>')
    for k in tiers:
        r = radii[k]
        cy = base - r
        ly = slots[k]
        anchor_y = cy - r + 10 if k != "som" else cy
        ax = cx + math.sqrt(max(r * r - (anchor_y - cy) ** 2, 0)) if k != "som" else cx + r
        s.raw(f'<path d="M{fmt(ax)},{fmt(anchor_y)} L{fmt(label_x - 10)},{fmt(ly - 4)}" fill="none" {s.stroke("rule")} stroke-width="1"/>')
        s.text(label_x, ly - 14, k.upper(), 10.5, "soft", mono=True)
        s.text(label_x, ly + 4, money(vals[k], cur, lang), 18, "ink", weight=600)
        note = m[k].get("label") or ""
        s.text(label_x + text_width(money(vals[k], cur, lang), 18) + 12, ly + 3, note, 12, "muted")
        s.text(label_x, ly + 20, tag_text(W, m[k].get("basis"), m[k].get("sources", [])), 10.5, "soft", mono=True)
    if tiny:
        s.text(MARGIN, hgt - 16, W["not_to_scale"], 11, "soft")
    return s


def chart_trend(data, theme, W, lang, h):
    pts = data["market"]["projection"]
    cur = data.get("meta", {}).get("currency", "USD")
    key = data["market"].get("projection_metric", "tam")
    vals = [float(p.get(key) or 0) for p in pts]
    ticks = nice_ticks(max(vals))
    left, top, ph = 72, 72, 220
    bw, gap = 44, 20
    w = max(left + len(pts) * (bw + gap) + MARGIN + 40, 420)
    s = Svg(w, top + ph + 64, "trend", W["trend"], ", ".join(f"{p.get('year')}: {money(v, cur, lang)}" for p, v in zip(pts, vals)),
            theme, f"{key.upper()} · {data['market'].get('unit', '')}", h)
    ymax = ticks[-1]
    for tv in ticks:
        y = top + ph - ph * tv / ymax
        s.raw(f'<line x1="{left}" y1="{fmt(y)}" x2="{w - MARGIN}" y2="{fmt(y)}" {s.stroke("grid" if tv else "rule")} stroke-width="1"/>')
        s.text(left - 8, y + 4, money(tv, cur, lang), 10.5, "soft", anchor="end", mono=True)
    has_proj = False
    for i, (p, v) in enumerate(zip(pts, vals)):
        x = left + 16 + i * (bw + gap)
        bh = ph * v / ymax
        proj = bool(p.get("projected"))
        has_proj |= proj
        y = top + ph - bh
        tip = f"{p.get('year')}: {money(v, cur, lang, compact=False)} ({W['projected'] if proj else W['actual']})"
        rr = min(4, bh / 2)
        d = (f"M{fmt(x)},{fmt(top + ph)} V{fmt(y + rr)} Q{fmt(x)},{fmt(y)} {fmt(x + rr)},{fmt(y)} "
             f"H{fmt(x + bw - rr)} Q{fmt(x + bw)},{fmt(y)} {fmt(x + bw)},{fmt(y + rr)} V{fmt(top + ph)} Z")
        s.raw(f'<path d="{d}" {s.fill("seriesLight" if proj else "series")}><title>{esc(tip)}</title></path>')
        s.text(x + bw / 2, top + ph + 18, p.get("year", ""), 11, "muted", anchor="middle", mono=True)
        if i in (0, len(pts) - 1):
            s.text(x + bw / 2, y - 6, money(v, cur, lang), 11, "ink", anchor="middle", weight=600)
    if has_proj:
        ly = top + ph + 42
        s.raw(f'<rect x="{left}" y="{ly - 9}" width="10" height="10" rx="2" {s.fill("series")}/>')
        s.text(left + 16, ly, W["actual"], 11, "muted")
        x2 = left + 32 + text_width(W["actual"], 11)
        s.raw(f'<rect x="{fmt(x2)}" y="{ly - 9}" width="10" height="10" rx="2" {s.fill("seriesLight")}/>')
        s.text(x2 + 16, ly, W["projected"], 11, "muted")
    return s


def monthly(price):
    v = price.get("value")
    if v is None:
        return None
    per = price.get("period", "month")
    return float(v) / 12 if per == "year" else float(v)


def chart_pricing(data, theme, W, lang, h):
    cur = data.get("meta", {}).get("currency", "USD")
    rows, missing = [], []
    for c in data["competitors"]:
        p = c.get("price")
        mv = monthly(p) if isinstance(p, dict) else None
        if mv is None:
            missing.append(c["name"])
        else:
            rows.append((c, mv))
    rows.sort(key=lambda r: r[1])
    unit = data.get("meta", {}).get("price_unit", "user")
    label_w = max([text_width(c["name"], 12) for c, _ in rows] + [60]) + 16
    left, top, bh, gap = MARGIN + label_w, 72, 22, 12
    plot_w = 420
    w = int(left + plot_w + 120)
    hgt = top + len(rows) * (bh + gap) + (44 if missing else 24)
    vmax = max([v for _, v in rows] + [1])
    s = Svg(w, hgt, "pricing", W["pricing"], "; ".join(f"{c['name']} {money(v, cur, lang)}" for c, v in rows), theme,
            f"{W['per']} {W.get(unit, unit)} / {W['month']}", h)
    s.raw(f'<line x1="{left}" y1="{top - 6}" x2="{left}" y2="{top + len(rows) * (bh + gap) - gap + 6}" {s.stroke("rule")} stroke-width="1"/>')
    for i, (c, v) in enumerate(rows):
        y = top + i * (bh + gap)
        you = bool(c.get("you"))
        s.text(left - 10, y + bh / 2 + 4, c["name"], 12, "ink", anchor="end", weight=600 if you else None)
        bw_ = max(plot_w * v / vmax, 2)
        r = min(4, bw_ / 2)
        d = (f"M{left},{y} H{fmt(left + bw_ - r)} Q{fmt(left + bw_)},{y} {fmt(left + bw_)},{fmt(y + r)} "
             f"V{fmt(y + bh - r)} Q{fmt(left + bw_)},{fmt(y + bh)} {fmt(left + bw_ - r)},{fmt(y + bh)} H{left} Z")
        orig = c["price"]
        tip = f"{c['name']}: {money(orig['value'], cur, lang, False)} / {W.get(orig.get('period', 'month'), orig.get('period'))}"
        if orig.get("note"):
            tip += f" — {orig['note']}"
        s.raw(f'<path d="{d}" {s.fill("accent" if you else "series")}><title>{esc(tip)}</title></path>')
        lab = W["free"] if v == 0 else money(v, cur, lang, compact=v >= 10000)
        s.text(left + bw_ + 8, y + bh / 2 + 4, lab, 12, "ink" if you else "muted", weight=600 if you else None)
    if missing:
        s.text(MARGIN, hgt - 14, f"{W['no_price']}: {', '.join(missing)}", 11, "soft")
    return s


FEATURE_STATES = ("full", "partial", "none", "unknown")


def glyph(s, x, y, state, you):
    r = 7
    role = "accent" if you else "series"
    if state == "full":
        return f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{r}" {s.fill(role)}/>'
    if state == "partial":
        return (f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{r - 0.75}" fill="none" {s.stroke(role)} stroke-width="1.5"/>'
                f'<path d="M{fmt(x)},{fmt(y - r)} A{r},{r} 0 0 0 {fmt(x)},{fmt(y + r)} Z" {s.fill(role)}/>')
    if state == "none":
        return f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{r - 0.75}" fill="none" {s.stroke("rule")} stroke-width="1.5"/>'
    return ""


def chart_features(data, theme, W, lang, h):
    feats, comps = data["features"], data["competitors"]
    label_w = max(text_width(f["label"], 12) for f in feats) + 16
    label_w = min(label_w, 260)
    col_w, row_h = 92, 30
    left, top = MARGIN + label_w, 96
    w = int(left + col_w * len(comps) + MARGIN)
    hgt = top + row_h * len(feats) + 56
    s = Svg(w, hgt, "features", W["features"], f"{len(feats)} features × {len(comps)} products", theme,
            f"{len(comps)} × {len(feats)}", h)
    for j, c in enumerate(comps):
        x = left + j * col_w
        if c.get("you"):
            s.raw(f'<rect x="{x + 4}" y="{top - 40}" width="{col_w - 8}" height="{row_h * len(feats) + 40}" rx="6" {s.fill("accentTint")}/>')
        lines = wrap(c["name"], 11.5, col_w - 10, 2)
        for k, ln in enumerate(lines):
            s.text(x + col_w / 2, top - 22 + k * 13 - (6 if len(lines) > 1 else 0), ln, 11.5,
                   "accent" if c.get("you") else "ink", weight=600, anchor="middle")
    for i, f in enumerate(feats):
        y = top + i * row_h
        if i:
            s.raw(f'<line x1="{MARGIN}" y1="{y}" x2="{w - MARGIN}" y2="{y}" {s.stroke("grid")} stroke-width="1"/>')
        s.text(left - 12, y + row_h / 2 + 4, wrap(f["label"], 12, label_w - 12, 1)[0], 12, "ink", anchor="end", tip=f["label"])
        for j, c in enumerate(comps):
            st = (c.get("features") or {}).get(f["id"], "unknown")
            cx, cy = left + j * col_w + col_w / 2, y + row_h / 2
            g = glyph(s, cx, cy, st, c.get("you"))
            tip = f"{c['name']} · {f['label']}: {W.get(st, st)}"
            if g:
                s.raw(f'<g>{g}<title>{esc(tip)}</title></g>')
            else:
                s.text(cx, cy + 4, "?", 12, "soft", anchor="middle", mono=True, tip=tip)
    ly = top + row_h * len(feats) + 30
    x = MARGIN
    for st in FEATURE_STATES:
        g = glyph(s, x + 7, ly - 4, st, False)
        if g:
            s.raw(g)
        else:
            s.text(x + 7, ly, "?", 12, "soft", anchor="middle", mono=True)
        s.text(x + 20, ly, W[st], 11, "muted")
        x += 36 + text_width(W[st], 11)
    return s


def place_point_labels(points, plot, size=11.5):
    """points: list of (x, y, text, r). Returns [(lx, ly, anchor)] avoiding overlaps."""
    boxes = [(x - r, y - r, x + r, y + r) for x, y, _, r in points]
    out = []
    px0, py0, px1, py1 = plot

    def hit(b):
        if b[0] < px0 - 2 or b[2] > px1 + 60 or b[1] < py0 - 14 or b[3] > py1 + 2:
            return True
        return any(not (b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3]) for o in boxes)

    for x, y, text, r in points:
        tw = text_width(text, size)
        cands = [
            (x + r + 6, y + 4, "start", (x + r + 4, y - 9, x + r + 8 + tw, y + 5)),
            (x - r - 6, y + 4, "end", (x - r - 8 - tw, y - 9, x - r - 4, y + 5)),
            (x, y - r - 6, "middle", (x - tw / 2, y - r - 18, x + tw / 2, y - r - 4)),
            (x, y + r + 15, "middle", (x - tw / 2, y + r + 3, x + tw / 2, y + r + 17)),
            (x + r + 6, y - r - 4, "start", (x + r + 4, y - r - 17, x + r + 8 + tw, y - r - 3)),
            (x + r + 6, y + r + 12, "start", (x + r + 4, y + r, x + r + 8 + tw, y + r + 14)),
        ]
        chosen = next((c for c in cands if not hit(c[3])), cands[0])
        boxes.append(chosen[3])
        out.append(chosen[:3])
    return out


def scatter_frame(s, plot, xl, yl, W, tint_quadrant=None, quad_labels=None):
    x0, y0, x1, y1 = plot
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if tint_quadrant == "tr":
        s.raw(f'<rect x="{fmt(mx)}" y="{fmt(y0)}" width="{fmt(x1 - mx)}" height="{fmt(my - y0)}" {s.fill("accentTint")}/>')
    s.raw(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" {s.stroke("rule")} stroke-width="1"/>')
    s.raw(f'<line x1="{fmt(mx)}" y1="{y0}" x2="{fmt(mx)}" y2="{y1}" {s.stroke("rule")} stroke-width="1"/>')
    s.raw(f'<line x1="{x0}" y1="{fmt(my)}" x2="{x1}" y2="{fmt(my)}" {s.stroke("rule")} stroke-width="1"/>')
    s.text(x0, y1 + 20, xl.get("low", ""), 11, "soft")
    s.text(x1, y1 + 20, xl.get("high", ""), 11, "soft", anchor="end")
    s.text(mx, y1 + 38, xl.get("label", ""), 12, "muted", anchor="middle", weight=600)
    s.raw(f'<g transform="translate({x0 - 14},{fmt(my)}) rotate(-90)"><text x="0" y="0" font-family="{esc(s.t["font"])}" '
          f'font-size="12" font-weight="600" text-anchor="middle" {s.fill("muted")}>{esc(yl.get("label", ""))}</text></g>')
    s.raw(f'<g transform="translate({x0 - 14},{y1}) rotate(-90)"><text x="0" y="0" font-family="{esc(s.t["font"])}" '
          f'font-size="11" {s.fill("soft")}>{esc(yl.get("low", ""))}</text></g>')
    s.raw(f'<g transform="translate({x0 - 14},{y0}) rotate(-90)"><text x="0" y="0" font-family="{esc(s.t["font"])}" '
          f'font-size="11" text-anchor="end" {s.fill("soft")}>{esc(yl.get("high", ""))}</text></g>')
    if quad_labels:
        tl, tr, bl, br = (quad_labels + [None] * 4)[:4]
        for txt, (qx, qy, anc) in zip((tl, tr, bl, br), ((x0 + 8, y0 + 16, "start"), (x1 - 8, y0 + 16, "end"),
                                                         (x0 + 8, y1 - 8, "start"), (x1 - 8, y1 - 8, "end"))):
            if txt:
                s.text(qx, qy, txt, 10.5, "soft", anchor=anc, mono=True)


def chart_positioning(data, theme, W, lang, h):
    pos = data["positioning"]
    pts = [c for c in data["competitors"] if c.get("x") is not None and c.get("y") is not None]
    x0, y0, size = 64, 64, 420
    plot = (x0, y0, x0 + size, y0 + size)
    w, hgt = x0 + size + 150, y0 + size + 56
    s = Svg(w, hgt, "positioning", W["positioning"],
            f"{pos['x'].get('label')} × {pos['y'].get('label')}: " + "; ".join(f"{c['name']} ({c['x']}, {c['y']})" for c in pts),
            theme, f"{pos['x'].get('label')} × {pos['y'].get('label')}", h)
    scatter_frame(s, plot, pos["x"], pos["y"], W, quad_labels=pos.get("quadrants"))
    marks = []
    for c in sorted(pts, key=lambda c: bool(c.get("you"))):
        px = x0 + size * float(c["x"]) / 10
        py = y0 + size - size * float(c["y"]) / 10
        r = 8 if c.get("you") else 6
        marks.append((px, py, c, r))
    labels = place_point_labels([(px, py, c["name"], r) for px, py, c, r in marks], plot)
    for (px, py, c, r), (lx, ly, anc) in zip(marks, labels):
        you = bool(c.get("you"))
        tip = f"{c['name']}: {pos['x'].get('label')} {c['x']}/10, {pos['y'].get('label')} {c['y']}/10"
        s.raw(f'<circle cx="{fmt(px)}" cy="{fmt(py)}" r="{r}" {s.fill("accent" if you else "series")} {s.stroke("paper")} '
              f'stroke-width="2"><title>{esc(tip)}</title></circle>')
        s.text(lx, ly, c["name"], 11.5, "accent" if you else "ink", anchor=anc, weight=600 if you else None)
    return s


def jitter(points):
    seen = {}
    out = []
    for key in points:
        n = seen.get(key, 0)
        seen[key] = n + 1
        out.append(n)
    return out


def chart_assumptions(data, theme, W, lang, h):
    items = data["assumptions"]
    x0, y0, size = 64, 64, 360
    plot = (x0, y0, x0 + size, y0 + size)
    list_x = x0 + size + 40
    list_w = 300
    rows = []
    for a in sorted(items, key=lambda a: -(a["impact"] * a["uncertainty"])):
        rows.append((a, wrap(a["text"], 11.5, list_w - 40, 2)))
    list_h = sum(16 * len(l) + 8 for _, l in rows)
    w, hgt = list_x + list_w, max(y0 + size + 56, y0 + list_h + 24)
    s = Svg(w, hgt, "assumptions", W["assumptions"],
            "; ".join(f"{a['id']} impact {a['impact']}, uncertainty {a['uncertainty']}" for a in items), theme,
            f"{W['impact']} × {W['uncertainty']}", h)
    scatter_frame(s, plot, {"label": W["uncertainty"], "low": "1", "high": "5"}, {"label": W["impact"], "low": "1", "high": "5"},
                  W, tint_quadrant="tr", quad_labels=[W["watch"], W["test_first"], W["accept"], W["monitor"]])
    keys = [(a["impact"], a["uncertainty"]) for a in items]
    nth = jitter(keys)
    for a, n in zip(items, nth):
        px = x0 + size * (float(a["uncertainty"]) - 0.5) / 5
        py = y0 + size - size * (float(a["impact"]) - 0.5) / 5
        if n:
            ang = n * 2.1
            px, py = px + 20 * math.cos(ang), py + 20 * math.sin(ang)
        hot = a["impact"] >= 4 and a["uncertainty"] >= 4
        tip = f"{a['id']}: {a['text']} ({a.get('category', '')})"
        s.raw(f'<g><circle cx="{fmt(px)}" cy="{fmt(py)}" r="12" {s.fill("accent" if hot else "series")} {s.stroke("paper")} stroke-width="2"/>'
              f'<text x="{fmt(px)}" y="{fmt(py + 3.5)}" font-family="{esc(s.t["mono"])}" font-size="9.5" font-weight="600" '
              f'text-anchor="middle" {s.fill("paper")}>{esc(a["id"])}</text><title>{esc(tip)}</title></g>')
    y = y0 + 4
    for a, lines in rows:
        hot = a["impact"] >= 4 and a["uncertainty"] >= 4
        s.text(list_x, y + 8, a["id"], 10.5, "accent" if hot else "soft", mono=True, weight=600)
        for k, ln in enumerate(lines):
            s.text(list_x + 34, y + 8 + 16 * k, ln, 11.5, "ink")
        y += 16 * len(lines) + 8
    return s


# --------------------------------------------------------------------- evidence and verdict
# The model writes scores; the script decides how much they are allowed to count.
# A "sourced" claim counts as sourced only when `verify` opened the page (or the
# founder's file) and found the quoted text there. Edit a source after verifying
# and its signature no longer matches, so it drops back to unverified.

PROFILES = {
    # founder goal -> go threshold, kill threshold, weight of the market dimension
    "side": {"go": 3.3, "kill": 2.4, "market_weight": 0.5},
    "bootstrapped": {"go": 3.5, "kill": 2.5, "market_weight": 1.0},
    "venture": {"go": 3.8, "kill": 2.8, "market_weight": 2.0},
}
STANDARD_WEIGHTS = {"problem": 2, "market": 1, "competition": 1, "differentiation": 1, "wtp": 2, "reach": 1, "feasibility": 1}
RED_FLAG_BELOW = 2.0
CHALLENGE_STEP = 0.5
# effective evidence -> (confidence weight, highest score it may support)
EFFECTIVE = {
    "tested": (1.0, 5.0),        # founder's own data file, verified
    "verified": (0.8, 5.0),      # public page opened, quote found
    "proxy": (0.5, 4.0),         # verified, but about another segment, market or geography ("direct": false)
    "resolved": (0.5, 4.0),      # page opened, quote not found (JS page, paywall, paraphrase)
    "estimated": (0.4, 4.0),     # arithmetic shown in the report
    "unverified": (0.2, 3.0),    # claims a source nobody checked, or the check failed
    "assumed": (0.1, 3.0),
}


_KEY = None


def verify_key():
    """Per-machine secret, kept outside the project, so a verification record cannot be written by hand."""
    global _KEY
    if _KEY is None:
        import os
        import secrets
        env = os.environ.get("SDD_PRODUCT_VERIFY_KEY")
        if env:
            _KEY = env.encode("utf-8")
        else:
            home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "sdd-product"
            kf = home / "verify.key"
            try:
                _KEY = kf.read_bytes().strip()
            except OSError:
                home.mkdir(parents=True, exist_ok=True)
                _KEY = secrets.token_hex(32).encode("ascii")
                kf.write_bytes(_KEY)
                try:
                    kf.chmod(0o600)
                except OSError:
                    pass
    return _KEY


def source_sig(src, file_hash="", rec=None):
    import hmac
    quotes = src.get("quotes") or ([src["quote"]] if src.get("quote") else [])
    rec = rec or {}
    blob = json.dumps({"url": src.get("url"), "path": src.get("path"), "quotes": quotes, "file": file_hash,
                       "status": rec.get("status"), "checked": rec.get("checked")}, sort_keys=True, ensure_ascii=False)
    return hmac.new(verify_key(), blob.encode("utf-8"), "sha256").hexdigest()[:20]


def file_hash(base, rel):
    try:
        return hashlib.sha1((Path(base) / rel).read_bytes()).hexdigest()[:12]
    except OSError:
        return "missing"


def source_state(src, base=None):
    """verified | resolved | tested | unverified for one source."""
    v = src.get("verification") or {}
    fh = file_hash(base, src["path"]) if (src.get("path") and base is not None) else v.get("file", "")
    if not v or v.get("sig") != source_sig(src, fh, v):
        return "unverified"
    if v.get("status") == "quote":
        return "tested" if src.get("path") else "verified"
    if v.get("status") == "url" and not src.get("path"):
        return "resolved"
    return "unverified"


def effective_evidence(claim, sources, base=None):
    level = claim.get("evidence") or claim.get("basis") or "assumed"
    if level in ("estimated", "assumed"):
        return level
    states = [source_state(sources[r], base) for r in claim.get("sources") or [] if r in sources]
    if level == "tested":
        return "tested" if "tested" in states else "unverified"
    for best in ("tested", "verified", "resolved"):
        if best in states:
            eff = "verified" if best == "tested" else best
            return "proxy" if eff == "verified" and claim.get("direct") is False else eff
    return "unverified"


def score_verdict(dims, profile):
    tw = sum(d["w"] for d in dims) or 1
    total = sum(d["used"] * d["w"] for d in dims) / tw
    red = [d["id"] for d in dims if d["used"] < RED_FLAG_BELOW]
    if total >= profile["go"] and not red:
        return total, red, "go"
    if total < profile["kill"] or len(red) >= 2:
        return total, red, "kill"
    return total, red, "pivot"


def compute_verdict(data, base=None):
    sc = data.get("scorecard") or {}
    raw = sc.get("dimensions") or []
    if not raw:
        return None
    pname = sc.get("profile") or "bootstrapped"
    profile = PROFILES.get(pname, PROFILES["bootstrapped"])
    sources = {s.get("id"): s for s in data.get("sources") or []}
    dims, capped = [], []
    # red-team challenges: a lower score proposed by the independent skeptic stands
    # unless it was rebutted with a verified or tested source
    # A challenge backed by a verified source (counter-evidence) applies in full. A challenge
    # without one ("the evidence is thin") may lower a score by at most CHALLENGE_STEP: thin
    # evidence is already priced in by the cap, so it must not be counted twice.
    challenged, backed = {}, set()
    for c in data.get("red_team") or []:
        did, prop = c.get("dimension"), c.get("proposed")
        if not isinstance(prop, (int, float)):
            continue
        rebut = [r for r in c.get("rebuttal_sources") or [] if r in sources and source_state(sources[r], base) in ("verified", "tested")]
        if c.get("resolution") == "rebutted" and rebut:
            continue
        proof = [r for r in c.get("sources") or [] if r in sources and source_state(sources[r], base) in ("verified", "tested")]
        challenged.setdefault(did, []).append((float(prop), bool(proof)))
        if proof:
            backed.add(did)
    for d in raw:
        eff = effective_evidence(d, sources, base)
        conf_w, cap = EFFECTIVE[eff]
        before = min(float(d["score"]), cap)
        for prop, proof in challenged.get(d["id"], []):
            cap = min(cap, prop if proof else max(prop, before - CHALLENGE_STEP))
        w = STANDARD_WEIGHTS.get(d["id"], float(d.get("weight", 1)))
        if d["id"] == "market":
            w = profile["market_weight"]
        used = min(float(d["score"]), cap)
        if used < float(d["score"]):
            capped.append(d["id"])
        dims.append({"id": d["id"], "w": w, "used": used, "score": float(d["score"]), "eff": eff, "conf": conf_w})
    total, red, v = score_verdict(dims, profile)
    raw_v = v
    # KILL needs evidence against the idea. When every low score is low only because evidence
    # is missing (assumed, unverified or thin), the honest answer is "not proven yet".
    if v == "kill":
        against = [d["id"] for d in dims if d["used"] < profile["kill"] and (d["eff"] in ("tested", "verified") or d["id"] in backed)]
        if not against:
            v = "unproven"
    tw = sum(d["w"] for d in dims) or 1
    conf = sum(d["conf"] * d["w"] for d in dims) / tw
    # fragile: one dimension moved by half a point flips the verdict
    fragile = []
    for i, d in enumerate(dims):
        for delta in (-0.5, 0.5):
            alt = [dict(x) for x in dims]
            alt[i]["used"] = max(0.0, min(EFFECTIVE[d["eff"]][1], d["used"] + delta))
            if score_verdict(alt, profile)[2] != raw_v:
                fragile.append(d["id"])
                break
    level = "high" if conf >= 0.65 else "medium" if conf >= 0.4 else "low"
    grounded = {"tested": 0.0, "verified": 0.0, "proxy": 0.0, "guess": 0.0}
    for d in dims:
        key = d["eff"] if d["eff"] in ("tested", "verified", "proxy") else "guess"
        grounded[key] += d["w"] / tw
    return {"score": round(total, 2), "verdict": v, "confidence": round(conf, 2), "confidence_level": level,
            "red_flags": red, "go_threshold": profile["go"], "kill_below": profile["kill"], "profile": pname,
            "capped": capped, "fragile": fragile, "challenged": sorted(challenged),
            "evidence": {d["id"]: d["eff"] for d in dims}, "used": {d["id"]: d["used"] for d in dims},
            "grounded": {k: round(v_ * 100) for k, v_ in grounded.items()}, "backed_challenges": sorted(backed)}


# --------------------------------------------------------------------- verify

MAX_BYTES = 3_000_000


def page_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


def norm(text):
    text = text.lower().replace("\u00a0", " ").replace("\u202f", " ")
    text = re.sub(r"[\u00ad\u200b-\u200d\u2060\ufeff]", "", text)
    text = re.sub(r"[\u2018\u2019\u201c\u201d\"'`«»]", "", text)
    text = re.sub(r"(?<=\d)[ ,.](?=\d{3}\b)", "", text)   # 52 000 / 52,000 / 52.000 -> 52000
    return re.sub(r"\s+", " ", text).strip()


MIN_QUOTE_WORDS = 5


def weak_quote(q):
    """A fragment like "70.89%" or "Self-serve $115" proves nothing about what the number counts."""
    return len(norm(q).split()) < MIN_QUOTE_WORDS


class PdfUnreadable(Exception):
    pass


def pdf_text(body):
    import shutil
    import subprocess
    exe = shutil.which("pdftotext")
    if not exe:
        raise PdfUnreadable("PDF: quotes need pdftotext (poppler) on this machine; the page counts as found, not verified")
    r = subprocess.run([exe, "-q", "-layout", "-", "-"], input=body, capture_output=True, timeout=60)
    if r.returncode:
        raise PdfUnreadable("PDF: pdftotext could not read it")
    return r.stdout.decode("utf-8", errors="replace")


def fetch(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (sdd-product source check)",
                                               "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(MAX_BYTES)
        if body[:5] == b"%PDF-" or "pdf" in (r.headers.get_content_type() or ""):
            return r.status, r.geturl(), pdf_text(body)
        charset = r.headers.get_content_charset() or "utf-8"
        return r.status, r.geturl(), body.decode(charset, errors="replace")


def verify_sources(data, base, today, fetcher=fetch):
    """Open every source and look for its quotes. Writes `verification` into each source."""
    results = []
    for src in data.get("sources") or []:
        quotes = src.get("quotes") or ([src["quote"]] if src.get("quote") else [])
        rec = {"checked": today}
        try:
            if src.get("path"):
                text = (Path(base) / src["path"]).read_text(encoding="utf-8", errors="replace")
                rec["http"] = "file"
                rec["file"] = file_hash(base, src["path"])
            elif src.get("url"):
                try:
                    status, final, raw = fetcher(src["url"])
                except PdfUnreadable as e:
                    rec.update(http=200, status="url", reason=str(e))
                    src["verification"] = {**rec, "sig": source_sig(src, "", rec)}
                    results.append((src.get("id"), rec))
                    continue
                rec["http"] = status
                if final != src["url"]:
                    rec["final_url"] = final
                text = page_text(raw)
            else:
                rec.update(status="failed", reason="no url or path")
                src["verification"] = {**rec, "sig": source_sig(src, "", rec)}
                results.append((src.get("id"), rec))
                continue
            page = norm(text)
            found = [q for q in quotes if norm(q) and norm(q) in page]
            if found:
                i = page.find(norm(found[0]))
                rec["excerpt"] = page[max(0, i - 120): i + len(norm(found[0])) + 120]
            if quotes and len(found) == len(quotes) and not all(weak_quote(q) for q in quotes):
                rec["status"] = "quote"
            else:
                rec["status"] = "url"
                rec["reason"] = ("no quote given" if not quotes else
                                 f"{len(quotes) - len(found)} of {len(quotes)} quotes not on the page" if len(found) < len(quotes) else
                                 f"quotes too short to show what the number counts (need {MIN_QUOTE_WORDS}+ words)")
        except Exception as e:  # network, HTTP 4xx/5xx, missing file
            rec.update(status="failed", reason=f"{type(e).__name__}: {str(e)[:120]}")
        src["verification"] = {**rec, "sig": source_sig(src, rec.get("file", ""), rec)}
        results.append((src.get("id"), rec))
    return results


def chart_scorecard(data, theme, W, lang, h):
    dims = data["scorecard"]["dimensions"]
    vd = data.get("_verdict") or compute_verdict(data)
    label_w = min(max(text_width(d["label"], 12) for d in dims) + 16, 240)
    left, top, bh, gap, plot_w = MARGIN + label_w, 128, 18, 14, 300
    w = int(left + plot_w + 230)
    hgt = top + len(dims) * (bh + gap) + 30
    s = Svg(w, hgt, "scorecard", W["scorecard"],
            f"{W['verdict']} {W[vd['verdict']]}, {vd['score']}/5, {W['confidence']} {W[vd['confidence_level']]}", theme,
            f"{W['weighted']} · 0–5", h)
    s.text(MARGIN, 88, f"{vd['score']:.1f}".replace(".", "," if lang == "uk" else "."), 34, "ink", weight=600)
    vx = MARGIN + text_width(f"{vd['score']:.1f}", 34) + 14
    s.text(vx, 74, W[vd["verdict"]], 15, "accent", weight=700, mono=True)
    s.text(vx, 92, f"{W['confidence']}: {W[vd['confidence_level']]} ({int(vd['confidence'] * 100)}%) · {W['profile']}: {W.get(vd['profile'], vd['profile'])}",
           11.5, "muted")
    if vd["fragile"]:
        names = ", ".join(next((x["label"] for x in dims if x["id"] == f), f) for f in vd["fragile"])
        s.text(MARGIN, 112, W["fragile"].format(dims=names), 11.5, "critical")
    else:
        s.text(MARGIN, 112, f"{W['grounded']}: {grounded_line(vd, W)}", 11.5, "muted")
    for i in range(6):
        x = left + plot_w * i / 5
        s.raw(f'<line x1="{fmt(x)}" y1="{top - 8}" x2="{fmt(x)}" y2="{hgt - 26}" {s.stroke("grid" if i else "rule")} stroke-width="1"/>')
        s.text(x, hgt - 10, str(i), 10.5, "soft", anchor="middle", mono=True)
    thr = left + plot_w * vd["go_threshold"] / 5
    s.raw(f'<line x1="{fmt(thr)}" y1="{top - 14}" x2="{fmt(thr)}" y2="{hgt - 26}" {s.stroke("ink")} stroke-width="1.5"/>')
    s.text(thr, top - 18, W["threshold"], 10.5, "ink", anchor="middle", mono=True)
    for i, d in enumerate(dims):
        y = top + i * (bh + gap)
        red = d["id"] in vd["red_flags"]
        s.text(left - 10, y + bh / 2 + 4, wrap(d["label"], 12, label_w - 12, 1)[0], 12, "ink", anchor="end", tip=d["label"])
        used, claimed = vd["used"][d["id"]], float(d["score"])
        eff = vd["evidence"][d["id"]]
        if claimed > used:
            gx = left + plot_w * claimed / 5
            s.raw(f'<rect x="{left}" y="{y + 0.75}" width="{fmt(gx - left - 0.75)}" height="{bh - 1.5}" rx="4" fill="none" '
                  f'{s.stroke("rule")} stroke-width="1.5"><title>{esc(W["capped"])}</title></rect>')
        bw_ = max(plot_w * used / 5, 2)
        r = min(4, bw_ / 2)
        dd = (f"M{left},{y} H{fmt(left + bw_ - r)} Q{fmt(left + bw_)},{y} {fmt(left + bw_)},{fmt(y + r)} "
              f"V{fmt(y + bh - r)} Q{fmt(left + bw_)},{fmt(y + bh)} {fmt(left + bw_ - r)},{fmt(y + bh)} H{left} Z")
        tip = f"{d['label']}: {fmt(used)}/5 · {W.get(eff, eff)}" + (f" ({W['capped']}: {fmt(claimed)})" if claimed > used else "") + \
            (f" — {d['why']}" if d.get("why") else "")
        s.raw(f'<path d="{dd}" {s.fill("critical" if red else "series")}><title>{esc(tip)}</title></path>')
        tag = f"{fmt(used)} · {W.get(eff, eff)}" if claimed <= used else f"{fmt(claimed)}→{fmt(used)} · {W.get(eff, eff)}"
        if red:
            tag = f"! {tag} · {W['red_flag']}"
        s.text(left + plot_w + 10, y + bh / 2 + 4, tag, 10.5, "critical" if red else "soft", mono=True)
    return s


def chart_experiments(data, theme, W, lang, h):
    ex = data["experiments"]
    weeks = max(int(e.get("start_week", 1)) + int(e.get("weeks", 1)) - 1 for e in ex)
    label_w = min(max(text_width(f"{e['id']}  {e['method']}", 12) for e in ex) + 16, 300)
    left, top, bh, gap = MARGIN + label_w, 84, 20, 12
    col = max(min(520 / weeks, 64), 28)
    w = int(left + col * weeks + MARGIN)
    hgt = top + len(ex) * (bh + gap) + 20
    s = Svg(w, hgt, "experiments", W["experiments"], "; ".join(f"{e['id']} {e['method']}: week {e.get('start_week', 1)}, {e.get('weeks', 1)}w" for e in ex),
            theme, f"{W['weeks']} 1–{weeks}", h)
    for k in range(weeks + 1):
        x = left + k * col
        s.raw(f'<line x1="{fmt(x)}" y1="{top - 6}" x2="{fmt(x)}" y2="{hgt - 14}" {s.stroke("grid" if k else "rule")} stroke-width="1"/>')
        if k < weeks:
            s.text(x + col / 2, top - 12, str(k + 1), 10.5, "soft", anchor="middle", mono=True)
    for i, e in enumerate(ex):
        y = top + i * (bh + gap)
        s.text(left - 10, y + bh / 2 + 4, wrap(f"{e['id']}  {e['method']}", 12, label_w - 12, 1)[0], 12, "ink", anchor="end",
               tip=e["method"])
        x = left + (int(e.get("start_week", 1)) - 1) * col + 2
        bw_ = int(e.get("weeks", 1)) * col - 4
        tip = f"{e['id']} → {e.get('assumption', '')}: {e.get('success', '')}"
        s.raw(f'<rect x="{fmt(x)}" y="{y}" width="{fmt(bw_)}" height="{bh}" rx="4" {s.fill("accent" if e.get("focal") else "series")}>'
              f'<title>{esc(tip)}</title></rect>')
        if e.get("assumption") and text_width(e["assumption"], 10.5) < bw_ - 10:
            s.text(x + 8, y + bh / 2 + 4, e["assumption"], 10.5, "paper", mono=True, weight=600)
    return s


CHARTS = [
    ("market", lambda d: isinstance(d.get("market"), dict) and any(isinstance(d["market"].get(k), dict) for k in ("tam", "sam", "som")), chart_market),
    ("trend", lambda d: isinstance(d.get("market"), dict) and len(d["market"].get("projection") or []) >= 2, chart_trend),
    ("pricing", lambda d: sum(1 for c in d.get("competitors") or [] if isinstance(c.get("price"), dict)) >= 2, chart_pricing),
    ("features", lambda d: bool(d.get("features")) and bool(d.get("competitors")), chart_features),
    ("positioning", lambda d: isinstance(d.get("positioning"), dict) and sum(1 for c in d.get("competitors") or [] if c.get("x") is not None) >= 2, chart_positioning),
    ("assumptions", lambda d: bool(d.get("assumptions")), chart_assumptions),
    ("scorecard", lambda d: bool((d.get("scorecard") or {}).get("dimensions")), chart_scorecard),
    ("experiments", lambda d: bool(d.get("experiments")), chart_experiments),
]

DATA_KEYS = {
    "market": ["market", "meta"], "trend": ["market", "meta"], "pricing": ["competitors", "meta"],
    "features": ["features", "competitors", "meta"], "positioning": ["positioning", "competitors", "meta"],
    "assumptions": ["assumptions", "meta"], "scorecard": ["scorecard", "sources", "meta"], "experiments": ["experiments", "meta"],
}


def chart_hash(data, name):
    sub = {k: data.get(k) for k in DATA_KEYS[name]}
    return hashlib.sha1(json.dumps(sub, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------- checks


def check(data, base=None):
    errors, warns = [], []
    meta = data.get("meta")
    if not isinstance(meta, dict) or not meta.get("title"):
        errors.append("meta.title is required")
    src_ids = set()
    for i, s in enumerate(data.get("sources") or []):
        if not s.get("id"):
            errors.append(f"sources[{i}] has no id")
        src_ids.add(s.get("id"))
        if not s.get("url") and not s.get("title"):
            errors.append(f"source {s.get('id')}: needs a url or a title")
        if s.get("url") and not s.get("accessed"):
            warns.append(f"source {s.get('id')}: no 'accessed' date")
        if (s.get("url") or s.get("path")) and source_state(s, base) == "unverified":
            warns.append(f"source {s.get('id')}: not verified (run verify); counts as unverified until then")
        for q in s.get("quotes") or []:
            if weak_quote(q):
                warns.append(f"source {s.get('id')}: quote \"{q[:40]}\" is a fragment; quote the whole sentence that says what the number counts")
        yr, today_y = s.get("data_year"), str((meta or {}).get("date", ""))[:4]
        if isinstance(yr, int) and today_y.isdigit() and int(today_y) - yr > 3:
            warns.append(f"source {s.get('id')}: data from {yr}; look for newer figures")

    src_by_id = {s.get("id"): s for s in data.get("sources") or []}

    def cite(where, obj):
        basis = obj.get("basis") or obj.get("evidence")
        if basis not in EVIDENCE:
            errors.append(f"{where}: basis/evidence must be one of {', '.join(EVIDENCE)}")
        refs = obj.get("sources") or []
        for r in refs:
            if r not in src_ids:
                errors.append(f"{where}: cites unknown source {r}")
        if basis == "sourced" and not refs:
            errors.append(f"{where}: marked sourced but cites no source")
        if basis == "sourced" and refs and not any(src_by_id.get(r, {}).get("url") or src_by_id.get(r, {}).get("path") for r in refs):
            errors.append(f"{where}: marked sourced but none of its sources has a url or a file path")
        if basis == "tested" and not any(src_by_id.get(r, {}).get("path") for r in refs):
            errors.append(f"{where}: marked tested but cites no founder data file (a source with \"path\")")

    m = data.get("market")
    if isinstance(m, dict):
        vals = {}
        for k in ("tam", "sam", "som"):
            if isinstance(m.get(k), dict):
                v = m[k].get("value")
                if not isinstance(v, (int, float)) or v < 0:
                    errors.append(f"market.{k}.value must be a non-negative number")
                else:
                    vals[k] = v
                cite(f"market.{k}", m[k])
        if "tam" in vals and "sam" in vals and vals["sam"] > vals["tam"]:
            errors.append("market: SAM is larger than TAM")
        if "sam" in vals and "som" in vals and vals["som"] > vals["sam"]:
            errors.append("market: SOM is larger than SAM")
        if "sam" in vals and "som" in vals and vals["sam"] and vals["som"] / vals["sam"] > 0.2:
            warns.append(f"market: SOM is {vals['som'] / vals['sam']:.0%} of SAM; above ~20% needs a strong reason")
        for k in ("tam", "sam", "som"):
            inp = (m.get(k) or {}).get("inputs") if isinstance(m.get(k), dict) else None
            if not inp:
                if isinstance(m.get(k), dict) and m[k].get("basis") == "estimated":
                    warns.append(f"market.{k}: estimated without 'inputs'; list each factor with its source or 'assumed'")
                continue
            prod = 1.0
            for j, f in enumerate(inp):
                if not isinstance(f.get("value"), (int, float)):
                    errors.append(f"market.{k}.inputs[{j}]: value must be a number")
                    prod = None
                    break
                prod *= f["value"]
                cite(f"market.{k}.inputs[{j}] ({f.get('label', '')})", f)
            if prod is not None and k in vals and vals[k] and abs(prod - vals[k]) / vals[k] > 0.02:
                errors.append(f"market.{k}: inputs multiply to {prod:,.0f}, not {vals[k]:,.0f}")
            guesses = [f.get("label", f"#{j}") for j, f in enumerate(inp) if f.get("basis") == "assumed"]
            if guesses:
                warns.append(f"market.{k} rests on assumed factor(s): {', '.join(guesses)}")
        if isinstance(m.get("tam"), dict) and m["tam"].get("basis") == "assumed":
            warns.append("market.tam is only assumed; find at least one source")
        for i, p in enumerate(m.get("projection") or []):
            if "year" not in p:
                errors.append(f"market.projection[{i}] has no year")
    comps = data.get("competitors") or []
    names = [c.get("name") for c in comps]
    if len(set(names)) != len(names):
        errors.append("competitors: duplicate names")
    if comps and sum(1 for c in comps if c.get("you")) != 1:
        errors.append("competitors: mark exactly one entry with \"you\": true (your product)")
    if len(comps) > 8:
        errors.append(f"competitors: {len(comps)} entries; keep at most 8 (you + 7), fold the rest into the report table")
    elif len(comps) - 1 < 3 and comps:
        warns.append("competitors: fewer than 3 rivals; check indirect alternatives (spreadsheets, agencies, doing nothing)")
    periods = set()
    for c in comps:
        if not c.get("name"):
            errors.append("competitors: an entry has no name")
        if not c.get("you") and not c.get("url"):
            warns.append(f"competitor {c.get('name')}: no url")
        for ax in ("x", "y"):
            v = c.get(ax)
            if v is not None and not (isinstance(v, (int, float)) and 0 <= v <= 10):
                errors.append(f"competitor {c.get('name')}: {ax} must be 0..10")
        p = c.get("price")
        if isinstance(p, dict):
            if p.get("value") is not None and not isinstance(p.get("value"), (int, float)):
                errors.append(f"competitor {c.get('name')}: price.value must be a number or null")
            per = p.get("period", "month")
            if per not in ("month", "year", "one-time"):
                errors.append(f"competitor {c.get('name')}: price.period must be month, year or one-time")
            periods.add("one-time" if per == "one-time" else "recurring")
            if not c.get("you"):
                cite(f"competitor {c.get('name')}.price", {"basis": p.get("basis", "sourced"), "sources": p.get("sources", [])})
        feats = c.get("features") or {}
        for fid, st in feats.items():
            if st not in FEATURE_STATES:
                errors.append(f"competitor {c.get('name')}: feature {fid} state '{st}' (use full|partial|none|unknown)")
    if len(periods) > 1:
        errors.append("pricing: one-time and recurring prices cannot share a chart; put them in separate data files or drop one")
    feats = data.get("features") or []
    fids = {f.get("id") for f in feats}
    if len(feats) > 12:
        errors.append(f"features: {len(feats)} rows; keep at most 12 that buyers actually choose on")
    for c in comps:
        for fid in (c.get("features") or {}):
            if fid not in fids:
                errors.append(f"competitor {c.get('name')}: unknown feature id {fid}")
    if feats and comps:
        unknown = sum(1 for c in comps for f in feats if (c.get("features") or {}).get(f.get("id"), "unknown") == "unknown")
        if unknown / (len(comps) * len(feats)) > 0.3:
            warns.append(f"features: {unknown} unknown cells; research more before drawing conclusions")
    pos = data.get("positioning")
    if isinstance(pos, dict):
        for ax in ("x", "y"):
            if not isinstance(pos.get(ax), dict) or not pos[ax].get("label"):
                errors.append(f"positioning.{ax}.label is required")
    for a in data.get("assumptions") or []:
        for k in ("impact", "uncertainty"):
            if not isinstance(a.get(k), (int, float)) or not 1 <= a[k] <= 5:
                errors.append(f"assumption {a.get('id')}: {k} must be 1..5")
        if not a.get("id") or not a.get("text"):
            errors.append("assumptions: each needs id and text")
    if len(data.get("assumptions") or []) > 12:
        warns.append("assumptions: more than 12 crowd the map; keep the riskiest")
    sc = data.get("scorecard")
    if isinstance(sc, dict):
        for d in sc.get("dimensions") or []:
            if not isinstance(d.get("score"), (int, float)) or not 0 <= d["score"] <= 5:
                errors.append(f"scorecard {d.get('id')}: score must be 0..5")
            cite(f"scorecard {d.get('id')}", {"evidence": d.get("evidence"), "sources": d.get("sources")})
            if d.get("id") in STANDARD_WEIGHTS and "weight" in d and d["weight"] != STANDARD_WEIGHTS[d["id"]]:
                warns.append(f"scorecard {d.get('id')}: custom weight ignored; standard dimensions use fixed weights")
        for k in ("go_threshold", "kill_below", "red_flag_below"):
            if k in sc:
                warns.append(f"scorecard.{k} is ignored; thresholds come from scorecard.profile")
        if sc.get("profile", "bootstrapped") not in PROFILES:
            errors.append(f"scorecard.profile must be one of {', '.join(PROFILES)}")
        vd = compute_verdict(data, base)
        if vd:
            if vd["capped"]:
                warns.append(f"scorecard: {', '.join(vd['capped'])} capped by evidence; raise the evidence, not the score")
            if vd["fragile"]:
                warns.append(f"scorecard: verdict is fragile on {', '.join(vd['fragile'])} (±0.5 flips it)")
            if not d.get("why"):
                warns.append(f"scorecard {d.get('id')}: no 'why'; a score without a reason cannot be challenged")
    dim_ids = {d.get("id") for d in (data.get("scorecard") or {}).get("dimensions") or []}
    for i, c in enumerate(data.get("red_team") or []):
        if c.get("dimension") not in dim_ids:
            errors.append(f"red_team[{i}]: unknown dimension {c.get('dimension')}")
        if c.get("resolution") not in ("accepted", "rebutted", None):
            errors.append(f"red_team[{i}]: resolution must be accepted or rebutted")
        if c.get("resolution") is None:
            warns.append(f"red_team[{i}] on {c.get('dimension')}: unresolved; the proposed score applies")
        for r in c.get("sources") or []:
            if r not in src_ids:
                errors.append(f"red_team[{i}]: cites unknown source {r}; add the skeptic's sources to 'sources' and run verify")
            elif source_state(src_by_id[r], base) not in ("verified", "tested"):
                warns.append(f"red_team[{i}] on {c.get('dimension')}: source {r} not verified, so the challenge lowers the score by at most {CHALLENGE_STEP}")
    for st in (meta or {}).get("steps") or []:
        if st.get("mode") in ("reduced", "skipped") and not st.get("reason"):
            errors.append(f"meta.steps: step {st.get('n')} ({st.get('skill')}) is {st.get('mode')} without a reason")
        if st.get("mode") in ("reduced", "skipped") and "time" in str(st.get("reason", "")).lower():
            warns.append(f"meta.steps: step {st.get('n')} ({st.get('skill')}) {st.get('mode')} to save time; run the skill")
    aids = {a.get("id") for a in data.get("assumptions") or []}
    for e in data.get("experiments") or []:
        if e.get("assumption") and e["assumption"] not in aids:
            warns.append(f"experiment {e.get('id')}: tests unknown assumption {e['assumption']}")
        if not e.get("success"):
            errors.append(f"experiment {e.get('id')}: needs a success criterion decided before it runs")
    hot = [a["id"] for a in data.get("assumptions") or [] if a.get("impact", 0) >= 4 and a.get("uncertainty", 0) >= 4]
    tested = {e.get("assumption") for e in data.get("experiments") or []}
    for a in hot:
        if data.get("experiments") is not None and a not in tested:
            warns.append(f"assumption {a} is in 'test first' but no experiment tests it")
    return errors, warns


# --------------------------------------------------------------------- dashboard


def table_html(name, data, W, lang):
    cur = data.get("meta", {}).get("currency", "USD")
    rows = []
    if name == "market":
        m = data["market"]
        rows = [["", "value", "basis", "sources", "note"]] + [[k.upper(), money(m[k]["value"], cur, lang, False), W.get(m[k].get("basis"), ""),
                                                           ", ".join(m[k].get("sources", [])), m[k].get("label", "")]
                                                          for k in ("tam", "sam", "som") if isinstance(m.get(k), dict)]
    elif name == "trend":
        key = data["market"].get("projection_metric", "tam")
        rows = [["year", key.upper(), ""]] + [[p.get("year"), money(p.get(key), cur, lang, False), W["projected"] if p.get("projected") else W["actual"]]
                                              for p in data["market"]["projection"]]
    elif name == "pricing":
        rows = [["", "price", "period", "note"]] + [[c["name"], money(c["price"].get("value"), cur, lang, False) if c["price"].get("value") is not None else W["no_price"],
                                                     W.get(c["price"].get("period", "month"), ""), c["price"].get("note", "")]
                                                    for c in data["competitors"] if isinstance(c.get("price"), dict)]
    elif name == "features":
        rows = [[""] + [c["name"] for c in data["competitors"]]] + [[f["label"]] + [W.get((c.get("features") or {}).get(f["id"], "unknown"), "")
                                                                                  for c in data["competitors"]] for f in data["features"]]
    elif name == "positioning":
        p = data["positioning"]
        rows = [["", p["x"]["label"], p["y"]["label"]]] + [[c["name"], c.get("x"), c.get("y")] for c in data["competitors"] if c.get("x") is not None]
    elif name == "assumptions":
        rows = [["id", "assumption", "category", W["impact"], W["uncertainty"]]] + [[a["id"], a["text"], a.get("category", ""), a["impact"], a["uncertainty"]]
                                                                                   for a in data["assumptions"]]
    elif name == "scorecard":
        vd = data.get("_verdict") or compute_verdict(data)
        rows = [["", "claimed", "counted", "evidence (claimed → checked)", "why"]] + [
            [d["label"], d["score"], vd["used"][d["id"]], f'{W.get(d.get("evidence"), "")} → {W.get(vd["evidence"][d["id"]], "")}', d.get("why", "")]
            for d in data["scorecard"]["dimensions"]]
    elif name == "experiments":
        rows = [["id", "method", "tests", "start", "weeks", "success"]] + [[e["id"], e["method"], e.get("assumption", ""), e.get("start_week", 1),
                                                                            e.get("weeks", 1), e.get("success", "")] for e in data["experiments"]]
    if not rows:
        return ""
    head = "".join(f"<th>{esc(c)}</th>" for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return f'<details><summary>{esc(W["table"])}</summary><div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></details>'


def grounded_line(vd, W):
    g = vd.get("grounded") or {}
    return W["grounded_parts"].format(t=g.get("tested", 0), v=g.get("verified", 0), p=g.get("proxy", 0), a=g.get("guess", 0))


def dashboard_html(data, items, theme, W, lang, vd, base=None):
    t, d = theme, DARK_THEME
    srcs_ = data.get("sources") or []
    checked = f"{sum(1 for s_ in srcs_ if source_state(s_, base) in ('verified', 'tested'))} / {len(srcs_)}"
    meta = data.get("meta", {})
    css = (
        f":root{{--paper:{t['paper']};--paper2:{t['paper2']};--ink:{t['ink']};--muted:{t['muted']};--soft:{t['soft']};"
        f"--rule:{t['rule']};--accent:{t['accent']};--link:{t['link']}}}"
        f"@media (prefers-color-scheme: dark){{:root{{--paper:{d['paper']};--paper2:{d['paper2']};--ink:{d['ink']};--muted:{d['muted']};"
        f"--soft:{d['soft']};--rule:{d['rule']};--accent:{d['accent']};--link:{d['link']}}}}}"
        f"*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:{t['font']};line-height:1.5}}"
        "main{max-width:1120px;margin:0 auto;padding:32px 16px 64px}h1{font-size:24px;margin:0 0 4px}"
        ".lede{color:var(--muted);margin:0 0 24px;max-width:72ch}.hero{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 32px}"
        ".tile{border:1px solid var(--rule);border-radius:8px;padding:12px 16px;min-width:150px;background:var(--paper)}"
        f".tile b{{display:block;font-size:22px}}.tile span{{font:11px {t['mono']};letter-spacing:.06em;color:var(--soft);text-transform:uppercase}}"
        ".v{color:var(--accent)}section{margin:0 0 40px}.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:8px}"
        ".scroll svg{display:block;max-width:none}details{margin-top:8px}summary{cursor:pointer;color:var(--muted);font-size:14px}"
        ".tw{overflow-x:auto}table{border-collapse:collapse;font-size:13px;margin-top:8px}th,td{border-bottom:1px solid var(--rule);"
        "padding:6px 10px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}a{color:var(--link)}"
        ".src li{margin:0 0 4px;font-size:13px;color:var(--muted)}footer{color:var(--soft);font-size:12px;margin-top:40px}"
    )
    out = [f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{esc(meta.get("title", W["dashboard"]))}</title><style>{css}</style></head><body><main>',
           f'<h1>{esc(meta.get("title", W["dashboard"]))}</h1>']
    if meta.get("idea"):
        out.append(f'<p class="lede">{esc(meta["idea"])}</p>')
    if meta.get("illustrative"):
        out.append(f'<p class="lede"><b>{esc(W["illustrative"])}</b></p>')
    if vd:
        out.append('<div class="hero">'
                   f'<div class="tile"><span>{esc(W["verdict"])}</span><b class="v">{esc(W[vd["verdict"]])}</b></div>'
                   f'<div class="tile"><span>{esc(W["weighted"])}</span><b>{vd["score"]:.1f} / 5</b></div>'
                   f'<div class="tile"><span>{esc(W["confidence"])}</span><b>{esc(W[vd["confidence_level"]])} · {int(vd["confidence"] * 100)}%</b></div>'
                   f'<div class="tile"><span>{esc(W["sources_checked"])}</span><b>{checked}</b></div>'
                   f'<div class="tile"><span>{esc(W["grounded"])}</span><b>{esc(grounded_line(vd, W))}</b></div>'
                   '</div>')
    for name, svg in items:
        out.append(f'<section id="{name}" data-chart="{name}"><div class="scroll">{svg}</div>{table_html(name, data, W, lang)}</section>')
    srcs = data.get("sources") or []
    if srcs:
        out.append(f'<h2>{esc(W["sources"])}</h2><ul class="src">')
        for s in srcs:
            link = f'<a href="{esc(s["url"])}" rel="noopener">{esc(s.get("title") or s["url"])}</a>' if s.get("url") else esc(s.get("title", ""))
            extra = " · ".join(x for x in (s.get("publisher", ""), s.get("accessed", "")) if x)
            st = source_state(s, base)
            out.append(f'<li><b>{esc(s["id"])}</b> {link}{" · " + esc(extra) if extra else ""} · <i>{esc(W.get(st, st))}</i></li>')
        out.append("</ul>")
    out.append(f'<footer>{esc(W["generated"])} data.json · {esc(meta.get("date", ""))}</footer></main></body></html>\n')
    return "".join(out)


# --------------------------------------------------------------------- provenance


def provenance(data, base=None):
    """Markdown table: every number the verdict uses, and what it actually rests on."""
    W, lang = words(data)
    cur = (data.get("meta") or {}).get("currency", "USD")
    sources = {s.get("id"): s for s in data.get("sources") or []}

    def backing(obj):
        level = obj.get("basis") or obj.get("evidence") or "sourced"
        refs = obj.get("sources") or []
        if not refs:
            return W.get(level, level)
        states = ", ".join(f"{r} {W.get(source_state(sources[r], base), '?')}" for r in refs if r in sources)
        return f"{W.get(level, level)}: {states}"

    rows = [W["prov"]]
    m = data.get("market") or {}
    for k in ("tam", "sam", "som"):
        x = m.get(k)
        if not isinstance(x, dict):
            continue
        rows.append((f"{k.upper()} {x.get('label', '')}".strip(), money(x.get("value"), cur, lang, False), backing(x)))
        for f in x.get("inputs") or []:
            rows.append((f"  × {f.get('label', '')}", fmt(f.get("value")), backing(f)))
    for c in data.get("competitors") or []:
        p = c.get("price")
        if isinstance(p, dict) and p.get("value") is not None:
            rows.append((f"{c.get('name')}: {W['price_of']}", money(p["value"], cur, lang, False), backing({"basis": p.get("basis", "sourced" if not c.get("you") else "assumed"), "sources": p.get("sources", [])})))
    vd = compute_verdict(data, base)
    if vd:
        for d in (data.get("scorecard") or {}).get("dimensions") or []:
            eff = vd["evidence"][d["id"]]
            rows.append((d.get("label", d["id"]), f"{fmt(d['score'])} → {fmt(vd['used'][d['id']])}", f"{W.get(eff, eff)}" + (f" ({', '.join(d.get('sources') or [])})" if d.get("sources") else "")))
    out = [f"| {' | '.join(rows[0])} |", "|---|---|---|"]
    out += [f"| {' | '.join(str(c).replace('|', '/') for c in r)} |" for r in rows[1:]]
    if vd:
        out.append("")
        out.append(f"{W['grounded']}: {grounded_line(vd, W)}")
    return "\n".join(out)


# --------------------------------------------------------------------- main


def build(data, out_dir, theme, write=True, base=None):
    W, lang = words(data)
    vd = compute_verdict(data, base)
    data = {**data, "_verdict": vd}
    items, report = [], {"charts": [], "skipped": [], "verdict": vd}
    for name, has, fn in CHARTS:
        if not has(data):
            report["skipped"].append(name)
            continue
        svg = fn(data, theme, W, lang, chart_hash(data, name)).render()
        items.append((name, svg))
        path = out_dir / f"{name}.svg"
        report["charts"].append({"name": name, "svg": str(path), "source_sha1": chart_hash(data, name)})
        if write:
            path.write_text(svg, encoding="utf-8")
    if write:
        (out_dir / "index.html").write_text(dashboard_html(data, items, theme, W, lang, vd, base), encoding="utf-8")
        (out_dir / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def stale(data, out_dir):
    msgs = []
    for name, has, _ in CHARTS:
        if not has(data):
            continue
        p = out_dir / f"{name}.svg"
        if not p.exists():
            msgs.append(f"{name}: not rendered yet")
            continue
        m = re.search(r'data-source-sha1="([0-9a-f]+)"', p.read_text(encoding="utf-8")[:2000])
        if not m or m.group(1) != chart_hash(data, name):
            msgs.append(f"{name}: older than data.json, rebuild")
    return msgs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "check", "verdict", "verify", "provenance"])
    ap.add_argument("data")
    ap.add_argument("--out")
    ap.add_argument("--tokens")
    ap.add_argument("--theme")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    path = Path(a.data)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error  {path}: {e}")
        return 1
    out_dir = Path(a.out) if a.out else path.parent / "charts"
    theme = load_theme(a.theme, a.tokens)
    base = path.parent
    if a.command == "provenance":
        print(provenance(data, base))
        return 0
    if a.command == "verdict":
        print(json.dumps(compute_verdict(data, base), ensure_ascii=False))
        return 0
    if a.command == "verify":
        import datetime
        res = verify_sources(data, base, datetime.date.today().isoformat())
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for sid, rec in res:
            print(f"{rec['status']:<7}{sid}  {rec.get('http', '')}  {rec.get('reason', '')}".rstrip())
        n_ok = sum(1 for _, r in res if r["status"] == "quote")
        print(f"VERIFY: {n_ok} of {len(res)} sources confirmed with their quotes; written to {path}")
        return 0
    errors, warns = check(data, base)
    warns += contrast_issues(theme)
    if a.command == "check":
        warns += stale(data, out_dir)
        for e in errors:
            print(f"error  {e}")
        for w in warns:
            print(f"warn   {w}")
        print(f"CHECK: {len(errors)} errors, {len(warns)} warnings")
        return 1 if errors or (a.strict and warns) else 0
    if errors:
        for e in errors:
            print(f"error  {e}")
        print("BUILD: refused, fix the errors above")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = build(data, out_dir, theme, base=base)
    for w in warns:
        print(f"warn   {w}")
    vd = rep["verdict"]
    print(f"CHARTS: {len(rep['charts'])} rendered ({', '.join(c['name'] for c in rep['charts'])}), skipped: {', '.join(rep['skipped']) or 'none'}")
    print(f"FILES: {out_dir / 'index.html'}")
    if vd:
        print(f"VERDICT: {vd['verdict'].upper()} {vd['score']}/5, confidence {vd['confidence_level']} ({vd['confidence']}), "
              f"red flags: {', '.join(vd['red_flags']) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
