/**
 * The catalogue key of an account's role, as a reader says it.
 *
 * ⚠️ THE SERVER'S WORD IS A CODE (`manager`), NEVER A LABEL: shown as it is, it put
 * « manager » on a French profile and « Manager » under the account's name (customer
 * recipe, 30 Sept 2026). A role this screen does not know reads « Non renseigné », not the
 * code.
 */
const ROLES = ['manager', 'admin', 'investor'] as const

export function roleKey(role: string | null | undefined): string {
  return role && (ROLES as readonly string[]).includes(role) ? `roles.${role}` : 'profile.notSet'
}
