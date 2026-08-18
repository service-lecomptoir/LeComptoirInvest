import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import {
  Banknote, Building2, CreditCard, FileText, KeyRound, LayoutDashboard, LogOut, Menu,
  PieChart, Receipt, Users, Wallet, X,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { confirmDialog } from '@/store/confirm'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'

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
      { to: '/treasury', key: 'nav.treasury', icon: Wallet },
      { to: '/projects', key: 'nav.projects', icon: Building2 },
      { to: '/distributions', key: 'nav.distributions', icon: Banknote },
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
    <nav className="flex-1 overflow-y-auto px-2 py-2 space-y-5">
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

export function Shell() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const logout = useAuthStore((s) => s.logout)
  const role = useAuthStore((s) => s.role)
  const email = useAuthStore((s) => s.email)
  const navigate = useNavigate()

  // ⚠️ Une fenêtre du PRODUIT, jamais `window.confirm`. Se déconnecter d'un clic mal placé
  // fait perdre ce qu'un formulaire ouvert contenait, et la boîte du navigateur ne sait ni
  // nommer le compte ni distinguer « annuler » de « partir ».
  const signOut = async () => {
    const ok = await confirmDialog({
      title: t('signOut.title'),
      message: email ? t('signOut.messageWithAccount', { email }) : t('signOut.message'),
      confirmLabel: t('common.signOut'),
    })
    if (!ok) return
    logout()
    navigate('/login')
  }

  const aside = (
    <>
      <Brand />
      <NavList onNavigate={() => setOpen(false)} />
      <div className="px-2 pb-3 pt-2 border-t border-white/10 space-y-2">
        <div className="px-1.5">
          <LanguageSwitcher dark />
        </div>
        <p className="px-2.5 text-[11px] text-white/40 capitalize">{role ?? ''}</p>
        <NavLink
          to="/change-password"
          onClick={() => setOpen(false)}
          className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-white/70 hover:bg-white/5 hover:text-white"
        >
          <KeyRound size={16} /> {t('password.title')}
        </NavLink>
        <button
          onClick={signOut}
          className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-white/70 hover:bg-white/5 hover:text-white"
        >
          <LogOut size={16} /> {t('common.signOut')}
        </button>
      </div>
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
        <header className="lg:hidden sticky top-0 z-30 flex items-center gap-3 h-14 px-4 bg-brand-navy">
          <button onClick={() => setOpen(true)} className="text-white" aria-label={t('common.openMenu')}>
            <Menu size={20} />
          </button>
          <span className="text-[15px] font-semibold text-white">
            {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
          </span>
        </header>
        <main className="px-4 sm:px-6 lg:px-8 py-6 max-w-[1400px]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
