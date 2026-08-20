import { useTranslation } from 'react-i18next'
import { Building2, Mail, ShieldCheck } from 'lucide-react'

import { Card, PageHeader } from '@/components/common/Primitives'
import { useAuthStore } from '@/store/authStore'

import { PasswordSection } from './PasswordSection'

/**
 * Mon profil : qui je suis ici, et le seul réglage qui m'appartienne.
 *
 * 🔴 CE QUI EST MONTRÉ N'EST PAS MODIFIABLE, ET C'EST LA RÈGLE DE LA MAISON. Le nom de la
 * société de gestion, l'adresse, le téléphone d'un compte sont tenus par la console
 * (Alice) : c'est elle qui provisionne les comptes et qui facture. Offrir ici un champ
 * modifiable créerait une seconde vérité sur une raison sociale, et la facture porterait
 * l'une pendant que l'écran montre l'autre.
 *
 * ⚠️ L'ÉCRAN LE DIT PLUTÔT QUE DE LAISSER DEVINER. Un champ grisé sans explication se lit
 * comme une panne ; une phrase qui nomme l'endroit où la valeur se change fait gagner
 * l'appel au support.
 *
 * 🔴 LE MOT DE PASSE, LUI, EST À MOI. Il n'est ni connu ni modifiable depuis la console :
 * c'est la seule chose de cette page que son titulaire décide seul, et c'est pourquoi elle
 * y a sa place plutôt que dans un écran séparé.
 */
export default function MyProfile() {
  const { t } = useTranslation()
  const email = useAuthStore((state) => state.email)
  const role = useAuthStore((state) => state.role)
  const accountName = useAuthStore((state) => state.accountName)

  const rows: { icon: typeof Mail; label: string; value: string | null }[] = [
    { icon: Building2, label: t('profile.company'), value: accountName },
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
                  {/* ⚠️ Une valeur absente se dit, elle ne se remplace pas par du vide :
                      un compte sans raison sociale existe, et une ligne blanche se lit
                      comme un défaut d'affichage. */}
                  <p className="text-sm text-gray-900 break-words">
                    {row.value?.trim() ? row.value : t('profile.notSet')}
                  </p>
                </div>
              </div>
            ))}
          </Card>
          <p className="mt-2 text-xs text-gray-500 leading-relaxed">
            {t('profile.managedByConsole')}
          </p>
        </section>

        <PasswordSection />
      </div>
    </>
  )
}
