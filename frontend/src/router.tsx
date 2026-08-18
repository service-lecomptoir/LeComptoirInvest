import type { ReactElement } from 'react'
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { Shell } from '@/components/layout/Shell'
import { useAuthStore } from '@/store/authStore'
import Login from '@/pages/Login'
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

function RequireAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
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

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <Shell />,
        children: [
          { path: '/', element: <Home /> },
          { path: '/projects', element: <Projects /> },
          { path: '/treasury', element: <FundOnly><Treasury /></FundOnly> },
          { path: '/distributions', element: <FundOnly><Distributions /></FundOnly> },
          { path: '/investors', element: <FundOnly><Investors /></FundOnly> },
          { path: '/subscriptions', element: <FundOnly><Subscriptions /></FundOnly> },
          { path: '/capital-calls', element: <Calls /> },
          { path: '/my-distributions', element: <MyDistributions /> },
          { path: '/statement', element: <StatementPage /> },
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
])
