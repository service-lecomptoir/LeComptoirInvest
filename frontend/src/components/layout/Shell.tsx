import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import {
  Banknote, Building2, CreditCard, FileText, LayoutDashboard, Menu,
  AlarmClock, Layers, PieChart, Receipt, TrendingUp, Users, Wallet, X,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ProfileMenu } from '@/components/layout/ProfileMenu'

interface Item {
  to: string
  /** A catalogue key, never a label. A menu written in one language is a menu that has
   *  to be found and rewritten the day the product crosses a border. */
  key: string
  icon: typeof LayoutDashboard
}

/**
 * The two navigations, and they are NOT one list with rows hidden.
 *
 * A fund manager and an investor use this product for different jobs: one runs the
 * vehicle, the other watches their money. Building a single menu and greying out what an
 * investor may not touch would show them the shape of everything they cannot have, on
 * every page, for ever.
 */
const FUND_NAV: { section: string; items: Item[] }[] = [
  {
    section: 'nav.fund',
    items: [
      { to: '/', key: 'nav.dashboard', icon: LayoutDashboard },
      { to: '/funds', key: 'nav.funds', icon: Layers },
      { to: '/treasury', key: 'nav.treasury', icon: Wallet },
      { to: '/late-calls', key: 'nav.lateCalls', icon: AlarmClock },
      { to: '/projects', key: 'nav.projects', icon: Building2 },
      { to: '/distributions', key: 'nav.distributions', icon: Banknote },
      { to: '/performance', key: 'nav.performance', icon: TrendingUp },
    ],
  },
  {
    section: 'nav.investorsSection',
    items: [
      { to: '/investors', key: 'nav.register', icon: Users },
      { to: '/subscriptions', key: 'nav.subscriptions', icon: Receipt },
    ],
  },
  {
    // ⚠️ SA PROPRE SECTION, et non une ligne de plus sous « Investisseurs ». Ce que le
    // gestionnaire paie pour utiliser le produit n'a rien à voir avec ce que les
    // investisseurs engagent dans le fonds : les ranger ensemble ferait lire « Abonnement »
    // comme un abonnement d'investisseur, dans le seul menu où ce contresens coûte cher.
    section: 'nav.myAccount',
    items: [{ to: '/billing', key: 'nav.billing', icon: CreditCard }],
  },
]

const INVESTOR_NAV: { section: string; items: Item[] }[] = [
  {
    section: 'nav.mySpace',
    items: [
      { to: '/', key: 'nav.myPortfolio', icon: PieChart },
      { to: '/capital-calls', key: 'nav.myCalls', icon: Wallet },
      { to: '/my-distributions', key: 'nav.myDistributions', icon: Banknote },
      { to: '/statement', key: 'nav.statement', icon: FileText },
      { to: '/projects', key: 'nav.theProjects', icon: Building2 },
    ],
  },
]

function Brand() {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2.5 px-4 h-14 shrink-0">
      <span className="grid place-items-center w-7 h-7 rounded-md bg-brand-teal text-white text-[13px] font-bold">
        C
      </span>
      <span className="text-[15px] font-semibold text-white tracking-tight">
        {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
      </span>
    </div>
  )
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  const groups = seesWholeFund ? FUND_NAV : INVESTOR_NAV
  return (
    <nav className="no-scrollbar flex-1 overflow-y-auto px-2 py-2 space-y-5">
      {groups.map((group) => (
        <div key={group.section}>
          <p className="px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/40">
            {t(group.section)}
          </p>
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] transition-colors',
                      isActive
                        ? 'bg-white/10 text-white font-medium'
                        : 'text-white/70 hover:bg-white/5 hover:text-white',
                    )
                  }
                >
                  <item.icon size={16} className="shrink-0" />
                  {t(item.key)}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

/** The pages a reader can be on that have no menu entry of their own.
 *
 *  ⚠️ Written out because they exist, not because a list is nice: `/change-password` is
 *  reached from the footer and is where a forced change lands, so it is the ONE page a new
 *  account sees first. A tab reading just « Le Comptoir Invest » there says nothing. */
const OFF_MENU_TITLES: Record<string, string> = {
  '/change-password': 'password.title',
}

/** Path -> catalogue key, built from the menu itself.
 *
 *  🔴 NOT A SECOND LIST. The sibling products each keep a hand-written `PAGE_TITLES`, and a
 *  hand-written list is one that drifts the day a screen is added - this repository has
 *  already forgotten « invest » in four of them. The menu already pairs a path with a key;
 *  reading it here means a new screen carries its own tab title in.
 *
 *  ⚠️ `/` IS NOT IN HERE, and it cannot be: it resolves to the dashboard for the fund and to
 *  the portfolio for an investor. It is answered below, where the role is known. */
const MENU_TITLES: Record<string, string> = Object.fromEntries(
  [...FUND_NAV, ...INVESTOR_NAV]
    .flatMap((group) => group.items)
    .filter((item) => item.to !== '/')
    .map((item) => [item.to, item.key]),
)

export function Shell() {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const seesWholeFund = useAuthStore((state) => state.seesWholeFund)

  // 🔴 THE TAB IS A LABEL TOO, so it is translated like every other one. The siblings write
  // theirs in French because they are French-only; this product is not, and a French tab
  // over an English screen is the kind of half-translation a reader notices immediately.
  //
  // ⚠️ `i18n.language` IS IN THE DEPENDENCIES, and that is not decoration: switching
  // language re-renders the screen but would leave the tab on the old wording, which is
  // exactly the corner nobody thinks to look at.
  useEffect(() => {
    const key =
      location.pathname === '/'
        ? seesWholeFund
          ? 'nav.dashboard'
          : 'nav.myPortfolio'
        : (MENU_TITLES[location.pathname] ?? OFF_MENU_TITLES[location.pathname])
    document.title = key ? `Le Comptoir Invest | ${t(key)}` : 'Le Comptoir Invest'
  }, [location.pathname, seesWholeFund, t, i18n.language])

  const aside = (
    <>
      <Brand />
      <NavList onNavigate={() => setOpen(false)} />
    </>
  )

  return (
    <div className="min-h-screen bg-gray-50">
      {/* A fixed rail on desktop. 240 px is the width these consoles settle on: wide
          enough for a two-word label, narrow enough to leave the table its room. */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-60 flex-col bg-brand-navy">
        {aside}
      </aside>

      {open && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="relative flex flex-col w-64 bg-brand-navy">
            <button
              onClick={() => setOpen(false)}
              className="absolute top-4 right-3 text-white/70 hover:text-white"
              aria-label={t('common.closeMenu')}
            >
              <X size={18} />
            </button>
            {aside}
          </aside>
        </div>
      )}

      <div className="lg:pl-60">
        {/* ⚠️ UNE SEULE BARRE, PAS UNE PAR TAILLE D'ECRAN. Elle portait le menu burger en
            mobile ; elle porte maintenant la langue et le compte partout. En faire deux
            aurait laisse l'une des deux prendre du retard sur l'autre, et c'est toujours
            celle qu'on ne regarde pas qui le prend.

            Le bandeau navy reste en mobile parce qu'il y remplace le menu lateral, absent ;
            en grand ecran le menu est la, et la barre s'efface en blanc. */}
        <header className="sticky top-0 z-30 flex items-center gap-3 h-14 px-4 lg:px-8 bg-brand-navy lg:bg-white lg:border-b lg:border-gray-200">
          <button
            onClick={() => setOpen(true)}
            className="lg:hidden text-white"
            aria-label={t('common.openMenu')}
          >
            <Menu size={20} />
          </button>
          <span className="lg:hidden text-[15px] font-semibold text-white">
            {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
          </span>

          {/* Pousse le reste a droite : c'est la seule chose que cette barre a a dire. */}
          <div className="ml-auto flex items-center gap-2">
            <LanguageSwitcher />
            <ProfileMenu />
          </div>
        </header>
        <main className="px-4 sm:px-6 lg:px-8 py-6 max-w-[1400px]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
