/**
 * Where to land after signing in: the page somebody was sent away from, as RH does it.
 *
 * 🔴 ONLY A PATH OF THIS SITE, NEVER AN ADDRESS. `?next=` is read from the URL, and a URL
 * can be written by anybody and sent in an e-mail: honouring `?next=https://evil.example`
 * would turn the sign-in page into an open redirect, the genuine sign-in screen handing the
 * freshly signed-in reader to a look-alike. So the value must start with one « / » and
 * nothing that a browser reads as another host:
 *
 *   * `//evil.example` is protocol-relative: another host;
 *   * `/\evil.example` is read as `//evil.example` by browsers that normalise the slash;
 *   * a control character (a tab, a newline) is stripped by the URL parser, which can
 *     rebuild either of the two above from something that looked harmless.
 *
 * ⚠️ AND NEVER THE SIGN-IN ITSELF: landing back on `/login` once signed in is a loop.
 */
export const LOGIN_ROUTE = '/login'

export function safeNext(raw: string | null | undefined): string | null {
  if (!raw) return null
  if (!raw.startsWith('/')) return null
  if (raw.startsWith('//') || raw.startsWith('/\\')) return null
  // eslint-disable-next-line no-control-regex -- the control characters ARE the target
  if (/[\u0000-\u001f\u007f]/.test(raw)) return null
  if (raw === LOGIN_ROUTE || raw.startsWith(`${LOGIN_ROUTE}?`) || raw.startsWith(`${LOGIN_ROUTE}/`)) return null
  return raw
}

/** The sign-in address that brings the reader back to `path` afterwards. */
export function loginFor(path: string): string {
  const next = safeNext(path)
  return next && next !== '/' ? `${LOGIN_ROUTE}?next=${encodeURIComponent(next)}` : LOGIN_ROUTE
}
