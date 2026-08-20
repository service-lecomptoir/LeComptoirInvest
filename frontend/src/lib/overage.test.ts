/**
 * Ce qu'un 402 doit devenir à l'écran, et ce qu'il ne doit jamais devenir.
 *
 * 🔴 POURQUOI UNE GARDE ICI. Le serveur refuse en 402 quand un ajout dépasse le forfait et
 * que l'offre autorise le dépassement : la phrase porte le compte et le prix mensuel. Trois
 * façons de perdre ça, et aucune ne casse quoi que ce soit :
 *
 *   1. l'intercepteur le traite comme une erreur et l'affiche en toast rouge fugace, alors
 *      que c'est une QUESTION à laquelle il faut pouvoir répondre « oui » ;
 *   2. l'écran redemande sans `accept_overage`, et le gestionnaire retombe sur le même
 *      refus en boucle sans comprendre pourquoi ;
 *   3. l'écran annonce « ajouté » alors que la personne a répondu « non ».
 *
 * Les trois donnent un produit qui a l'air de marcher. Seule la dernière se voit, et
 * seulement une fois.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const asked: { title: string; message?: string }[] = []
let answer = true

vi.mock('@/i18n', () => ({
  default: { t: (key: string) => key, language: 'fr' },
}))
vi.mock('@/api/client', () => ({
  errorMessage: (error: any) => error?.response?.data?.detail ?? 'generic',
}))
vi.mock('@/store/confirm', () => ({
  confirmDialog: (request: { title: string; message?: string }) => {
    asked.push(request)
    return Promise.resolve(answer)
  },
}))

const { withOverageConsent } = await import('./overage')

/** Un refus du serveur, dans la forme exacte qu'axios donne à l'appelant. */
function refusal(status: number, detail: string) {
  return Object.assign(new Error(detail), { response: { status, data: { detail } } })
}

const OVER_PLAN =
  'Cet enregistrement dépasse votre forfait (50/50). Chaque investisseur au-delà est ' +
  'facturé 12 €/mois, ajouté à votre abonnement. Confirmez pour continuer.'

describe('withOverageConsent', () => {
  beforeEach(() => {
    asked.length = 0
    answer = true
  })

  it('ne demande rien quand rien ne dépasse', async () => {
    const run = vi.fn().mockResolvedValue('créé')
    expect(await withOverageConsent(run)).toBe('créé')
    expect(asked).toEqual([])
    expect(run).toHaveBeenCalledTimes(1)
    expect(run).toHaveBeenCalledWith(false)
  })

  it('pose la question du serveur, mot pour mot', async () => {
    // 🔴 LE PRIX VIENT DE LA CONSOLE, PAS DU FRONT. Reconstruire la phrase ici créerait une
    // seconde vérité sur un tarif que cet écran ne connaît pas : le jour où l'offre change,
    // il annoncerait l'ancien montant et rien n'aurait l'air faux.
    const run = vi.fn()
      .mockRejectedValueOnce(refusal(402, OVER_PLAN))
      .mockResolvedValueOnce('créé')

    expect(await withOverageConsent(run)).toBe('créé')
    expect(asked).toHaveLength(1)
    expect(asked[0].message).toBe(OVER_PLAN)
  })

  it('rejoue avec le consentement, jamais sans', async () => {
    // ⚠️ Le second appel doit porter `true`. Rejouer à l'identique redonnerait le même 402,
    // et l'écran tournerait en rond en ayant l'air d'obéir.
    const run = vi.fn()
      .mockRejectedValueOnce(refusal(402, OVER_PLAN))
      .mockResolvedValueOnce('créé')

    await withOverageConsent(run)
    expect(run.mock.calls).toEqual([[false], [true]])
  })

  it('rend null quand la personne refuse le supplément, et ne rejoue pas', async () => {
    answer = false
    const run = vi.fn().mockRejectedValue(refusal(402, OVER_PLAN))

    expect(await withOverageConsent(run)).toBeNull()
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('laisse passer tout ce qui n est pas une question', async () => {
    // 400 = l'offre interdit le dépassement. Aucune confirmation ne peut lever ça : la
    // transformer en dialogue proposerait un « oui » qui n'existe pas.
    const run = vi.fn().mockRejectedValue(refusal(400, 'Limite atteinte (50/50).'))
    await expect(withOverageConsent(run)).rejects.toThrow('Limite atteinte (50/50).')
    expect(asked).toEqual([])
    expect(run).toHaveBeenCalledTimes(1)
  })
})
