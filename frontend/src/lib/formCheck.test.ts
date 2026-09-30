import { describe, expect, it } from 'vitest'
import type { TFunction } from 'i18next'

import { fieldErrors, labelsInError } from './formCheck'

/** The catalogue key, with its count: enough to tell the messages apart. */
const t = ((key: string, options?: { count?: number }) =>
  options?.count ? `${key}:${options.count}` : key) as unknown as TFunction

describe('what a form checks before it sends', () => {
  it('says a required field is missing, and leaves an optional empty one alone', () => {
    expect(
      fieldErrors(
        [
          { name: 'name', value: '  ', required: true },
          { name: 'note', value: '' },
        ],
        t,
      ),
    ).toEqual({ name: 'form.required' })
  })

  it('refuses a negative amount or a third decimal, which the browser no longer stops', () => {
    const rules = (value: string) => [{ name: 'amount', value, amount: true }]
    expect(fieldErrors(rules('-5'), t)).toEqual({ amount: 'form.amount' })
    expect(fieldErrors(rules('10.005'), t)).toEqual({ amount: 'form.amount' })
    expect(fieldErrors(rules('abc'), t)).toEqual({ amount: 'form.amount' })
    expect(fieldErrors(rules('1250.50'), t)).toEqual({})
    expect(fieldErrors(rules('0'), t)).toEqual({})
  })

  it('checks an address and a length, and names the fields for a summary', () => {
    const rules = [
      { name: 'email', value: 'pas-une-adresse', email: true, label: 'Adresse e-mail' },
      { name: 'password', value: 'court', minLength: 10, label: 'Mot de passe' },
      { name: 'city', value: 'Paris', required: true, label: 'Ville' },
    ]
    const errors = fieldErrors(rules, t)
    expect(errors).toEqual({ email: 'form.email', password: 'form.minLength:10' })
    expect(labelsInError(rules, errors)).toEqual(['Adresse e-mail', 'Mot de passe'])
  })
})
