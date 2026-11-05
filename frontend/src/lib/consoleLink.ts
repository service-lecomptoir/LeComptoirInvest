/**
 * What the console's sign-in link carries (`POST /internal/managers/{id}/login-link`).
 *
 * 🔴 THE SIGN-IN PAGE NEVER READ IT (found 4 Nov 2026): support opened `/login?token=…` and
 * landed on an empty form. Two shapes, decided by the server:
 * - `/login?token=<session>` when the holder has no second factor: the session opens;
 * - `/login#two_factor=<five-minute token>` when they have one: the code step opens, as after
 *   the password. The fragment never reaches a server nor an access log.
 */
export interface ConsoleLink {
  session: string | null
  twoFactor: string | null
}

export function readConsoleLink(search: string, hash: string): ConsoleLink {
  const session = new URLSearchParams(search).get('token')
  const twoFactor = new URLSearchParams(hash.replace(/^#/, '')).get('two_factor')
  return { session: session || null, twoFactor: twoFactor || null }
}

/** The query once the link's token is taken out of it: nothing of the link stays in the
 *  address bar, where a reload would replay it and a screenshot would show it. */
export function withoutLink(search: string): string {
  const params = new URLSearchParams(search)
  params.delete('token')
  const left = params.toString()
  return left ? `?${left}` : ''
}
