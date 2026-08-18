import { create } from 'zustand'
import { authApi } from '@/api'
import { TOKEN_KEY } from '@/api/client'

/**
 * Qui est connecté, et ce que l'application a le droit de lui dessiner.
 *
 * 🔴 LE RÔLE EST REDEMANDÉ AU SERVEUR, PLUS RELU DANS LE STOCKAGE LOCAL. La première
 * version recopiait le rôle renvoyé à la connexion dans `localStorage` et s'y fiait à
 * chaque rechargement. Deux défauts : n'importe qui peut éditer cette valeur dans sa
 * console, et surtout elle reste FIGÉE — un compte rétrogradé ou bloqué depuis Alice
 * continuait de voir la navigation du gestionnaire jusqu'à sa prochaine connexion. Le jeton
 * reste local ; ce qu'il autorise vient de `/auth/me`.
 *
 * ⚠️ CELA RESTE UNE RÈGLE D'AFFICHAGE. Ce qu'un investisseur peut LIRE est décidé par le
 * périmètre de l'API : un portail qui filtre dans le navigateur a déjà reçu ce qu'il cache.
 */
interface AuthState {
  role: string | null
  email: string | null
  isAuthenticated: boolean
  isInitializing: boolean
  seesWholeFund: boolean
  /** Le titulaire doit remplacer un identifiant que quelqu'un d'autre lui a transmis. */
  mustChangePassword: boolean

  login: (email: string, password: string) => Promise<void>
  logout: () => void
  initialize: () => Promise<void>
  refreshMe: () => Promise<void>
}

const CLEARED = {
  role: null,
  email: null,
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
    try {
      await useAuthStore.getState().refreshMe()
    } catch {
      // Jeton expiré ou compte désactivé : on repart d'un état propre plutôt que de
      // dessiner une application à moitié autorisée.
      localStorage.removeItem(TOKEN_KEY)
      set({ ...CLEARED })
    } finally {
      set({ isInitializing: false })
    }
  },

  login: async (email, password) => {
    const { data } = await authApi.login(email, password)
    localStorage.setItem(TOKEN_KEY, data.access_token)
    // On relit `/auth/me` plutôt que de se contenter de la réponse de connexion : une
    // seule source décide de ce que l'application dessine.
    await useAuthStore.getState().refreshMe()
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    set({ ...CLEARED })
  },
}))
