"""Design system for the dashboard: injected CSS + HTML components.

One aesthetic, executed consistently: a "precision instrument" look — deep
navy sidebar, cool paper canvas with a faint gradient wash, Sora display type
over IBM Plex Sans/Mono, a single indigo→blue→teal gradient family, soft
elevated cards with staggered reveals. Motion is CSS-only and honors
prefers-reduced-motion. Data colors stay the validated chart palette.
"""

from __future__ import annotations

import html

import streamlit as st

# gradient family (brand), distinct from the data palette used inside charts
BRAND_DEEP = "#16305e"
BRAND_BLUE = "#2a78d6"
BRAND_TEAL = "#1baf7a"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --ink: #101623;
  --ink-2: #465062;
  --muted: #7b8494;
  --paper: #f6f8fb;
  --card: #ffffff;
  --line: #e4e8f0;
  --brand-deep: #16305e;
  --brand-blue: #2a78d6;
  --brand-teal: #1baf7a;
  --grad: linear-gradient(96deg, var(--brand-deep) 0%,
          var(--brand-blue) 55%, var(--brand-teal) 130%);
  --shadow-sm: 0 1px 2px rgba(16,24,40,.05);
  --shadow-md: 0 8px 24px -12px rgba(22,48,94,.22), 0 2px 6px -2px rgba(16,24,40,.06);
  --radius: 14px;
  --ease: cubic-bezier(.22,.61,.36,1);
}

/* ---------- canvas ---------- */
html, body, [data-testid="stAppViewContainer"] {
  font-family: 'IBM Plex Sans', sans-serif;
  color: var(--ink);
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(900px 320px at 18% -60px,
      rgba(42,120,214,.10), transparent 62%),
    radial-gradient(700px 280px at 85% -80px,
      rgba(27,175,122,.07), transparent 60%),
    var(--paper);
}
[data-testid="stHeader"] { background: transparent; }

/* main column enters with a soft rise */
[data-testid="stMainBlockContainer"] { animation: rise .45s var(--ease) both; }
@keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

h1, h2, h3 { font-family: 'Sora', sans-serif !important; letter-spacing: -.02em; color: var(--ink); }
[data-testid="stMarkdownContainer"] p { color: var(--ink-2); }
[data-testid="stCaptionContainer"] { color: var(--muted) !important; }

/* ---------- sidebar: the instrument's dark panel ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(178deg, #0e1c3a 0%, var(--brand-deep) 58%, #123c66 130%);
  border-right: 1px solid rgba(255,255,255,.06);
}
[data-testid="stSidebar"] * { color: #dbe4f5 !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong { color: #ffffff !important; }
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] {
  border-radius: 10px;
  transition: background .18s var(--ease), transform .18s var(--ease);
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover {
  background: rgba(255,255,255,.08);
  transform: translateX(2px);
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: linear-gradient(92deg, rgba(42,120,214,.35), rgba(27,175,122,.18));
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.10);
}
[data-testid="stSidebar"] code {
  background: rgba(255,255,255,.10); color: #cfe3ff !important;
}

/* ---------- widgets ---------- */
[data-baseweb="select"] > div {
  border-radius: 10px !important;
  border-color: var(--line) !important;
  transition: border-color .18s var(--ease), box-shadow .18s var(--ease);
}
[data-baseweb="select"] > div:focus-within {
  border-color: var(--brand-blue) !important;
  box-shadow: 0 0 0 3px rgba(42,120,214,.18);
}
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {
  font-family: 'IBM Plex Mono', monospace;
}
[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
[data-testid="stExpander"] details {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--card);
  box-shadow: var(--shadow-sm);
  transition: box-shadow .2s var(--ease);
}
[data-testid="stExpander"] details:hover { box-shadow: var(--shadow-md); }
hr { border-color: var(--line); }

/* ---------- custom components ---------- */
.tab-hero { margin: 0 0 .35rem 0; }
.tab-hero h1 {
  font-size: 2.05rem; font-weight: 700; margin: 0;
  background: var(--grad);
  background-size: 200% 100%;
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: sheen 9s ease-in-out infinite alternate;
}
@keyframes sheen { from { background-position: 0% 0; } to { background-position: 100% 0; } }
.tab-hero .rule {
  height: 3px; width: 64px; margin-top: .55rem; border-radius: 99px;
  background: var(--grad);
}
.tab-hero p { color: var(--ink-2); margin: .6rem 0 0 0; max-width: 62rem; line-height: 1.55; }

.tab-verdict {
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background: var(--card);
  box-shadow: var(--shadow-md);
  padding: 1.05rem 1.25rem 1.05rem 1.15rem;
  position: relative; overflow: hidden;
  margin: .35rem 0 .9rem 0;
  animation: rise .5s var(--ease) both;
}
.tab-verdict::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 5px;
  background: var(--vgrad);
}
.tab-verdict .v-head { display: flex; align-items: center; gap: .7rem; }
.tab-verdict .v-icon {
  width: 2.1rem; height: 2.1rem; border-radius: 50%;
  display: grid; place-items: center; font-size: 1.05rem;
  background: var(--vtint); flex: none;
}
.tab-verdict .v-title {
  font-family: 'Sora', sans-serif; font-weight: 600; font-size: 1.06rem;
  color: var(--ink); line-height: 1.35;
}
.tab-verdict .v-note {
  color: var(--ink-2); font-size: .88rem; line-height: 1.5;
  margin: .55rem 0 0 2.8rem; position: relative;
}
.tab-verdict .v-note::before {
  content: ""; position: absolute; left: -1rem; top: .55em;
  width: 5px; height: 5px; border-radius: 50%; background: var(--vdot);
}

.tab-grid {
  display: grid; gap: .8rem; margin: .2rem 0 .4rem 0;
  grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
}
.tab-stat {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: .85rem 1rem .8rem 1rem;
  box-shadow: var(--shadow-sm);
  transition: transform .18s var(--ease), box-shadow .18s var(--ease);
  animation: rise .5s var(--ease) both;
}
.tab-grid .tab-stat:nth-child(2) { animation-delay: .05s; }
.tab-grid .tab-stat:nth-child(3) { animation-delay: .10s; }
.tab-grid .tab-stat:nth-child(4) { animation-delay: .15s; }
.tab-grid .tab-stat:nth-child(5) { animation-delay: .20s; }
.tab-stat:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.tab-stat .s-label {
  font-size: .72rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); display: flex; align-items: center; gap: .4rem;
}
.tab-stat .s-value {
  font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums;
  font-size: 1.42rem; font-weight: 600; color: var(--ink); margin-top: .15rem;
}
.tab-stat .s-sub { font-size: .78rem; color: var(--muted); margin-top: .1rem; line-height: 1.45; }
.tab-stat .s-value.good { color: #0b7a44; }
.tab-stat .s-value.bad { color: #c02f2f; }
.tab-stat .s-value.grad {
  background: var(--grad); -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.s-dot { width: .55rem; height: .55rem; border-radius: 50%; display: inline-block; }
.s-dot.ok { background: #12b06a; box-shadow: 0 0 0 3px rgba(18,176,106,.16); }
.s-dot.fail { background: #d03b3b; box-shadow: 0 0 0 3px rgba(208,59,59,.16); }
.s-dot.warn { background: #e9a13b; box-shadow: 0 0 0 3px rgba(233,161,59,.18); }

.tab-section {
  font-family: 'Sora', sans-serif; font-weight: 600; font-size: 1.12rem;
  color: var(--ink); margin: 1.4rem 0 .15rem 0;
  display: flex; align-items: center; gap: .55rem;
}
.tab-section::before {
  content: ""; width: 8px; height: 8px; border-radius: 3px;
  background: var(--grad); transform: rotate(45deg); flex: none;
}

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, lede: str) -> None:
    """Page header: gradient display title + rule + lede paragraph."""
    st.markdown(
        f'<div class="tab-hero"><h1>{html.escape(title)}</h1>'
        f'<div class="rule"></div><p>{lede}</p></div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown(f'<div class="tab-section">{html.escape(title)}</div>', unsafe_allow_html=True)


_VERDICT_STYLES = {
    "ship": {
        "vgrad": "linear-gradient(180deg,#12b06a,#1baf7a)",
        "vtint": "rgba(18,176,106,.14)",
        "vdot": "#12b06a",
        "icon": "✓",
    },
    "keep": {
        "vgrad": "linear-gradient(180deg,#2a78d6,#16305e)",
        "vtint": "rgba(42,120,214,.13)",
        "vdot": "#2a78d6",
        "icon": "⌂",
    },
    "warn": {
        "vgrad": "linear-gradient(180deg,#e9a13b,#d97e12)",
        "vtint": "rgba(233,161,59,.16)",
        "vdot": "#d97e12",
        "icon": "!",
    },
    "invalid": {
        "vgrad": "linear-gradient(180deg,#d03b3b,#8f1d1d)",
        "vtint": "rgba(208,59,59,.13)",
        "vdot": "#d03b3b",
        "icon": "✕",
    },
}


def verdict_card(kind: str, title: str, notes: list[str]) -> None:
    """The decision banner. kind: ship | keep | warn | invalid."""
    s = _VERDICT_STYLES[kind]
    notes_html = "".join(f'<div class="v-note">{html.escape(n)}</div>' for n in notes)
    st.markdown(
        f'<div class="tab-verdict" style="--vgrad:{s["vgrad"]};--vtint:{s["vtint"]};'
        f'--vdot:{s["vdot"]}">'
        f'<div class="v-head"><div class="v-icon">{s["icon"]}</div>'
        f'<div class="v-title">{html.escape(title)}</div></div>{notes_html}</div>',
        unsafe_allow_html=True,
    )


def stat_grid(cards: list[dict[str, str]]) -> None:
    """Row of stat cards. Each: label, value, sub?, dot? (ok|fail|warn), tone? (good|bad|grad)."""
    out = ['<div class="tab-grid">']
    for c in cards:
        dot = f'<span class="s-dot {c["dot"]}"></span>' if c.get("dot") else ""
        tone = f' {c["tone"]}' if c.get("tone") else ""
        sub = f'<div class="s-sub">{html.escape(c["sub"])}</div>' if c.get("sub") else ""
        out.append(
            f'<div class="tab-stat"><div class="s-label">{dot}{html.escape(c["label"])}</div>'
            f'<div class="s-value{tone}">{html.escape(c["value"])}</div>{sub}</div>'
        )
    out.append("</div>")
    st.markdown("".join(out), unsafe_allow_html=True)
