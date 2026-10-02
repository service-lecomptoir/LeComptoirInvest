import { describe, expect, it } from 'vitest'

import HTML from '../index.html?raw'

// The sentence a messaging app shows under a shared link is the page's `description`. On
// 2 Oct 2026 a link to Le Comptoir RH read « au meme endroit : conges... » on WhatsApp: no
// accents, an ordinary space before the colon. The same guard stands in every product of
// the range. It is a text the reader sees before the product, so it follows the screens'
// rules: it exists, it keeps its accents, and it writes `&#160;` before « : ; ? ! ».
const description = /name="description"\s+content="([^"]*)"/.exec(HTML)?.[1] ?? ''

// The words the RH sentence lost, their usual company in a French UI sentence, and the
// words of the descriptions of the range.
const UNACCENTED =
  /\b(meme|deja|etat|equipe|reglages?|parametres?|conges?|salaries?|carrieres?|durees?|sejours?|societes?|vehicules?|coproprietes?|coproprietaires?|tantiemes?|cloture|assemblee|generale?|metre|depots?|reservee|operateurs?|comptabilite|independants|liberales|fidelite|metiers?|batiment|materiel)\b/i

describe('the link preview', () => {
  it('has a description', () => {
    expect(description.length).toBeGreaterThan(20)
  })

  it('keeps its accents', () => {
    expect(description).not.toMatch(UNACCENTED)
  })

  it('puts a non-breaking space before the colon', () => {
    expect(description).not.toMatch(/ [:;?!]/)
  })
})
