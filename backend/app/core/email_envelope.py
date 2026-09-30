"""The envelope a letter travels in: a header, the body, a signature and a footer, in a look.

🔴 THE LOOKS ARE ALICE'S, THE ENVELOPE IS OURS (the manager, 29 Sept 2026: everything common
lives in Alice, reachable by API). The console hosts one catalogue of e-mail looks for every
product; each look is a LAYOUT and three colours. This module only knows how to lay a letter
out in any of them, so a look added in the console dresses this product's letters without a
line changing here.

    band    -> coloured banner, name on the left. Reads as letterhead.
    center  -> coloured banner, name centred, accent rule. Formal.
    rule    -> white header, name on the left, coloured rule underneath. Light.
    crest   -> white header, name centred, accent rule. Elegant.
    none    -> no header nor footer: the message and its signature.

⚠️ PURE, ON PURPOSE. No network, no database, no language lookup: the caller hands in the
words already written in the reader's language, and the same letter in the same look gives
the same HTML. `services.email_themes` fetches the looks; this module never does.

🔴 THE PLAIN TEXT STAYS THE LETTER. A capital call's whole content is a figure, a date and a
reference the investor retypes, and a client that strips HTML must still show all three.
`Letter.text()` is sent alongside the HTML, never instead of it.

⚠️ EVERY VALUE THAT REACHES A STYLE ATTRIBUTE IS CHECKED. A colour comes from another
service; `Look.parse` refuses anything that is not `#rrggbb`, so a catalogue entry cannot
inject markup into the letter. Every word is escaped for the same reason: a fund's name is
typed by a person.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

#: The arrangements a look can name. Anything else is refused at parsing, never guessed.
LAYOUTS: tuple[str, ...] = ("center", "band", "rule", "crest", "none")

_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")

#: The house navy: the built-in look's ink, and the platform's own colour.
_NAVY = "#0D2F5C"

#: 🔴 A WORD LONGER THAN THE LETTER IS CUT, NOT OBEYED. A table grows to fit its longest
#: unbreakable word and `max-width` cannot stop it: an IBAN or a long reference would widen
#: the whole letter past a phone's screen. Both properties, because mail clients support one
#: or the other.
_BREAK_LONG_WORDS = "overflow-wrap:anywhere;word-break:break-word"


@dataclass(frozen=True)
class Look:
    """One look: where things sit, and in which colours."""

    key: str
    layout: str
    ink: str
    accent: str
    soft: str

    @classmethod
    def parse(cls, raw: object) -> Look | None:
        """A look from one catalogue entry, or None when the entry is not usable.

        ⚠️ NONE, NEVER A PARTIAL LOOK. A layout this module does not know, or a colour that
        is not `#rrggbb`, drops the whole entry: the letter then falls back on the default,
        which is the console's contract for a look nobody can render.
        """
        if not isinstance(raw, dict):
            return None
        key, layout = raw.get("key"), raw.get("layout")
        colours = [raw.get(name) for name in ("ink", "accent", "soft")]
        if not isinstance(key, str) or not key.strip() or layout not in LAYOUTS:
            return None
        if not all(isinstance(c, str) and _COLOUR.match(c) for c in colours):
            return None
        ink, accent, soft = colours
        return cls(key=key, layout=layout, ink=ink, accent=accent, soft=soft)


#: 🔴 THE LOOK OF LAST RESORT, when the console never answered and no copy is kept: the
#: letter's name, a plain rule and the signature. Never a naked mail, and never a refused
#: send because a catalogue was out of reach.
BUILT_IN = Look(key="built_in", layout="rule", ink=_NAVY, accent=_NAVY, soft="#64748b")


@dataclass(frozen=True)
class Letter:
    """What the envelope carries, every word already in the reader's language."""

    #: The subject, repeated under the name in the header.
    title: str
    #: Who writes: printed in the header, the signature and the footer.
    brand: str
    #: The letter itself, in plain text: paragraphs separated by a blank line.
    body: str
    #: The closing lines, in order (« Cordialement, », then who signs).
    signature: tuple[str, ...]
    footer: str
    #: The `lang` of the document, so a reader's screen reader speaks the right language.
    lang: str
    #: One thing to do, as (label, http(s) address): a button under the body in the HTML
    #: part, the bare address in the plain text. A two-hundred-character link written out
    #: in the body fills eight lines of a phone; a button is one tap.
    action: tuple[str, str] | None = None

    def text(self) -> str:
        """The plain-text part: the body, the action's address, and the same signature as
        the HTML one."""
        parts = [self.body] if self.action is None else [self.body, self.action[1]]
        return "\n\n".join(parts) + "\n\n" + "\n".join(self.signature)


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _paragraphs(body: str) -> str:
    """Plain text to paragraphs, each line kept where the letter put it."""
    blocks = [block for block in body.split("\n\n") if block.strip()]
    return "".join(
        '<p style="margin:0 0 14px">'
        + "<br>".join(_escape(line) for line in block.split("\n"))
        + "</p>"
        for block in blocks
    )


def _action(look: Look, letter: Letter) -> str:
    """The letter's one action as a button, its address in small print underneath.

    ⚠️ ONLY AN http(s) ADDRESS BECOMES A LINK: anything else (`javascript:`, a typo) is left
    out rather than rendered clickable.
    """
    if letter.action is None:
        return ""
    label, url = letter.action
    if not url.lower().startswith(("https://", "http://")):
        return ""
    href = _escape(url)
    return (
        '<div style="text-align:center;margin:6px 0 18px">'
        f'<a href="{href}" style="display:inline-block;background:{look.ink};'
        "color:#ffffff;text-decoration:none;padding:12px 24px;border-radius:8px;"
        f'font-weight:bold;font-size:14px">{_escape(label)}</a></div>'
        f'<p style="margin:0 0 14px;font-size:12px;color:#94a3b8;{_BREAK_LONG_WORDS}">'
        f"{href}</p>"
    )


def _signature(letter: Letter) -> str:
    lines = [line for line in letter.signature if line.strip()]
    if not lines:
        return ""
    first, rest = lines[0], lines[1:]
    rows = [f'<p style="margin:0 0 6px">{_escape(first)}</p>'] + [
        f'<p style="margin:2px 0;font-weight:600;color:#111827">{_escape(line)}</p>'
        for line in rest
    ]
    return (
        '<div style="margin-top:20px;border-top:1px solid #e5e7eb;padding-top:12px">'
        + "".join(rows)
        + "</div>"
    )


def _header(look: Look, letter: Letter) -> str:
    """Four layouts, not one branch per look: every look is a palette on one of them."""
    brand, title = _escape(letter.brand), _escape(letter.title)
    ink, accent, soft = look.ink, look.accent, look.soft
    if look.layout == "band":
        return (
            f'<tr><td style="background:{ink};padding:18px 24px;{_BREAK_LONG_WORDS}">'
            f'<div style="color:#ffffff;font-size:17px;font-weight:bold">{brand}</div>'
            f'<div style="color:{soft};font-size:12px;margin-top:2px">{title}</div>'
            "</td></tr>"
        )
    if look.layout == "rule":
        return (
            f'<tr><td style="background:#ffffff;border-bottom:3px solid {accent};'
            f'padding:18px 24px;{_BREAK_LONG_WORDS}">'
            f'<div style="color:{ink};font-size:17px;font-weight:bold">{brand}</div>'
            f'<div style="color:{soft};font-size:12px;margin-top:2px">{title}</div>'
            "</td></tr>"
        )
    if look.layout == "crest":
        return (
            f'<tr><td style="background:#ffffff;border-bottom:3px solid {accent};'
            f'padding:22px 24px;text-align:center;{_BREAK_LONG_WORDS}">'
            f'<div style="color:{ink};font-size:18px;font-weight:bold">{brand}</div>'
            f'<div style="color:{soft};font-size:13px;margin-top:6px">{title}</div>'
            "</td></tr>"
        )
    # center: coloured banner, name centred, accent rule.
    return (
        f'<tr><td style="background:{ink};border-bottom:3px solid {accent};'
        f'padding:22px 24px;text-align:center;{_BREAK_LONG_WORDS}">'
        f'<div style="color:#ffffff;font-size:18px;font-weight:bold">{brand}</div>'
        f'<div style="color:{soft};font-size:13px;margin-top:6px">{title}</div>'
        "</td></tr>"
    )


def _footer(look: Look, letter: Letter) -> str:
    """The footer, in the header's palette.

    Light headers get a light footer: a coloured band under a white header reads as two
    different letters stapled together.
    """
    text = _escape(letter.footer)
    if look.layout in ("rule", "crest"):
        return (
            '<tr><td style="background:#f4f6fb;border-top:1px solid #e5e7eb;'
            f"padding:14px 24px;text-align:center;font-size:12px;color:#94a3b8;"
            f'{_BREAK_LONG_WORDS}">{text}</td></tr>'
        )
    return (
        f'<tr><td style="background:{look.ink};padding:14px 24px;text-align:center;'
        f'font-size:12px;color:{look.soft};{_BREAK_LONG_WORDS}">{text}</td></tr>'
    )


def render(look: Look, letter: Letter) -> str:
    """The whole HTML document of one letter, in one look.

    ⚠️ READABLE ON A PHONE: the viewport is declared (without it a phone lays the letter out
    on 980 pixels and shrinks it), the letter is at most 600 pixels wide and never wider
    than the screen, and a long word breaks instead of pushing the edge.
    """
    content = _paragraphs(letter.body) + _action(look, letter) + _signature(letter)
    body_cell = (
        '<tr><td style="padding:24px;color:#334155;font-size:14px;line-height:1.7;'
        f'{_BREAK_LONG_WORDS}">{content}</td></tr>'
    )
    bare = look.layout == "none"
    page = "#ffffff" if bare else "#f5f5f5"
    frame = (
        "background:#ffffff"
        if bare
        else "background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb"
    )
    rows = (
        body_cell if bare else _header(look, letter) + body_cell + _footer(look, letter)
    )
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{_escape(letter.lang)}">\n'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_escape(letter.title)}</title></head>\n"
        '<body style="font-family:Arial,Helvetica,sans-serif;color:#333333;margin:0;'
        f'padding:0;background:{page}">\n'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{page}">\n'
        '<tr><td align="center" style="padding:24px 12px">\n'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;width:100%;{frame}">\n'
        f"{rows}\n"
        "</table>\n</td></tr>\n</table>\n</body>\n</html>\n"
    )


__all__ = ["BUILT_IN", "LAYOUTS", "Letter", "Look", "render"]
