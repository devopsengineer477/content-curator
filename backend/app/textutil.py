"""HTML -> clean readable text, plus small text helpers."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "section", "article", "br", "li", "ul", "ol", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "table",
    "header", "footer", "figure", "figcaption", "hr", "td", "th", "dd", "dt",
}

# Elements whose entire subtree is never article text. Removed as paired blocks
# first, then any orphaned opening/closing tags, so an unclosed tag can never
# poison the parse.
_NON_TEXT = (
    "script|style|noscript|template|svg|iframe|object|embed|canvas|math|head|form"
)
_DROP_BLOCK = re.compile(rf"<(?:{_NON_TEXT})\b[^>]*>.*?</(?:{_NON_TEXT})\s*>",
                         re.S | re.I)
_DROP_LEFTOVER = re.compile(rf"</?(?:{_NON_TEXT})\b[^>]*>", re.I)

_WS = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL = re.compile(r"\n{3,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_TAG = re.compile(r"<[^>]+>")


class _TextExtractor(HTMLParser):
    """
    Block-aware tag stripper.

    Deliberately has no subtree-skipping logic: a counter-based "inside a
    <script>" flag gets permanently stuck on real-world HTML with unclosed
    tags, which silently discards the whole document. Instead non-text elements
    are removed by regex before we get here, and this parser only maps block
    tags to newlines.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if data:
            self.parts.append(data)


def strip_html(raw: str) -> str:
    """Turn an HTML fragment into readable plain text."""
    if not raw:
        return ""
    txt = _DROP_BLOCK.sub(" ", raw)
    txt = _DROP_LEFTOVER.sub(" ", txt)
    parser = _TextExtractor()
    try:
        parser.feed(txt)
        out = "".join(parser.parts)
    except Exception:
        out = _TAG.sub(" ", txt)
    out = html.unescape(out)
    out = out.replace("\xa0", " ")
    lines = [_WS.sub(" ", ln).strip() for ln in out.split("\n")]
    out = "\n".join(ln for ln in lines if ln)
    out = _MULTI_NL.sub("\n\n", out)
    return out.strip()


def clean_text(raw: str, max_chars: int = 12000) -> str:
    """Normalise arbitrary feed payload (html or markdown) to plain text."""
    if not raw:
        return ""
    txt = strip_html(raw)
    # markdown leftovers
    txt = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", txt)      # images
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)   # links
    txt = re.sub(r"^\s{0,3}#{1,6}\s*", "", txt, flags=re.M)
    txt = re.sub(r"^\s{0,3}>\s?", "", txt, flags=re.M)
    txt = re.sub(r"`{1,3}", "", txt)
    txt = re.sub(r"\*\*|__|\*|_", "", txt)
    txt = _MULTI_NL.sub("\n\n", txt)
    if len(txt) > max_chars:
        txt = txt[:max_chars].rsplit(" ", 1)[0] + " …"
    return txt.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’\-]+", text or ""))


def first_sentences(text: str, n: int = 2, max_chars: int = 360) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        return text[:max_chars]
    out = ""
    for s in sentences[:n]:
        candidate = (out + " " + s).strip()
        if len(candidate) > max_chars and out:
            break
        out = candidate
    if not out:
        out = sentences[0][:max_chars]
    return out.strip()


def truncate(text: str, n: int) -> str:
    """Truncate on a word boundary - never mid-word."""
    text = text or ""
    if len(text) <= n:
        return text
    cut = text[:n]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.\u2014-") + "\u2026"


STOPWORDS = set(
    """a about after all also am an and any are as at be because been before being
    between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if
    in into is it its itself just me more most my myself no nor not now of off on
    once only or other our ours ourselves out over own same she should so some
    such than that the their theirs them themselves then there these they this
    those through to too under until up very was we were what when where which
    while who whom why will with would you your yours yourself yourselves
    using use used based new one two get gets got make makes made like also
    via per etc ie eg vs""".split()
)

_WORD = re.compile(r"[a-z0-9][a-z0-9'’\.\+\#/-]*")


def tokenize(text: str) -> list[str]:
    toks = _WORD.findall((text or "").lower())
    return [t for t in toks if len(t) > 2 and t not in STOPWORDS and not t.isdigit()]
