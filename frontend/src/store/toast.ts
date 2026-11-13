import { create } from 'zustand'

export type ToastKind = 'success' | 'error' | 'info'

/** A screen of the application the message points to (« Mon abonnement »...). */
export interface ToastLink {
  to: string
  label: string
}

export interface Toast {
  id: number
  kind: ToastKind
  message: string
  link?: ToastLink
}

interface ToastState {
  toasts: Toast[]
  push: (kind: ToastKind, message: string, link?: ToastLink) => void
  dismiss: (id: number) => void
}

let nextId = 1

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (kind, message, link) => {
    // The SAME sentence already on screen is not shown twice: the interceptor says a
    // refusal with its link (a write during the thirty days to export, 13 Nov 2026) and
    // the screen's own handler may say the same sentence again; the first, with its link,
    // stays.
    if (useToastStore.getState().toasts.some((t) => t.kind === kind && t.message === message)) return
    const id = nextId++
    set((s) => ({ toasts: [...s.toasts, { id, kind, message, ...(link ? { link } : {}) }] }))
    // Errors stay longer: they usually carry a sentence the user has to read, not a
    // confirmation they already expected.
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), kind === 'error' ? 8000 : 4000)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export const toast = {
  success: (m: string) => useToastStore.getState().push('success', m),
  /** `link`: the screen where it can be settled, a click away. */
  error: (m: string, link?: ToastLink) => useToastStore.getState().push('error', m, link),
  info: (m: string) => useToastStore.getState().push('info', m),
}
