import type { ReactElement } from 'react'
import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom'
import { Shell } from '@/components/layout/Shell'
import { useAuthStore } from '@/store/authStore'
import Login from '@/pages/Login'
import Pricing from '@/pages/Pricing'
import MyProfile from '@/pages/profile/MyProfile'
import Dashboard from '@/pages/Dashboard'
import Treasury from '@/pages/Treasury'
import Projects from '@/pages/Projects'
import Distributions from '@/pages/Distributions'
import Investors from '@/pages/Investors'
import Subscriptions from '@/pages/Subscriptions'
import Portfolio from '@/pages/Portfolio'
import Calls from '@/pages/Calls'
import MyDistributions from '@/pages/MyDistributions'
import StatementPage from '@/pages/Statement'
import Billing from '@/pages/Billing'
import Performance from '@/pages/Performance'
import LateCalls from '@/pages/LateCalls'
import Funds from '@/pages/Funds'
import Guide from '@/pages/Guide'

/* eslint-disable react-refresh/only-export-components -- this file IS the route
   table: it exports `router` beside the four guard components that only make
   sense next to it. Fast refresh reloads the whole tree on a change here anyway. */

// 🔴 THE PROFILE IS ALSO THE DOOR OF THE FORCED CHANGE, and that is why there is
// only one constant. The password is a SECTION there: two screens, one to introduce
// oneself and the other to change one's password, would have let the forced change
// land on a page without context, the very one a brand-new account sees first.
// See pages/profile/MyProfile.tsx.
const PROFILE_ROUTE = '/profile'

function RequireAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword)
  const location = useLocation()

  if (!isAuthenticated) return <Navigate to="/login" replace />

  // 🔴 THE FORCED CHANGE BLOCKS EVERYTHING ELSE, and this is the only place to apply it.
  // Putting it on every screen would leave the one we forget serve as a back door, and it
  // is always the twelfth screen added under pressure that gets forgotten.
  if (mustChangePassword && location.pathname !== PROFILE_ROUTE) {
    return <Navigate to={PROFILE_ROUTE} replace />
  }
  return <Outlet />
}

/** The fund's screens and the investor's are different ROUTES, not one set with rows
 *  hidden. `/` resolves to whichever home the account actually has. */
function Home() {
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  return seesWholeFund ? <Dashboard /> : <Portfolio />
}

/**
 * A manager-only screen reached by typing the URL sends an investor home rather than
 * showing them an empty page.
 *
 * ⚠️ THIS IS COURTESY, NOT PROTECTION. The API refuses those reads on its own; if this
 * component were the only thing standing between an investor and the fund's register,
 * the register would already have been sent to their browser.
 */
function FundOnly({ children }: { children: ReactElement }) {
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  return seesWholeFund ? children : <Navigate to="/" replace />
}

/**
 * And the converse, which was missing.
 *
 * ⚠️ A manager who reached `/statement` read « Rien à déclarer pour 2026 » -- a FALSE
 * sentence: they are not an investor, the screen does not concern them, and the API
 * answered 400, which the page turned into an empty state. A screen that lies about an edge
 * case is a screen one stops believing on the others.
 */
function InvestorOnly({ children }: { children: ReactElement }) {
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  return seesWholeFund ? <Navigate to="/" replace /> : children
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  // 🔴 PUBLIC, as on Le Comptoir Immo and RH: the catalogue plans and the sign-up, no
  // account needed. Outside `RequireAuth`, so a visitor is never sent to the sign-in first.
  { path: '/pricing', element: <Pricing /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <Shell />,
        children: [
          { path: '/', element: <Home /> },
          { path: PROFILE_ROUTE, element: <MyProfile /> },
          // What each screen is for, a card per screen. Every account reads it.
          { path: '/guide', element: <Guide /> },
          { path: '/projects', element: <Projects /> },
          { path: '/treasury', element: <FundOnly><Treasury /></FundOnly> },
          { path: '/distributions', element: <FundOnly><Distributions /></FundOnly> },
          { path: '/investors', element: <FundOnly><Investors /></FundOnly> },
          { path: '/subscriptions', element: <FundOnly><Subscriptions /></FundOnly> },
          // The subscription TO THE PRODUCT: reserved for whoever pays for it, so for the fund's management.
          { path: '/billing', element: <FundOnly><Billing /></FundOnly> },
          { path: '/funds', element: <FundOnly><Funds /></FundOnly> },
          { path: '/performance', element: <FundOnly><Performance /></FundOnly> },
          { path: '/late-calls', element: <FundOnly><LateCalls /></FundOnly> },
          { path: '/capital-calls', element: <InvestorOnly><Calls /></InvestorOnly> },
          { path: '/my-distributions', element: <InvestorOnly><MyDistributions /></InvestorOnly> },
          { path: '/statement', element: <InvestorOnly><StatementPage /></InvestorOnly> },
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
])
