import { create } from 'zustand'
import { authApi } from '@/api'
import { TOKEN_KEY } from '@/api/client'

/**
 * Who is signed in, and what the application is allowed to draw for them.
 *
 * 🔴 THE ROLE IS ASKED OF THE SERVER AGAIN, NO LONGER RE-READ FROM LOCAL STORAGE. The first
 * version copied the role returned at sign-in into `localStorage` and relied on it at every
 * reload. Two defects: anybody can edit that value in their console, and above all it stays
 * FROZEN -- an account demoted or blocked from Alice kept seeing the manager's navigation
 * until its next sign-in. The token stays local; what it authorises comes from `/auth/me`.
 *
 * ⚠️ THIS REMAINS A DISPLAY RULE. What an investor can READ is decided by the scope of the
 * API: a portal that filters in the browser has already received what it hides.
 */
interface AuthState {
  role: string | null
  email: string | null
  /** The name of the MANAGEMENT COMPANY, the one the account carries.
   *
   *  ⚠️ It is not the name of the product. The side bar showed the brand and nothing
   *  else: a manager who opens three consoles of the house could not tell, at a glance,
   *  which one was theirs. `/auth/me` was already returning it. */
  accountName: string | null
  /** « Club ou fonds » or « Société de gestion », as the server words it in the reader's
   *  language. Null when the console never said who the account works for. */
  accountKindLabel: string | null
  isAuthenticated: boolean
  isInitializing: boolean
  seesWholeFund: boolean
  /** The holder must replace an id that somebody else passed on to them. */
  mustChangePassword: boolean

  login: (email: string, password: string) => Promise<void>
  /** Open the session a password link just earned (the token the server answered). */
  adopt: (token: string) => Promise<void>
  logout: () => void
  initialize: () => Promise<void>
  refreshMe: () => Promise<void>
}

const CLEARED = {
  role: null,
  email: null,
  accountName: null,
  accountKindLabel: null,
  isAuthenticated: false,
  seesWholeFund: false,
  mustChangePassword: false,
}

export const useAuthStore = create<AuthState>((set) => ({
  ...CLEARED,
  isInitializing: true,

  refreshMe: async () => {
    const { data } = await authApi.me()
    set({
      role: data.role,
      email: data.email,
      accountName: data.account_name,
      accountKindLabel: data.account_kind_label,
      isAuthenticated: true,
      seesWholeFund: data.sees_whole_fund,
      mustChangePassword: data.must_change_password,
    })
  },

  initialize: async () => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      set({ ...CLEARED, isInitializing: false })
      return
    }
    // 🔴 ONLY A REFUSAL SIGNS OUT, NEVER A SILENCE. The first version dropped the token on
    // ANY failure of `/auth/me`: a page reloaded while the API restarted (every
    // deployment, twenty seconds) sent the holder back to the sign-in page, token gone
    // (found in the sister product Compta, 27 Sept 2026). A 401 is the server saying
    // « this session is over »; a network error or a 5xx says nothing about the session,
    // so it is asked again, a few times.
    for (let attempt = 0; attempt < 8; attempt++) {
      try {
        await useAuthStore.getState().refreshMe()
        set({ isInitializing: false })
        return
      } catch (error: any) {
        if (error?.response?.status === 401 || error?.response?.status === 403) break
        await new Promise((resolve) => window.setTimeout(resolve, 2500))
      }
    }
    // Expired token or disabled account: start from a clean state rather than draw a
    // half-authorised application.
    localStorage.removeItem(TOKEN_KEY)
    set({ ...CLEARED, isInitializing: false })
  },

  login: async (email, password) => {
    const { data } = await authApi.login(email, password)
    localStorage.setItem(TOKEN_KEY, data.access_token)
    // We re-read `/auth/me` rather than settling for the sign-in response: a single
    // source decides what the application draws.
    await useAuthStore.getState().refreshMe()
  },

  adopt: async (token) => {
    localStorage.setItem(TOKEN_KEY, token)
    await useAuthStore.getState().refreshMe()
  },

  logout: () => {
    // The server closes the session too, so a copy of the token stops working. Read
    // before the wipe, sent after it, never awaited: the screen signs out at once, even
    // offline, and a failed call leaves only a token that expires on its own.
    const token = localStorage.getItem(TOKEN_KEY)
    localStorage.removeItem(TOKEN_KEY)
    set({ ...CLEARED })
    if (token) void authApi.logout(token).catch(() => undefined)
  },
}))

// 🔴 A SIGN-OUT IN ONE TAB SIGNS OUT EVERY TAB. The token lives in localStorage, shared by
// the tabs of the site: once one tab signed out, the others still showed the account's
// data until their next request came back 401. The browser tells the other tabs when a key
// changes (`storage` fires in every tab but the one that wrote): a token gone means the
// session is over here too, and the sign-in page is where the tab goes.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== TOKEN_KEY && event.key !== null) return
    if (event.key !== null && event.newValue !== null) return
    if (!useAuthStore.getState().isAuthenticated) return
    useAuthStore.setState({ ...CLEARED })
    window.location.assign('/login')
  })
}
