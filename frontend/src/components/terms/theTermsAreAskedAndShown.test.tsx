import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import i18n from '@/i18n'
import type { TermsAcceptance, TermsDocumentStatus, TermsStatus, TermsText } from '@/api/terms'

import { UNTICKED, pendingDocument, readToTheEnd, termsBlock, termsGiven, type TermsBox, type TermsOverview } from '@/lib/terms'

import { AcceptedTermsView } from './AcceptedTerms'
import { SubprocessorsView } from './Subprocessors'
import { TermsBoxes } from './TermsBoxes'
import { TermsGateScreen } from './TermsGate'
import { TermsBody } from './TermsReader'
import SIGNUP_FORM from '../signup/SignupForm.tsx?raw'
import GATE from './TermsGate.tsx?raw'
import READER from './TermsReader.tsx?raw'
import ROUTER from '../../router.tsx?raw'
import PROFILE from '../../pages/profile/MyProfile.tsx?raw'
import BILLING from '../../pages/Billing.tsx?raw'
import PLAN_CHANGE from '../billing/PlanChangeOffer.tsx?raw'
import LANDING from '../../pages/Landing.tsx?raw'
import fr from '../../i18n/locales/fr.json'
import en from '../../i18n/locales/en.json'

/**
 * The terms of use and of sale (the manager, 2 Oct 2026): asked at the sign-up, asked again
 * at the door when a version is owed, and shown read-only in the profile.
 *
 * 🔴 WHAT IS GUARDED: the boxes start unticked and hold the button; « loading » is never
 * « no terms »; the gate shows only itself, with a way out, when something is owed, and lets
 * the application through when nothing is or the console is silent; the profile says the
 * version and the moment, opens the text, and has no « withdraw » button.
 *
 * 🔴 THE DATA PROCESSING AGREEMENT (the owner, 13 Oct 2026) follows the terms of sale on
 * every one of these paths: a box with a catalogue plan, the gate after the terms of sale,
 * its acceptance on the subscription screen, its sub-processors under its text.
 */

const CGU: TermsText = {
  kind: 'cgu', product: 'invest', audience: 'manager', version: '2026-10', language: 'fr',
  requested_language: 'fr', fell_back: false, title: "Conditions générales d'utilisation",
  body: 'Article 1. Objet', effective_from: '2026-10-01', summary_of_changes: null,
}
const CGV: TermsText = { ...CGU, kind: 'cgv', audience: 'all', version: '2026-09', title: 'Conditions générales de vente' }
const DPA: TermsText = { ...CGU, kind: 'dpa', audience: 'all', version: '2026-10', title: 'Accord de traitement des données' }
/** The markup as a reader sees it: React escapes the apostrophe. */
const render = (element: ReactElement) => renderToStaticMarkup(element).split('&#x27;').join("'")
const ready = (text: TermsText): TermsBox => ({ state: 'ready', text })
const NOTHING: TermsBox = { state: 'none' }
const BOTH = { cgu: ready(CGU), cgv: ready(CGV), dpa: NOTHING }
const ALL = { cgu: ready(CGU), cgv: ready(CGV), dpa: ready(DPA) }

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
    expect(termsBlock(BOTH, true, { cgu: true, cgv: false, dpa: false })).toBe('unticked')
    expect(termsBlock(BOTH, true, { cgu: true, cgv: true, dpa: false })).toBeNull()
    // The form's button reads that verdict, and the payload carries what was ticked.
    expect(SIGNUP_FORM).toContain('disabled={termsHold !== null}')
    expect(SIGNUP_FORM).toContain('terms: termsGiven(termBoxes, withSale, ticked, language)')
    expect(termsGiven(BOTH, true, { cgu: true, cgv: true, dpa: false }, 'fr')).toEqual({ cgu: '2026-10', cgv: '2026-09', dpa: null, language: 'fr' })
  })

  it('asks the data processing agreement beside the terms of sale, with its own sentence', async () => {
    await i18n.changeLanguage('fr')
    const html = render(<TermsBoxes boxes={ALL} withSale ticked={UNTICKED} onTick={() => undefined} />)
    expect(html.split('type="checkbox"').length - 1).toBe(3)
    expect(html).toContain("J'ai lu et j'accepte l'accord de traitement des données")
    expect(html).toContain("Lire l'accord")
    expect(html).not.toContain('checked')
    expect(termsBlock(ALL, true, { cgu: true, cgv: true, dpa: false })).toBe('unticked')
    expect(termsBlock(ALL, true, { cgu: true, cgv: true, dpa: true })).toBeNull()
    expect(termsGiven(ALL, true, { cgu: true, cgv: true, dpa: true }, 'fr')).toEqual({
      cgu: '2026-10', cgv: '2026-09', dpa: '2026-10', language: 'fr',
    })
    // A quotation takes no licence: no agreement asked, none sent.
    expect(termsBlock(ALL, false, { cgu: true, cgv: false, dpa: false })).toBeNull()
    expect(termsGiven(ALL, false, { cgu: true, cgv: true, dpa: true }, 'fr').dpa).toBeNull()
    expect(render(<TermsBoxes boxes={ALL} withSale={false} ticked={UNTICKED} onTick={() => undefined} />))
      .not.toContain('accord de traitement')
    await i18n.changeLanguage('en')
    expect(render(<TermsBoxes boxes={ALL} withSale ticked={UNTICKED} onTick={() => undefined} />))
      .toContain('I have read and accept the data processing agreement')
    await i18n.changeLanguage('fr')
  })

  it('asks no terms of sale of a quotation', () => {
    expect(termsBlock(BOTH, false, { cgu: true, cgv: false, dpa: false })).toBeNull()
    expect(termsGiven(BOTH, false, { cgu: true, cgv: true, dpa: false }, 'fr').cgv).toBeNull()
    const html = render(
      <TermsBoxes boxes={BOTH} withSale={false} ticked={UNTICKED} onTick={() => undefined} />,
    )
    expect(html).not.toContain('conditions générales de vente')
  })

  it('says nothing while loading, nothing when unpublished, and closes when unreachable', async () => {
    await i18n.changeLanguage('fr')
    const loading = { cgu: { state: 'loading' } as TermsBox, cgv: { state: 'loading' } as TermsBox, dpa: { state: 'loading' } as TermsBox }
    expect(render(<TermsBoxes boxes={loading} withSale ticked={UNTICKED} onTick={() => undefined} />)).toBe('')
    expect(termsBlock(loading, true, UNTICKED)).toBe('loading')

    const none = { cgu: NOTHING, cgv: NOTHING, dpa: NOTHING }
    expect(render(<TermsBoxes boxes={none} withSale ticked={UNTICKED} onTick={() => undefined} />)).toBe('')
    expect(termsBlock(none, true, UNTICKED)).toBeNull()

    const down = { cgu: { state: 'unavailable' } as TermsBox, cgv: ready(CGV), dpa: ready(DPA) }
    const html = render(<TermsBoxes boxes={down} withSale ticked={UNTICKED} onTick={() => undefined} />)
    expect(html).toContain('Les conditions générales ne peuvent pas être chargées pour le moment : réessayez dans quelques minutes.')
    expect(termsBlock(down, true, { cgu: true, cgv: true, dpa: true })).toBe('unavailable')
    // The agreement unreachable closes the door the same way.
    expect(termsBlock({ ...ALL, dpa: { state: 'unavailable' } }, true, { cgu: true, cgv: true, dpa: true })).toBe('unavailable')
  })
})

describe('the gate', () => {
  it('asks the terms of use first, then the terms of sale', () => {
    const both = status({ cgu: owed(), cgv: owed({ version: '2026-09', audience: 'all' }), subscriber: true })
    expect(pendingDocument(both)?.kind).toBe('cgu')
    expect(pendingDocument(status({ cgv: owed({ audience: 'all' }), subscriber: true }))?.kind).toBe('cgv')
  })

  it('asks the data processing agreement after the terms of sale, one document at a time', () => {
    const agreement = owed({ version: '2026-10', audience: 'all' })
    expect(pendingDocument(status({ cgv: owed({ audience: 'all' }), dpa: agreement, subscriber: true }))?.kind).toBe('cgv')
    const alone = pendingDocument(status({ dpa: agreement, subscriber: true }))
    expect(alone?.kind).toBe('dpa')
    expect(alone?.document.version).toBe('2026-10')
    // An older console sends no `dpa`; one that does says null to anyone but the subscriber.
    expect(pendingDocument(status({ dpa: null }))).toBeNull()
    expect(pendingDocument(status({ dpa: undefined }))).toBeNull()
  })

  it('shows the agreement with its sub-processors under it, and holds « J’accepte » the same way', async () => {
    await i18n.changeLanguage('fr')
    const page = render(
      <TermsGateScreen kind="dpa" document={owed({ audience: 'all' })} text={DPA} refusal={null}
        busy={false} onAccept={() => undefined} onSignOut={() => undefined} />,
    )
    expect(page).toContain("Merci de lire et d'accepter l'accord de traitement des données (art. 28 RGPD)")
    expect(page).toContain('Accord de traitement des données')
    expect(page).toContain('Sous-traitants ultérieurs')
    expect(page).toMatch(/<button[^>]*disabled[^>]*>J'accepte<\/button>/)
    expect(GATE).toContain("{kind === 'dpa' && <Subprocessors />}")
    expect(READER).toContain("{text.kind === 'dpa' && <Subprocessors />}")
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
    expect(newer).toContain('Mon abonnement › Gérer mon abonnement')
  })

  it('shows the agreement accepted like the terms of sale', async () => {
    await i18n.changeLanguage('fr')
    const accepted: TermsAcceptance = {
      ...entry, kind: 'dpa', audience: 'all', title: 'Accord de traitement des données', method: 'plan',
    }
    const html = render(
      <AcceptedTermsView kind="dpa" overview={overview({ history: { entries: [entry, accepted], unavailable: false } })} onRead={() => undefined} />,
    )
    expect(html).toContain('Accord de traitement des données, version 2026-10')
    expect(html).toContain('Lire ce texte')
    const none = render(
      <AcceptedTermsView kind="dpa" overview={overview()} onRead={() => undefined} />,
    )
    expect(none).toContain("Vous n'avez encore accepté aucune version de l'accord de traitement des données.")
  })

  it('is in the profile of every account that accepts, and the terms of sale on the subscription screen', () => {
    expect(PROFILE).toContain("{role !== 'admin' && <TermsOfUseSection />}")
    expect(BILLING).toContain('{subscriber && <AcceptedTerms kind="cgv" overview={terms} />}')
    expect(BILLING).toContain('{subscriber && <AcceptedTerms kind="dpa" overview={terms} />}')
    // The agreement's box: asked only when the status names a published version, ticked
    // beside the terms of sale, and its version sent with the plan.
    expect(BILLING).toContain('const dpaVersion = terms?.status?.dpa?.version ?? null')
    expect(BILLING).toContain("{ cgv: versionTicked('cgv'), dpa: versionTicked('dpa'), language }")
    expect(BILLING).toContain("dpa: 'terms.signup.acceptDpa'")
    expect(PLAN_CHANGE).toContain('dpa: ticked?.dpa')
    // No plan is taken while the terms of sale are owed and unticked (PlanChangeOffer).
    expect(BILLING).toContain('blocked={saleHold !== null}')
  })
})

describe('the sub-processors', () => {
  const row = {
    name: 'OVHcloud', service: 'Hébergement', data: 'Toutes les données', location: 'France',
    safeguards: null, products_label: 'Tous les produits', website: null,
    effective_from: '2026-01-01', ended_on: null,
  }

  it('lists who, for what and where, then the additions announced with their date', async () => {
    await i18n.changeLanguage('fr')
    const html = render(
      <SubprocessorsView
        found={{
          state: 'ready',
          list: {
            current: [row],
            announced: [{ ...row, name: 'Brevo', service: 'Envoi des e-mails', effective_from: '2026-11-15' }],
            contact_email: 'dpo@example.org',
          },
        }}
      />,
    )
    expect(html).toContain('Sous-traitants ultérieurs')
    expect(html).toContain('OVHcloud')
    expect(html).toContain('Hébergement, France')
    expect(html).toContain('Ajouts annoncés')
    expect(html).toContain('Brevo')
    expect(html).toContain('À partir du 15/11/2026')
    expect(html).toContain('Pour vous opposer à un ajout, écrivez à dpo@example.org.')
    // The explanation lives in a bubble, not under the title.
    expect(html).toContain('aria-describedby')
  })

  it('says a list it cannot read is unavailable, never « no sub-processor »', async () => {
    await i18n.changeLanguage('fr')
    const html = render(<SubprocessorsView found={{ state: 'unavailable' }} />)
    expect(html).toContain('La liste des sous-traitants ultérieurs ne peut pas être chargée pour le moment')
    expect(html).not.toContain("Aucun sous-traitant ultérieur n'est déclaré.")
    const empty = render(
      <SubprocessorsView found={{ state: 'ready', list: { current: [], announced: [], contact_email: null } }} />,
    )
    expect(empty).toContain("Aucun sous-traitant ultérieur n'est déclaré.")
    expect(empty).not.toContain('@')
  })
})

describe('the public page', () => {
  it('says who is the controller and where the sub-processors are read, in every language', () => {
    expect(LANDING).toContain("'processing',")
    expect(fr.landing.faq.items.processing.a).toContain('accord de traitement des données')
    expect(fr.landing.faq.items.processing.a).toContain('sous-traitants ultérieurs')
    expect(en.landing.faq.items.processing.a).toContain('data processing agreement')
    expect(en.landing.faq.items.processing.a).toContain('sub-processors')
  })
})
