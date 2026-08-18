import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import clsx from 'clsx'

export interface SelectOption {
  value: string
  label: string
}

interface SelectProps {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  /** Class of the trigger button (kept in line with the form inputs' style). */
  className?: string
  id?: string
  disabled?: boolean
  'aria-label'?: string
}

/**
 * A custom dropdown that ALWAYS opens downwards (`top-full`), unlike the native
 * `<select>` whose direction the browser picks from the room available. The scrolling
 * list is height-bounded so it fits under the field. Keyboard accessible (arrows,
 * Enter, Escape) and closed by a click outside.
 */
export function Select({
  value, onChange, options, placeholder, className, id, disabled,
  'aria-label': ariaLabel,
}: SelectProps) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState<number>(-1)
  const ref = useRef<HTMLDivElement>(null)
  const current = options.find(o => o.value === value)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  // On opening, put the keyboard cursor on the current option.
  useEffect(() => {
    if (open) setActive(Math.max(0, options.findIndex(o => o.value === value)))
  }, [open, value, options])

  const choose = (v: string) => { onChange(v); setOpen(false) }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) { setOpen(true); return }
      setActive(a => Math.min(options.length - 1, a + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) { setOpen(true); return }
      setActive(a => Math.max(0, a - 1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      if (open && active >= 0) { e.preventDefault(); choose(options[active].value) }
      else if (!open) { e.preventDefault(); setOpen(true) }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        id={id}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => !disabled && setOpen(o => !o)}
        onKeyDown={onKeyDown}
        className={clsx(className, 'text-left flex items-center justify-between gap-2', disabled && 'opacity-60 cursor-not-allowed')}
      >
        <span className={clsx('truncate', !current && 'text-gray-400')}>
          {current ? current.label : placeholder}
        </span>
        <ChevronDown size={16} className="shrink-0 text-gray-400" />
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute z-50 left-0 top-full mt-1 w-full max-h-60 overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg py-1"
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(o.value)}
              className={clsx(
                'px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-2',
                i === active ? 'bg-brand-navy/5' : '',
                o.value === value ? 'text-brand-navy font-medium' : 'text-gray-700',
              )}
            >
              <span className="truncate">{o.label}</span>
              {o.value === value && <Check size={15} className="shrink-0 text-brand-navy" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
