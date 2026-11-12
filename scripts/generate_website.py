#!/usr/bin/env python3
"""
Generates the modernized static website in `docs/` (ready for GitHub Pages and local viewing).
"""

import glob
import html as html_lib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.extract_data import ROOT_DIR, WEBSITE_DIR, build_dataset
from scripts.generate_exports import EXPORTS_DIR, format_person_display_name, generate_all_exports

DOCS_DIR = os.path.join(ROOT_DIR, "docs")


def esc(s):
    if s is None:
        return ""
    return html_lib.escape(str(s))


def page_shell(title, body_html, rel_root=".", active_nav="", extra_head=""):
    """Wraps page content in the modern responsive HTML5 layout."""
    r = rel_root.rstrip("/")
    nav_items = [
        ("home", f"{r}/index.html", "Home"),
        ("explorer", f"{r}/tree/explorer.html", "Interactive Tree"),
        ("map", f"{r}/misc/map.html", "Tree Map"),
        ("ancestors", f"{r}/people/index.html", "Direct Ancestors"),
        ("people", f"{r}/people/indexall.html", "All People"),
        ("angelos", f"{r}/angelos/angelos.html", "The Angelos"),
        ("notes", f"{r}/notes/index.html", "Course Notes"),
        ("exports", f"{r}/exports/index.html", "Data & GEDCOM"),
    ]
    nav_links_html = "\n".join(
        f'          <a href="{href}" class="nav-link{" active" if key == active_nav else ""}">{label}</a>'
        for key, href, label in nav_items
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)} — The Muir Family Tree</title>
  <meta name="description" content="The Muir Family Tree &amp; Genealogy Archive — Muir, Steuart, Angelo, Van Cortlandt, Whiteway, Endacott, Whitfield, and Hall family history.">
  <link rel="stylesheet" href="{r}/assets/style.css">
  {extra_head}
</head>
<body data-rel-root="{r}">
  <header class="site-header">
    <div class="header-inner">
      <a href="{r}/index.html" class="brand">
        <span class="brand-crest">M</span>
        <span class="brand-text">
          <strong>The Muir Family Tree</strong>
          <small>Genealogy &amp; Family History Archive</small>
        </span>
      </a>
      <nav class="main-nav" aria-label="Main Navigation">
{nav_links_html}
      </nav>
      <div class="header-actions">
        <div class="search-wrapper">
          <input type="search" id="global-person-search" class="search-input" placeholder="Search 696 people..." autocomplete="off" aria-label="Search people">
          <div id="global-search-results" class="search-dropdown" hidden></div>
        </div>
        <button type="button" id="theme-toggle" class="theme-btn" title="Toggle dark/light mode" aria-label="Toggle theme">◐</button>
      </div>
    </div>
  </header>

  <main class="main-container">
{body_html}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <div>
        <strong>The Muir Family Tree &amp; Genealogy Archive</strong>
        <p>Originally researched by Richard Francis Muir (1930–2019) and created by Francis Muir (2000–2001). Modernized with complete Access database &amp; GEDCOM exports.</p>
      </div>
      <div class="footer-links">
        <a href="{r}/index.html">Home</a>
        <a href="{r}/tree/explorer.html">Interactive Tree</a>
        <a href="{r}/misc/map.html">Map</a>
        <a href="{r}/people/index.html">Direct Ancestors</a>
        <a href="{r}/people/indexall.html">All People</a>
        <a href="{r}/exports/index.html">Downloads &amp; GEDCOM</a>
        <a href="{r}/misc/history.html">Site History</a>
      </div>
    </div>
  </footer>

  <script src="{r}/assets/tree-data.js"></script>
  <script src="{r}/assets/app.js"></script>
</body>
</html>
"""


def write_assets(ds):
    assets_dir = os.path.join(DOCS_DIR, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # 1. Write docs/assets/tree-data.js (compact index for instant search & interactive tree explorer)
    people = ds["people"]
    families = ds["families"]
    trees = ds["trees"]

    compact_people = {}
    for pid, p in sorted(people.items()):
        compact_people[pid] = {
            "id": pid,
            "sn": p["surname"],
            "cn": p["cname"],
            "name": format_person_display_name(p),
            "da": bool(p["is_direct_ancestor"]),
            "ref": p["ahnentafel"],
            "gen": p["generation"],
            "sex": p["gender"],
            "dates": p["dates"],
            "b": p["birth"],
            "d": p["death"],
            "prof": p["profession"],
            "tid": p["tree_id"] or "",
            "p": p["parents"],
            "s": p["spouses"],
            "c": p["children"],
        }

    tree_titles = {tid: t["title"] for tid, t in trees.items()}

    js_data = (
        "window.FAMILY_DATA = "
        + json.dumps(
            {"people": compact_people, "families": families, "trees": tree_titles},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + ";\n"
    )
    with open(os.path.join(assets_dir, "tree-data.js"), "w", encoding="utf-8") as f:
        f.write(js_data)

    # 2. Write docs/assets/style.css
    style_css = """/* Modern Heritage Stylesheet for The Muir Family Tree */
:root {
  --bg: #f8f6f1;
  --bg-elevated: #ffffff;
  --bg-subtle: #f0ece1;
  --text: #1c252c;
  --text-muted: #566370;
  --primary: #1e3a5f;
  --primary-hover: #142842;
  --accent: #9c6b27;
  --accent-soft: #f7eedc;
  --border: #dcd5c7;
  --border-strong: #b8ae9c;
  --shadow: 0 2px 8px rgba(28, 37, 44, 0.07);
  --shadow-lg: 0 8px 24px rgba(28, 37, 44, 0.12);
  --radius: 10px;
  --radius-sm: 6px;
  --connector-color: #697887;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-serif: "Georgia", "Times New Roman", serif;
}

[data-theme="dark"] {
  --bg: #12171d;
  --bg-elevated: #1b232c;
  --bg-subtle: #232d38;
  --text: #e6edf3;
  --text-muted: #9aa7b4;
  --primary: #68a0e8;
  --primary-hover: #8bb8f2;
  --accent: #e0a958;
  --accent-soft: #2c261c;
  --border: #2e3b48;
  --border-strong: #465768;
  --shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
  --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.5);
  --connector-color: #7d8e9e;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  background-color: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  line-height: 1.6;
  font-size: 16px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

a {
  color: var(--primary);
  text-decoration: none;
  transition: color 0.15s ease;
}

a:hover {
  color: var(--accent);
  text-decoration: underline;
}

/* Header & Navigation */
.site-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow);
}

.header-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0.65rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  text-decoration: none !important;
  color: var(--text);
}

.brand-crest {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: linear-gradient(135deg, #1e3a5f, #2d5488);
  color: #fff;
  font-family: var(--font-serif);
  font-weight: 700;
  font-size: 1.35rem;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.15);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.brand-text strong {
  font-family: var(--font-serif);
  font-size: 1.1rem;
  color: var(--text);
}

.brand-text small {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.main-nav {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.nav-link {
  padding: 0.4rem 0.7rem;
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  font-weight: 500;
  color: var(--text-muted);
  text-decoration: none !important;
}

.nav-link:hover, .nav-link.active {
  background: var(--bg-subtle);
  color: var(--primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.search-wrapper {
  position: relative;
  width: 240px;
}

.search-input {
  width: 100%;
  padding: 0.42rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--bg);
  color: var(--text);
  font-size: 0.86rem;
  outline: none;
}

.search-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(30, 58, 95, 0.15);
}

.search-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 340px;
  max-height: 400px;
  overflow-y: auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  z-index: 200;
}

.search-item {
  display: block;
  padding: 0.55rem 0.85rem;
  border-bottom: 1px solid var(--border);
  text-decoration: none !important;
  color: var(--text);
}

.search-item:last-child {
  border-bottom: none;
}

.search-item:hover {
  background: var(--bg-subtle);
}

.search-item-title {
  font-weight: 600;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.search-item-meta {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.theme-btn {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  width: 34px;
  height: 34px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.theme-btn:hover {
  background: var(--bg-subtle);
}

/* Main Content Container */
.main-container {
  max-width: 1360px;
  width: 100%;
  margin: 0 auto;
  padding: 1.75rem 1.25rem 3rem;
  flex: 1;
}

/* Typography & Common UI */
h1, h2, h3 {
  font-family: var(--font-serif);
  color: var(--text);
  margin-top: 0;
}

h1 {
  font-size: 2rem;
  margin-bottom: 0.75rem;
}

.page-header {
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.breadcrumbs {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--bg-subtle);
  color: var(--text-muted);
  border: 1px solid var(--border);
}

.badge-ancestor {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent);
}

.badge-primary {
  background: rgba(30, 58, 95, 0.1);
  color: var(--primary);
  border-color: rgba(30, 58, 95, 0.25);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.95rem;
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  font-weight: 600;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text);
  cursor: pointer;
  text-decoration: none !important;
  transition: all 0.15s ease;
}

.btn:hover {
  background: var(--bg-subtle);
  border-color: var(--border-strong);
}

.btn-primary {
  background: var(--primary);
  color: #fff !important;
  border-color: var(--primary);
}

.btn-primary:hover {
  background: var(--primary-hover);
}

/* Cards & Grids */
.card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  box-shadow: var(--shadow);
  margin-bottom: 1.25rem;
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.25rem;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.15rem;
}

/* Home Hero */
.hero-banner {
  background: linear-gradient(135deg, #1e3a5f 0%, #2c4c75 100%);
  color: #fff;
  border-radius: var(--radius);
  padding: 2.25rem;
  margin-bottom: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  flex-wrap: wrap;
  box-shadow: var(--shadow-lg);
}

.hero-content {
  flex: 1;
  min-width: 280px;
}

.hero-content h1 {
  color: #fff;
  font-size: 2.2rem;
  margin-bottom: 0.5rem;
}

.hero-content p {
  color: rgba(255, 255, 255, 0.88);
  font-size: 1.05rem;
  margin-bottom: 1.25rem;
}

.hero-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.hero-crest-img {
  background: #fff;
  padding: 0.75rem;
  border-radius: var(--radius);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  max-width: 190px;
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.75rem;
}

.stat-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  text-align: center;
  box-shadow: var(--shadow);
}

.stat-num {
  font-family: var(--font-serif);
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--primary);
  display: block;
}

.stat-label {
  font-size: 0.82rem;
  color: var(--text-muted);
}

/* 3-Generation Family Tree Page Layout */
.tree-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.tree-viewport {
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2rem 1.5rem;
  box-shadow: var(--shadow);
  min-height: 320px;
}

.tree-stage {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  gap: 4.25rem;
  min-width: 100%;
  transform-origin: top left;
  transition: transform 0.15s ease;
}

.tree-connectors-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}

.tree-gen-row {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: stretch;
  gap: 1.25rem;
}

.tree-gen-badge {
  flex: 0 0 64px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-subtle);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0.5rem 0.25rem;
  font-weight: 700;
  color: var(--text-muted);
  font-size: 0.78rem;
  text-transform: uppercase;
}

.tree-gen-badge strong {
  font-size: 1.25rem;
  color: var(--text);
  font-family: var(--font-serif);
}

.tree-row-nodes {
  flex: 1;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 1.15rem;
}

.tree-node-card {
  position: relative;
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-top: 4px solid var(--primary);
  border-radius: var(--radius-sm);
  padding: 0.65rem 0.8rem;
  min-width: 145px;
  max-width: 220px;
  box-shadow: var(--shadow);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  font-size: 0.85rem;
  line-height: 1.35;
}

.tree-node-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.tree-node-card[data-accent="#FFFF99"] { border-top-color: #d99b26; }
.tree-node-card[data-accent="#8080FF"] { border-top-color: #4a5fd9; }
.tree-node-card[data-accent="#80FF80"] { border-top-color: #2e9e5b; }
.tree-node-card[data-accent="#00FFCC"] { border-top-color: #0d9488; }
.tree-node-card[data-accent="#FF6666"] { border-top-color: #dc2626; }

.tree-nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  width: 100%;
  padding: 0.22rem 0.45rem;
  margin-bottom: 0.4rem;
  border-radius: 4px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  font-size: 0.73rem;
  font-weight: 600;
  color: var(--primary);
  text-decoration: none !important;
}

.tree-nav-btn.down {
  margin-top: 0.5rem;
  margin-bottom: 0;
}

.tree-nav-btn:hover {
  background: var(--primary);
  color: #fff !important;
}

.person-block-name {
  font-weight: 700;
  color: var(--primary);
  display: block;
}

.person-block-dates {
  font-size: 0.76rem;
  color: var(--text-muted);
  display: block;
}

.spouse-divider {
  margin: 0.38rem 0;
  padding-top: 0.35rem;
  border-top: 1px dashed var(--border);
  font-size: 0.73rem;
  font-style: italic;
  color: var(--text-muted);
}

.issue-pill, .note-pill {
  display: inline-block;
  margin-top: 0.25rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
}

.issue-pill {
  background: var(--bg-subtle);
  color: var(--text-muted);
}

.note-pill {
  background: var(--accent-soft);
  color: var(--accent);
}

/* Tables */
.data-table-wrapper {
  overflow-x: auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

table.data-table, .legacy-content table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}

table.data-table th, table.data-table td,
.legacy-content table th, .legacy-content table td {
  padding: 0.65rem 0.9rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

table.data-table th, .legacy-content table th {
  background: var(--bg-subtle);
  font-weight: 600;
  color: var(--text);
  position: sticky;
  top: 0;
}

table.data-table tr:hover {
  background: rgba(30, 58, 95, 0.03);
}

.legacy-content td.map-cell {
  background: var(--bg-subtle);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  text-align: center;
  vertical-align: middle;
  font-weight: 600;
  padding: 0.55rem 0.75rem;
}

.legacy-content td.map-cell a {
  display: block;
}

/* Person Profile Immediate Family Diagram */
.family-mini-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}

.mini-person-card {
  display: block;
  padding: 0.75rem 0.9rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: var(--radius-sm);
  text-decoration: none !important;
  color: var(--text);
  transition: transform 0.12s ease, border-color 0.12s ease;
}

.mini-person-card:hover {
  transform: translateY(-1px);
  border-color: var(--accent);
  background: var(--bg-subtle);
}

.mini-person-card.ancestor {
  border-left-color: var(--accent);
}

.mini-person-card strong {
  display: block;
  color: var(--primary);
  font-size: 0.92rem;
}

.mini-person-card span {
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* Alphabet Bar */
.alpha-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 1.25rem;
}

.alpha-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  height: 34px;
  padding: 0 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  font-weight: 600;
  font-size: 0.88rem;
  color: var(--text);
  text-decoration: none !important;
}

.alpha-pill:hover, .alpha-pill.active {
  background: var(--primary);
  color: #fff !important;
  border-color: var(--primary);
}

.alpha-pill.disabled {
  opacity: 0.4;
  pointer-events: none;
}

/* Footer */
.site-footer {
  background: var(--bg-elevated);
  border-top: 1px solid var(--border);
  padding: 1.5rem 1.25rem;
  margin-top: auto;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.footer-inner {
  max-width: 1360px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.footer-links {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .header-inner {
    flex-direction: column;
    align-items: stretch;
  }
  .search-wrapper {
    width: 100%;
  }
  .search-dropdown {
    width: 100%;
  }
}

@media print {
  .site-header, .site-footer, .tree-toolbar {
    display: none !important;
  }
  .tree-viewport {
    overflow: visible !important;
    border: none !important;
    box-shadow: none !important;
  }
}
"""
    with open(os.path.join(assets_dir, "style.css"), "w", encoding="utf-8") as f:
        f.write(style_css)

    # 3. Write docs/assets/app.js (Global search, theme toggle, SVG tree connector drawing, interactive explorer)
    app_js = """/* Client-side interactivity for The Muir Family Tree */
(function () {
  const relRoot = document.body.getAttribute("data-rel-root") || ".";

  // 1. Theme Toggle
  const savedTheme = localStorage.getItem("muir_theme");
  if (savedTheme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      if (next === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
      localStorage.setItem("muir_theme", next);
    });
  }

  // 2. Global Instant Search
  const searchInput = document.getElementById("global-person-search");
  const searchResults = document.getElementById("global-search-results");
  if (searchInput && searchResults && window.FAMILY_DATA) {
    const peopleList = Object.values(window.FAMILY_DATA.people);

    searchInput.addEventListener("input", function () {
      const q = searchInput.value.trim().toLowerCase();
      if (!q) {
        searchResults.hidden = true;
        searchResults.innerHTML = "";
        return;
      }
      const tokens = q.split(/\\s+/);
      const matches = [];
      for (let i = 0; i < peopleList.length; i++) {
        const p = peopleList[i];
        const hay = (p.name + " " + p.sn + " " + p.cn + " " + p.dates + " " + p.b + " " + p.d + " " + p.prof + " " + p.ref).toLowerCase();
        if (tokens.every(function (t) { return hay.indexOf(t) !== -1; })) {
          matches.push(p);
        }
      }
      matches.sort(function (a, b) {
        if (a.da !== b.da) return a.da ? -1 : 1;
        return a.sn.localeCompare(b.sn) || a.cn.localeCompare(b.cn);
      });

      const top = matches.slice(0, 15);
      if (top.length === 0) {
        searchResults.innerHTML = '<div class="search-item"><span class="search-item-meta">No matching people found.</span></div>';
      } else {
        searchResults.innerHTML = top.map(function (p) {
          const badge = p.da ? '<span class="badge badge-ancestor">★ Direct</span>' : '<span class="badge">Gen ' + p.gen + '</span>';
          const prof = p.prof ? " · " + p.prof : "";
          return '<a class="search-item" href="' + relRoot + '/people/' + p.id + '.html">' +
            '<div class="search-item-title"><span>' + p.sn + ', ' + p.cn + '</span>' + badge + '</div>' +
            '<div class="search-item-meta">' + (p.dates || "") + prof + '</div>' +
          '</a>';
        }).join("");
      }
      searchResults.hidden = false;
    });

    document.addEventListener("click", function (e) {
      if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.hidden = true;
      }
    });
  }

  // 3. Draw SVG Connecting Lines on 3-Generation Tree Pages
  const treeStage = document.getElementById("tree-stage");
  const svgOverlay = document.getElementById("tree-connectors-svg");

  function drawTreeConnectors() {
    if (!treeStage || !svgOverlay) return;
    const stageRect = treeStage.getBoundingClientRect();
    const scale = parseFloat(treeStage.getAttribute("data-zoom") || "1");
    const w = treeStage.scrollWidth;
    const h = treeStage.scrollHeight;
    svgOverlay.setAttribute("width", w);
    svgOverlay.setAttribute("height", h);
    svgOverlay.setAttribute("viewBox", "0 0 " + w + " " + h);

    const cards = treeStage.querySelectorAll(".tree-node-card[data-parent-node]");
    let pathsHtml = "";

    const accentMap = {
      "#FFFF99": "#d99b26",
      "#8080FF": "#4a5fd9",
      "#80FF80": "#2e9e5b",
      "#00FFCC": "#0d9488",
      "#FF6666": "#dc2626"
    };

    cards.forEach(function (childCard) {
      const parentId = childCard.getAttribute("data-parent-node");
      if (!parentId) return;
      const parentCard = document.getElementById(parentId);
      if (!parentCard) return;

      const pRect = parentCard.getBoundingClientRect();
      const cRect = childCard.getBoundingClientRect();

      const x1 = (pRect.left - stageRect.left + pRect.width / 2) / scale;
      const y1 = (pRect.bottom - stageRect.top) / scale;
      const x2 = (cRect.left - stageRect.left + cRect.width / 2) / scale;
      const y2 = (cRect.top - stageRect.top) / scale;
      const midY = y1 + (y2 - y1) * 0.5;

      const colorCode = childCard.getAttribute("data-accent") || "";
      const stroke = accentMap[colorCode] || "var(--connector-color)";

      const d = "M " + x1.toFixed(1) + " " + y1.toFixed(1) +
                " L " + x1.toFixed(1) + " " + midY.toFixed(1) +
                " L " + x2.toFixed(1) + " " + midY.toFixed(1) +
                " L " + x2.toFixed(1) + " " + y2.toFixed(1);
      pathsHtml += '<path d="' + d + '" fill="none" stroke="' + stroke + '" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>';
      pathsHtml += '<circle cx="' + x2.toFixed(1) + '" cy="' + y2.toFixed(1) + '" r="3.2" fill="' + stroke + '"/>';
    });

    svgOverlay.innerHTML = pathsHtml;
  }

  if (treeStage && svgOverlay) {
    window.addEventListener("load", drawTreeConnectors);
    window.addEventListener("resize", drawTreeConnectors);
    setTimeout(drawTreeConnectors, 60);

    let zoom = 1;
    const zoomInBtn = document.getElementById("tree-zoom-in");
    const zoomOutBtn = document.getElementById("tree-zoom-out");
    const zoomResetBtn = document.getElementById("tree-zoom-reset");

    function applyZoom(newZoom) {
      zoom = Math.max(0.5, Math.min(1.5, newZoom));
      treeStage.setAttribute("data-zoom", zoom.toString());
      treeStage.style.transform = "scale(" + zoom + ")";
      drawTreeConnectors();
    }

    if (zoomInBtn) zoomInBtn.addEventListener("click", function () { applyZoom(zoom + 0.12); });
    if (zoomOutBtn) zoomOutBtn.addEventListener("click", function () { applyZoom(zoom - 0.12); });
    if (zoomResetBtn) zoomResetBtn.addEventListener("click", function () { applyZoom(1); });
  }
})();
"""
    with open(os.path.join(assets_dir, "app.js"), "w", encoding="utf-8") as f:
        f.write(app_js)


def generate_home_page(ds):
    people = ds["people"]
    trees = ds["trees"]
    families = ds["families"]
    mdb_rows = ds["mdb_rows"]

    body = f"""
    <section class="hero-banner">
      <div class="hero-content">
        <span class="badge" style="background:rgba(255,255,255,0.18);color:#fff;border-color:rgba(255,255,255,0.3);margin-bottom:0.65rem;">Est. July 2000 · Modernized Edition</span>
        <h1>Welcome to the Muir Family Tree</h1>
        <p>Originally created as a 70th birthday present for <strong>Richard Francis Muir</strong> (25th July 1930 – 2019) from his years of genealogical research, and suggested by Lindsey Muir. Explore 19 generations of family history from 15th-century Scotland to the present day.</p>
        <div class="hero-actions">
          <a href="tree/00000282.html" class="btn btn-primary" style="background:#d99b26;border-color:#d99b26;">Start at R. F. Muir's Family Tree →</a>
          <a href="tree/explorer.html" class="btn" style="background:rgba(255,255,255,0.14);color:#fff;border-color:rgba(255,255,255,0.35);">Interactive Tree Explorer</a>
          <a href="exports/index.html" class="btn" style="background:rgba(255,255,255,0.14);color:#fff;border-color:rgba(255,255,255,0.35);">Excel, XML &amp; GEDCOM Exports</a>
        </div>
      </div>
      <div style="text-align:center;">
        <img src="images/muir_family.gif" alt="Muir Family Crest - Duris Non Frangor" class="hero-crest-img">
      </div>
    </section>

    <section class="stat-strip">
      <div class="stat-card">
        <span class="stat-num">{len(people)}</span>
        <span class="stat-label">Individuals with Profile Pages</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{len(trees)}</span>
        <span class="stat-label">3-Generation Family Trees</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{len(families)}</span>
        <span class="stat-label">Marriages &amp; Family Units</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{len(mdb_rows)}</span>
        <span class="stat-label">Access DB Ancestor Records</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">1430–2021</span>
        <span class="stat-label">19 Generations Mapped</span>
      </div>
    </section>

    <div class="grid-2">
      <div class="card">
        <h2>Main Family Branches</h2>
        <p style="color:var(--text-muted);font-size:0.92rem;">Select a family line below to view its earliest 3-generation family tree or explore key ancestors:</p>
        <div class="family-mini-grid" style="margin-top:1rem;">
          <a href="tree/00000262.html" class="mini-person-card ancestor">
            <strong>MUIR Family Line</strong>
            <span>From John Muir (d. 1596, Plewlands) to R. F. Muir (1930–2019)</span>
          </a>
          <a href="tree/00000385.html" class="mini-person-card ancestor">
            <strong>STEUART / STUART Line</strong>
            <span>From King James II of Scotland (1430–1460) &amp; Mary of Gueldres</span>
          </a>
          <a href="tree/00000403.html" class="mini-person-card ancestor">
            <strong>ANGELO (Tremamando)</strong>
            <span>From Anthony Angelo Malevolti Tremamando (1747–1829)</span>
          </a>
          <a href="tree/00000448.html" class="mini-person-card ancestor">
            <strong>VAN CORTLANDT Line</strong>
            <span>From Oloff Stevense van Cortlandt (1600–1684, New Amsterdam)</span>
          </a>
          <a href="tree/00000495.html" class="mini-person-card ancestor">
            <strong>WHITEWAY Family Line</strong>
            <span>From Richard Whiteway (d. 1565, Devon) to Logie Elizabeth Whiteway</span>
          </a>
          <a href="tree/00000118.html" class="mini-person-card ancestor">
            <strong>ENDACOTT Family Line</strong>
            <span>From John Endacott of Ideford, Devon (d. 1691)</span>
          </a>
          <a href="tree/00000532.html" class="mini-person-card ancestor">
            <strong>WHITFIELD Family Line</strong>
            <span>From John Whitfield (1721–1792) to Evelyn Mary Whitfield</span>
          </a>
          <a href="people/00000148.html" class="mini-person-card ancestor">
            <strong>HALL &amp; MICHELL (Bahamas)</strong>
            <span>William Henry Hall (1817–1891) &amp; Margaret Michell (1815–1885)</span>
          </a>
        </div>
      </div>

      <div class="card">
        <h2>Explore the Archive</h2>
        <ul style="line-height:1.9;padding-left:1.2rem;">
          <li><a href="misc/welcome.html"><strong>Welcome</strong></a> — Introduction to the family tree project.</li>
          <li><a href="misc/history.html"><strong>History of this site</strong></a> — Chronological log of updates from 2000–2001.</li>
          <li><a href="misc/plans.html"><strong>Work in progress</strong></a> — Original plans and reader contributions.</li>
          <li><a href="misc/about.html"><strong>About the family trees</strong></a> — How the 3-generation trees and generation numbers work.</li>
          <li><a href="tree/00000282.html"><strong>My Father's &amp; My Family Tree</strong></a> — Start at Generation 0 (Richard Francis Muir &amp; Christine Mary Gosling).</li>
          <li><a href="misc/map.html"><strong>Map of the Family Trees</strong></a> — Visual grid of all family trees across Generations 14 to 0.</li>
          <li><a href="tree/explorer.html"><strong>Interactive Family Tree Explorer</strong></a> — Pan, zoom, and trace ancestors or descendants dynamically.</li>
          <li><a href="people/indexall.html"><strong>Alphabetical Index of All {len(people)} People</strong></a> — Searchable directory where every person has their own profile page.</li>
          <li><a href="people/index.html"><strong>Index of Direct Ancestors</strong></a> — Ordered by generation and Ahnentafel reference number (<code>:Ref/Level:</code>).</li>
          <li><a href="angelos/angelos.html"><strong>The Angelos in Britain &amp; India</strong></a> — Letters, biographies, and Helena Angelo's 1857 Cawnpore diary.</li>
          <li><a href="notes/index.html"><strong>Genealogy Course Notes</strong></a> — 15 reference guides prepared by R. F. Muir for his genealogy course.</li>
          <li><a href="exports/index.html"><strong>Data &amp; GEDCOM Exports</strong></a> — Download Excel (<code>.xlsx</code>), XML, JSON, CSV, and Ancestry.co.uk GEDCOM (<code>.ged</code>) files.</li>
        </ul>
      </div>
    </div>
    """
    html_out = page_shell("Home", body, rel_root=".", active_nav="home")
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)


def render_person_segment_html(seg, people):
    pid = seg.get("pid")
    lines = seg.get("lines", [])
    up_tree = seg.get("up_tree")
    notes = seg.get("notes", [])
    has_issue = seg.get("has_issue", False)
    issue_text = seg.get("issue_text", "-- Issue")
    order = seg.get("marriage_order")

    parts = []
    if up_tree:
        parts.append(f'<a href="{up_tree}.html" class="tree-nav-btn" title="Go up a generation">↑ Prev Gen Tree</a>')

    order_prefix = f'<span class="badge" style="padding:0 0.35rem;font-size:0.68rem;">({order})</span> ' if order else ""

    # Separate name lines from dates/notes in parentheses
    name_lines = []
    meta_lines = []
    for l in lines:
        l_clean = re.sub(r"^\([123]\)\s*", "", l).strip()
        if not l_clean:
            continue
        if (l_clean.startswith("(") and l_clean.endswith(")") and any(c.isdigit() or c == "?" for c in l_clean)) or l_clean.lower().startswith("div"):
            meta_lines.append(l_clean)
        else:
            name_lines.append(l_clean)

    name_str = " ".join(name_lines) if name_lines else seg.get("text", "Unknown")
    meta_str = " ".join(meta_lines)

    if pid and pid in people:
        p = people[pid]
        da_star = ' <span title="Direct Ancestor" style="color:var(--accent);">★</span>' if p["is_direct_ancestor"] else ""
        parts.append(
            f'{order_prefix}<a href="../people/{pid}.html" class="person-block-name">{esc(name_str)}{da_star}</a>'
        )
    else:
        parts.append(f'{order_prefix}<span class="person-block-name" style="color:var(--text-muted);">{esc(name_str)}</span>')

    if meta_str:
        parts.append(f'<span class="person-block-dates">{esc(meta_str)}</span>')

    if has_issue:
        parts.append(f'<span class="issue-pill">{esc(issue_text)}</span>')

    for n in notes:
        n_num = n.replace("note", "")
        parts.append(f' <a href="../misc/notes.html#{n}" class="note-pill">Note {n_num}</a>')

    return "\n".join(parts)


def generate_tree_pages(ds):
    tree_dir = os.path.join(DOCS_DIR, "tree")
    os.makedirs(tree_dir, exist_ok=True)
    people = ds["people"]
    trees = ds["trees"]
    notes_map = ds["notes_map"]

    for tid, tdata in trees.items():
        title = tdata["title"]
        doc_notes = tdata["doc_notes"]
        has_angelos = tdata["has_angelos_link"]

        notes_banner = ""
        if doc_notes:
            note_items = []
            for n in doc_notes:
                n_num = n.replace("note", "")
                n_txt = notes_map.get(n, "")
                note_items.append(f'<li><strong><a href="../misc/notes.html#{n}">Note {n_num}</a>:</strong> {esc(n_txt)}</li>')
            notes_banner = f"""
            <div class="card" style="background:var(--accent-soft);border-color:var(--accent);padding:0.85rem 1.15rem;margin-bottom:1rem;">
              <strong style="color:var(--accent);">Document Notes:</strong>
              <ul style="margin:0.35rem 0 0;padding-left:1.25rem;font-size:0.88rem;">
                {"".join(note_items)}
              </ul>
            </div>
            """

        rows_html = []
        for grow in tdata["rows"]:
            gen_num = grow["gen"]
            nodes_html = []
            for node in grow["nodes"]:
                nid = node["node_id"]
                pnode = node.get("parent_node_id") or ""
                accent = node.get("color") or "#8080FF"
                primary_html = render_person_segment_html(node["primary"], people)

                spouses_html = []
                for sp in node["spouses"]:
                    sp_block = render_person_segment_html(sp, people)
                    spouses_html.append(f'<div class="spouse-divider">m.</div>\n{sp_block}')

                down_btn = ""
                if node.get("down_tree"):
                    dn_tid = node["down_tree"]
                    down_btn = f'\n<a href="{dn_tid}.html" class="tree-nav-btn down" title="Go down a generation">↓ Next Gen Tree</a>'

                card_html = f"""
                <div class="tree-node-card" id="{nid}" data-parent-node="{pnode}" data-accent="{accent}">
                  {primary_html}
                  {"".join(spouses_html)}
                  {down_btn}
                </div>
                """
                nodes_html.append(card_html)

            rows_html.append(
                f"""
              <div class="tree-gen-row">
                <div class="tree-gen-badge">
                  <span>Gen</span>
                  <strong>{esc(gen_num)}</strong>
                </div>
                <div class="tree-row-nodes">
                  {"".join(nodes_html)}
                </div>
              </div>
            """
            )

        angelos_btn = (
            '<a href="../angelos/angelos.html" class="btn">The Angelos Index</a>'
            if has_angelos
            else ""
        )
        root_person_btn = (
            f'<a href="../people/{tid}.html" class="btn">Root Person Profile</a>'
            if tid in people
            else ""
        )

        body = f"""
        <div class="page-header">
          <div>
            <div class="breadcrumbs">
              <a href="../index.html">Home</a> · <a href="../misc/map.html">Tree Map</a> · Family Tree {esc(tid)}
            </div>
            <h1>{esc(title)}</h1>
          </div>
          <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
            {root_person_btn}
            <a href="explorer.html?root={esc(tid)}" class="btn">Open in Interactive Explorer</a>
            {angelos_btn}
          </div>
        </div>

        {notes_banner}

        <div class="tree-toolbar">
          <div style="font-size:0.86rem;color:var(--text-muted);">
            <strong>Tip:</strong> Click any person's name to view their full biography &amp; immediate family. Lines connect parents to their children.
          </div>
          <div style="display:flex;gap:0.4rem;">
            <button type="button" id="tree-zoom-out" class="btn" style="padding:0.3rem 0.65rem;">− Zoom Out</button>
            <button type="button" id="tree-zoom-reset" class="btn" style="padding:0.3rem 0.65rem;">100%</button>
            <button type="button" id="tree-zoom-in" class="btn" style="padding:0.3rem 0.65rem;">+ Zoom In</button>
          </div>
        </div>

        <div class="tree-viewport">
          <div class="tree-stage" id="tree-stage" data-zoom="1">
            <svg class="tree-connectors-svg" id="tree-connectors-svg"></svg>
            {"".join(rows_html)}
          </div>
        </div>
        """
        out_html = page_shell(f"Tree: {title}", body, rel_root="..", active_nav="map")
        with open(os.path.join(tree_dir, f"{tid}.html"), "w", encoding="utf-8") as f:
            f.write(out_html)


def generate_interactive_explorer(ds):
    tree_dir = os.path.join(DOCS_DIR, "tree")
    os.makedirs(tree_dir, exist_ok=True)

    body = """
    <div class="page-header">
      <div>
        <div class="breadcrumbs"><a href="../index.html">Home</a> · Interactive Family Tree Explorer</div>
        <h1>Interactive Family Tree Explorer</h1>
        <p style="color:var(--text-muted);margin:0;">Dynamically trace ancestors (pedigree) or descendants across all 19 generations.</p>
      </div>
    </div>

    <div class="tree-toolbar" style="gap:0.75rem;">
      <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
        <label for="explorer-root-select" style="font-weight:600;font-size:0.88rem;">Root Person:</label>
        <select id="explorer-root-select" class="search-input" style="width:280px;border-radius:6px;"></select>

        <label for="explorer-mode-select" style="font-weight:600;font-size:0.88rem;margin-left:0.5rem;">View Mode:</label>
        <select id="explorer-mode-select" class="search-input" style="width:190px;border-radius:6px;">
          <option value="ancestors">Pedigree (Ancestors ↑)</option>
          <option value="descendants">Descendants (Issue ↓)</option>
        </select>

        <label for="explorer-depth-select" style="font-weight:600;font-size:0.88rem;margin-left:0.5rem;">Generations:</label>
        <select id="explorer-depth-select" class="search-input" style="width:110px;border-radius:6px;">
          <option value="3">3 Gens</option>
          <option value="4" selected>4 Gens</option>
          <option value="5">5 Gens</option>
          <option value="6">6 Gens</option>
          <option value="8">8 Gens</option>
        </select>
      </div>
      <div style="display:flex;gap:0.4rem;flex-wrap:wrap;">
        <button type="button" class="btn" data-preset="00000282" data-mode="ancestors">R. F. Muir Ancestors</button>
        <button type="button" class="btn" data-preset="00000385" data-mode="descendants">King James II Descendants</button>
        <button type="button" class="btn" data-preset="00000448" data-mode="descendants">Van Cortlandt Descendants</button>
        <button type="button" class="btn" data-preset="00000403" data-mode="descendants">Angelo Descendants</button>
      </div>
    </div>

    <div class="tree-viewport" id="explorer-viewport">
      <div class="tree-stage" id="tree-stage" data-zoom="1">
        <svg class="tree-connectors-svg" id="tree-connectors-svg"></svg>
        <div id="explorer-rows-container" style="display:flex;flex-direction:column;gap:4rem;"></div>
      </div>
    </div>

    <script>
    (function() {
      window.addEventListener("DOMContentLoaded", function() {
        if (!window.FAMILY_DATA) return;
        const people = window.FAMILY_DATA.people;
        const rootSelect = document.getElementById("explorer-root-select");
        const modeSelect = document.getElementById("explorer-mode-select");
        const depthSelect = document.getElementById("explorer-depth-select");
        const container = document.getElementById("explorer-rows-container");
        const stage = document.getElementById("tree-stage");
        const svg = document.getElementById("tree-connectors-svg");

        // Populate dropdown with key people & all people with connections
        const allList = Object.values(people).filter(function(p) {
          return p.p.length > 0 || p.c.length > 0 || p.da;
        }).sort(function(a, b) {
          if (a.da !== b.da) return a.da ? -1 : 1;
          return a.sn.localeCompare(b.sn) || a.cn.localeCompare(b.cn);
        });

        rootSelect.innerHTML = allList.map(function(p) {
          const star = p.da ? "★ " : "";
          return '<option value="' + p.id + '">' + star + p.sn + ', ' + p.cn + ' (' + p.dates + ') [Gen ' + p.gen + ']</option>';
        }).join("");

        const params = new URLSearchParams(window.location.search);
        const initialRoot = params.get("root") && people[params.get("root")] ? params.get("root") : "00000282";
        const initialMode = params.get("mode") || (people[initialRoot] && people[initialRoot].c.length > 0 && people[initialRoot].p.length === 0 ? "descendants" : "ancestors");
        rootSelect.value = initialRoot;
        modeSelect.value = initialMode;

        function renderExplorer() {
          const rootId = rootSelect.value;
          const mode = modeSelect.value;
          const maxDepth = parseInt(depthSelect.value, 10) || 4;
          if (!people[rootId]) return;

          const levels = [];
          const seen = new Set([rootId]);
          levels.push([{ pid: rootId, parentNodeId: null }]);

          for (let d = 1; d < maxDepth; d++) {
            const prevLevel = levels[d - 1];
            const nextLevel = [];
            prevLevel.forEach(function(item) {
              const p = people[item.pid];
              if (!p) return;
              const nodeDomId = "exp_" + (d - 1) + "_" + item.pid;
              const relIds = mode === "ancestors" ? p.p : p.c;
              relIds.forEach(function(rid) {
                if (!seen.has(rid) && people[rid]) {
                  seen.add(rid);
                  nextLevel.push({ pid: rid, parentNodeId: nodeDomId });
                }
              });
            });
            if (nextLevel.length === 0) break;
            levels.push(nextLevel);
          }

          // If mode is ancestors, display oldest generation at top and root at bottom!
          const displayLevels = mode === "ancestors" ? levels.slice().reverse() : levels;

          let html = "";
          displayLevels.forEach(function(lvl, rowIdx) {
            const origDepth = mode === "ancestors" ? (levels.length - 1 - rowIdx) : rowIdx;
            const sampleP = people[lvl[0].pid];
            const genLabel = sampleP ? sampleP.gen : "";
            const cardsHtml = lvl.map(function(item) {
              const p = people[item.pid];
              const domId = "exp_" + origDepth + "_" + item.pid;
              let parentAttr = "";
              if (mode === "descendants" && item.parentNodeId) {
                parentAttr = ' data-parent-node="' + item.parentNodeId + '"';
              }
              const star = p.da ? ' <span style="color:var(--accent);">★</span>' : '';
              const spNames = (p.s || []).map(function(sid) {
                return people[sid] ? '<div class="spouse-divider">m. <a href="../people/' + sid + '.html">' + people[sid].name + '</a></div>' : '';
              }).join("");
              const treeBtn = p.tid ? '<a href="' + p.tid + '.html" class="tree-nav-btn down">View 3-Gen Tree</a>' : '';
              return '<div class="tree-node-card" id="' + domId + '"' + parentAttr + ' data-child-target="' + (item.parentNodeId || "") + '" data-accent="' + (p.da ? "#FFFF99" : "#8080FF") + '">' +
                '<button type="button" class="tree-nav-btn exp-recenter" data-pid="' + p.id + '">⊕ Focus Tree Here</button>' +
                '<a href="../people/' + p.id + '.html" class="person-block-name">' + p.name + star + '</a>' +
                '<span class="person-block-dates">' + (p.dates || "") + '</span>' +
                (p.prof ? '<span class="issue-pill">' + p.prof.slice(0, 38) + '</span>' : '') +
                spNames +
                treeBtn +
              '</div>';
            }).join("");

            html += '<div class="tree-gen-row">' +
              '<div class="tree-gen-badge"><span>Gen</span><strong>' + genLabel + '</strong></div>' +
              '<div class="tree-row-nodes">' + cardsHtml + '</div>' +
            '</div>';
          });

          container.innerHTML = html;

          // If mode is ancestors, wire data-parent-node from upper row (parents) to lower row (child)
          if (mode === "ancestors") {
            container.querySelectorAll(".tree-node-card").forEach(function(card) {
              const childTarget = card.getAttribute("data-child-target");
              if (childTarget) {
                // card is a parent of childTarget; in top-down SVG drawing, child has data-parent-node
                card.removeAttribute("data-parent-node");
              }
            });
          }

          // Draw SVG connectors for explorer
          setTimeout(function() {
            const stageRect = stage.getBoundingClientRect();
            const w = stage.scrollWidth;
            const h = stage.scrollHeight;
            svg.setAttribute("width", w);
            svg.setAttribute("height", h);
            svg.setAttribute("viewBox", "0 0 " + w + " " + h);
            let paths = "";
            container.querySelectorAll(".tree-node-card").forEach(function(card) {
              const pId = mode === "descendants" ? card.getAttribute("data-parent-node") : card.id;
              const cId = mode === "descendants" ? card.id : card.getAttribute("data-child-target");
              if (!pId || !cId) return;
              const pEl = document.getElementById(pId);
              const cEl = document.getElementById(cId);
              if (!pEl || !cEl) return;
              const pRect = pEl.getBoundingClientRect();
              const cRect = cEl.getBoundingClientRect();
              const x1 = pRect.left - stageRect.left + pRect.width / 2;
              const y1 = pRect.bottom - stageRect.top;
              const x2 = cRect.left - stageRect.left + cRect.width / 2;
              const y2 = cRect.top - stageRect.top;
              const midY = y1 + (y2 - y1) * 0.5;
              const d = "M " + x1.toFixed(1) + " " + y1.toFixed(1) + " L " + x1.toFixed(1) + " " + midY.toFixed(1) + " L " + x2.toFixed(1) + " " + midY.toFixed(1) + " L " + x2.toFixed(1) + " " + y2.toFixed(1);
              paths += '<path d="' + d + '" fill="none" stroke="var(--connector-color)" stroke-width="2.2"/>';
            });
            svg.innerHTML = paths;
          }, 30);

          container.querySelectorAll(".exp-recenter").forEach(function(btn) {
            btn.addEventListener("click", function() {
              rootSelect.value = btn.getAttribute("data-pid");
              renderExplorer();
            });
          });
        }

        rootSelect.addEventListener("change", renderExplorer);
        modeSelect.addEventListener("change", renderExplorer);
        depthSelect.addEventListener("change", renderExplorer);

        document.querySelectorAll("[data-preset]").forEach(function(btn) {
          btn.addEventListener("click", function() {
            rootSelect.value = btn.getAttribute("data-preset");
            modeSelect.value = btn.getAttribute("data-mode");
            renderExplorer();
          });
        });

        renderExplorer();
      });
    })();
    </script>
    """
    out_html = page_shell("Interactive Family Tree Explorer", body, rel_root="..", active_nav="explorer")
    with open(os.path.join(tree_dir, "explorer.html"), "w", encoding="utf-8") as f:
        f.write(out_html)


def generate_person_pages(ds):
    people_dir = os.path.join(DOCS_DIR, "people")
    os.makedirs(people_dir, exist_ok=True)
    people = ds["people"]
    trees = ds["trees"]

    def render_mini_cards(pid_list, empty_msg):
        if not pid_list:
            return f'<p style="color:var(--text-muted);font-size:0.9rem;margin:0;">{empty_msg}</p>'
        cards = []
        for xid in pid_list:
            xp = people.get(xid)
            if not xp:
                continue
            cls = "mini-person-card ancestor" if xp["is_direct_ancestor"] else "mini-person-card"
            star = " ★" if xp["is_direct_ancestor"] else ""
            cards.append(
                f"""<a href="{xid}.html" class="{cls}">
                  <strong>{esc(format_person_display_name(xp))}{star}</strong>
                  <span>{esc(xp['dates'])} · Gen {esc(xp['generation'])}</span>
                </a>"""
            )
        return f'<div class="family-mini-grid">{"".join(cards)}</div>'

    for pid, p in people.items():
        disp_name = format_person_display_name(p)
        badges = [f'<span class="badge">Generation {esc(p["generation"])}</span>']
        if p["is_direct_ancestor"]:
            badges.append('<span class="badge badge-ancestor">★ Direct Ancestor</span>')
        if p["ahnentafel"]:
            badges.append(f'<span class="badge badge-primary">Ahnentafel {esc(p["ahnentafel"])}</span>')

        tree_buttons = []
        for tid in p["trees_appeared"]:
            t_title = trees.get(tid, {}).get("title", tid)
            tree_buttons.append(
                f'<a href="../tree/{tid}.html" class="btn btn-primary">View Family Tree ({esc(t_title)})</a>'
            )
        if not tree_buttons and p["tree_id"]:
            tree_buttons.append(
                f'<a href="../tree/{p["tree_id"]}.html" class="btn btn-primary">View Family Tree</a>'
            )

        fields = [
            ("Surname", p["surname"]),
            ("Given Name(s)", p["cname"] or "—"),
            ("Generation", p["generation"]),
            ("Direct Ancestor", f"Yes ({p['ahnentafel']})" if p["is_direct_ancestor"] and p["ahnentafel"] else ("Yes (**)" if p["is_direct_ancestor"] else "No")),
            ("Birth", p["birth"] or "—"),
            ("Death", p["death"] or "—"),
            ("Marriage", p["marriage"] or "—"),
            ("Profession / Occupation", p["profession"] or "—"),
            ("Notes", p["notes"] or "—"),
        ]
        rows_html = "\n".join(
            f"<tr><th style='width:28%;'>{esc(k)}</th><td>{esc(v)}</td></tr>"
            for k, v in fields
        )

        body = f"""
        <div class="page-header">
          <div>
            <div class="breadcrumbs">
              <a href="../index.html">Home</a> · <a href="indexall.html">All People</a> · {esc(disp_name)}
            </div>
            <h1>{esc(disp_name)} <span style="font-weight:400;color:var(--text-muted);font-size:1.35rem;">({esc(p['dates'])})</span></h1>
            <div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.4rem;">
              {"".join(badges)}
            </div>
          </div>
          <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
            {"".join(tree_buttons)}
            <a href="../tree/explorer.html?root={esc(pid)}" class="btn">Interactive Explorer</a>
          </div>
        </div>

        <div class="grid-2">
          <div class="card">
            <h2>Biographical Information</h2>
            <div class="data-table-wrapper">
              <table class="data-table">
                <tbody>
                  {rows_html}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <div class="card">
              <h3>Parents ({len(p['parents'])})</h3>
              {render_mini_cards(p['parents'], "No parents recorded in this archive.")}
            </div>

            <div class="card">
              <h3>Spouse(s) ({len(p['spouses'])})</h3>
              {render_mini_cards(p['spouses'], "No spouse recorded.")}
            </div>

            <div class="card">
              <h3>Issue / Children ({len(p['children'])})</h3>
              {render_mini_cards(p['children'], "No children recorded on this branch.")}
            </div>

            <div class="card">
              <h3>Siblings ({len(p['siblings'])})</h3>
              {render_mini_cards(p['siblings'], "No siblings recorded.")}
            </div>
          </div>
        </div>
        """
        out_html = page_shell(disp_name, body, rel_root="..", active_nav="people")
        with open(os.path.join(people_dir, f"{pid}.html"), "w", encoding="utf-8") as f:
            f.write(out_html)

    # Also write people/notmapped.html for backward compatibility
    notmapped_body = """
    <div class="card">
      <h1>Family Tree Not Mapped Yet</h1>
      <p>This branch had not yet been mapped into a separate 3-generation chart on the original site. You can explore all connected individuals in the <a href="indexall.html">All People Index</a> or <a href="../tree/explorer.html">Interactive Tree Explorer</a>.</p>
    </div>
    """
    with open(os.path.join(people_dir, "notmapped.html"), "w", encoding="utf-8") as f:
        f.write(page_shell("Family Tree Not Mapped Yet", notmapped_body, rel_root="..", active_nav="people"))


def generate_index_pages(ds):
    people_dir = os.path.join(DOCS_DIR, "people")
    os.makedirs(people_dir, exist_ok=True)
    people = ds["people"]

    # 1. Direct ancestors index (people/index.html)
    direct_rows = []
    for ref_txt, pid, dates_txt in ds["direct_index_order"]:
        p = people.get(pid)
        if not p:
            continue
        tid = p["tree_id"]
        tree_link = f'<a href="../tree/{tid}.html" class="btn" style="padding:0.2rem 0.55rem;font-size:0.78rem;">Family Tree</a>' if tid else "—"
        direct_rows.append(
            f"""<tr>
              <td><code>{esc(ref_txt)}</code></td>
              <td><strong><a href="{pid}.html">{esc(p['surname'])}, {esc(p['cname'])}</a></strong></td>
              <td>{esc(p['generation'])}</td>
              <td>{esc(dates_txt)}</td>
              <td>{esc(p['profession'])}</td>
              <td>{tree_link}</td>
            </tr>"""
        )

    direct_body = f"""
    <div class="page-header">
      <div>
        <div class="breadcrumbs"><a href="../index.html">Home</a> · Index of Direct Ancestors</div>
        <h1>Index of Direct Ancestors</h1>
        <p style="color:var(--text-muted);margin:0;">Ordered by generation number and Ahnentafel reference (<code>:Ref/Level:</code>), combining records from the website and <code>Docs/family.mdb</code>.</p>
      </div>
      <div>
        <a href="indexall.html" class="btn">View All {len(people)} People →</a>
      </div>
    </div>

    <div class="data-table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Reference</th>
            <th>Name</th>
            <th>Gen</th>
            <th>Dates</th>
            <th>Profession / Details</th>
            <th>Family Tree</th>
          </tr>
        </thead>
        <tbody>
          {"".join(direct_rows)}
        </tbody>
      </table>
    </div>
    """
    with open(os.path.join(people_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page_shell("Index of Direct Ancestors", direct_body, rel_root="..", active_nav="ancestors"))

    # 2. Alphabetical index pages: indexall.html + indexa.html..indexz.html
    active_letters = sorted(
        set(
            p["surname"][0].upper()
            for p in people.values()
            if p["surname"] and p["surname"][0].isalpha()
        )
    )

    def build_alpha_bar(current_letter=None):
        pills = [
            f'<a href="indexall.html" class="alpha-pill{" active" if current_letter is None else ""}">All ({len(people)})</a>'
        ]
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if ch in active_letters:
                cls = "alpha-pill active" if current_letter == ch else "alpha-pill"
                pills.append(f'<a href="index{ch.lower()}.html" class="{cls}">{ch}</a>')
            else:
                pills.append(f'<span class="alpha-pill disabled">{ch}</span>')
        return f'<div class="alpha-bar">{"".join(pills)}</div>'

    sorted_pids = sorted(
        people.keys(),
        key=lambda pid: (
            0 if people[pid]["surname"] != "??" else 1,
            people[pid]["surname"].upper(),
            people[pid]["cname"].upper(),
            pid,
        ),
    )

    def render_people_table(pids):
        trs = []
        for pid in pids:
            p = people[pid]
            star = ' <span class="badge badge-ancestor">★ Direct</span>' if p["is_direct_ancestor"] else ""
            tid = p["tree_id"]
            t_cell = f'<a href="../tree/{tid}.html">Family Tree ({tid})</a>' if tid else "—"
            trs.append(
                f"""<tr data-da="{'1' if p['is_direct_ancestor'] else '0'}">
                  <td><strong><a href="{pid}.html">{esc(p['surname'])}, {esc(p['cname'])}</a></strong>{star}</td>
                  <td>{esc(p['dates'])}</td>
                  <td>{esc(p['generation'])}</td>
                  <td>{esc(p['profession'])}</td>
                  <td>{t_cell}</td>
                </tr>"""
            )
        return f"""
        <div class="data-table-wrapper">
          <table class="data-table" id="people-directory-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Dates</th>
                <th>Gen</th>
                <th>Profession</th>
                <th>Family Tree</th>
              </tr>
            </thead>
            <tbody>
              {"".join(trs)}
            </tbody>
          </table>
        </div>
        """

    indexall_body = f"""
    <div class="page-header">
      <div>
        <div class="breadcrumbs"><a href="../index.html">Home</a> · Index of All People</div>
        <h1>Index of All People ({len(people)})</h1>
        <p style="color:var(--text-muted);margin:0;">Every person on the family trees now has their own dedicated profile page with full relationship links.</p>
      </div>
      <div>
        <a href="index.html" class="btn">Direct Ancestors Only</a>
      </div>
    </div>

    {build_alpha_bar(None)}

    <div class="tree-toolbar" style="margin-bottom:1rem;">
      <input type="search" id="table-filter-input" class="search-input" style="max-width:360px;" placeholder="Filter table by name, year, or profession...">
      <label style="font-size:0.88rem;display:flex;align-items:center;gap:0.4rem;cursor:pointer;">
        <input type="checkbox" id="filter-direct-only"> Show Direct Ancestors (★) only
      </label>
    </div>

    {render_people_table(sorted_pids)}

    <script>
    (function() {{
      const inp = document.getElementById("table-filter-input");
      const cb = document.getElementById("filter-direct-only");
      const rows = document.querySelectorAll("#people-directory-table tbody tr");
      function filterRows() {{
        const q = (inp.value || "").toLowerCase().trim();
        const daOnly = cb.checked;
        rows.forEach(function(r) {{
          const matchText = !q || r.textContent.toLowerCase().indexOf(q) !== -1;
          const matchDa = !daOnly || r.getAttribute("data-da") === "1";
          r.style.display = (matchText && matchDa) ? "" : "none";
        }});
      }}
      if (inp) inp.addEventListener("input", filterRows);
      if (cb) cb.addEventListener("change", filterRows);
    }})();
    </script>
    """
    with open(os.path.join(people_dir, "indexall.html"), "w", encoding="utf-8") as f:
        f.write(page_shell("Index of All People", indexall_body, rel_root="..", active_nav="people"))

    for ch in active_letters:
        letter_pids = [
            pid for pid in sorted_pids if people[pid]["surname"] and people[pid]["surname"][0].upper() == ch
        ]
        letter_body = f"""
        <div class="page-header">
          <div>
            <div class="breadcrumbs"><a href="../index.html">Home</a> · <a href="indexall.html">All People</a> · Letter {ch}</div>
            <h1>People — Surname Starting with "{ch}" ({len(letter_pids)})</h1>
          </div>
          <div>
            <a href="indexall.html" class="btn">All Letters ({len(people)})</a>
          </div>
        </div>
        {build_alpha_bar(ch)}
        {render_people_table(letter_pids)}
        """
        with open(os.path.join(people_dir, f"index{ch.lower()}.html"), "w", encoding="utf-8") as f:
            f.write(page_shell(f"People Index - {ch}", letter_body, rel_root="..", active_nav="people"))


def generate_exports_page(ds):
    docs_exports_dir = os.path.join(DOCS_DIR, "exports")
    os.makedirs(docs_exports_dir, exist_ok=True)

    # Copy all export files from exports/ into docs/exports/
    for fname in os.listdir(EXPORTS_DIR):
        src = os.path.join(EXPORTS_DIR, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(docs_exports_dir, fname))

    body = f"""
    <div class="page-header">
      <div>
        <div class="breadcrumbs"><a href="../index.html">Home</a> · Data &amp; GEDCOM Exports</div>
        <h1>Extracted Data &amp; Genealogy Exports</h1>
        <p style="color:var(--text-muted);margin:0;">All relationship data, biographical records, and the legacy Microsoft Access 97 database (<code>Docs/family.mdb</code>) extracted into modern open formats.</p>
      </div>
    </div>

    <div class="grid-2">
      <div class="card" style="border-top:4px solid var(--accent);">
        <span class="badge badge-ancestor" style="margin-bottom:0.5rem;">Recommended for Spreadsheets</span>
        <h2>Excel Workbook (<code>.xlsx</code>) &amp; CSVs</h2>
        <p>Multi-sheet Microsoft Excel workbook containing 4 worksheets: <strong>People ({len(ds['people'])})</strong>, <strong>Families &amp; Marriages ({len(ds['families'])})</strong>, <strong>Relationships</strong>, and the decoded <strong>Access DB (Family Table, {len(ds['mdb_rows'])} records)</strong>.</p>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:1rem;">
          <a href="muir_family_tree.xlsx" class="btn btn-primary" download>⬇ Download Excel Workbook (.xlsx)</a>
          <a href="people.csv" class="btn" download>people.csv</a>
          <a href="families.csv" class="btn" download>families.csv</a>
          <a href="relationships.csv" class="btn" download>relationships.csv</a>
          <a href="access_family_table.csv" class="btn" download>access_family_table.csv</a>
        </div>
      </div>

      <div class="card" style="border-top:4px solid var(--primary);">
        <span class="badge badge-primary" style="margin-bottom:0.5rem;">Ancestry.co.uk / FindMyPast / MyHeritage</span>
        <h2>Standard GEDCOM 5.5.1 (<code>.ged</code>)</h2>
        <p>Complete Lineage-Linked GEDCOM 5.5.1 file containing all {len(ds['people'])} individuals (<code>INDI</code>) and {len(ds['families'])} families (<code>FAM</code>), ready for direct upload to <strong>Ancestry.co.uk</strong> or any genealogy software.</p>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:1rem;">
          <a href="muir_family_tree.ged" class="btn btn-primary" download>⬇ Download GEDCOM (.ged) for Ancestry.co.uk</a>
        </div>
        <div style="margin-top:1rem;padding:0.75rem;background:var(--bg-subtle);border-radius:var(--radius-sm);font-size:0.85rem;">
          <strong>How to import into Ancestry.co.uk:</strong>
          <ol style="margin:0.35rem 0 0;padding-left:1.25rem;">
            <li>Sign in to <strong>Ancestry.co.uk</strong> and click <strong>Trees</strong> → <strong>Create &amp; Manage Trees</strong>.</li>
            <li>Click <strong>Upload a GEDCOM file</strong> at the bottom of the list.</li>
            <li>Select <code>muir_family_tree.ged</code> and name your tree (e.g., <em>The Muir Family Tree</em>).</li>
          </ol>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Structured XML &amp; JSON Exports</h2>
      <p>Hierarchical machine- and human-readable exports containing all person attributes, parent/spouse/child cross-references, and the raw 46-column Microsoft Access database records.</p>
      <div style="display:flex;gap:0.65rem;flex-wrap:wrap;margin-top:0.75rem;">
        <a href="family_tree.xml" class="btn" download>⬇ Download XML (family_tree.xml)</a>
        <a href="family_tree.json" class="btn" download>⬇ Download JSON (family_tree.json)</a>
      </div>
    </div>
    """
    with open(os.path.join(docs_exports_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page_shell("Data & GEDCOM Exports", body, rel_root="..", active_nav="exports"))


def convert_legacy_content_pages():
    """Converts angelos/*.html, notes/*.html, misc/*.html, and Helen.htm into modern styled UTF-8 pages."""
    subdirs = [
        ("angelos", "angelos", ".."),
        ("notes", "notes", ".."),
        ("misc", "map", ".."),
    ]
    for folder, nav_key, rel_root in subdirs:
        src_dir = os.path.join(WEBSITE_DIR, folder)
        dst_dir = os.path.join(DOCS_DIR, folder)
        os.makedirs(dst_dir, exist_ok=True)

        for fpath in sorted(glob.glob(os.path.join(src_dir, "*.html"))):
            fname = os.path.basename(fpath)
            with open(fpath, "r", encoding="cp1252", errors="replace") as f:
                raw_html = f.read()

            title_m = re.search(r"<TITLE>(.*?)</TITLE>", raw_html, re.S | re.I)
            title = html_lib.unescape(title_m.group(1).strip()) if title_m else fname

            body_m = re.search(r"<BODY[^>]*>(.*?)</BODY>", raw_html, re.S | re.I)
            inner = body_m.group(1).strip() if body_m else raw_html

            # Strip top and bottom legacy navigation lines like `<A HREF="../index.html">Home</A> - <A HREF="index.html">Index</A>`
            lines = inner.splitlines()
            cleaned_lines = []
            for idx, l in enumerate(lines):
                s = l.strip()
                if (idx < 4 or idx > len(lines) - 5) and (
                    'HREF="../index.html"' in s.upper()
                    or 'HREF="angelos.html"' in s.upper()
                    or 'HREF="index.html"' in s.upper()
                ) and "<H1" not in s.upper() and "<P" not in s.upper() and "<LI" not in s.upper():
                    continue
                cleaned_lines.append(l)
            inner_clean = "\n".join(cleaned_lines).strip()

            # Upgrade table attributes for clean CSS rendering
            if fname == "map.html":
                inner_clean = inner_clean.replace('BGCOLOR="SILVER"', 'class="map-cell"')

            breadcrumb_section = folder.capitalize()
            breadcrumb_link = (
                '<a href="angelos.html">The Angelos</a>'
                if folder == "angelos" and fname != "angelos.html"
                else (
                    '<a href="index.html">Course Notes</a>'
                    if folder == "notes" and fname != "index.html"
                    else breadcrumb_section
                )
            )

            active = "map" if fname == "map.html" else ("home" if folder == "misc" else nav_key)
            body = f"""
            <div class="breadcrumbs" style="margin-bottom:1rem;">
              <a href="../index.html">Home</a> · {breadcrumb_link} · {esc(title)}
            </div>
            <div class="card legacy-content" style="overflow-x:auto;">
              {inner_clean}
            </div>
            """
            out_html = page_shell(title, body, rel_root=rel_root, active_nav=active)
            with open(os.path.join(dst_dir, fname), "w", encoding="utf-8") as f:
                f.write(out_html)

    # Also convert website/Helen.htm -> docs/Helen.htm
    helen_src = os.path.join(WEBSITE_DIR, "Helen.htm")
    if os.path.exists(helen_src):
        with open(helen_src, "r", encoding="cp1252", errors="replace") as f:
            raw_h = f.read()
        body_m = re.search(r"<body[^>]*>(.*?)</body>", raw_h, re.S | re.I)
        inner = body_m.group(1).strip() if body_m else raw_h
        body = f'<div class="card legacy-content">{inner}</div>'
        with open(os.path.join(DOCS_DIR, "Helen.htm"), "w", encoding="utf-8") as f:
            f.write(page_shell("Helen's Updates", body, rel_root=".", active_nav="home"))

    # Copy website/images/ to docs/images/
    src_img = os.path.join(WEBSITE_DIR, "images")
    dst_img = os.path.join(DOCS_DIR, "images")
    if os.path.exists(src_img):
        shutil.copytree(src_img, dst_img, dirs_exist_ok=True)


def build_all():
    ds = build_dataset()
    export_paths = generate_all_exports(ds)
    os.makedirs(DOCS_DIR, exist_ok=True)
    write_assets(ds)
    generate_home_page(ds)
    generate_tree_pages(ds)
    generate_interactive_explorer(ds)
    generate_person_pages(ds)
    generate_index_pages(ds)
    generate_exports_page(ds)
    convert_legacy_content_pages()
    return ds, export_paths


if __name__ == "__main__":
    ds, export_paths = build_all()
    print(f"Website generated in {DOCS_DIR}")
    print(f"Total people pages: {len(ds['people'])}")
    print(f"Total tree pages: {len(ds['trees'])} + explorer.html")

