import type { ReactElement } from 'react'
import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom'
import { Shell } from '@/components/layout/Shell'
import { useAuthStore } from '@/store/authStore'
import Login from '@/pages/Login'
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

// 🔴 LE PROFIL EST AUSSI LA PORTE DU CHANGEMENT IMPOSE, et c'est pourquoi il n'y a
// qu'une constante. Le mot de passe y est une SECTION : deux ecrans, l'un pour se
// presenter et l'autre pour changer son mot de passe, auraient laisse le changement force
// atterrir sur une page sans contexte, celle-la meme qu'un compte tout neuf voit en
// premier. Voir pages/profile/MyProfile.tsx.
const PROFILE_ROUTE = '/profile'

function RequireAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword)
  const location = useLocation()

  if (!isAuthenticated) return <Navigate to="/login" replace />

  // 🔴 LE CHANGEMENT IMPOSÉ BLOQUE TOUT LE RESTE, et c'est le seul endroit où l'appliquer.
  // Le poser sur chaque écran laisserait celui qu'on oublie servir de porte dérobée, et
  // c'est toujours le douzième écran ajouté sous pression qui l'est.
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
 * Et la réciproque, qui manquait.
 *
 * ⚠️ Un gestionnaire qui atteignait `/statement` lisait « Rien à déclarer pour 2026 » —
 * une phrase FAUSSE : il n'est pas investisseur, l'écran ne le concerne pas, et l'API
 * répondait 400 que la page traduisait en état vide. Un écran qui ment sur un cas limite
 * est un écran auquel on cesse de croire sur les autres.
 */
function InvestorOnly({ children }: { children: ReactElement }) {
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  return seesWholeFund ? <Navigate to="/" replace /> : children
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <Shell />,
        children: [
          { path: '/', element: <Home /> },
          { path: PROFILE_ROUTE, element: <MyProfile /> },
          { path: '/projects', element: <Projects /> },
          { path: '/treasury', element: <FundOnly><Treasury /></FundOnly> },
          { path: '/distributions', element: <FundOnly><Distributions /></FundOnly> },
          { path: '/investors', element: <FundOnly><Investors /></FundOnly> },
          { path: '/subscriptions', element: <FundOnly><Subscriptions /></FundOnly> },
          // L'abonnement AU PRODUIT : réservé à qui le paie, donc à la gestion du fonds.
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
