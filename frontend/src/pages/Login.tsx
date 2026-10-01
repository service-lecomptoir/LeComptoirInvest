import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { ChevronRight, Lock } from 'lucide-react'
import { Button, Input } from '@/components/ui'
import { Notice } from '@/components/common/Primitives'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { authApi } from '@/api'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { LogoMark } from '@/components/common/Logo'
import { SignupForm } from '@/components/signup/SignupForm'
import { safeNext } from '@/lib/nextPath'
import { useFieldCheck } from '@/lib/formCheck'

export default function Login() {
  const { t, i18n } = useTranslation()

  // ⚠️ SIGN-IN IS OUTSIDE THE SHELL, therefore outside the effect that names the tabs. It
  // is however the only screen a reader sees BEFORE having an account open, and often the
  // one they leave in a tab while looking for their password elsewhere.
  useEffect(() => {
    document.title = `Le Comptoir Invest | ${t('login.title')}`
  }, [t, i18n.language])
  const { login, isAuthenticated } = useAuthStore()
  const navigate = useNavigate()
  // Where the reader was sent away from, if it is a path of this site (`lib/nextPath`).
  const [params] = useSearchParams()
  const next = safeNext(params.get('next')) ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { errors, check } = useFieldCheck()
  // 🔴 THE SIGN-UP GOES THROUGH THE CONSOLE (`SignupForm`), as on Le Comptoir RH: the
  // prospect chooses a catalogue plan, Alice confirms the e-mail and opens the account.
  const [signingUp, setSigningUp] = useState(false)
  // The sign-up's title follows the form: an account, or a quote (as Le Comptoir Immo).
  const [signupQuoted, setSignupQuoted] = useState(false)
  // 🔴 A FORGOTTEN PASSWORD HAS A WAY BACK (customer recipe, 30 Sept 2026: there was none,
  // and the only exit was writing to support). A link by e-mail, never a password.
  const [forgetting, setForgetting] = useState(false)

  if (isAuthenticated) return <Navigate to={next} replace />

  const secured = window.location.protocol === 'https:'

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const fine = check([
      { name: 'email', value: email, required: true, email: true },
      { name: 'password', value: password, required: true },
    ])
    if (!fine) return
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate(next, { replace: true })
    } catch (err) {
      // Shown in place rather than as a toast: the user is looking at this form, and a
      // message that fades while they retype is a message they will miss.
      setError(signInError(err, t))
    } finally {
      setBusy(false)
    }
  }

  const points = [t('login.point1'), t('login.point2'), t('login.point3')]

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2">
      {/* The left panel is the only decorative surface in the product. Every other screen
          is a table: a fund console earns trust by being legible, not by being styled.
          Laid out as Le Comptoir Immo's: the mark, what the product does, and the door to
          the public page. On a telephone it gives way to the compact header of the form. */}
      <div className="relative hidden lg:flex flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-navy to-brand-navy-light p-10 text-white">
        <div className="pointer-events-none absolute -top-32 -right-32 h-96 w-96 rounded-full bg-brand-teal opacity-20 blur-3xl" />
        <div className="relative flex items-center gap-2.5">
          <LogoMark size={40} className="shrink-0 rounded-lg ring-1 ring-white/25 text-brand-teal" />
          <span className="text-lg font-semibold tracking-tight">
            {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
          </span>
        </div>
        <div className="relative max-w-md">
          <p className="text-2xl font-semibold leading-snug tracking-tight">{t('login.pitchTitle')}</p>
          <p className="mt-4 text-sm text-white/70 leading-relaxed">{t('login.pitchBody')}</p>
          <ul className="mt-6 space-y-2.5">
            {points.map((point) => (
              <li key={point} className="flex items-start gap-2.5 text-sm text-white/85">
                <ChevronRight size={16} className="mt-0.5 shrink-0 text-brand-orange" />
                {point}
              </li>
            ))}
          </ul>
          {/* The door to the public page: without it, whoever lands on the sign-in never
              finds what the product does nor its plans. */}
          <div className="mt-8 border-t border-white/15 pt-4">
            <Link to="/" className="inline-flex items-center gap-1 text-sm font-semibold text-brand-orange hover:underline">
              {t('login.discover')} <ChevronRight size={14} />
            </Link>
            <p className="mt-1 text-xs text-white/60">{t('login.discoverHelp')}</p>
          </div>
        </div>
        <p className="relative text-xs text-white/40">
          © {new Date().getFullYear()} {t('brand.full')}
        </p>
      </div>

      <div className="flex min-w-0 items-center justify-center p-6 bg-white">
        <div className={signingUp ? 'w-full max-w-md' : 'w-full max-w-sm'}>
          <div className="flex items-center justify-between gap-3 mb-8">
            <Link to="/" className="lg:hidden flex min-w-0 items-center gap-2.5">
              <LogoMark size={32} className="shrink-0 rounded-md text-brand-teal" />
              <span className="truncate text-base font-semibold text-brand-navy tracking-tight">
                {t('brand.full')}
              </span>
            </Link>
            {/* The picker is on the sign-in page on purpose: somebody who cannot read the
                form is exactly the person who needs to change the language. */}
            <div className="ml-auto">
              <LanguageSwitcher />
            </div>
          </div>

          {forgetting ? (
            <ForgotPassword email={email} onBack={() => setForgetting(false)} />
          ) : signingUp ? (
            <div>
              <h1 className="text-xl font-semibold text-gray-900 tracking-tight">
                {signupQuoted ? t('signup.quoteTitle') : t('signup.title')}
              </h1>
              {/* The opening sentence is the form's own (the demo, or the quotation): the
                  pricing page shows the same form and says the same thing. */}
              <Link to="/pricing" className="mt-1 mb-4 inline-block text-sm text-brand-navy underline">
                {t('login.seePricing')}
              </Link>
              <SignupForm onBack={() => setSigningUp(false)} onQuotedChange={setSignupQuoted} />
            </div>
          ) : (
            <form onSubmit={submit} noValidate>
              <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{t('login.title')}</h1>
              <p className="mt-1 mb-6 text-sm text-gray-500">{t('login.subtitle')}</p>

              <div className="space-y-4">
                <Input
                  label={t('login.email')}
                  hint={t('login.emailHint')}
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  error={errors.email}
                />
                <div>
                  <Input
                    label={t('login.password')}
                    hint={t('login.passwordHint')}
                    type="password"
                    revealable
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    error={errors.password}
                  />
                  <button
                    type="button"
                    onClick={() => setForgetting(true)}
                    className="mt-2 text-sm text-brand-navy underline"
                  >
                    {t('login.forgot')}
                  </button>
                </div>
              </div>

              {error && (
                <p className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <Button type="submit" fullWidth isLoading={busy} className="mt-6">
                {t('login.submit')}
              </Button>

              {/* Said only when it is true: the page itself came over HTTPS. */}
              {secured && (
                <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-gray-400">
                  <Lock size={13} className="shrink-0" />
                  {t('login.secured')}
                </p>
              )}

              <div className="mt-6 border-t border-gray-100 pt-4 text-sm text-gray-600">
                <p>
                  {t('login.noAccount')}{' '}
                  <button
                    type="button"
                    onClick={() => setSigningUp(true)}
                    className="font-medium text-brand-navy underline"
                  >
                    {t('login.askAccess')}
                  </button>
                </p>
                <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  <Link to="/pricing" className="text-brand-navy underline">
                    {t('login.seePricing')}
                  </Link>
                  {/* The public page, reachable on a telephone too, where the brand panel
                      and its link are not shown. */}
                  <Link to="/" className="text-brand-navy underline lg:hidden">
                    {t('login.discover')}
                  </Link>
                </p>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * What a failed sign-in tells the reader, case by case, from what the server REALLY answers
 * (`api/v1/auth.py`): 401 for wrong credentials and 403 for a disabled account, each with
 * its own sentence, which is shown as written; 422 for an address the validator refuses.
 *
 * 🔴 « WRONG PASSWORD » IS NEVER SAID FOR A SILENT SERVER. A reader told their password is
 * wrong while the API restarts retypes it, then resets it, for nothing: an unreachable
 * server, a proxy answering 502 to 504 during a deployment and a server error each get
 * their own words (as Le Comptoir Immo).
 */
function signInError(err: any, t: TFunction): string {
  const status = err?.response?.status as number | undefined
  const raw = err?.response?.data?.detail
  const detail = typeof raw === 'string' && raw.trim() ? raw : undefined
  if (!err?.response) return t('login.errors.unreachable')
  if (status === 401 || status === 403) return detail ?? t('login.errors.badCredentials')
  if (status === 422) return t('login.errors.invalidEmail')
  if (status === 502 || status === 503 || status === 504) return t('login.errors.unavailable')
  if (status && status >= 500) return detail ?? t('login.errors.serverError')
  return detail ?? errorMessage(err)
}

/**
 * « Mot de passe oublié »: an address in, a link out by e-mail.
 *
 * ⚠️ THE SAME ANSWER WHETHER THE ADDRESS HOLDS AN ACCOUNT OR NOT: the server words it, and
 * this screen shows it as it is. Telling « unknown address » apart would tell anybody which
 * addresses hold an account on a fund.
 */
function ForgotPassword({ email: typed, onBack }: { email: string; onBack: () => void }) {
  const { t } = useTranslation()
  const [email, setEmail] = useState(typed)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  const { errors, check } = useFieldCheck()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!check([{ name: 'email', value: email, required: true, email: true }])) return
    setBusy(true)
    try {
      const { data } = await authApi.forgotPassword(email.trim())
      setSent(data.message)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{t('login.forgotTitle')}</h1>
      <p className="mt-1 mb-6 text-sm text-gray-500">{t('login.forgotHelp')}</p>
      {sent ? (
        <Notice tone="info" title={t('login.forgotSentTitle')}>
          {sent}
        </Notice>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          <Input
            label={t('login.email')}
            hint={t('login.forgotEmailHint')}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            error={errors.email}
          />
          {error && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          <Button type="submit" fullWidth isLoading={busy}>
            {t('login.forgotSubmit')}
          </Button>
        </form>
      )}
      <button type="button" onClick={onBack} className="mt-6 text-sm text-brand-navy underline">
        {t('login.backToSignIn')}
      </button>
    </div>
  )
}
