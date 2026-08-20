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
 * Changer son mot de passe. Une SECTION du profil, plus un écran à part.
 *
 * 🔴 POURQUOI CE N'EST PLUS UNE PAGE. « Changer de mot de passe » répondait à une
 * question qu'on ne se pose presque jamais, et occupait la seule entrée de menu qui
 * répondait à « qui suis-je ». Un lecteur qui vient du Comptoir Immo cherche son profil,
 * et y trouve son mot de passe parmi le reste : c'est l'organisation de la maison.
 *
 * 🔴 L'ÉCRAN QUI MANQUAIT, ET SON ABSENCE NE RESSEMBLAIT PAS À UNE PANNE.
 * `must_change_password` était posé à trois endroits — l'amorçage, la création d'un compte
 * par Alice, chaque réinitialisation — et fidèlement renvoyé à la connexion. Rien ne
 * permettait d'y répondre. Un contrôle qu'on ne peut pas satisfaire n'est pas un contrôle,
 * c'est un panneau.
 *
 * ⚠️ LE MOT DE PASSE ACTUEL EST DEMANDÉ MÊME QUAND LE CHANGEMENT EST IMPOSÉ. C'est
 * précisément là qu'on serait tenté de l'assouplir — « de toute façon il doit changer » —
 * et là que ça coûte : un jeton dérobé suffirait à s'approprier le compte définitivement,
 * la victime perdant l'accès que l'attaquant conserve.
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
      // En place, pas en toast : l'utilisateur regarde ce formulaire, et un message qui
      // s'efface pendant qu'il ressaisit est un message qu'il ne lira pas.
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
          {/* Le titre de l'encadré n'est PAS celui de la page : répété, il ne dit
              rien et pousse le message utile plus bas. */}
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
