import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { KeyRound } from 'lucide-react'
import { authApi } from '@/api'
import { errorMessage } from '@/api/client'
import { Button, Input } from '@/components/ui'
import { Card, Notice } from '@/components/common/Primitives'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toast'

/**
 * Changing one's password. A SECTION of the profile, no longer a screen apart.
 *
 * 🔴 WHY IT IS NO LONGER A PAGE. « Changer de mot de passe » answered a question one almost
 * never asks, and took up the only menu entry that answered « qui suis-je ». A reader
 * coming from Le Comptoir Immo looks for their profile, and finds their password there
 * among the rest: that is the organisation of the house.
 *
 * 🔴 THE SCREEN THAT WAS MISSING, AND ITS ABSENCE DID NOT LOOK LIKE A BREAKDOWN.
 * `must_change_password` was set in three places -- the seeding, the creation of an account
 * by Alice, every reset -- and faithfully returned at sign-in. Nothing allowed it to be
 * answered. A check one cannot satisfy is not a check, it is a signpost.
 *
 * ⚠️ THE CURRENT PASSWORD IS ASKED FOR EVEN WHEN THE CHANGE IS FORCED. That is precisely
 * where one would be tempted to soften it -- « de toute façon il doit changer » -- and
 * where it costs: a stolen token would be enough to take over the account for good, the
 * victim losing the access the attacker keeps.
 */
export function PasswordSection() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const mustChange = useAuthStore((s) => s.mustChangePassword)
  const refreshMe = useAuthStore((s) => s.refreshMe)

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (next !== confirm) {
      setError(t('password.mismatch'))
      return
    }
    if (next.length < 10) {
      setError(t('password.tooShort'))
      return
    }
    setBusy(true)
    try {
      await authApi.changePassword(current, next)
      toast.success(t('password.done'))
      await refreshMe()
      navigate('/', { replace: true })
    } catch (err) {
      // In place, not in a toast: the user is looking at this form, and a message that
      // fades away while they type it again is a message they will not read.
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="max-w-xl">
      <h2 className="mb-3 text-sm font-semibold text-gray-900">{t('password.title')}</h2>
      <div>
        <div className="mb-5">
          {/* The title of the box is NOT that of the page: repeated, it says
              nothing and pushes the useful message further down. */}
          <Notice
            tone={mustChange ? 'warn' : 'info'}
            title={mustChange ? t('password.mustTitle') : t('password.optionalTitle')}
          >
            {mustChange ? t('password.forced') : t('password.optional')}
          </Notice>
        </div>

        <Card className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <Input
              label={t('password.current')}
              type="password"
              revealable
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              hint={t('password.whyCurrent')}
            />
            <Input
              label={t('password.new')}
              type="password"
              revealable
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              minLength={10}
            />
            <Input
              label={t('password.confirm')}
              type="password"
              revealable
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />

            {error && (
              <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <Button type="submit" isLoading={busy}>
              <KeyRound size={15} /> {t('password.submit')}
            </Button>
          </form>
        </Card>
      </div>
    </section>
  )
}
