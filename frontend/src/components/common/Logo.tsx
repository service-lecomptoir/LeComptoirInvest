/**
 * The product's mark: the Comptoir « C » become a compass, in the family's colours.
 *
 * 🔴 THE SAME GLYPH AS THE FAVICON, AND THAT IS THE WHOLE POINT. `public/favicon.svg`
 * already carried the real mark; the sidebar drew the LETTER « C » in a teal box instead.
 * Two marks for one product means the tab and the screen do not look like the same
 * company, and the one nobody edits is the one that ends up being wrong.
 *
 * ⚠️ THE ARC IS DRAWN IN `currentColor`, so the mark takes the colour of whatever it sits
 * on: teal on navy in the rail, navy on white elsewhere. A hard-coded fill would have
 * needed a second copy the first time it appeared on a light background.
 */
export function LogoMark({ size = 28, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="Le Comptoir Invest"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Le carré navy du favicon : c'est lui qui fait reconnaître la famille. */}
      <rect width="64" height="64" rx="14" fill="#0D2F5C" />
      <path
        d="M41.5 22.8a13.2 13.2 0 0 0-9.4-3.8c-7.4 0-13.1 5.7-13.1 13s5.7 13 13.1 13c3.7 0 7-1.4 9.4-3.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="6.2"
        strokeLinecap="round"
      />
      {/* The compass needle: the family pin's orange points at the next country
          to invest in (variant I-C, chosen by the user on 5 September). */}
      <g transform="rotate(38 32 32)">
        <path d="M32 17.2 L36 32 L32 46.8 L28 32 Z" fill="#ffffff" />
        <path d="M32 17.2 L36 32 H28 Z" fill="#F97316" />
      </g>
      <circle cx="32" cy="32" r="3" fill="#ffffff" />
      <circle cx="32" cy="32" r="1.3" fill="#0D2F5C" />
      <circle cx="50.8" cy="40.8" r="1.9" fill="#FACC15" />
      <circle cx="48.4" cy="48.4" r="1.9" fill="#38BDF8" />
    </svg>
  )
}
