/**
 * What a 402 must become on screen, and what it must never become.
 *
 * 🔴 WHY A GUARD HERE. The server refuses with a 402 when an addition goes past the plan
 * and the offer allows the overage: the sentence carries the count and the monthly price.
 * Three ways to lose that, and none of them breaks anything:
 *
 *   1. the interceptor treats it as an error and shows it as a fleeting red toast, when it
 *      is a QUESTION one must be able to answer « oui » to;
 *   2. the screen asks again without `accept_overage`, and the manager falls back on the
 *      same refusal in a loop without understanding why;
 *   3. the screen announces « ajouté » when the person answered « non ».
 *
 * The three give a product that looks as if it works. Only the last one shows, and only
 * once.
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

/** A refusal from the server, in the exact shape axios gives the caller. */
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
    // 🔴 THE PRICE COMES FROM THE CONSOLE, NOT FROM THE FRONT END. Rebuilding the sentence
    // here would create a second truth about a tariff this screen does not know: the day
    // the offer changes, it would announce the old amount and nothing would look wrong.
    const run = vi.fn()
      .mockRejectedValueOnce(refusal(402, OVER_PLAN))
      .mockResolvedValueOnce('créé')

    expect(await withOverageConsent(run)).toBe('créé')
    expect(asked).toHaveLength(1)
    expect(asked[0].message).toBe(OVER_PLAN)
  })

  it('rejoue avec le consentement, jamais sans', async () => {
    // ⚠️ The second call must carry `true`. Replaying it identically would give back the
    // same 402, and the screen would go round in circles while looking as if it obeyed.
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
    // 400 = the offer forbids the overage. No confirmation can lift that: turning it into
    // a dialogue would offer a « oui » that does not exist.
    const run = vi.fn().mockRejectedValue(refusal(400, 'Limite atteinte (50/50).'))
    await expect(withOverageConsent(run)).rejects.toThrow('Limite atteinte (50/50).')
    expect(asked).toEqual([])
    expect(run).toHaveBeenCalledTimes(1)
  })
})
