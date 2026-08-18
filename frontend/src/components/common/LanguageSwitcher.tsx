import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { SUPPORTED_LANGS } from '@/i18n'

/**
 * Flags drawn in SVG, never as emoji.
 *
 * ⚠️ ON WINDOWS, FLAG EMOJI DO NOT RENDER: they come out as the two letters « FR », « GB ».
 * The house runs on Windows. An SVG is a real flag on every platform, and the language
 * picker is the one control a user reaches for when they cannot read the page.
 */
function Flag({ code, className = '' }: { code: string; className?: string }) {
  const uid = useId()
  if (code === 'fr') {
    return (
      <svg viewBox="0 0 3 2" className={className} aria-hidden="true">
        <rect width="3" height="2" fill="#fff" />
        <rect width="1" height="2" fill="#0055A4" />
        <rect x="2" width="1" height="2" fill="#EF4135" />
      </svg>
    )
  }
  if (code === 'en') {
    // The Union Jack. The clip-paths carry a unique id so several flags can share a page.
    const s = `s-${uid}`
    const t = `t-${uid}`
    return (
      <svg viewBox="0 0 60 30" className={className} aria-hidden="true">
        <clipPath id={s}><path d="M0,0 v30 h60 v-30 z" /></clipPath>
        <clipPath id={t}><path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" /></clipPath>
        <g clipPath={`url(#${s})`}>
          <path d="M0,0 v30 h60 v-30 z" fill="#012169" />
          <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" strokeWidth={6} />
          <path d="M0,0 L60,30 M60,0 L0,30" clipPath={`url(#${t})`} stroke="#C8102E" strokeWidth={4} />
          <path d="M30,0 v30 M0,15 h60" stroke="#fff" strokeWidth={10} />
          <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" strokeWidth={6} />
        </g>
      </svg>
    )
  }
  return <span className="text-[10px] font-semibold">{code.toUpperCase()}</span>
}

/**
 * A segmented control: one button per language, flag plus code, the active one filled in
 * the brand navy. Adding a language to `SUPPORTED_LANGS` adds it here with no code at all.
 *
 * `dark` renders it for the navy rail, where the light version would disappear.
 */
export function LanguageSwitcher({ dark = false }: { dark?: boolean }) {
  const { i18n, t } = useTranslation()
  const current = (i18n.resolvedLanguage || i18n.language || 'fr').slice(0, 2)

  return (
    <div
      role="group"
      aria-label={t('common.language')}
      className={clsx(
        'inline-flex items-center gap-0.5 rounded-lg p-0.5 border',
        dark ? 'border-white/15 bg-white/5' : 'border-gray-200 bg-gray-50',
      )}
    >
      {SUPPORTED_LANGS.map((l) => {
        const active = current === l.code
        return (
          <button
            key={l.code}
            type="button"
            onClick={() => i18n.changeLanguage(l.code)}
            aria-pressed={active}
            title={l.label}
            className={clsx(
              'flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors',
              active
                ? 'bg-brand-navy text-white shadow-sm'
                : dark
                  ? 'text-white/60 hover:text-white hover:bg-white/10'
                  : 'text-gray-500 hover:text-gray-800 hover:bg-white',
              active && dark && 'bg-white text-brand-navy',
            )}
          >
            <Flag code={l.code} className="w-4 h-auto rounded-[2px] ring-1 ring-black/10" />
            <span className="uppercase">{l.code}</span>
          </button>
        )
      })}
    </div>
  )
}
