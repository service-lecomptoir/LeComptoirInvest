import { useTranslation } from 'react-i18next'
import { Building2, Landmark, Mail, ShieldCheck } from 'lucide-react'

import { Card, PageHeader } from '@/components/common/Primitives'
import { useAuthStore } from '@/store/authStore'

import { EmailThemeSection } from './EmailThemeSection'
import { PasswordSection } from './PasswordSection'

/**
 * My profile: who I am here, and the settings that belong to the account.
 *
 * 🔴 WHAT IS SHOWN IS NOT EDITABLE, AND THAT IS THE RULE OF THE HOUSE. The name of the
 * management company, the address, the telephone of an account are held by the console
 * (Alice): it is the console that provisions the accounts and that invoices. Offering an
 * editable field here would create a second truth about a company name, and the invoice
 * would carry one while the screen shows the other.
 *
 * ⚠️ THE SCREEN SAYS SO RATHER THAN LEAVING ONE TO GUESS. A greyed-out field without an
 * explanation reads as a breakdown; a sentence that names the place where the value is
 * changed saves the call to support.
 *
 * 🔴 THE PASSWORD, FOR ITS PART, IS MINE. It is neither known nor editable from the
 * console: it is the only thing on this page that its holder decides alone, and that is why
 * it has its place here rather than on a separate screen.
 *
 * ⚠️ THE LOOK OF THE E-MAILS IS SHOWN ONLY TO THOSE WHO RUN THE FUND. It is the management
 * company's setting, the letters to investors go out in it, and an investor's login sends
 * nothing: offering it the choice would offer a setting the server refuses.
 */
export default function MyProfile() {
  const { t } = useTranslation()
  const email = useAuthStore((state) => state.email)
  const role = useAuthStore((state) => state.role)
  const accountName = useAuthStore((state) => state.accountName)
  const accountKindLabel = useAuthStore((state) => state.accountKindLabel)
  const seesWholeFund = useAuthStore((state) => state.seesWholeFund)

  const rows: { icon: typeof Mail; label: string; value: string | null; help?: string }[] = [
    { icon: Building2, label: t('profile.company'), value: accountName },
    // 🔴 WHO THE ACCOUNT WORKS FOR, as the console qualified it. Only for the accounts
    // that run the fund: an investor's login has no such kind, and « Non renseigné » there
    // would read as a missing piece of their own file.
    ...(seesWholeFund
      ? [
          {
            icon: Landmark,
            label: t('profile.accountKind'),
            value: accountKindLabel,
            help: t('profile.accountKindHelp'),
          },
        ]
      : []),
    { icon: Mail, label: t('profile.email'), value: email },
    { icon: ShieldCheck, label: t('profile.role'), value: role },
  ]

  return (
    <>
      <PageHeader title={t('profile.title')} subtitle={t('profile.subtitle')} />

      <div className="max-w-xl space-y-8">
        <section>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">
            {t('profile.identity')}
          </h2>
          <Card className="divide-y divide-gray-100">
            {rows.map((row) => (
              <div key={row.label} className="flex items-start gap-3 px-4 py-3">
                <row.icon size={16} className="mt-0.5 shrink-0 text-gray-400" />
                <div className="min-w-0">
                  <p className="text-xs text-gray-500">{row.label}</p>
                  {/* ⚠️ An absent value is said, it is not replaced by emptiness:
                      an account without a company name exists, and a blank line reads
                      as a display defect. */}
                  <p className="text-sm text-gray-900 break-words">
                    {row.value?.trim() ? row.value : t('profile.notSet')}
                  </p>
                  {row.help && <p className="mt-0.5 text-xs text-gray-500">{row.help}</p>}
                </div>
              </div>
            ))}
          </Card>
          <p className="mt-2 text-xs text-gray-500 leading-relaxed">
            {t('profile.managedByConsole')}
          </p>
        </section>

        {seesWholeFund && <EmailThemeSection />}

        <PasswordSection />
      </div>
    </>
  )
}
