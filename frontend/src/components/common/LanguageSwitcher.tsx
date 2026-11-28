import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
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
 * The interface language picker, ONE button (the owner, 28 Nov 2026, after Le Comptoir Immo's:
 * the flags as a list, in every Le Comptoir tool). It shows the current flag and the
 * language's code; the menu lists every language by its own name, and a language added to
 * `SUPPORTED_LANGS` comes in with no code at all. A navigation menu, not a modal: a click
 * outside or Escape closes it, nothing is lost.
 *
 * It replaced a segmented control, one button per language side by side, which took a
 * phone's bar for itself (the same component as Immo's `LanguageMenu`).
 *
 * `withCode` writes the current language's code after its flag (« fr »). `align` says on
 * which side of the button the list opens: `right` anchors it on the button's right edge, for
 * a button at the right end of a bar, where a list opened to the right would run off the
 * screen.
 */
export function LanguageMenu({ withCode = false, align = 'left' }: {
  withCode?: boolean
  align?: 'left' | 'right'
} = {}) {
  const { i18n, t } = useTranslation()
  // Two languages, both two-letter codes: the cut is the code itself.
  const current = (i18n.resolvedLanguage || i18n.language || 'fr').slice(0, 2)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('common.language')}
        title={SUPPORTED_LANGS.find((l) => l.code === current)?.label}
        className="flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-white"
      >
        <Flag code={current} className="w-4 h-auto rounded-[2px] ring-1 ring-black/10" />
        {withCode && <span>{current.slice(0, 2)}</span>}
        <ChevronDown size={12} className={clsx('text-gray-400 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div
          role="menu"
          className={clsx(
            'absolute z-50 mt-2 w-48 overflow-hidden rounded-xl border border-gray-200 bg-white py-1 shadow-lg',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {SUPPORTED_LANGS.map((l) => {
            const active = current === l.code
            return (
              <button
                key={l.code}
                type="button"
                role="menuitemradio"
                aria-checked={active}
                lang={l.code}
                onClick={() => {
                  setOpen(false)
                  void i18n.changeLanguage(l.code)
                }}
                className={clsx(
                  'flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm transition-colors',
                  active ? 'bg-gray-50 font-semibold text-brand-navy' : 'text-gray-700 hover:bg-gray-50',
                )}
              >
                <Flag code={l.code} className="w-4 h-auto rounded-[2px] ring-1 ring-black/10" />
                {l.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
