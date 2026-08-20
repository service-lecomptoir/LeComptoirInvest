"""The annual statement as a document that LEAVES.

🔴 WHY A PDF AND NOT A SCREEN. Everything else this product renders is read by somebody who
is signed in, on a page that can be reloaded. This one is attached to a tax return, or
forwarded to an accountant, or filed for seven years. It is read by people who never touch
the product, long after the year it describes, and it can never be corrected in place.

🔴 WHICH MAKES THE LANGUAGE A PROPERTY OF THE READER, NOT OF THE CALLER. `i18n.use_lang`
exists for exactly this: a manager clicks, an investor reads. This module is its third
caller, after the capital-call notice and the statement endpoint. Rendering from the
caller's `Accept-Language` would put French headings on a British investor's tax file, and
nothing would look wrong, because the figures are identical either way.

⚠️ THE ENGINE IS `xhtml2pdf`, THE SAME AS THE SISTER PRODUCT, and that is deliberate. Its
rival needs Pango, Cairo and HarfBuzz installed in the image; this one is pure Python and
runs on a developer's Windows machine as it runs in the container. A document that only the
server can produce is a document nobody debugs.

⚠️ AND THE VALUES ARE ESCAPED. An investor is named by whoever created their file, and a
company name carrying `&` or `<` would silently break the layout of a document that leaves
the building. Autoescaping is on.
"""

from __future__ import annotations

import io
from decimal import Decimal

from jinja2 import Environment, select_autoescape

from app.core import i18n

from app.services.statement_service import Statement

#: A4, sober, and printable in black and white: this is filed and photocopied, not admired.
_TEMPLATE = """
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      @page { size: A4; margin: 1.8cm 1.6cm; }
      body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #14213d; }
      h1 { font-size: 15pt; margin: 0 0 2mm 0; }
      .meta { font-size: 9pt; color: #52606d; margin-bottom: 6mm; }
      .meta strong { color: #14213d; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 5mm; }
      th { background: #eef2f7; text-align: left; font-size: 8.5pt;
           padding: 2mm; border-bottom: 0.6pt solid #b9c4d0; }
      td { padding: 2mm; border-bottom: 0.4pt solid #e2e8f0; font-size: 9.5pt; }
      td.n, th.n { text-align: right; }
      tr.total td { font-weight: bold; background: #f7f9fc; }
      h2 { font-size: 11pt; margin: 5mm 0 2mm 0; }
      .note { font-size: 8pt; color: #52606d; line-height: 1.4; }
      .empty { font-size: 9.5pt; color: #52606d; padding: 4mm 0; }
    </style>
  </head>
  <body>
    <h1>{{ labels.title }}</h1>
    <div class="meta">
      <strong>{{ labels.for_investor }} :</strong> {{ statement.investor_name }}<br />
      {% if issuer %}<strong>{{ labels.issued_by }} :</strong> {{ issuer }}{% endif %}
    </div>

    {% if not statement.lines %}
      <p class="empty">{{ labels.nothing }}</p>
    {% else %}
    <table>
      <thead>
        <tr>
          <th>{{ labels.instrument }}</th>
          <th>{{ labels.currency }}</th>
          <th class="n">{{ labels.income_gross }}</th>
          <th class="n">{{ labels.withholding }}</th>
          <th class="n">{{ labels.income_net }}</th>
          <th class="n">{{ labels.capital_repaid }}</th>
          <th class="n">{{ labels.received }}</th>
        </tr>
      </thead>
      <tbody>
        {% for line in statement.lines %}
        <tr>
          <td>{{ line.instrument }}</td>
          <td>{{ line.currency }}</td>
          <td class="n">{{ money(line.income_gross) }}</td>
          <td class="n">{{ money(line.withholding) }}</td>
          <td class="n">{{ money(line.income_net) }}</td>
          <td class="n">{{ money(line.capital_repaid) }}</td>
          <td class="n">{{ money(line.received) }}</td>
        </tr>
        {% endfor %}
        {% for currency, block in totals.items() %}
        <tr class="total">
          <td>{{ labels.totals }}</td>
          <td>{{ currency }}</td>
          <td class="n">{{ money(block.income_gross) }}</td>
          <td class="n">{{ money(block.withholding) }}</td>
          <td class="n">{{ money(block.income_gross - block.withholding) }}</td>
          <td class="n">{{ money(block.capital_repaid) }}</td>
          <td class="n">{{ money(block.received) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}

    {% if statement.capital_at_work %}
    <h2>{{ labels.capital_at_work }}</h2>
    <table>
      <tbody>
        {% for currency, amount in statement.capital_at_work.items() %}
        <tr><td>{{ currency }}</td><td class="n">{{ money(amount) }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}

    {#- 🔴 APART, AND NEVER ADDED IN. Money decided and still on the fund's account is not
        income the investor received; putting it in the totals would make this document the
        evidence for a return they should not have filed. -#}
    {% if statement.decided_not_paid %}
    <h2>{{ labels.decided_not_paid }}</h2>
    <table>
      <tbody>
        {% for currency, amount in statement.decided_not_paid.items() %}
        <tr><td>{{ currency }}</td><td class="n">{{ money(amount) }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="note">{{ labels.decided_not_paid_note }}</p>
    {% endif %}
  </body>
</html>
"""


def _money(value: Decimal) -> str:
    """Two decimals, grouped, and no currency sign.

    ⚠️ THE CURRENCY HAS ITS OWN COLUMN, on purpose. A statement can carry euros and dollars
    on the same page, and gluing a sign onto every figure is how a reader adds two of them
    together. Here the amount is a number and the currency is a heading.

    🔴 AND THE SEPARATORS FOLLOW THE READER, like every other choice in this document.
    « 1 234,56 » and « 1,234.56 » are the same amount; read under the wrong convention,
    « 1,234 » is either a thousand or one and a bit. On a document somebody files with a
    tax authority that is not a cosmetic difference, and getting it wrong looks like
    nothing at all.
    """
    text = f"{Decimal(value):,.2f}"
    if i18n.current_lang() == "en":
        return text
    return text.replace(",", " ").replace(".", ",")


def render_html(statement: Statement, labels: dict, *, issuer: str = "") -> str:
    """The document as HTML, in the language currently in force.

    ⚠️ IT DOES NOT OPEN `use_lang` ITSELF, and that is deliberate: `labels` is already
    built, and a second language switch here could disagree with the one that built them.
    One decision, taken by the caller, applied to the whole document.

    🔴 `issuer` IS THE INSTALLATION'S OWN SENDING IDENTITY, the one a manager set in the
    console, and it is EMPTY when they never did. It is not derived, not guessed, and above
    all not borrowed from a fund: an investor's statement can span several vehicles, and
    naming one of them as the issuer would attribute the whole document to a fund that paid
    part of it. An absent line is a gap; a wrong one is a false record.
    """
    env = Environment(autoescape=select_autoescape(default_for_string=True))
    template = env.from_string(_TEMPLATE)
    return template.render(
        statement=statement,
        labels=labels,
        totals=statement.totals_by_currency(),
        issuer=issuer,
        money=_money,
    )


def render_pdf(statement: Statement, labels: dict, *, issuer: str = "") -> bytes:
    """The bytes an investor files. Raises rather than returning an empty document.

    🔴 A PDF THAT FAILED TO BUILD MUST NOT BE SERVED AS ZERO BYTES. The browser would
    download it, the reader would open nothing, and they would conclude the fund paid them
    nothing that year. An error the manager sees is a retry; a blank statement is a belief.
    """
    from xhtml2pdf import pisa

    buffer = io.BytesIO()
    result = pisa.CreatePDF(
        render_html(statement, labels, issuer=issuer),
        dest=buffer,
        encoding="utf-8",
    )
    if result.err:
        raise RuntimeError(f"PDF generation failed (code {result.err})")
    return buffer.getvalue()
