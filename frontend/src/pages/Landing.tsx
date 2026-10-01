import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, ArrowDownLeft, ArrowUpRight, Mail, Menu, Minus, Plus, Scale, X } from 'lucide-react'
import i18n from '@/i18n'
import { GUIDE_SECTIONS, type GuideCard } from '@/lib/guide'
import { LogoMark } from '@/components/common/Logo'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { PlanOffer } from '@/pages/Pricing'

/**
 * The public home page, served at `/` to a visitor (a signed-in reader gets their home
 * there, as before). Laid out like Le Comptoir Immo's: a sticky header with four anchors,
 * the hero, how it works, the features, the pricing and the questions.
 *
 * 🔴 EVERY SENTENCE IS THE PRODUCT'S OWN. The features are the GUIDE's cards (`lib/guide`),
 * which a guard ties to the router: a screen added or removed changes this page with it,
 * and nothing here describes a screen that does not exist. The plans are the console's,
 * through the same `PlanOffer` the pricing page draws. The journey of « Comment ça marche »
 * is the sign-up's (`SignupForm`, the console's double opt-in, `SetPassword`), and each
 * answer of the FAQ points at the code that makes it true (see the catalogue's
 * `landing.faq.items`).
 */

/** The four anchors, in the order of the page. The addresses are English: an anchor is a URL. */
const NAV = [
  { href: '#how-it-works', key: 'landing.nav.howItWorks' },
  { href: '#features', key: 'landing.nav.features' },
  { href: '#pricing', key: 'landing.nav.pricing' },
  { href: '#faq', key: 'landing.nav.faq' },
]

const STEPS = ['1', '2', '3']

/** The questions, in the order they are read. Their answers live in the catalogue. */
const FAQ_KEYS = [
  'who',
  'investors',
  'bank',
  'currencies',
  'security',
  'audit',
  'billing',
  'demo',
  'languages',
]

/** The product's contact address, the one its refusals already give (`api/v1/public.py`). */
const CONTACT_EMAIL = 'contact@lecomptoir.services'

/** The four movements the product reconciles, as the hero card names them. */
const MOVEMENTS = [
  { key: 'committed', icon: Scale },
  { key: 'called', icon: ArrowUpRight },
  { key: 'received', icon: ArrowDownLeft },
  { key: 'paid', icon: ArrowRight },
]

function Brand() {
  const { t } = useTranslation()
  return (
    <span className="flex shrink-0 items-center gap-2.5">
      <LogoMark size={32} className="shrink-0 rounded-md text-brand-teal" />
      <span className="whitespace-nowrap text-[15px] font-semibold text-brand-navy">{t('brand.full')}</span>
    </span>
  )
}

function Header({ onSignup }: { onSignup: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <header className="sticky top-0 z-40 border-b border-gray-100 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <a href="#top" onClick={() => setOpen(false)} className="min-w-0">
          <Brand />
        </a>

        {/* Under `lg` the anchors and the buttons do not fit on one line: a menu, rather than
            labels broken in two. */}
        <nav className="hidden items-center gap-6 whitespace-nowrap lg:flex">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="text-sm text-gray-600 hover:text-gray-900">
              {t(n.key)}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-2.5 whitespace-nowrap lg:flex">
          <LanguageSwitcher />
          <Link to="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100">
            {t('pricing.signIn')}
          </Link>
          <button
            type="button"
            onClick={onSignup}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-navy px-4 py-2 text-sm font-semibold text-white hover:bg-brand-navy-light"
          >
            {t('signup.title')} <ArrowRight size={15} />
          </button>
        </div>

        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="-mr-2 rounded-lg p-2 text-gray-700 hover:bg-gray-100 lg:hidden"
          aria-label={open ? t('common.closeMenu') : t('common.openMenu')}
          aria-expanded={open}
        >
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {open && (
        <div className="border-t border-gray-100 bg-white lg:hidden">
          <nav className="flex flex-col gap-1 px-4 py-3">
            {NAV.map((n) => (
              <a
                key={n.href}
                href={n.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                {t(n.key)}
              </a>
            ))}
            <div className="px-3 py-2.5">
              <LanguageSwitcher />
            </div>
            <Link
              to="/login"
              onClick={() => setOpen(false)}
              className="rounded-lg px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              {t('pricing.signIn')}
            </Link>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                onSignup()
              }}
              className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-brand-navy px-3 py-2.5 text-sm font-semibold text-white"
            >
              {t('signup.title')} <ArrowRight size={15} />
            </button>
          </nav>
        </div>
      )}
    </header>
  )
}

function Hero({ onSignup }: { onSignup: () => void }) {
  const { t } = useTranslation()
  return (
    <section
      id="top"
      className="relative overflow-hidden bg-gradient-to-br from-brand-navy to-brand-navy-light"
    >
      <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-teal opacity-20 blur-3xl" />
      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 sm:py-24 lg:grid-cols-2">
        <div className="text-center lg:text-left">
          <span className="mb-6 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white/90">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-orange" /> {t('landing.hero.badge')}
          </span>
          <h1 className="text-3xl font-bold leading-tight text-white sm:text-5xl">{t('landing.hero.title')}</h1>
          <p className="mx-auto mt-5 max-w-xl text-base text-blue-100 sm:text-lg lg:mx-0">{t('landing.hero.subtitle')}</p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row lg:justify-start">
            <button
              type="button"
              onClick={onSignup}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-brand-orange px-6 py-3 text-sm font-semibold text-white shadow-lg hover:opacity-90 sm:w-auto"
            >
              {t('signup.title')} <ArrowRight size={16} />
            </button>
            <a
              href="#pricing"
              className="inline-flex w-full items-center justify-center rounded-xl border border-white/30 px-6 py-3 text-sm font-semibold text-white hover:bg-white/10 sm:w-auto"
            >
              {t('login.seePricing')}
            </a>
          </div>
        </div>

        <div className="mx-auto w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl ring-1 ring-black/5 lg:max-w-none">
          <p className="text-sm font-semibold text-brand-navy">{t('landing.movements.title')}</p>
          <ul className="mt-4 space-y-3">
            {MOVEMENTS.map(({ key, icon: Icon }) => (
              <li key={key} className="flex items-start gap-3 rounded-xl border border-gray-100 p-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-teal/10 text-brand-teal">
                  <Icon size={16} />
                </span>
                <span className="min-w-0 text-sm text-gray-700">{t(`landing.movements.${key}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function HowItWorks() {
  const { t } = useTranslation()
  return (
    <section id="how-it-works" className="scroll-mt-16 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <h2 className="text-2xl font-bold text-brand-navy sm:text-3xl">{t('landing.how.title')}</h2>
          <p className="mt-3 text-gray-500">{t('landing.how.subtitle')}</p>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {STEPS.map((n) => (
            <div key={n} className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-navy font-bold text-white">
                {n}
              </div>
              <h3 className="mb-1.5 font-semibold text-gray-900">{t(`landing.how.steps.${n}.title`)}</h3>
              <p className="text-sm leading-relaxed text-gray-500">{t(`landing.how.steps.${n}.text`)}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/** The screens of the menu, by audience, from the guide: the account's own screens (profile,
 *  subscription) are not features to sell and stay out. */
const ACCOUNT_SECTION = 'guide.sections.account'
const FEATURE_GROUPS: { key: string; cards: GuideCard[] }[] = (['fund', 'investor'] as const).map((audience) => ({
  key: `landing.features.${audience}`,
  cards: GUIDE_SECTIONS.filter((section) => section.key !== ACCOUNT_SECTION)
    .flatMap((section) => section.cards)
    .filter((card) => card.audience === audience),
}))

function Features() {
  const { t } = useTranslation()
  return (
    <section id="features" className="scroll-mt-16 bg-gray-50 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <h2 className="text-2xl font-bold text-brand-navy sm:text-3xl">{t('landing.features.title')}</h2>
          <p className="mt-3 text-gray-500">{t('landing.features.subtitle')}</p>
        </div>
        <div className="space-y-12">
          {FEATURE_GROUPS.map((group) => (
            <div key={group.key}>
              <h3 className="mb-5 text-sm font-semibold text-gray-500">{t(group.key)}</h3>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {group.cards.map((card) => (
                  <div key={card.id} className="rounded-2xl border border-gray-100 bg-white p-6">
                    <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-teal/10 text-brand-teal">
                      <card.icon size={20} />
                    </div>
                    <h4 className="mb-1.5 font-semibold text-gray-900">{t(card.title)}</h4>
                    <p className="text-sm leading-relaxed text-gray-500">{t(`guide.cards.${card.id}.what`)}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function PricingSection({ chosen, open }: { chosen: string | null; open: (plan: string) => void }) {
  const { t } = useTranslation()
  return (
    <section id="pricing" className="scroll-mt-16 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto mb-10 max-w-2xl text-center">
          <h2 className="text-2xl font-bold text-brand-navy sm:text-3xl">{t('pricing.headline')}</h2>
          <p className="mt-3 text-gray-500">{t('pricing.lead')}</p>
        </div>
        <PlanOffer chosen={chosen} setChosen={open} />
      </div>
    </section>
  )
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="overflow-hidden rounded-xl border border-gray-100 bg-white">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-gray-900">{q}</span>
        <span className="shrink-0 text-gray-400">{open ? <Minus size={18} /> : <Plus size={18} />}</span>
      </button>
      {open && <p className="-mt-1 px-5 pb-4 text-sm leading-relaxed text-gray-500">{a}</p>}
    </div>
  )
}

function Faq() {
  const { t } = useTranslation()
  return (
    <section id="faq" className="scroll-mt-16 bg-gray-50 py-20 sm:py-24">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <div className="mb-14 text-center">
          <h2 className="text-2xl font-bold text-brand-navy sm:text-3xl">{t('landing.faq.title')}</h2>
          <p className="mt-3 text-gray-500">{t('landing.faq.subtitle')}</p>
        </div>
        <div className="space-y-3">
          {FAQ_KEYS.map((k) => (
            <FaqItem key={k} q={t(`landing.faq.items.${k}.q`)} a={t(`landing.faq.items.${k}.a`)} />
          ))}
        </div>
        <div className="mt-10 text-center">
          <p className="text-sm text-gray-500">{t('landing.faq.another')}</p>
          {/* A CONTACT gesture, not a sign-up one (Le Comptoir Immo, 4 Sept): a visitor with a
              question is not asked for their company. */}
          <a
            href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(t('landing.faq.mailSubject'))}`}
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-brand-navy px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-navy-light"
          >
            <Mail size={15} /> {t('landing.faq.contact')}
          </a>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  const { t } = useTranslation()
  return (
    <footer className="border-t border-gray-100 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 sm:flex-row sm:px-6">
        <Brand />
        <p className="text-center text-xs text-gray-400">
          © {new Date().getFullYear()} {t('brand.full')}
        </p>
        <Link to="/login" className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-navy">
          {t('pricing.signIn')} <ArrowRight size={14} />
        </Link>
      </div>
    </footer>
  )
}

/**
 * The tab title, the description and the FAQ as structured data, set while the page is
 * shown and taken back when it is left (the signed-in screens name their own tabs).
 *
 * ⚠️ `i18n.language` IS A DEPENDENCY: switching language retranslates the page, and the tab
 * and the description follow it.
 */
function useLandingSeo(language: string) {
  useEffect(() => {
    const title = i18n.t('landing.seo.title')
    const desc = i18n.t('landing.seo.desc')
    const prevTitle = document.title
    document.title = title

    const created: HTMLElement[] = []
    const upsertMeta = (attr: 'name' | 'property', key: string, content: string) => {
      let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
      if (!el) {
        el = document.createElement('meta')
        el.setAttribute(attr, key)
        document.head.appendChild(el)
        created.push(el)
      }
      el.setAttribute('content', content)
    }
    upsertMeta('name', 'description', desc)
    upsertMeta('property', 'og:title', title)
    upsertMeta('property', 'og:description', desc)
    upsertMeta('property', 'og:type', 'website')
    upsertMeta('property', 'og:locale', language.startsWith('en') ? 'en_GB' : 'fr_FR')
    upsertMeta('property', 'og:site_name', 'Le Comptoir Invest')

    const ld = document.createElement('script')
    ld.type = 'application/ld+json'
    ld.textContent = JSON.stringify([
      {
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        name: 'Le Comptoir Invest',
        applicationCategory: 'BusinessApplication',
        operatingSystem: 'Web',
        description: desc,
      },
      {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: FAQ_KEYS.map((k) => ({
          '@type': 'Question',
          name: i18n.t(`landing.faq.items.${k}.q`),
          acceptedAnswer: { '@type': 'Answer', text: i18n.t(`landing.faq.items.${k}.a`) },
        })),
      },
    ])
    document.head.appendChild(ld)
    created.push(ld)

    return () => {
      document.title = prevTitle
      created.forEach((el) => el.remove())
    }
  }, [language])
}

export default function Landing() {
  const { i18n: instance } = useTranslation()
  useLandingSeo(instance.language || 'fr')
  // The sign-up form under the plans: a plan's id, « » for no plan yet, « quote » for a
  // quotation. Every « Créer mon compte » of the page opens it.
  const [chosen, setChosen] = useState<string | null>(null)
  const open = (plan: string) => {
    setChosen(plan)
    // Already open on that choice: the state does not change, so the form's own scroll does
    // not run, and the reader is taken to it here.
    if (plan === chosen) document.getElementById('signup')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    // ⚠️ NO `overflow-x-hidden` HERE: it would make this box the scroll container of the
    // sticky header, which would then scroll away. The hero clips its own halo.
    <div className="min-h-screen bg-white">
      <Header onSignup={() => open('')} />
      <main>
        <Hero onSignup={() => open('')} />
        <HowItWorks />
        <Features />
        <PricingSection chosen={chosen} open={open} />
        <Faq />
      </main>
      <Footer />
    </div>
  )
}
