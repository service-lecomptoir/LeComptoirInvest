import { create } from 'zustand'
import { authApi } from '@/api'
import { TOKEN_KEY } from '@/api/client'

const ROLE_KEY = 'lecomptoirinvest-role'

/** Roles that see the fund as a whole. Mirrors `FUND_WIDE_ROLES` in app/models/user.py.
 *
 *  ⚠️ THIS IS A DISPLAY RULE, NEVER A SECURITY ONE. It decides which navigation to draw;
 *  what an investor may READ is decided by the API's scope, because a portal that filters
 *  in the browser has already been sent the data it is hiding. */
const FUND_WIDE_ROLES = ['admin', 'manager']

interface AuthState {
  role: string | null
  isAuthenticated: boolean
  isInitializing: boolean
  seesWholeFund: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  initialize: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  role: null,
  isAuthenticated: false,
  isInitializing: true,
  seesWholeFund: false,

  initialize: () => {
    const token = localStorage.getItem(TOKEN_KEY)
    const role = localStorage.getItem(ROLE_KEY)
    set({
      role,
      isAuthenticated: !!token,
      seesWholeFund: !!role && FUND_WIDE_ROLES.includes(role),
      isInitializing: false,
    })
  },

  login: async (email, password) => {
    const { data } = await authApi.login(email, password)
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(ROLE_KEY, data.role)
    set({
      role: data.role,
      isAuthenticated: true,
      seesWholeFund: FUND_WIDE_ROLES.includes(data.role),
    })
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    set({ role: null, isAuthenticated: false, seesWholeFund: false })
  },
}))
