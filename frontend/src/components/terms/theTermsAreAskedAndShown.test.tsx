import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import i18n from '@/i18n'
import type { TermsAcceptance, TermsDocumentStatus, TermsStatus, TermsText } from '@/api/terms'

import { UNTICKED, pendingDocument, readToTheEnd, termsBlock, termsGiven, type TermsBox, type TermsOverview } from '@/lib/terms'

import { AcceptedTermsView } from './AcceptedTerms'
import { TermsBoxes } from './TermsBoxes'
import { TermsGateScreen } from './TermsGate'
import { TermsBody } from './TermsReader'
import SIGNUP_FORM from '../signup/SignupForm.tsx?raw'
import GATE from './TermsGate.tsx?raw'
import READER from './TermsReader.tsx?raw'
import ROUTER from '../../router.tsx?raw'
import PROFILE from '../../pages/profile/MyProfile.tsx?raw'
import BILLING from '../../pages/Billing.tsx?raw'

/**
 * The terms of use and of sale (the manager, 2 Oct 2026): asked at the sign-up, asked again
 * at the door when a version is owed, and shown read-only in the profile.
 *
 * 🔴 WHAT IS GUARDED: the boxes start unticked and hold the button; « loading » is never
 * « no terms »; the gate shows only itself, with a way out, when something is owed, and lets
 * the application through when nothing is or the console is silent; the profile says the
 * version and the moment, opens the text, and has no « withdraw » button.
 */

const CGU: TermsText = {
  kind: 'cgu', product: 'invest', audience: 'manager', version: '2026-10', language: 'fr',
  requested_language: 'fr', fell_back: false, title: "Conditions générales d'utilisation",
  body: 'Article 1. Objet', effective_from: '2026-10-01', summary_of_changes: null,
}
const CGV: TermsText = { ...CGU, kind: 'cgv', audience: 'all', version: '2026-09', title: 'Conditions générales de vente' }
/** The markup as a reader sees it: React escapes the apostrophe. */
const render = (element: ReactElement) => renderToStaticMarkup(element).split('&#x27;').join("'")
const ready = (text: TermsText): TermsBox => ({ state: 'ready', text })
const BOTH = { cgu: ready(CGU), cgv: ready(CGV) }

const owed = (patch: Partial<TermsDocumentStatus> = {}): TermsDocumentStatus => ({
  version: '2026-11', product: 'invest', audience: 'manager', effective_from: '2026-11-01',
  accepted_version: null, accepted_at: null, up_to_date: false, anything_to_accept: true,
  pending: true, ...patch,
})
const status = (patch: Partial<TermsStatus> = {}): TermsStatus => ({
  cgu: owed({ pending: false, up_to_date: true }), cgv: null, unavailable: false, subscriber: false, ...patch,
})

describe('the sign-up boxes', () => {
  it('start unticked and hold the button until every published text is ticked', async () => {
    await i18n.changeLanguage('fr')
    const html = render(
      <TermsBoxes boxes={BOTH} withSale ticked={UNTICKED} onTick={() => undefined} />,
    )
    expect(html).toContain("J'accepte les conditions générales d'utilisation")
    expect(html).toContain("J'accepte les conditions générales de vente")
    expect(html.split('type="checkbox"').length - 1).toBe(2)
    expect(html).not.toContain('checked')
    expect(html).toContain('Lire les conditions')
    expect(html).toContain('Obligatoire pour créer votre compte. Version 2026-10, en vigueur le 01/10/2026.')

    expect(termsBlock(BOTH, true, UNTICKED)).toBe('unticked')
    expect(termsBlock(BOTH, true, { cgu: true, cgv: false })).toBe('unticked')
    expect(termsBlock(BOTH, true, { cgu: true, cgv: true })).toBeNull()
    // The form's button reads that verdict, and the payload carries what was ticked.
    expect(SIGNUP_FORM).toContain('disabled={termsHold !== null}')
    expect(SIGNUP_FORM).toContain('terms: termsGiven(termBoxes, withSale, ticked, language)')
    expect(termsGiven(BOTH, true, { cgu: true, cgv: true }, 'fr')).toEqual({ cgu: '2026-10', cgv: '2026-09', language: 'fr' })
  })

  it('asks no terms of sale of a quotation', () => {
    expect(termsBlock(BOTH, false, { cgu: true, cgv: false })).toBeNull()
    expect(termsGiven(BOTH, false, { cgu: true, cgv: true }, 'fr').cgv).toBeNull()
    const html = render(
      <TermsBoxes boxes={BOTH} withSale={false} ticked={UNTICKED} onTick={() => undefined} />,
    )
    expect(html).not.toContain('conditions générales de vente')
  })

  it('says nothing while loading, nothing when unpublished, and closes when unreachable', async () => {
    await i18n.changeLanguage('fr')
    const loading = { cgu: { state: 'loading' } as TermsBox, cgv: { state: 'loading' } as TermsBox }
    expect(render(<TermsBoxes boxes={loading} withSale ticked={UNTICKED} onTick={() => undefined} />)).toBe('')
    expect(termsBlock(loading, true, UNTICKED)).toBe('loading')

    const none = { cgu: { state: 'none' } as TermsBox, cgv: { state: 'none' } as TermsBox }
    expect(render(<TermsBoxes boxes={none} withSale ticked={UNTICKED} onTick={() => undefined} />)).toBe('')
    expect(termsBlock(none, true, UNTICKED)).toBeNull()

    const down = { cgu: { state: 'unavailable' } as TermsBox, cgv: ready(CGV) }
    const html = render(<TermsBoxes boxes={down} withSale ticked={UNTICKED} onTick={() => undefined} />)
    expect(html).toContain('Les conditions générales ne peuvent pas être chargées pour le moment : réessayez dans quelques minutes.')
    expect(termsBlock(down, true, { cgu: true, cgv: true })).toBe('unavailable')
  })
})

describe('the gate', () => {
  it('asks the terms of use first, then the terms of sale', () => {
    const both = status({ cgu: owed(), cgv: owed({ version: '2026-09', audience: 'all' }), subscriber: true })
    expect(pendingDocument(both)?.kind).toBe('cgu')
    expect(pendingDocument(status({ cgv: owed({ audience: 'all' }), subscriber: true }))?.kind).toBe('cgv')
  })

  it('lets the application through when nothing is owed or the console is silent', () => {
    expect(pendingDocument(status())).toBeNull()
    expect(pendingDocument(status({ cgu: null, unavailable: true }))).toBeNull()
    expect(pendingDocument(null)).toBeNull()
    expect(GATE).toContain('if (!owed || textFailed) return <>{children}</>')
    expect(ROUTER).toMatch(/<TermsGate>\s*<Outlet \/>\s*<\/TermsGate>/)
  })

  it('shows only the question, with the text, « J’accepte » and a way out', async () => {
    await i18n.changeLanguage('fr')
    const first = render(
      <TermsGateScreen kind="cgu" document={owed()} text={{ ...CGU, version: '2026-11' }} refusal={null}
        busy={false} onAccept={() => undefined} onSignOut={() => undefined} />,
    )
    expect(first).toContain('Avant de commencer')
    expect(first).toContain("Merci de lire et d'accepter les conditions générales d'utilisation.")
    expect(first).toContain('Article 1. Objet')
    expect(first).toContain("J'accepte")
    expect(first).toContain('Se déconnecter')

    const changed = render(
      <TermsGateScreen kind="cgu" document={owed({ accepted_version: '2026-10' })}
        text={{ ...CGU, version: '2026-11', fell_back: true, summary_of_changes: 'Article 4 réécrit.' }}
        refusal="Les conditions ont changé." busy={false} onAccept={() => undefined} onSignOut={() => undefined} />,
    )
    expect(changed).toContain('Nos conditions ont changé')
    expect(changed).toContain('Article 4 réécrit.')
    expect(changed).toContain("Ce texte n'existe pas encore dans votre langue : il est affiché en français.")
    expect(changed).toContain('Les conditions ont changé.')
  })

  it('holds « J’accepte » until the text is read to the end (10 Oct 2026)', async () => {
    await i18n.changeLanguage('fr')
    const page = render(
      <TermsGateScreen kind="cgu" document={owed()} text={{ ...CGU, version: '2026-11' }} refusal={null}
        busy={false} onAccept={() => undefined} onSignOut={() => undefined} />,
    )
    expect(page).toContain("Faites défiler le texte jusqu'à la fin pour pouvoir l'accepter.")
    expect(page).toMatch(/<button[^>]*disabled[^>]*>J'accepte<\/button>/)
    // The bottom of the box, within a few pixels, or a text that fits whole.
    expect(readToTheEnd(0, 300, 1200)).toBe(false)
    expect(readToTheEnd(896, 300, 1200)).toBe(true)
    expect(readToTheEnd(0, 300, 280)).toBe(true)
    // Read from the source: the box's check runs in an effect, which a static render does not run.
    expect(GATE).toContain('<TermsBody text={text} onReadToEnd={() => setReadText(text)} />')
    expect(GATE).toContain('disabled={!text || !read}')
    expect(READER).toContain('onScroll={scroll ? check : undefined}')
    expect(READER).toMatch(/useEffect\(\(\) => \{\s*if \(scroll\) check\(\)\s*\}, \[text, scroll, check\]\)/)
    // The box takes the keyboard, so the end can be reached without a mouse.
    expect(render(<TermsBody text={CGU} onReadToEnd={() => undefined} />)).toContain('tabindex="0"')
  })

  it('leaves « J’accepte » free for a short text that fits whole in the box', () => {
    // No scroll can ever come on a box that does not overflow: the box's check on mount is
    // the only signal. React runs that child effect BEFORE any effect of the gate, so a
    // « read » flag reset by an effect of the gate would undo it and lock the button for
    // good. What was read is the text itself; a new text is simply not that one.
    expect(readToTheEnd(0, 400, 120)).toBe(true)
    expect(GATE).toContain('const read = !!text && readText === text')
    expect(GATE).not.toMatch(/setRead\w*\((false|null)\)/)
    expect(GATE).not.toMatch(/useEffect\([^)]*setRead/)
  })
})

describe('the text itself', () => {
  const MARKDOWN = '## Article 1. Objet\n\n**Le service** est fourni tel quel.'

  it('is laid out from the HTML Alice serves: headings and bold are elements, no « ** »', () => {
    const html = render(
      <TermsBody
        text={{
          ...CGU,
          body: MARKDOWN,
          body_html: '<h2>Article 1. Objet</h2>\n<p><strong>Le service</strong> est fourni tel quel.</p>',
        }}
      />,
    )
    expect(html).toContain('<h2>Article 1. Objet</h2>')
    expect(html).toContain('<strong>Le service</strong>')
    expect(html).not.toContain('**')
    expect(html).not.toContain('##')
    expect(html).not.toContain('whitespace-pre-wrap')
    expect(html).toContain('[&amp;_h2]:font-semibold')
  })

  it('falls back to the Markdown as written while Alice serves no HTML', () => {
    const html = render(<TermsBody text={{ ...CGU, body: MARKDOWN }} />)
    expect(html).toContain('whitespace-pre-wrap')
    expect(html).toContain('## Article 1. Objet')
    expect(html).toContain('**Le service** est fourni tel quel.')
    expect(html).not.toContain('<h2>')
    expect(html).not.toContain('<strong>')
  })
})

describe('the profile section', () => {
  const entry: TermsAcceptance = {
    kind: 'cgu', product: 'invest', audience: 'investor', version: '2026-10', language: 'fr',
    title: "Conditions générales d'utilisation", effective_from: '2026-10-01', method: 'update',
    accepted_at: '2026-10-02T07:30:00+00:00',
  }
  const overview = (patch: Partial<TermsOverview> = {}): TermsOverview => ({
    history: { entries: [entry], unavailable: false }, status: status(), ...patch,
  })

  it('shows the version, the date with its time and the reader, and no withdraw button', async () => {
    await i18n.changeLanguage('fr')
    const html = render(<AcceptedTermsView kind="cgu" overview={overview()} onRead={() => undefined} />)
    expect(html).toContain("Conditions d'utilisation")
    expect(html).toContain('version 2026-10')
    expect(html).toMatch(/Acceptée le 02\/10\/2026( à)?,? \d{2}:\d{2}/)
    expect(html).toContain('Lire ce texte')
    expect(html.split('<button').length - 1).toBe(1)
    expect(html).not.toMatch(/retirer mon accord|withdraw/i)
    expect(html).toContain('Lecture seule. Pour retirer votre accord, fermez votre compte : demandez-le')
  })

  it("names Alice's contact address when one is known, and none otherwise", async () => {
    await i18n.changeLanguage('fr')
    const known = render(
      <AcceptedTermsView kind="cgu" overview={overview()} onRead={() => undefined} contact="ecrire@example.org" />,
    )
    expect(known).toContain('Vous pouvez aussi nous écrire à ecrire@example.org.')
    const unknown = render(<AcceptedTermsView kind="cgu" overview={overview()} onRead={() => undefined} />)
    expect(unknown).not.toContain('@')
    expect(unknown).not.toContain('écrire à')
  })

  it('says plainly when nothing was accepted, and when a newer version is owed', async () => {
    await i18n.changeLanguage('fr')
    const none = render(
      <AcceptedTermsView kind="cgu" overview={overview({ history: { entries: [], unavailable: false } })} onRead={() => undefined} />,
    )
    expect(none).toContain("Vous n'avez encore accepté aucune version des conditions générales d'utilisation.")
    const newer = render(
      <AcceptedTermsView kind="cgu" overview={overview({ status: status({ cgu: owed({ accepted_version: '2026-10' }), subscriber: true }) })} onRead={() => undefined} />,
    )
    expect(newer).toContain('Une nouvelle version 2026-11 est en vigueur depuis le 01/11/2026.')
    expect(newer).toContain('Abonnement › Gérer mon abonnement')
  })

  it('is in the profile of every account that accepts, and the terms of sale on the subscription screen', () => {
    expect(PROFILE).toContain("{role !== 'admin' && <TermsOfUseSection />}")
    expect(BILLING).toContain('{subscriber && <AcceptedTerms kind="cgv" overview={terms} />}')
    expect(BILLING).toContain('disabled={busy === plan.id || saleHold !== null}')
  })
})
