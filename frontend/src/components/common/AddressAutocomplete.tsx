import { useEffect, useRef, useState } from 'react'
import { publicApi } from '@/api'

/** What a chosen suggestion hands back: the parts a form stores apart. */
export interface AddressParts {
  street: string
  postcode: string
  city: string
  label: string
  /** A state, a province, a region: the international address has one. */
  region: string
}

/**
 * Address autocompletion, in France and abroad. The rule is the platform's: no bare
 * address box anywhere.
 *
 * 🔴 THROUGH THIS PRODUCT'S OWN SERVER, which relays to the console (28 Sept 2026: « tout
 * ce qui est commun, ça sera dans Alice »). The console asks the Base Adresse Nationale in
 * France and Photon elsewhere; the browser never calls them, so the gateway's security
 * policy blocks nothing. When nothing answers, typing by hand is all there is.
 *
 * Same behaviour as Le Comptoir RH's `AddressAutocomplete`, the reference.
 */
export function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  className,
  country,
  id,
  required = false,
}: {
  value: string
  onChange: (value: string) => void
  onSelect: (parts: AddressParts) => void
  className?: string
  /** The form's country (ISO code): the search keeps to it. France by default. */
  country?: string
  id?: string
  required?: boolean
}) {
  const [items, setItems] = useState<AddressParts[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const box = useRef<HTMLDivElement>(null)
  const focused = useRef(false)
  // A choice writes the box: that write must not fire a search of its own.
  const skip = useRef(false)

  useEffect(() => {
    const q = value.trim()
    if (skip.current) {
      skip.current = false
      return
    }
    if (!focused.current || q.length < 3) {
      setItems([])
      setOpen(false)
      return
    }
    const control = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const { data } = await publicApi.address(q, country || 'FR', control.signal)
        const list = (Array.isArray(data) ? data : []).slice(0, 7).map((row) => ({
          street: row.street,
          postcode: row.zip_code,
          city: row.city,
          label: row.label || [row.street, row.zip_code, row.city].filter(Boolean).join(' '),
          region: row.region ?? '',
        }))
        setItems(list)
        setOpen(list.length > 0)
        setActive(-1)
      } catch {
        // The network is away: typing the address by hand stays possible.
      }
    }, 250)
    return () => {
      clearTimeout(timer)
      control.abort()
    }
  }, [value, country])

  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  // 🔴 ONE CALL ON A CHOICE, NOT TWO. `onSelect` writes street, postcode and town in one
  // patch; a second `onChange(street)` right after it would be applied on the form's STALE
  // draft and wipe the postcode and the town it had just filled (measured on RH, 24 Sept).
  const choose = (parts: AddressParts) => {
    skip.current = true
    onSelect({ ...parts, street: parts.street || parts.label })
    setOpen(false)
    setItems([])
  }

  return (
    <div className="relative" ref={box}>
      <input
        id={id}
        type="text"
        autoComplete="off"
        required={required}
        className={className}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
          focused.current = true
          if (items.length) setOpen(true)
        }}
        onBlur={() => {
          focused.current = false
        }}
        onKeyDown={(e) => {
          if (!open || items.length === 0) return
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, items.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === 'Enter' && active >= 0) {
            e.preventDefault()
            choose(items[active])
          } else if (e.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {open && items.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-gray-200 bg-white text-sm shadow-lg"
        >
          {items.map((a, i) => (
            <li
              key={`${a.label}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(a)
              }}
              className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-gray-100' : 'hover:bg-gray-50'}`}
            >
              <span className="text-gray-900">{a.street || a.label}</span>
              {(a.postcode || a.city) && (
                <span className="text-gray-400">, {[a.postcode, a.city].filter(Boolean).join(' ')}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
