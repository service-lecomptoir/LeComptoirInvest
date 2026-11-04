import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ShieldCheck, X } from 'lucide-react'
import { authApi } from '@/api'
import { useAuthStore } from '@/store/authStore'

/** « Plus tard » silences it for a month, never for good (one reminder a month). */
const SNOOZE_MS = 30 * 24 * 3600 * 1000

const snoozeKey = (email: string) => `lecomptoirinvest-two-factor-banner:${email}`

function readSnooze(key: string): number {
  try {
    return Number(localStorage.getItem(key) || '0')
  } catch {
    return 0
  }
}

/**
 * RECOMMENDED, NOT REQUIRED (the owner, 2 Nov 2026): a discreet line inviting whoever runs
 * the fund (its managers, the platform's administrator) to switch the second factor on,
 * from « Mon profil ». Nothing is blocked, and the line goes away once the factor is on.
 * The server decides who is invited (`recommended`), the screen only asks; an investor's
 * account is offered the factor in its profile and never sees this line.
 */
export function TwoFactorBanner() {
  const { t } = useTranslation()
  const email = useAuthStore((s) => s.email)
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  const [show, setShow] = useState(false)
  const key = email ? snoozeKey(email) : ''

  useEffect(() => {
    if (!email || !seesWholeFund) return
    if (readSnooze(key) > Date.now()) return
    let alive = true
    authApi.twoFactor
      .status()
      .then(({ data }) => {
        if (alive) setShow(data.recommended && !data.enabled)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [email, seesWholeFund, key])

  if (!show) return null

  const snooze = () => {
    try {
      localStorage.setItem(key, String(Date.now() + SNOOZE_MS))
    } catch {
      // A browser that refuses the storage shows the line again next time: harmless.
    }
    setShow(false)
  }

  return (
    <div className="mx-4 mt-3 flex items-center gap-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900 sm:mx-6 lg:mx-8">
      <ShieldCheck size={16} className="shrink-0" />
      <span className="min-w-0 flex-1">{t('twoFactor.bannerText')}</span>
      <Link to="/profile#security" onClick={() => setShow(false)} className="shrink-0 font-medium underline">
        {t('twoFactor.bannerAction')}
      </Link>
      <button
        type="button"
        onClick={snooze}
        title={t('twoFactor.bannerDismissHelp')}
        className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-xs text-sky-800 hover:bg-sky-100"
      >
        <X size={13} /> <span className="hidden sm:inline">{t('twoFactor.bannerDismiss')}</span>
        <span className="sr-only sm:hidden">{t('twoFactor.bannerDismiss')}</span>
      </button>
    </div>
  )
}
