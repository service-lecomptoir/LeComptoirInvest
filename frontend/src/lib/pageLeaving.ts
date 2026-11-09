/**
 * 🔴 A REQUEST CUT SHORT BY LEAVING THE PAGE IS NOT A BROKEN CONNECTION (the owner,
 * 9 Nov 2026: on the iPhone, « Connexion au serveur impossible » at every click on
 * « Ajouter un moyen de paiement », just before Stripe opened).
 *
 * Every write reloads the blocks on screen (`store/dataRevision`), and a payment button
 * writes, then sends the browser to Stripe. Leaving the page aborts those reloads; iOS
 * Safari reports an aborted request as a network error with no response, and the
 * interceptor toasted it, every time. Coming back with « Précédent », Safari restored the
 * page as it was left (back-forward cache): the toast and « Connexion au serveur
 * impossible » in the page itself, on a page that had loaded fine.
 *
 * So a response-less error waits a moment before it is said: when the page is being left
 * it is held (the page is gone, or `pagehide` came first), when the connection is
 * really down it is said a beat later. And a page restored from that cache reloads its
 * data at once instead of showing what it was holding when it left.
 *
 * 🔴 A DEPARTURE THAT DOES NOT HAPPEN LEAVES THE PAGE AS IT WAS. `beforeunload` is not a
 * departure (a « Leave site? » prompt the user cancels, a navigation that fails): it is not
 * listened to. A departure through `leaveFor` that has not happened after
 * `STILL_HERE_AFTER_MS` is over: the flag drops and every error held meanwhile is said, as
 * if the page had never been leaving. A screen waiting on an error is never left waiting.
 */

let leaving = false
let stillHere: ReturnType<typeof setTimeout> | undefined
let held: Array<() => void> = []

/** How long a response-less error waits before it is shown. */
export const NO_RESPONSE_GRACE_MS = 800

/** How long a departure through `leaveFor` may take before the page counts as still here. */
export const STILL_HERE_AFTER_MS = 10_000

export function isPageLeaving(): boolean {
  return leaving
}

function forgetStillHere(): void {
  if (stillHere !== undefined) clearTimeout(stillHere)
  stillHere = undefined
}

/** The page is being left for good (`pagehide`). */
export function markLeaving(): void {
  forgetStillHere()
  leaving = true
}

/** The page is shown again from the back-forward cache (`pageshow`): it reloads, what it held is forgotten. */
export function markBack(): void {
  forgetStillHere()
  leaving = false
  held = []
}

/** The page did not leave after all: every error held meanwhile is said. */
export function markStillHere(): void {
  forgetStillHere()
  leaving = false
  const due = held
  held = []
  due.forEach(say => say())
}

/**
 * 🔴 THE ONE WAY TO SEND THE BROWSER TO ANOTHER SITE (Stripe's payment page, its portal,
 * an invoice to pay): the page is being left from this moment, so the reloads it cuts
 * short say nothing, unless the page is still here `STILL_HERE_AFTER_MS` later.
 * `aPageLeftIsNotABrokenConnection.test.ts` refuses any other.
 */
export function leaveFor(url: string): void {
  forgetStillHere()
  leaving = true
  stillHere = setTimeout(markStillHere, STILL_HERE_AFTER_MS)
  window.location.href = url
}

/** Says a response-less error, unless the page is being left by then: then it is held. */
export function sayUnlessLeaving(say: () => void, wait = NO_RESPONSE_GRACE_MS): void {
  setTimeout(() => {
    if (leaving) held.push(say)
    else say()
  }, wait)
}

/**
 * Listens to the page's life once: `onRestored` runs when the browser shows the page
 * again from its back-forward cache, so the screens reload instead of showing their state
 * from before the departure.
 */
export function watchPageLeaving(onRestored: () => void): void {
  window.addEventListener('pagehide', markLeaving)
  window.addEventListener('pageshow', event => {
    markBack()
    if ((event as PageTransitionEvent).persisted) onRestored()
  })
}
