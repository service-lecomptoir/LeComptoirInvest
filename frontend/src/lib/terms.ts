import { useEffect, useState } from 'react'
import {
  termsApi, type TermsDocumentStatus, type TermsHistory, type TermsKind, type TermsStatus,
  type TermsText,
} from '@/api/terms'

/**
 * The rules the screens of the terms share: which document is asked, what holds a form,
 * what travels to the server. Pure functions and hooks, apart from the components that
 * draw them, so each rule is written once and tested without a browser.
 */

/**
 * What the sign-up knows of one document: nothing yet, nothing published, a text, or a
 * console that did not answer.
 *
 * 🔴 « LOADING » IS NOT « NO TERMS ». Until the answer arrives the form shows nothing about
 * the box and refuses to send: drawing no box and an active button would claim there is
 * nothing to accept before anybody knows.
 */
export type TermsBox =
  | { state: 'loading' }
  | { state: 'none' }
  | { state: 'unavailable' }
  | { state: 'ready'; text: TermsText }

export type Ticked = Record<TermsKind, boolean>

export const UNTICKED: Ticked = { cgu: false, cgv: false }

/** The documents a sign-up is asked: the terms of sale only with a catalogue plan. */
export function asked(withSale: boolean): TermsKind[] {
  return withSale ? ['cgu', 'cgv'] : ['cgu']
}

/**
 * Why the form may not be sent yet, or null when it may.
 *
 * 🔴 FAIL CLOSED: a console that cannot serve the text cannot record its acceptance, and a
 * sign-up that cannot record it must not go through.
 */
export function termsBlock(
  boxes: Record<TermsKind, TermsBox>,
  withSale: boolean,
  ticked: Ticked,
): 'loading' | 'unavailable' | 'unticked' | null {
  const kinds = asked(withSale)
  if (kinds.some((kind) => boxes[kind].state === 'loading')) return 'loading'
  if (kinds.some((kind) => boxes[kind].state === 'unavailable')) return 'unavailable'
  if (kinds.some((kind) => boxes[kind].state === 'ready' && !ticked[kind])) return 'unticked'
  return null
}

/** The versions ticked, as the server hands them to Alice. */
export function termsGiven(
  boxes: Record<TermsKind, TermsBox>,
  withSale: boolean,
  ticked: Ticked,
  language: string,
): { cgu: string | null; cgv: string | null; language: string } {
  const version = (kind: TermsKind) => {
    const box = boxes[kind]
    return asked(withSale).includes(kind) && box.state === 'ready' && ticked[kind]
      ? box.text.version
      : null
  }
  return { cgu: version('cgu'), cgv: version('cgv'), language }
}

/** The texts a person signing up is asked, in the form's language. `attempt` reads them
 *  again (after a 409: a version published while the form was open). */
export function useSignupTerms(language: string, attempt = 0): Record<TermsKind, TermsBox> {
  const [boxes, setBoxes] = useState<Record<TermsKind, TermsBox>>({
    cgu: { state: 'loading' },
    cgv: { state: 'loading' },
  })
  useEffect(() => {
    let live = true
    setBoxes({ cgu: { state: 'loading' }, cgv: { state: 'loading' } })
    const read = (kind: TermsKind) =>
      termsApi
        .forSignup(kind, language)
        .then(({ data }): TermsBox => ({ state: 'ready', text: data }))
        .catch((error): TermsBox =>
          error?.response?.status === 404 ? { state: 'none' } : { state: 'unavailable' },
        )
        .then((box) => {
          if (live) setBoxes((was) => ({ ...was, [kind]: box }))
        })
    void read('cgu')
    void read('cgv')
    return () => {
      live = false
    }
  }, [language, attempt])
  return boxes
}

/** The document the gate asks first: the terms of use, then the terms of sale. */
export function pendingDocument(
  status: TermsStatus | null,
): { kind: TermsKind; document: TermsDocumentStatus } | null {
  if (!status || status.unavailable) return null
  for (const kind of ['cgu', 'cgv'] as const) {
    const document = status[kind]
    if (document?.pending && document.version) return { kind, document }
  }
  return null
}

/** What the account accepted and where it stands now: `null` until both answers arrive. */
export interface TermsOverview {
  history: TermsHistory | null
  status: TermsStatus | null
}

/**
 * The account's acceptances and its status, read together.
 *
 * ⚠️ A FAILED READ IS « UNAVAILABLE », NEVER « NOTHING ACCEPTED »: the screen must not tell
 * somebody they agreed to nothing because the console was slow.
 */
export function useTermsOverview(attempt = 0): TermsOverview | null {
  const [overview, setOverview] = useState<TermsOverview | null>(null)
  useEffect(() => {
    let live = true
    setOverview(null)
    Promise.allSettled([termsApi.history(), termsApi.status()]).then(([history, status]) => {
      if (!live) return
      setOverview({
        history:
          history.status === 'fulfilled' ? history.value.data : { entries: [], unavailable: true },
        status: status.status === 'fulfilled' ? status.value.data : null,
      })
    })
    return () => {
      live = false
    }
  }, [attempt])
  return overview
}

/**
 * Has the reader reached the end of the text? (the manager, 10 Oct 2026: « même sans avoir
 * tout lu, on peut déjà accepter »). True at the bottom of the scrolling box, within a few
 * pixels, and at once for a text that fits whole in the box.
 */
export function readToTheEnd(scrollTop: number, clientHeight: number, scrollHeight: number): boolean {
  return scrollTop + clientHeight >= scrollHeight - 8
}
