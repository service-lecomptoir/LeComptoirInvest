import i18n from '@/i18n'
import { errorMessage } from '@/api/client'
import { confirmDialog } from '@/store/confirm'

/**
 * Run an action that may exceed the plan's investor allowance, asking first if it does.
 *
 * 🔴 THE SENTENCE COMES FROM THE SERVER, AND THAT IS THE WHOLE DESIGN. The refusal carries
 * the count and the monthly price — « 50/50, each investor beyond it is billed 12 €/month »
 * — already written in the reader's language by `license_service`. Rebuilding it here would
 * create a second truth about a price, in a front end that does not know the plan: the day
 * the console changes the tariff, the screen would keep announcing the old one and nothing
 * would look wrong.
 *
 * 🔴 AND IT ASKS BEFORE IT SPENDS. A 402 means the plan allows the overage: the fund bought
 * that freedom, so refusing outright would deny something it pays for. But adding an
 * investor that silently costs more every month is exactly what this dialog prevents —
 * nobody should discover a supplement on their next invoice.
 *
 * ⚠️ RETURNS `null` WHEN THE USER SAYS NO, which is neither a success nor an error. A caller
 * that showed « added » on `null` would announce something that did not happen.
 */
export async function withOverageConsent<T>(
  run: (acceptOverage: boolean) => Promise<T>,
): Promise<T | null> {
  try {
    return await run(false)
  } catch (error: any) {
    if (error?.response?.status !== 402) throw error
    const accepted = await confirmDialog({
      title: i18n.t('investors.overageTitle'),
      message: errorMessage(error),
      confirmLabel: i18n.t('investors.overageConfirm'),
    })
    if (!accepted) return null
    return await run(true)
  }
}
