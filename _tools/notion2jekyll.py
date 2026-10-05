#!/usr/bin/env python3
"""Convert the Notion HTML exports in _sources/*.zip into Jekyll pages.

Usage:  python3 _tools/notion2jekyll.py   (needs beautifulsoup4)

Simple blocks (paragraphs, headings, lists, inline formatting) become
Markdown; Notion-only blocks (callouts, tables, databases, toggles,
columns, figures) become plain HTML with classes styled in _sass/_notion.scss.
Anything that cannot be mapped is logged to _tools/conversion-report.md.
"""
import difflib
import html
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "_sources"  # Notion export zips
CONTENT = ROOT / "content"   # editable site content (pages, _guides, _data)
SYNC = ROOT / "_tools" / "notion-sync"  # Notion versions of locked pages (see stage())

# Notion page id -> (output, slug, short nav title, order[, label])
# `label` picks a colour theme for the page (see _sass/_colors.scss).
PAGES = {
    # group 1: medical transition
    "8ac130903cbd47e6bf39ee35f45e330b": ("guide", "gender-affirming-healthcare", "Gender-affirming healthcare", 1),
    "00af3e86cb544f908b52a30623e19a07": ("guide", "transfeminine-hrt", "Transfem HRT", 2),
    "cb6a57ec1b6e40bea1a43427b2c9b4b9": ("guide", "transmasculine-hrt", "Transmasc HRT", 3, "transmasculine"),
    "b1a395e460a54e63b730da30d23cca9d": ("guide", "non-binary-transition", "Non-binary transition", 4, "non-binary"),
    "12a30fc11df480eb92ebf83a29f0e573": ("guide", "private-doctors", "Private doctors & GPs", 5),
    # group 2: social & wellbeing
    "c15ecfd42ecb4436afd0d11e836d665f": ("guide", "social-transition", "Social transition", 6),
    "df8b5db122234f66968bff4ba95b4068": ("guide", "psychological-emotional-resources", "Psychological and emotional resources", 7),
    "669ec7f5af1a41e3bee8c6b256d3e848": ("guide", "haircuts", "Haircuts", 8),
    # group 3
    "605187b8c5c548f0aa922de0ee33eddb": ("guide", "national-service", "National Service", 9),
    "e2e778405b144390a6e83155bbb7cc52": ("guide", "self-managing-transfeminine-hrt", "Self-managing transfem HRT", 10),
    "2d62a97fd5594d9aaa15fb7ffb1c2f25": ("about", "about", "About", 0),
    # side pages: not in the menu or guide lists; served under their parent guide
    "61b17bdc50da47e58a419b9fab347156": ("side", "catchment-areas", "What are catchment areas?", 0),
}
# Side page slug -> parent guide slug (URL /guide/<parent>/<slug>/, "back to" link).
SIDE_PARENTS = {
    "catchment-areas": "gender-affirming-healthcare",
    "minors": "gender-affirming-healthcare",
}

# Side pages whose URL differs from their file name (file stays content/_guides/minors.md).
SIDE_URL_SLUGS = {
    "minors": "below-21",
}

# Sections split off a guide into their own side page: guide slug -> list of
# (heading block id, side page slug). Everything from that top-level heading to
# the next heading of the same level moves; the guide keeps a short pointer.
SPLITS = {
    "gender-affirming-healthcare": [("bc1fa2ef-ae43-4e35-8ace-7524a00f723e", "minors")],
}
for _parent, _splits in SPLITS.items():
    for _hid, _slug in _splits:
        PAGES[f"split:{_slug}"] = ("side", _slug, None, 0)
# heading id -> side page URL, filled in as splits are written (used to fix links)
SPLIT_ANCHORS = {}
# Drop-down menu groups (separated by a rule), by slug. See _includes/header.html.
NAV_GROUPS = [
    ["gender-affirming-healthcare", "transfeminine-hrt", "transmasculine-hrt", "non-binary-transition", "private-doctors"],
    ["social-transition", "psychological-emotional-resources", "haircuts"],
    ["national-service", "self-managing-transfeminine-hrt"],
]
# Older/alternate Notion ids that point at pages in this set.
ALIASES = {
    "da9330ebbaef47c3ad68c6983b3371b4": "df8b5db122234f66968bff4ba95b4068",
    # 2022 healthcare guide was superseded by the 2023 edition
    "45d6313aef534974ac4ebbeb9ec1de93": "8ac130903cbd47e6bf39ee35f45e330b",
}

# Distribution notices. The original Notion callouts referenced information
# security levels; they are replaced by _includes/notice.html (shared wording,
# keyed by audience) plus any page-specific lines below, kept verbatim.
EDITS = "Suggest edits in #library-suggestions and reach out to a librarian for changes in information there."
NOTICES = {
    "gender-affirming-healthcare": ("community", [EDITS]),
    "transfeminine-hrt": ("community", [EDITS]),
    "transmasculine-hrt": ("community", [EDITS]),
    "non-binary-transition": ("community", [EDITS]),
    "private-doctors": ("community", []),
    "psychological-emotional-resources": ("community", [EDITS]),
    "social-transition": ("community", [EDITS]),
    "haircuts": ("community", [
        "While the topic of this guide is largely uncontroversial, sharing this guide widely may make people aware of our presence.",
        "This guide is maintained by the Transcend Library. For updates and suggestions, please go to #fashion (where this guide is pinned) or #library-suggestions.",
    ]),
    "self-managing-transfeminine-hrt": ("transcend", [
        "We may occasionally remove this article from listing or place it on private. **This article is not an endorsement of self-managing or DIY-ing hormone replacement therapy**; you should, by now, be aware that some of the effects of HRT are irreversible and will be costly to reverse, especially in the long term.",
        "This document presumes that you have read and understood the [transfeminine guide to HRT]({{site.baseurl}}/guide/transfeminine-hrt/). If you have not read that, please go on to do so. Like now. Suggest edits and additions on #library-suggestions.",
    ]),
    "national-service": ("transcend", [
        "Within Transcend, please keep it to the #ns-and-reservist channel, except within specific contexts.",
        "This document is maintained by the Transcend Library. You can make suggestions or updates in #library-suggestions or discuss the guide in the #ns-and-reservist channel.",
        "This document is reflective of the personal experiences of multiple transgender persons in the community. However, they have not been legally verified, may not be typical for all trans people, and should not be taken as legal or professional advice. All statements were made by individuals complying with the 1970 Singapore Enlistment Act. Readers are advised to seek guidance from relevant authorities in the Singapore Armed Forces, such as enlistment and medical officers. This document’s contributing authors do not guarantee the quality, accuracy or completeness of any information on this document.",
        "This document is also largely compiled from experiences in the SAF, and may not be indicative of experiences within the SPF and SCDF NS cohorts. If you have relevant information regarding this - please let us know!",
    ]),
    "about": ("transcend", []),
}
CALLOUT_COLOURS = ("blue", "pink", "purple")

# Images that have been retired from the site: never copied out of the exports again.
RETIRED_ASSETS = {
    "CGH_HRT_flowcharts.png",
    "HRT_access_flowchart_-for_Notion-_-1-.png",
    "NUH_HRT_flowcharts_-new-.png",
}

# Notion databases rendered as cards instead of a table, by page slug. The first
# column is the card title, the first tag column a subtitle, other tag columns
# labelled tag rows, link columns short links, and the rest labelled text.
DB_AS_CARDS = {"private-doctors", "psychological-emotional-resources"}
# Short labels for link columns on cards (column name -> link text).
CARD_LINK_LABELS = {"Healthhub link": "HealthHub listing", "Website link": "Website", "Webpage": "Website"}

# Links to another guide that are really about one of its sections -> that heading.
# By source page slug, then link text; value is (target slug, heading block id), or a
# list of those (or None to leave as-is) when the same text appears more than once,
# consumed in document order.
CROSS_LINKS = {
    "gender-affirming-healthcare": {
        "transmasculine guide to HRT": ("transmasculine-hrt", "189a9997-ca49-480f-9ecc-86b82e0b502c"),           # Lab tests ("blood tests")
        "psychological and emotional resource guide.": [
            ("psychological-emotional-resources", "db96e90e-7dbc-42e5-9dc6-35e928e457a2"),                        # …in public healthcare
            None,                                                                                                 # general mention
        ],
        "psychological and emotional resource guide": ("psychological-emotional-resources", "0a7f10d5-5ed2-4265-ab40-1939a1ab61a9"),  # counselling providers list
    },
    "non-binary-transition": {
        "transmasculine guide to HRT": ("transmasculine-hrt", "7f399f4d-87e9-4ce0-8801-c27867f1a985"),           # Expected changes from T
        "transfeminine guide to HRT.": ("transfeminine-hrt", "bd64ad1e-1700-45f0-8dce-dcca645819dc"),            # Expected changes from transfem HRT
    },
    "psychological-emotional-resources": {
        "the guide to gender-affirming healthcare": ("gender-affirming-healthcare", "5657a66f-6ba7-4b79-8b43-5d873adb7950"),  # Psychological medicine
        "gender-affirming healthcare guide": ("gender-affirming-healthcare", "0b3252d9-4244-44aa-9d53-0377af45d82b"),         # Private psychological assessments
    },
    "national-service": {
        "gender-affirming healthcare guide": ("gender-affirming-healthcare", "830fc323-de70-4410-bfd6-a653a36b81e3"),         # Accessing HRT across all known routes
    },
}

# Unlinked text that refers to a section of the same page -> link the phrase
# (first occurrence) to that heading.
TEXT_LINKS = {
    # A target is a heading id on the same page, or (page slug, heading id).
    "catchment-areas": [
        ("NUH and its gender clinic", ("gender-affirming-healthcare", "0d3633fb-7d1f-45ca-8400-89c2b680ac03")),   # The NUH route
        ("CGH and its gender clinic", ("gender-affirming-healthcare", "89e707a0-1b2b-47a0-8204-0a211323231c")),   # The CGH route
        ("IMH Psychology to CGH/NUH Endocrinology", ("gender-affirming-healthcare", "0dd2d765-fa85-4594-a93d-fe8b756f174c")),  # The route from IMH
        ("medical examination report", ("social-transition", "e4741761-ece0-4d5d-a5b8-98e1f08e0ae2")),            # doctors who sign the ICA MER
    ],
    "gender-affirming-healthcare": [
        ("section on gender-affirming care for minors", "bc1fa2ef-ae43-4e35-8ace-7524a00f723e"),
    ],
    "national-service": [
        ("the next section", "31f21554-18c1-43bc-9290-b820b6455225"),   # For people currently in service
    ],
}

# Notion links from a page to itself (always to the top) -> the heading they mean.
# Keyed by page slug, then by the link's text; values are Notion heading block ids.
SELF_LINKS = {
    "gender-affirming-healthcare": {
        "gender-affirming care for minors": "bc1fa2ef-ae43-4e35-8ace-7524a00f723e",   # Gender-affirming care for minors
        "here": "3733bd9a-13d8-4cf0-88b5-d17167831e8d",                               # Other places to get gender-affirming care
        "see above": "830fc323-de70-4410-bfd6-a653a36b81e3",                          # Accessing gender-affirming HRT… (MOH rule)
        "above": "830fc323-de70-4410-bfd6-a653a36b81e3",                              # Accessing gender-affirming HRT… (adult routes)
    },
    "national-service": {
        "second review section": "553e0b82-7a69-4e34-b8d2-acfe51daaa41",            # For a second review at CMPB’s MCC (or IMH)
    },
}

# Replacement cover images (kept outside assets/notion, which is regenerated):
# (path, focal point, show the whole image instead of a cropped banner)
COVER_OVERRIDES = {
    "about": ("/assets/img/about-cover.webp", "45%", True),
}

# Publishing date shown on every guide (front matter `date`).
GUIDE_PUBLISHED = "2022-11-17"
# "Updated" date shown on every guide (front matter `last_modified_at`), with
# per-guide overrides keyed by slug.
GUIDE_UPDATED = "2026-10-05"
GUIDE_UPDATED_OVERRIDES = {}

# Per-guide publishing date overrides, keyed by slug.
GUIDE_PUBLISHED_OVERRIDES = {
    "private-doctors": "2024-10-25",  # "This document was first written on October 25, 2024."
}

report = defaultdict(list)  # page title -> list of notes


def url_for(pid):
    kind, slug, *_ = PAGES[pid]
    if kind == "about":
        return "/about/"
    if kind == "side":
        return f"/guide/{SIDE_PARENTS[slug]}/{SIDE_URL_SLUGS.get(slug, slug)}/"
    return f"/guide/{slug}/"


def slug_url(slug):
    return url_for(next(pid for pid, v in PAGES.items() if v[1] == slug))


class Converter:
    def __init__(self, pid, html_path):
        self.pid = pid
        self.kind, self.slug, self.nav_title, self.order, *rest = PAGES[pid]
        self.label = rest[0] if rest else None
        self.callout_count = 0
        self.cover_alt = None
        self.cross_seen = Counter()
        self.src_dir = html_path.parent
        self.asset_dir = ROOT / "assets" / "notion" / self.slug
        self.asset_url = f"/assets/notion/{self.slug}"
        self.soup = BeautifulSoup(html_path.read_text(), "html.parser")
        self.title = self.soup.find("h1", class_="page-title").get_text().strip()
        self.normalise()

    def normalise(self):
        """Notion splits formatting runs into adjacent/nested duplicate tags
        (<strong>a</strong><strong>b</strong>, <em><em>x</em></em>), which
        would produce broken Markdown like `**a****b**`. Merge them."""
        inline = ("strong", "em", "del", "code")
        for name in inline:
            for t in self.soup.find_all(name):
                if t.find_parent(name):
                    t.unwrap()
        for t in self.soup.find_all("span", style=re.compile("border-bottom")):
            if t.find_parent("span", style=re.compile("border-bottom")):
                t.unwrap()
        changed = True
        while changed:
            changed = False
            for t in self.soup.find_all(list(inline) + ["span"]):
                if t.parent is None:
                    continue
                if t.name == "span" and "border-bottom" not in t.get("style", ""):
                    continue
                nxt = t.next_sibling
                if isinstance(nxt, Tag) and nxt.name == t.name and nxt.get("style") == t.get("style"):
                    for c in list(nxt.children):
                        t.append(c.extract())
                    nxt.decompose()
                    changed = True
        # Links split into adjacent pieces ("[p][sychological…]", "[guide][.]")
        for a in self.soup.find_all("a"):
            if a.parent is None:
                continue
            nxt = a.next_sibling
            while isinstance(nxt, Tag) and nxt.name == "a" and nxt.get("href") == a.get("href"):
                for c in list(nxt.children):
                    a.append(c.extract())
                nxt.decompose()
                nxt = a.next_sibling
        # empty formatting tags
        for t in self.soup.find_all(list(inline)):
            if not t.get_text() and not t.find(["img", "br"]):
                t.decompose()

    def note(self, msg):
        if msg not in report[self.title]:
            report[self.title].append(msg)

    # ---------- assets & links ----------
    def asset(self, src):
        if src.startswith("http"):
            if "discordapp" in src:
                self.note(f"Image hot-linked from Discord CDN (likely expired): `{src[:80]}`")
            elif "unsplash" not in src:
                self.note(f"Remote image kept as hot-link: `{src[:80]}`")
            return src
        path = self.src_dir / unquote(src)
        if not path.exists():
            self.note(f"Missing local image `{src}`")
            return src
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", path.name).strip("-")
        if name in RETIRED_ASSETS:
            return f"{self.asset_url}/{name}"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, self.asset_dir / name)
        return f"{self.asset_url}/{name}"

    def href(self, href, text=None):
        href = html.unescape(href)
        m = re.match(r"https://(?:app|www)\.notion\.(?:com|so)/(?:[^/]+/)?[^?#]*?([0-9a-f]{32})", href)
        if m:
            pid = ALIASES.get(m.group(1), m.group(1))
            if pid == self.pid:
                target = SELF_LINKS.get(self.slug, {}).get((text or "").strip())
                if target:
                    return "#h-" + target
                self.note(f"Link to this same page with no heading mapped in SELF_LINKS (text: {text!r})")
            if pid in PAGES:
                anchor = ""
                spec = CROSS_LINKS.get(self.slug, {}).get((text or "").strip())
                if isinstance(spec, list):
                    key = (text or "").strip()
                    i = self.cross_seen[key]
                    self.cross_seen[key] += 1
                    spec = spec[i] if i < len(spec) else None
                if spec:
                    target_slug, heading = spec
                    if url_for(pid) != url_for(next(k for k, v in PAGES.items() if v[1] == target_slug)):
                        self.note(f"CROSS_LINKS target {target_slug} doesn't match the link's page")
                    anchor = "#h-" + heading
                return "{{site.baseurl}}" + url_for(pid) + anchor
            self.note(f"Link to a Notion page that was not exported (left pointing at Notion): {href.split('?')[0]}")
            return href.split("?")[0]
        if href.startswith("#"):
            return "#h-" + href[1:]
        if not href.startswith(("http", "mailto:")) and "@" in href:
            return "mailto:" + href
        if not href.startswith(("http", "mailto:", "{{")):
            return self.asset(href)  # link to a local file (e.g. full-size image)
        return href

    # ---------- inline ----------
    def inline_html(self, node):
        """Inline content as HTML (used inside raw-HTML blocks)."""
        if isinstance(node, NavigableString):
            return html.escape(str(node), quote=False)
        if not isinstance(node, Tag):
            return ""
        inner = "".join(self.inline_html(c) for c in node.children)
        t = node.name
        if t == "br":
            return "<br>"
        if t in ("strong", "em", "code", "del"):
            return f"<{t}>{inner}</{t}>" if inner.strip() else inner
        if t == "mark":
            return f"<mark{highlight_class(node)}>{inner}</mark>"
        if t == "a":
            if node.get("href", "-") in ("", "-"):
                return inner
            return f'<a href="{self.href(node.get("href", ""), node.get_text())}">{inner}</a>'
        if t == "img":
            if {"icon", "property-icon"} & set(node.get("class") or []):
                return ""
            return f'<img src="{self.asset(node["src"])}" alt="" loading="lazy">'
        if t == "span":
            style = node.get("style", "")
            cls = node.get("class") or []
            if "border-bottom" in style:
                return f"<u>{inner}</u>"
            if "icon" in cls:
                return node.get("data-emoji", "")
            if "selected-value" in cls:
                color = next((c.split("-")[-1] for c in cls if c.startswith("select-value-color-")), "default")
                return f'<span class="tag tag-{color}">{inner}</span>'
            return inner
        if t in ("svg",):
            return ""
        if t == "p":
            return inner + "<br>"
        if t in ("ul", "ol"):
            return f"<{t}>{inner}</{t}>"
        if t == "li":
            return f"<li>{inner}</li>"
        return inner

    def inline_md(self, nodes):
        """Inline content as a single Markdown line."""
        out = []
        for node in nodes:
            out.append(self._md(node))
        s = "".join(out)
        s = re.sub(r"(<br>\s*)+$", "", s.strip())
        return s

    MD_ESC = re.compile(r"([\\`*_\[\]|<>~$])")

    def _md(self, node):
        if isinstance(node, NavigableString):
            text = self.MD_ESC.sub(r"\\\1", str(node))
            return text.replace("{{", "{\\{").replace("{%", "{\\%").replace("\n", " ")
        if not isinstance(node, Tag):
            return ""
        t = node.name
        if t == "br":
            return "<br>"
        if t == "img":
            return "" if "icon" in (node.get("class") or []) else f"![]({self.asset(node['src'])})"
        inner = "".join(self._md(c) for c in node.children)
        wrap = {"strong": "**", "em": "*", "del": "~~"}.get(t)
        if wrap:
            core = inner.strip()
            if not core or core.replace("<br>", "").strip() == "":
                return inner
            lead = inner[: len(inner) - len(inner.lstrip())]
            trail = inner[len(inner.rstrip()):]
            # <br> at either edge must sit outside the markers
            m1 = re.match(r"^((?:<br>)+)", core)
            m2 = re.search(r"((?:<br>)+)$", core)
            pre = m1.group(1) if m1 else ""
            post = m2.group(1) if m2 else ""
            core = core[len(pre): len(core) - len(post)].strip()
            if not core:
                return inner
            return f"{lead}{pre}{wrap}{core}{wrap}{post}{trail}"
        if t == "code":
            return "`" + node.get_text().replace("`", "") + "`"
        if t == "mark":
            self.note("Highlighted text (Notion background colour) rendered as <mark>")
            inner_html = re.sub(r"^<mark[^>]*>|</mark>$", "", self.inline_html(node.__copy__()))
            return f"<mark{highlight_class(node)}>{inner_html}</mark>"
        if t == "a":
            text = inner.strip() or html.escape(node.get("href", ""))
            href = self.href(node.get("href", ""), node.get_text()).replace(" ", "%20").replace("(", "%28").replace(")", "%29")
            lead = " " if inner[:1].isspace() else ""
            trail = " " if inner[-1:].isspace() else ""
            return f"{lead}[{text}]({href}){trail}"
        if t == "span":
            style = node.get("style", "")
            cls = node.get("class") or []
            if "border-bottom" in style:
                # raw HTML: a paragraph starting with "<u>" would be an HTML block to kramdown
                return f"<u>{self.inline_html(node.__copy__()).strip()}</u>".replace("<u><u>", "<u>").replace("</u></u>", "</u>")
            if "icon" in cls:
                return node.get("data-emoji", "")
            return inner
        return inner

    # ---------- blocks ----------
    def blocks(self, parent, depth=0):
        """Convert block-level children of `parent` to a list of Markdown chunks."""
        chunks = []
        kids = [k for k in parent.children if not (isinstance(k, NavigableString) and not k.strip())]
        i = 0
        pending_inline = []

        def flush():
            if pending_inline:
                s = self.inline_md(pending_inline)
                if s:
                    chunks.append(self.escape_line_start(s))
                pending_inline.clear()

        while i < len(kids):
            k = kids[i]
            if isinstance(k, NavigableString) or k.name in ("strong", "em", "a", "span", "br", "code", "del", "img", "mark"):
                pending_inline.append(k)
                i += 1
                continue
            flush()
            cls = k.get("class") or []
            t = k.name
            if t in ("ul", "ol"):
                # Notion exports each list item as its own <ul>/<ol>; merge runs.
                run = [k]
                while i + 1 < len(kids) and isinstance(kids[i + 1], Tag) and kids[i + 1].name == t:
                    i += 1
                    run.append(kids[i])
                chunks.append(self.list_md(run, t))
            elif t == "p":
                # Notion nests child blocks (lists, callouts) inside <p>
                chunks.extend(self.blocks(k, depth))
            elif t in ("h1", "h2", "h3", "h4"):
                chunks.append(self.heading(k))
            elif t == "aside" and "callout" in cls:
                chunks.append(self.callout(k))
            elif t == "nav" and "table_of_contents" in cls:
                chunks.append(self.toc(k))
            elif t == "table":
                chunks.append(self.table(k))
            elif t == "div" and "collection-content" in cls:
                chunks.append(self.database(k))
            elif t == "details":
                chunks.append(self.toggle(k))
            elif t == "div" and "column-list" in cls:
                chunks.append(self.columns(k))
            elif t == "div" and "indented" in cls:
                chunks.append(self.html_wrap("div", "indented", self.blocks(k, depth + 1)))
            elif t == "figure" and "image" in cls:
                chunks.append(self.figure(k))
            elif t == "figure" and "link-to-page" in cls:
                a = k.find("a")
                self.note("Link-to-page block rendered as a plain link")
                chunks.append(f"→ [{a.get_text().strip()}]({self.href(a['href'])})")
            elif t == "div" and k.get("style", "").startswith("width:100%"):
                chunks.extend(self.blocks(k, depth))
            elif t == "div":
                chunks.extend(self.blocks(k, depth))
            else:
                self.note(f"Unhandled block `<{t} class='{' '.join(cls)}'>` (flattened)")
                s = self.inline_md(k.children)
                if s:
                    chunks.append(s)
            i += 1
        flush()
        return [c for c in chunks if c]

    @staticmethod
    def escape_line_start(s):
        s = re.sub(r"^(\s*)([#+\-=>]|\d+\.)(\s)", lambda m: m.group(1) + "\\" + m.group(2) + m.group(3), s)
        return s

    def heading(self, h):
        # Page title is the only h1; shift Notion's in-body levels down one.
        level = min(int(h.name[1]) + 1, 6)
        text = self.inline_md(h.children)
        hid = h.get("id")
        return "#" * level + " " + text + (f"\n{{: #{ 'h-' + hid }}}" if hid else "")

    def list_md(self, run, t, indent=0):
        lines = []
        n = int(run[0].get("start", 1)) if t == "ol" else 0
        alpha = t == "ol" and run[0].get("type") in ("a", "i")
        for lst in run:
            for li in lst.find_all("li", recursive=False):
                inline, nested = [], []
                for c in li.children:
                    if isinstance(c, Tag) and (c.name in ("ul", "ol", "p", "div", "figure", "table", "details", "aside")):
                        nested.append(c)
                    else:
                        inline.append(c)
                marker = f"{n}." if t == "ol" else "-"
                n += 1
                pad = " " * (len(marker) + 1)
                text = self.inline_md(inline) or "&nbsp;"
                lines.append(f"{marker} {text}")
                if nested:
                    holder = BeautifulSoup("<div></div>", "html.parser").div
                    for c in nested:
                        holder.append(c.__copy__())
                    for chunk in self.blocks(holder, 1):
                        lines.append("")
                        lines.extend(pad + l if l else "" for l in chunk.split("\n"))
        if alpha:
            self.note("Lettered (a, b, c) numbered list — kept via `type` attribute")
            lines.append('{: type="a"}')
        return "\n".join(lines)

    def html_wrap(self, tag, cls, chunks, extra=""):
        body = "\n\n".join(chunks)
        return f'<{tag} class="{cls}" markdown="1"{extra}>\n\n{body}\n\n</{tag}>'

    def callout(self, aside):
        icon_html = ""
        icon_div = aside.find("div", recursive=False)
        img = icon_div.find("img") if icon_div else None
        emoji = icon_div.find("span", class_="icon") if icon_div else None
        if img:
            icon_html = f'<img src="{self.asset(img["src"])}" alt="">'
            self.note("Callout with a custom image icon")
        elif emoji:
            icon_html = emoji.get("data-emoji", "")
        colour = CALLOUT_COLOURS[self.callout_count % len(CALLOUT_COLOURS)]
        self.callout_count += 1
        cls = f"callout callout-{colour}"
        if emoji is not None and emoji.get("data-emoji") == "🖼️" and not self.cover_alt:
            # Notion workaround for cover alt text: use it as real alt text instead.
            self.cover_alt = aside.find_all("div", recursive=False)[-1].get_text(" ", strip=True)
            self.callout_count -= 1
            return ""
        if re.search(r"This Level \d document", aside.get_text()):
            audience, extras = NOTICES[self.slug]
            chunks = [f'{{% include notice.html audience="{audience}" %}}'] + extras
            cls += " callout-notice"
            icon_html = ""
        else:
            chunks = self.blocks(aside.find_all("div", recursive=False)[-1])
        inner = "\n\n".join(chunks)
        icon = f'<div class="callout-icon" aria-hidden="true">{icon_html}</div>\n' if icon_html else ""
        return (f'<aside class="{cls}">\n{icon}'
                f'<div class="callout-body" markdown="1">\n\n{inner}\n\n</div>\n</aside>')

    def toc(self, nav):
        lines = ['<nav class="toc" aria-label="Contents" markdown="1">', ""]
        for item in nav.find_all("div", class_="table_of_contents-item"):
            lvl = next(int(c.rsplit("-", 1)[1]) for c in item["class"] if c.startswith("table_of_contents-indent-"))
            a = item.find("a")
            text = self.MD_ESC.sub(r"\\\1", a.get_text().strip())
            lines.append("  " * lvl + f"- [{text}](#h-{a['href'][1:]})")
        lines += ["", "</nav>"]
        return "\n".join(lines)

    def table(self, tbl):
        rows = []
        header_row = "simple-table-header" in " ".join(" ".join(c.get("class") or []) for c in tbl.find_all(["td", "th"])[:20])
        for ri, tr in enumerate(tbl.find_all("tr")):
            cells = []
            for cell in tr.find_all(["td", "th"]):
                is_head = cell.name == "th" or "simple-table-header" in (cell.get("class") or [])
                tag = "th" if is_head else "td"
                cells.append(f"<{tag}>{self.inline_html(cell).strip()}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        if header_row:
            self.note("Simple table with header row/column")
        return '<div class="table-wrap"><table>\n' + "\n".join(rows) + "\n</table></div>"

    def database(self, div):
        self.note("Inline Notion database (rendered as a static table; filters, sorts and row pages lost)")
        out = []
        title = div.find(class_="collection-title")
        if title:
            out.append(f"<p class=\"db-title\"><strong>{html.escape(title.get_text().strip())}</strong></p>")
        tbl = div.find("table")
        if self.slug in DB_AS_CARDS:
            out.append(self.database_cards(tbl))
            return "\n".join(out)
        rows = []
        for tr in tbl.find_all("tr"):
            cells = []
            for cell in tr.find_all(["td", "th"]):
                for svg in cell.find_all(["svg"]):
                    svg.decompose()
                for a in cell.find_all("a"):
                    if "notion.com/p/" in a.get("href", "") and a.get("data-notion-page-id"):
                        a.unwrap()  # row sub-pages were not exported
                        self.note("Database row titles linked to row sub-pages that were not exported (links removed)")
                cells.append(f"<{cell.name}>{self.inline_html(cell).strip()}</{cell.name}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        out.append('<div class="table-wrap"><table class="db">\n' + "\n".join(rows) + "\n</table></div>")
        return "\n".join(out)

    def database_cards(self, tbl):
        """Render a Notion database table as a grid of cards (see DB_AS_CARDS)."""
        trs = tbl.find_all("tr")
        heads = [c.get_text(" ", strip=True) for c in trs[0].find_all(["th", "td"])]
        cards = []
        for tr in trs[1:]:
            cells = tr.find_all(["td", "th"])
            for cell in cells:
                for svg in cell.find_all("svg"):
                    svg.decompose()
                for a in cell.find_all("a"):
                    if "notion.com/p/" in a.get("href", "") and a.get("data-notion-page-id"):
                        a.unwrap()
            title = self.inline_html(cells[0]).strip()
            subtitle, tag_rows, fields, links = "", [], [], []
            for head, cell in zip(heads[1:], cells[1:]):
                if not cell.get_text(strip=True):
                    continue
                if cell.find(class_="selected-value"):
                    tags = self.inline_html(cell).strip()
                    if not subtitle:
                        subtitle = tags
                    else:
                        tag_rows.append((head, tags))
                elif head in CARD_LINK_LABELS or (cell.find("a") and cell.get_text(strip=True).startswith("http")):
                    for a in cell.find_all("a"):
                        label = CARD_LINK_LABELS.get(head, head)
                        links.append(f'<a href="{self.href(a.get("href", ""))}">{html.escape(label)}</a>')
                else:
                    for strong in cell.find_all("strong"):
                        strong.unwrap()  # addresses were bolded in Notion
                    fields.append((head, self.inline_html(cell).strip()))
            # "Name (Role)" titles: show the role as the subtitle
            m = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", re.sub(r"\s+", " ", title))
            if m and not subtitle:
                title, subtitle = m.group(1), f'<span class="db-card-role">{m.group(2)}</span>'
            parts = [f'<article class="db-card">', f'<h3 class="db-card-title">{title}</h3>']
            if subtitle:
                parts.append(f'<div class="db-card-type">{subtitle}</div>')
            for head, tags in tag_rows:
                parts.append(f'<p class="db-card-label">{html.escape(head)}</p><div class="db-card-tags">{tags}</div>')
            if fields:
                parts.append('<dl class="db-card-fields">' + "".join(
                    f"<dt>{html.escape(h)}</dt><dd>{v}</dd>" for h, v in fields) + "</dl>")
            if links:
                parts.append('<p class="db-card-links">' + " ".join(links) + "</p>")
            parts.append("</article>")
            cards.append("\n".join(parts))
        self.note("Database rendered as cards (DB_AS_CARDS)")
        return '<div class="db-cards">\n' + "\n".join(cards) + "\n</div>"

    def split_section(self, md, hid, side_slug):
        """Move the section headed by `hid` into its own side page; return the
        guide's Markdown with a pointer in its place."""
        m = re.search(r"^(#+) (.+)\n\{: #h-" + re.escape(hid) + r"\}\n", md, re.M)
        if not m:
            self.note(f"SPLITS heading not found: {hid}")
            return md
        level = len(m.group(1))
        nxt = re.compile(r"^#{1,%d} " % level, re.M).search(md, m.end())
        end = nxt.start() if nxt else len(md)
        section, title = md[m.end():end], re.sub(r"[*_]", "", m.group(2)).strip()
        main_url = url_for(self.pid)
        side_url = url_for(f"split:{side_slug}")
        moved = anchor_ids(section) | {hid}
        for i in moved:
            SPLIT_ANCHORS[i] = side_url
        # links inside the moved section to the rest of the guide
        section = re.sub(r"\]\(#h-([0-9a-f-]{36})\)",
                         lambda x: x.group(0) if x.group(1) in moved else f"]({{{{site.baseurl}}}}{main_url}#h-{x.group(1)})", section)
        section = re.sub(r'href="#h-([0-9a-f-]{36})"',
                         lambda x: x.group(0) if x.group(1) in moved else f'href="{{{{site.baseurl}}}}{main_url}#h-{x.group(1)}"', section)
        # the guide's distribution notice goes on the side page too
        notice = re.search(r'<aside class="callout[^"]*callout-notice">.*?</aside>', md, re.S)
        body = (notice.group(0) + "\n\n" if notice else "") + section.strip() + "\n"
        front = ["---", "layout: guide", f"permalink: {side_url}", f"parent: {self.slug}",
                 f"title: {quote_yaml(title)}", "---", ""]
        out = CONTENT / "_guides" / f"{side_slug}.md"   # split-off sections are guides in their own right
        text = "\n".join(front) + "\n" + body
        if is_kept(out):
            print(f"kept {out.relative_to(ROOT)}: {stage(side_slug, text)}")
        else:
            out.parent.mkdir(exist_ok=True)
            out.write_text(text)
            print("wrote", out.relative_to(ROOT), "(split from", self.slug + ")")
        # in the guide: keep the heading as a short pointer to the new page
        pointer = (f"{m.group(0)}\nThis section now has its own page: "
                   f"**[{title} →]({{{{site.baseurl}}}}{side_url})**\n\n")
        md = md[:m.start()] + pointer + md[end:]
        return md

    def toggle(self, det):
        self.note("Toggle block rendered as <details>")
        summary = det.find("summary")
        h = summary.find(["h1", "h2", "h3", "h4"])
        level = min(int(h.name[1]) + 1, 6) if h else 0
        title = self.inline_html(h or summary).strip()
        sid = f' id="h-{h["id"]}"' if h and h.get("id") else ""
        head = f"<h{level}{sid}>{title}</h{level}>" if level else title
        body = det.find("div", class_="indented") or det
        chunks = self.blocks(body)
        return (f'<details class="toggle" open>\n<summary>{head}</summary>\n<div markdown="1">\n\n'
                + "\n\n".join(chunks) + "\n\n</div>\n</details>")

    def columns(self, div):
        self.note("Multi-column layout (stacks on small screens)")
        cols = []
        for col in div.find_all("div", class_="column", recursive=False):
            cols.append(self.html_wrap("div", "column", self.blocks(col)))
        return '<div class="columns">\n' + "\n".join(cols) + "\n</div>"

    def figure(self, fig):
        img = fig.find("img")
        cap = fig.find("figcaption")
        src = self.asset(img["src"])
        w = re.search(r"width:(\d+)", img.get("style", ""))
        width = f' width="{w.group(1)}"' if w else ""
        caption = f"\n<figcaption>{self.inline_html(cap)}</figcaption>" if cap else ""
        alt = html.escape(cap.get_text().strip()) if cap else ""
        if not alt:
            self.note("Image without alt text / caption")
        return f'<figure class="image"><a href="{src}"><img src="{src}" alt="{alt}"{width} loading="lazy"></a>{caption}</figure>'

    # ---------- page ----------
    def run(self):
        header = self.soup.find("header")
        fm = {"title": self.title, "nav_title": self.nav_title, "order": self.order}
        group = next((i + 1 for i, g in enumerate(NAV_GROUPS) if self.slug in g), None)
        if group:
            fm["nav_group"] = group
        if self.label:
            fm["label"] = self.label
        if self.kind == "guide":
            fm["date"] = GUIDE_PUBLISHED_OVERRIDES.get(self.slug, GUIDE_PUBLISHED)
            fm["last_modified_at"] = GUIDE_UPDATED_OVERRIDES.get(self.slug, GUIDE_UPDATED)
        cover = header.find("img", class_="page-cover-image")
        if cover and self.slug not in COVER_OVERRIDES:
            fm["cover"] = self.asset(html.unescape(cover["src"]))
            pos = re.search(r"object-position:center ([\d.]+)%", cover.get("style", ""))
            if pos:
                fm["cover_position"] = f"{float(pos.group(1)):.0f}%"
        # Page icons (emoji / custom emoji above the title) are intentionally dropped.
        body = self.soup.find("div", class_="page-body")
        chunks = self.blocks(body)
        md = "\n\n".join(chunks)
        for phrase, target in TEXT_LINKS.get(self.slug, []):
            if isinstance(target, tuple):
                href = "{{site.baseurl}}" + slug_url(target[0]) + "#h-" + target[1]
            else:
                href = "#h-" + target
            if phrase in md:
                md = md.replace(phrase, f"[{phrase}]({href})", 1)
            else:
                self.note(f"TEXT_LINKS phrase not found: {phrase!r}")
        if self.slug in COVER_OVERRIDES:
            fm["cover"], fm["cover_position"], full = COVER_OVERRIDES[self.slug]
            if full:
                fm["cover_full"] = True
        if self.cover_alt:
            fm["cover_alt"] = self.cover_alt
        # Liquid in hrefs is emitted literally; everything else must not be parsed as Liquid.
        md = md.replace("{\\{", "&#123;&#123;").replace("{\\%", "&#123;%")
        for hid, side_slug in SPLITS.get(self.slug, []):
            md = self.split_section(md, hid, side_slug)
        front = ["---", "layout: guide"]
        if self.kind == "about":
            front.append("permalink: /about/")
        if self.kind == "side":
            front.append(f"permalink: {url_for(self.pid)}")
            front.append(f"parent: {SIDE_PARENTS[self.slug]}")
        for k, v in fm.items():
            front.append(f"{k}: {quote_yaml(v)}")
        front.append("---")
        folder = {"guide": "_guides", "side": "_side"}.get(self.kind, ".")
        out = CONTENT / folder / f"{self.slug}.md"
        text = "\n".join(front) + "\n\n" + md + "\n"
        if is_kept(out):
            print(f"kept {out.relative_to(ROOT)}: {stage(self.slug, text)}")
            return out
        out.parent.mkdir(exist_ok=True)
        out.write_text(text)
        return out


def stage(slug, text):
    """A locked (`converter: keep`) page was re-converted from Notion. Instead of
    overwriting it, compare with the last Notion version we saw (the baseline)
    and, if Notion changed, save the new version and a diff of just the Notion
    changes to merge into the hand-edited page. Returns a status message."""
    base = SYNC / "baseline" / f"{slug}.md"
    new = SYNC / "incoming" / f"{slug}.md"
    diff = SYNC / "incoming" / f"{slug}.diff"
    if not base.exists():
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text(text)
        return "baseline saved"
    old = base.read_text()
    if old == text:
        new.unlink(missing_ok=True)
        diff.unlink(missing_ok=True)
        return "no Notion changes"
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text(text)
    diff.write_text("".join(difflib.unified_diff(
        old.splitlines(True), text.splitlines(True),
        f"baseline/{slug}.md (last Notion version)", f"incoming/{slug}.md (new Notion version)")))
    report["Notion changes waiting to be merged"].append(
        f"`{slug}`: see `_tools/notion-sync/incoming/{slug}.diff`")
    return f"NOTION CHANGED -> _tools/notion-sync/incoming/{slug}.diff"


def accept(slug):
    """After merging, make the incoming Notion version the new baseline."""
    new = SYNC / "incoming" / f"{slug}.md"
    if not new.exists():
        sys.exit(f"No incoming Notion version for {slug}")
    new.replace(SYNC / "baseline" / f"{slug}.md")
    (SYNC / "incoming" / f"{slug}.diff").unlink(missing_ok=True)
    print("accepted: baseline updated for", slug)


def is_kept(path):
    """Files marked `converter: keep` in their front matter are hand-edited:
    never overwrite them."""
    try:
        head = path.read_text().split("\n---", 1)[0]
    except FileNotFoundError:
        return False
    return re.search(r"^converter:\s*keep\b", head, re.M) is not None


def anchor_ids(md):
    return set(re.findall(r'(?:\{: #|id=")h-([0-9a-f-]{36})', md))


def highlight_class(node):
    """Keep Notion's highlight colour: data-notion-highlight="yellow_background" -> class="highlight-yellow"."""
    colour = (node.get("data-notion-highlight") or "").replace("_background", "")
    return f' class="highlight-{colour}"' if colour else ""


def quote_yaml(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def extract(zip_path, dest):
    """Extract a Notion export. Some exports store UTF-8 names (e.g. curly
    apostrophes) without the UTF-8 flag, which zipfile decodes as cp437."""
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if not info.flag_bits & 0x800:
                try:
                    info.filename = info.filename.encode("cp437").decode("utf-8")
                except UnicodeError:
                    pass
            zf.extract(info, dest)


def fix_split_links():
    """Links to headings that moved into a split-off side page -> that page."""
    if not SPLIT_ANCHORS:
        return
    for f in list((CONTENT / "_guides").glob("*.md")) + list((CONTENT / "_side").glob("*.md")) + [CONTENT / "about.md"]:  # noqa
        if is_kept(f):
            continue
        text = f.read_text()
        here = re.search(r"^permalink: (.+)$", text, re.M)
        slug = f.stem
        own = here.group(1).strip() if here else f"/guide/{slug}/"
        def fix(m):
            prefix, path, hid = m.group(1), m.group(2) or "", m.group(3)
            target = SPLIT_ANCHORS.get(hid)
            if not target:
                return m.group(0)
            if not path and own == target:
                return m.group(0)                        # already on the side page
            if path and path != _parent_of(target):
                return m.group(0)
            if hid in SPLIT_TOPS:
                return f"{prefix}{{{{site.baseurl}}}}{target}"   # top of the side page
            return f"{prefix}{{{{site.baseurl}}}}{target}#h-{hid}"
        new = re.sub(r'(\]\(|href=")(?:\{\{site\.baseurl\}\}(/guide/[^/#)"]+/))?#h-([0-9a-f-]{36})', fix, text)
        if new != text:
            f.write_text(new)


def _parent_of(side_url):
    return "/" + "/".join(side_url.strip("/").split("/")[:2]) + "/"


SPLIT_TOPS = {hid for splits in SPLITS.values() for hid, _ in splits}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--accept":
        return accept(sys.argv[2])
    # Oldest first, so a newer export of the same page replaces an older one.
    zips = sorted(SOURCES.glob("*_ExportBlock-*.zip"), key=lambda z: z.stat().st_mtime)
    if not zips:
        sys.exit("No Notion export zips found in " + str(SOURCES))
    # Images are added/updated, never deleted: hand-edited pages may still use them.
    with tempfile.TemporaryDirectory() as tmp:
        latest = {}
        for z in zips:
            d = Path(tmp) / z.stem
            extract(z, d)
            for h in d.glob("*.html"):
                pid = h.stem.rsplit(" ", 1)[-1]
                if pid in latest:
                    print(f"newer export of {PAGES.get(pid, (0, pid))[1]}: using {z.name}")
                latest[pid] = h
        for pid, h in latest.items():
            if True:
                if pid not in PAGES:
                    print("skip (unknown page id):", h.name)
                    continue
                was_kept = is_kept(CONTENT / {"guide": "_guides", "side": "_side"}.get(PAGES[pid][0], ".") / f"{PAGES[pid][1]}.md")
                out = Converter(pid, h).run()
                if not was_kept:
                    print("wrote", out.relative_to(ROOT))
    fix_split_links()
    pending = sorted(p.stem for p in (SYNC / "incoming").glob("*.diff")) if (SYNC / "incoming").exists() else []
    if pending:
        print("\nNotion changes waiting to be merged:", ", ".join(pending))
    lines = ["# Notion → Jekyll conversion notes", "",
             "Generated by `_tools/notion2jekyll.py`. Per-page notes on Notion features that needed special handling.", ""]
    for title in sorted(report):
        lines.append(f"## {title}\n")
        lines += [f"- {n}" for n in report[title]]
        lines.append("")
    (ROOT / "_tools" / "conversion-report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
