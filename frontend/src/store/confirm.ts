import { create } from 'zustand'

/**
 * Asking for confirmation, without ever going through a box of the browser.
 *
 * 🔴 `window.confirm` IS FORBIDDEN HERE, and not for reasons of looks. It can say nothing
 * useful: no formatting, no amount, no name, no distinction between « annuler » and
 * « détruire ». It blocks the browser's execution thread, some browsers suppress it purely
 * and simply when it comes from an iframe or a background tab, and it carries the name of
 * the domain rather than that of the product. A question that decides an irreversible
 * action deserves to be asked by the product.
 *
 * The API is a PROMISE, so that the caller writes what follows on the next line rather than
 * scattering its logic across two callbacks.
 */
export interface ConfirmRequest {
  title: string
  message?: string
  /** Label of the button that acts. By default: « Confirmer ». */
  confirmLabel?: string
  cancelLabel?: string
  /** Red rather than navy: reserved for what destroys or cuts off an access. */
  danger?: boolean
}

interface ConfirmState {
  request: (ConfirmRequest & { resolve: (ok: boolean) => void }) | null
  ask: (request: ConfirmRequest) => Promise<boolean>
  answer: (ok: boolean) => void
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  request: null,

  ask: (request) =>
    new Promise<boolean>((resolve) => {
      // ⚠️ A second request while a first one is waiting would answer « non » to the
      // first without anybody having decided it. We refuse to open it instead.
      if (get().request) {
        resolve(false)
        return
      }
      set({ request: { ...request, resolve } })
    }),

  answer: (ok) => {
    const current = get().request
    if (!current) return
    set({ request: null })
    current.resolve(ok)
  },
}))

/** To be called from any screen: `if (await confirmDialog({ title })) …` */
export const confirmDialog = (request: ConfirmRequest): Promise<boolean> =>
  useConfirmStore.getState().ask(request)
