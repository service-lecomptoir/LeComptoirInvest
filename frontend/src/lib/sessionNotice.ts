/**
 * A sentence the server said while closing a session, carried to the sign-in page.
 *
 * 🔴 A SUSPENDED FIRM WOULD BE SENT BACK TO /login IN SILENCE (the owner, 8 Nov 2026): a
 * colleague in the middle of their work meets a 401, and the page reloads on an empty
 * sign-in form with nothing to say why. The client leaves the server's sentence here and
 * the sign-in page shows it.
 *
 * `sessionStorage`, read once: the notice belongs to this tab and this moment, never to the
 * next visit. Wrapped, because a private window may refuse storage altogether.
 */

const KEY = 'lecomptoirinvest-session-notice'

export function leaveSessionNotice(text: string): void {
  try {
    sessionStorage.setItem(KEY, text)
  } catch {
    // Storage refused: the sign-in page will simply say nothing more than before.
  }
}

export function takeSessionNotice(): string | null {
  try {
    const text = sessionStorage.getItem(KEY)
    if (text) sessionStorage.removeItem(KEY)
    return text
  } catch {
    return null
  }
}
