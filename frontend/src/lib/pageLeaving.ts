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
 * it is dropped (the page is gone, or `pagehide` came first), when the connection is
 * really down it is said a beat later. And a page restored from that cache reloads its
 * data at once instead of showing what it was holding when it left.
 */

let leaving = false

/** How long a response-less error waits before it is shown. */
export const NO_RESPONSE_GRACE_MS = 800

export function isPageLeaving(): boolean {
  return leaving
}

/** The page is being left (`pagehide`, `beforeunload`). */
export function markLeaving(): void {
  leaving = true
}

/** The page is shown again (`pageshow`). */
export function markBack(): void {
  leaving = false
}

/**
 * 🔴 THE ONE WAY TO SEND THE BROWSER TO ANOTHER SITE (Stripe's payment page, its portal,
 * an invoice to pay): the page is being left from this moment, so the reloads it cuts
 * short say nothing. `aPageLeftIsNotABrokenConnection.test.ts` refuses any other.
 */
export function leaveFor(url: string): void {
  markLeaving()
  window.location.href = url
}

/** Says a response-less error, unless the page is being left by then. */
export function sayUnlessLeaving(say: () => void, wait = NO_RESPONSE_GRACE_MS): void {
  setTimeout(() => {
    if (!leaving) say()
  }, wait)
}

/**
 * Listens to the page's life once: `onRestored` runs when the browser shows the page
 * again from its back-forward cache, so the screens reload instead of showing their state
 * from before the departure.
 */
export function watchPageLeaving(onRestored: () => void): void {
  window.addEventListener('pagehide', markLeaving)
  window.addEventListener('beforeunload', markLeaving)
  window.addEventListener('pageshow', event => {
    markBack()
    if ((event as PageTransitionEvent).persisted) onRestored()
  })
}
