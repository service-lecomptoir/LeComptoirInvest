import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/authStore'
import { GUIDE_SECTIONS, type GuideCard } from '@/lib/guide'

/**
 * What each screen is for and how to use it, a card per screen, as in Le Comptoir RH.
 *
 * ⚠️ A CARD FOR A SCREEN THE READER DOES NOT HAVE IS A FALSE PROMISE: the fund's screens
 * are shown to the fund and the investor's to the investor, from the same flag as the menu.
 */

/** A vignette drawn like a small screen: a bar, a few lines, and the screen's icon. */
function Vignette({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <div
      aria-hidden
      className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg border border-brand-navy/10 bg-brand-navy/5 sm:w-24"
    >
      <div className="absolute inset-x-2 top-2 h-1.5 rounded bg-brand-navy/30" />
      <div className="absolute left-2 top-6 h-1 w-10 rounded bg-gray-300/70" />
      <div className="absolute left-2 top-9 h-1 w-12 rounded bg-gray-300/70" />
      <div className="absolute left-2 top-12 h-1 w-8 rounded bg-gray-300/70" />
      <div className="absolute bottom-2 right-2 flex h-9 w-9 items-center justify-center rounded-full bg-white shadow-sm">
        <Icon size={18} className="text-brand-navy" />
      </div>
    </div>
  )
}

function Card({ card }: { card: GuideCard }) {
  const { t } = useTranslation()
  return (
    <li className="flex gap-3 rounded-xl border border-gray-200 bg-white p-3">
      <Vignette icon={card.icon} />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-gray-900">{t(card.title)}</p>
        <p className="mt-0.5 text-sm text-gray-600">{t(`guide.cards.${card.id}.what`)}</p>
        <p className="mt-2 text-xs font-medium text-gray-500">{t('guide.gestures')}</p>
        <p className="text-sm text-gray-600">{t(`guide.cards.${card.id}.how`)}</p>
      </div>
    </li>
  )
}

export default function Guide() {
  const { t } = useTranslation()
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  const audience = seesWholeFund ? 'fund' : 'investor'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">{t('guide.title')}</h1>
        <p className="mt-1 text-sm text-gray-500">{t('guide.intro')}</p>
      </div>

      {GUIDE_SECTIONS.map((section) => {
        const cards = section.cards.filter((card) => !card.audience || card.audience === audience)
        if (!cards.length) return null
        return (
          <section key={section.key} className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">{t(section.key)}</h2>
            <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {cards.map((card) => (
                <Card key={card.id} card={card} />
              ))}
            </ul>
          </section>
        )
      })}

      <p className="text-xs text-gray-500">{t('guide.help')}</p>
    </div>
  )
}
