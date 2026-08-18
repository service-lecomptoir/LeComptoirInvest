import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { KeyRound } from 'lucide-react'
import { authApi } from '@/api'
import { errorMessage } from '@/api/client'
import { Button, Input } from '@/components/ui'
import { Card, Notice, PageHeader } from '@/components/common/Primitives'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toast'

/**
 * L'écran qui manquait, et son absence ne ressemblait pas à une panne.
 *
 * 🔴 `must_change_password` était posé à trois endroits — l'amorçage, la création d'un
 * compte par Alice, chaque réinitialisation — et fidèlement renvoyé à la connexion. Rien ne
 * permettait d'y répondre. On exigeait d'un utilisateur qu'il remplace un identifiant qu'un
 * autre avait vu, sans lui en donner le moyen. Un contrôle qu'on ne peut pas satisfaire
 * n'est pas un contrôle, c'est un panneau.
 *
 * ⚠️ LE MOT DE PASSE ACTUEL EST DEMANDÉ MÊME QUAND LE CHANGEMENT EST IMPOSÉ. C'est
 * précisément là qu'on serait tenté de l'assouplir — « de toute façon il doit changer » —
 * et c'est là que ça coûte : un jeton dérobé suffirait à s'approprier le compte
 * définitivement, la victime perdant l'accès que l'attaquant conserve.
 */
export default function ChangePassword() {
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
      // En place, pas en toast : l'utilisateur regarde ce formulaire, et un message qui
      // s'efface pendant qu'il ressaisit est un message qu'il ne lira pas.
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title={t('password.title')} />

      <div className="max-w-xl">
        <div className="mb-5">
          <Notice tone={mustChange ? 'warn' : 'info'} title={t('password.title')}>
            {mustChange ? t('password.forced') : t('password.optional')}
          </Notice>
        </div>

        <Card className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <Input
              label={t('password.current')}
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              hint={t('password.whyCurrent')}
            />
            <Input
              label={t('password.new')}
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              minLength={10}
            />
            <Input
              label={t('password.confirm')}
              type="password"
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
    </>
  )
}
