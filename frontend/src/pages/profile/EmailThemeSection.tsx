import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { Check } from 'lucide-react'
import { accountApi } from '@/api'
import { errorMessage } from '@/api/client'
import { Card, Notice } from '@/components/common/Primitives'
import { Spinner } from '@/components/ui'
import { toast } from '@/store/toast'
import type { EmailLook, EmailTheme } from '@/types'

/**
 * The look of the e-mails the management company sends: a choice among Alice's catalogue.
 *
 * 🔴 THE LIST IS THE CONSOLE'S, NOT THIS SCREEN'S. Families, names and colours come from
 * `/account/email-theme`, which relays Alice's catalogue: a look added in the console
 * appears here without a deploy, and none is written in this file.
 *
 * ⚠️ « THE PRODUCT'S OWN » IS A CHOICE OF ITS OWN (null), not a copy of today's default.
 * It follows the console when the console changes its default; picking the same look by
 * name would freeze it.
 *
 * ⚠️ THE THUMBNAIL IS DRAWN FROM THE LOOK'S LAYOUT AND COLOURS, the same four values the
 * server lays a letter out with, so what is chosen is what goes out.
 */

/** A small header in the look's colours, over two lines of body. */
function Thumb({ theme }: { theme: EmailTheme | null }) {
  const layout = theme?.layout ?? 'rule'
  const ink = theme?.ink ?? '#0D2F5C'
  const accent = theme?.accent ?? '#0D2F5C'
  const soft = theme?.soft ?? '#64748b'
  const dark = layout === 'band' || layout === 'center'
  const centred = layout === 'center' || layout === 'crest'
  return (
    <div aria-hidden className="overflow-hidden rounded-md border border-gray-200 bg-white">
      {layout !== 'none' && (
        <div
          className={clsx('flex flex-col gap-1 px-3 py-2', centred && 'items-center')}
          style={{
            background: dark ? ink : '#ffffff',
            borderBottom: layout === 'band' ? undefined : `3px solid ${accent}`,
          }}
        >
          <span className="block h-2 w-16 rounded-sm" style={{ background: dark ? '#ffffff' : ink }} />
          <span className="block h-1.5 w-10 rounded-sm" style={{ background: soft }} />
        </div>
      )}
      <div className="space-y-1 px-3 py-2">
        <span className="block h-1.5 w-full rounded-sm bg-gray-200" />
        <span className="block h-1.5 w-2/3 rounded-sm bg-gray-200" />
      </div>
    </div>
  )
}

function Option({
  theme, name, description, chosen, busy, onPick,
}: {
  theme: EmailTheme | null
  name: string
  description: string
  chosen: boolean
  busy: boolean
  onPick: () => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      role="radio"
      aria-checked={chosen}
      disabled={busy}
      onClick={onPick}
      className={clsx(
        'w-full min-w-0 rounded-lg border p-3 text-left transition-colors',
        chosen ? 'border-[#0D2F5C] ring-1 ring-[#0D2F5C]' : 'border-gray-200 hover:border-gray-300',
      )}
    >
      <Thumb theme={theme} />
      <div className="mt-2 flex items-start justify-between gap-2">
        <p className="min-w-0 break-words text-sm font-medium text-gray-900">{name}</p>
        {chosen && (
          <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-[#0D2F5C]">
            <Check size={13} /> {t('emailTheme.chosen')}
          </span>
        )}
        {busy && <Spinner />}
      </div>
      {description && <p className="mt-0.5 break-words text-xs text-gray-500">{description}</p>}
    </button>
  )
}

export function EmailThemeSection() {
  const { t } = useTranslation()
  const [look, setLook] = useState<EmailLook | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The key being saved ('' for the product's own), so only that card shows a spinner.
  const [saving, setSaving] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    accountApi
      .emailTheme()
      .then(({ data }) => { if (!cancelled) setLook(data) })
      .catch((err) => { if (!cancelled) setError(errorMessage(err)) })
    return () => { cancelled = true }
  }, [])

  const pick = async (key: string | null) => {
    if (!look || saving !== null || key === look.email_theme) return
    setError(null)
    setSaving(key ?? '')
    try {
      const { data } = await accountApi.setEmailTheme(key)
      setLook(data)
      toast.success(t('emailTheme.saved'))
    } catch (err) {
      // In place: the manager is looking at this list, not at a toast that fades.
      setError(errorMessage(err))
    } finally {
      setSaving(null)
    }
  }

  const byKey = new Map((look?.themes ?? []).map((theme) => [theme.key, theme]))
  const defaultTheme = look?.default ? byKey.get(look.default) ?? null : null
  const known = new Set((look?.families ?? []).map((family) => family.key))
  const others = (look?.themes ?? []).filter((theme) => !known.has(theme.family))
  const groups = [
    ...(look?.families ?? []).map((family) => ({
      key: family.key,
      name: family.name,
      hint: family.hint,
      themes: (look?.themes ?? []).filter((theme) => theme.family === family.key),
    })),
    ...(others.length ? [{ key: '', name: t('emailTheme.otherFamily'), hint: '', themes: others }] : []),
  ].filter((group) => group.themes.length)

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold text-gray-900">{t('emailTheme.title')}</h2>
      <p className="mb-3 text-sm text-gray-600 leading-relaxed">{t('emailTheme.lead')}</p>

      {error && (
        <p className="mb-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {!look && !error && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Spinner /> {t('emailTheme.loading')}
        </div>
      )}

      {look && !look.catalogue_available && (
        <Notice tone="warn" title={t('emailTheme.unavailableTitle')}>
          {t('emailTheme.unavailable')}
        </Notice>
      )}

      {look && look.catalogue_available && (
        <Card className="p-4">
          <div role="radiogroup" aria-label={t('emailTheme.title')} className="space-y-5">
            <Option
              theme={defaultTheme}
              name={t('emailTheme.productDefault')}
              description={
                defaultTheme
                  ? t('emailTheme.productDefaultNamed', { name: defaultTheme.name })
                  : t('emailTheme.productDefaultUnnamed')
              }
              chosen={look.email_theme === null}
              busy={saving === ''}
              onPick={() => pick(null)}
            />
            {groups.map((group) => (
              <div key={group.key || 'others'}>
                <p className="text-xs font-semibold text-gray-700">{group.name}</p>
                {group.hint && <p className="mt-0.5 text-xs text-gray-500">{group.hint}</p>}
                <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {group.themes.map((theme) => (
                    <Option
                      key={theme.key}
                      theme={theme}
                      name={theme.name}
                      description={theme.description}
                      chosen={look.email_theme === theme.key}
                      busy={saving === theme.key}
                      onPick={() => pick(theme.key)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
      <p className="mt-2 text-xs text-gray-500 leading-relaxed">{t('emailTheme.help')}</p>
    </section>
  )
}
