import { Info } from 'lucide-react'
import { useId, useLayoutEffect, useRef, useState } from 'react'

/** How long the hover and focus of a tap come before its click, at most. */
const TAP_GESTURE_MS = 600

/** The gap kept between the bubble and the edge of the content it opens in. */
const EDGE_GAP = 12

/**
 * An « i » beside a title or a status, its explanation in a bubble.
 *
 * 🔴 THE OWNER'S RULE (10 Oct 2026): no sentence under a figure, a card or a status. A
 * long text widens the card and drowns what it explains; the figure is read first, the
 * explanation on demand. Same component as Le Comptoir BTP's and Le Comptoir Compta's.
 *
 * Accessible: a focusable button with a short NAME (`label`), its bubble tied by
 * `aria-describedby`; it opens on hover, on focus and on a tap (a phone has no hover).
 * At 375 px the bubble is never wider than the screen.
 *
 * ⚠️ THE BUBBLE IS ALWAYS IN THE DOM, hidden by a class: `aria-describedby` must point at
 * an element that exists, or the description is lost while it is closed.
 *
 * ⚠️ THE BUBBLE STAYS INSIDE THE CONTENT (the owner, 12 Oct 2026, on Alice): centred on an
 * icon near the left of a card, it ran out of the content and lay against the side menu's
 * border. Once open, it is measured and slid sideways to keep EDGE_GAP from the edges of
 * the `main` area (the window when there is none), as Alice's `InfoTip` does.
 */
export function InfoBubble({
  text,
  label,
  align = 'center',
}: {
  text: string
  label: string
  /** Centred under the icon, ending at it (near the right edge) or starting at it. */
  align?: 'center' | 'end' | 'start'
}) {
  const [open, setOpen] = useState(false)
  // ⚠️ A TAP IS A HOVER, A FOCUS AND A CLICK IN A ROW (a phone sends all three): the first two
  // open the bubble, so a click that simply toggled shut it at once and the phone never saw it
  // (found on Market at 375 px, 31 Oct 2026). The click closes only a bubble opened before this gesture.
  const openedAt = useRef(0)
  const show = () => {
    if (!open) openedAt.current = Date.now()
    setOpen(true)
  }
  const id = useId()
  const bubble = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    const el = bubble.current
    if (!open || !el) return
    // `translate`, not `transform`: it adds to the centring the class already gives.
    el.style.translate = ''
    const area = el.closest('main')?.getBoundingClientRect() ?? { left: 0, right: document.documentElement.clientWidth }
    const rect = el.getBoundingClientRect()
    const shift =
      rect.left < area.left + EDGE_GAP
        ? area.left + EDGE_GAP - rect.left
        : rect.right > area.right - EDGE_GAP
          ? area.right - EDGE_GAP - rect.right
          : 0
    if (shift) el.style.translate = `${Math.round(shift)}px 0`
  }, [open])

  if (!text) return null
  const place = align === 'end' ? 'right-0' : align === 'start' ? 'left-0' : 'left-1/2 -translate-x-1/2'
  return (
    <span className="relative inline-flex items-center">
      <button
        type="button"
        aria-label={label}
        aria-describedby={id}
        aria-expanded={open}
        onMouseEnter={show}
        onMouseLeave={() => setOpen(false)}
        onFocus={show}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((v) => !v || Date.now() - openedAt.current < TAP_GESTURE_MS)
        }}
        className="text-gray-400 hover:text-gray-700 focus:outline-none focus-visible:text-gray-700 align-middle"
      >
        <Info size={13} aria-hidden />
      </button>
      <span
        ref={bubble}
        id={id}
        role="tooltip"
        className={`absolute top-full z-50 mt-1 w-64 max-w-[calc(100vw-2rem)] whitespace-pre-line rounded-lg border border-gray-200 bg-white p-2.5 text-left text-xs font-normal leading-snug text-gray-700 shadow-lg ${place} ${open ? '' : 'hidden'}`}
      >
        {text}
      </span>
    </span>
  )
}
