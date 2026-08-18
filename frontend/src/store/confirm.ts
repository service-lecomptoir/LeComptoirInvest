import { create } from 'zustand'

/**
 * Demander confirmation, sans jamais passer par une boîte du navigateur.
 *
 * 🔴 `window.confirm` EST INTERDIT ICI, et pas pour des raisons d'esthétique. Elle ne peut
 * rien dire d'utile : pas de mise en forme, pas de montant, pas de nom, pas de distinction
 * entre « annuler » et « détruire ». Elle bloque le fil d'exécution du navigateur, certains
 * navigateurs la suppriment purement et simplement quand elle vient d'une iframe ou d'un
 * onglet en arrière-plan, et elle porte le nom du domaine plutôt que celui du produit. Une
 * question qui décide d'une action irréversible mérite d'être posée par le produit.
 *
 * L'API est une PROMESSE, pour que l'appelant écrive la suite à la ligne suivante plutôt
 * que d'éclater sa logique dans deux fonctions de rappel.
 */
export interface ConfirmRequest {
  title: string
  message?: string
  /** Libellé du bouton qui agit. Par défaut : « Confirmer ». */
  confirmLabel?: string
  cancelLabel?: string
  /** Rouge plutôt que navy : réservé à ce qui détruit ou coupe un accès. */
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
      // ⚠️ Une seconde demande pendant qu'une première attend répondrait « non » à la
      // première sans que personne l'ait décidé. On refuse plutôt de l'ouvrir.
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

/** À appeler depuis n'importe quel écran : `if (await confirmDialog({ title })) …` */
export const confirmDialog = (request: ConfirmRequest): Promise<boolean> =>
  useConfirmStore.getState().ask(request)
