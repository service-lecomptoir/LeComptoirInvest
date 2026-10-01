import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'

/**
 * Tells the reader a NEWER build of the app has been deployed, and offers one gesture to
 * pick it up. Ported from Le Comptoir Immo (`components/layout/UpdateBanner.tsx`).
 *
 * Why it exists: a deploy swaps the hashed bundles on the server, but a tab opened days ago
 * keeps running the old code against the new API. A fix reported « not deployed » on Immo
 * came from exactly that gap (4 Sept): the fix WAS live, the tab was not.
 *
 * How it detects: the entry HTML names the main script with a content hash
 * (`index-<hash>.js`). `/` is fetched again, cache busted, on a slow interval and whenever
 * the tab comes back into view, and the hash the server serves is compared with the one
 * this page booted from. A different hash is a new build. No API, no version endpoint to
 * keep, nothing to add to the pipeline: Vite's bundle name IS the build stamp.
 */

const SIGNATURE = /index-[A-Za-z0-9_-]+\.js/

function bootSignature(): string | null {
  const script = document.querySelector<HTMLScriptElement>('script[src*="index-"]')
  const m = script?.src.match(SIGNATURE)
  return m ? m[0] : null
}

async function liveSignature(): Promise<string | null> {
  try {
    const res = await fetch(`/?update-probe=${Date.now()}`, { cache: 'no-store' })
    if (!res.ok) return null
    const m = (await res.text()).match(SIGNATURE)
    return m ? m[0] : null
  } catch {
    return null
  }
}

const CHECK_EVERY_MS = 15 * 60 * 1000

export function UpdateBanner() {
  const { t } = useTranslation()
  const [updateReady, setUpdateReady] = useState(false)

  useEffect(() => {
    // In development the entry is `/src/main.tsx`, with no hash: nothing to compare.
    const booted = bootSignature()
    if (!booted) return

    let cancelled = false
    const check = async () => {
      const live = await liveSignature()
      if (!cancelled && live && live !== booted) setUpdateReady(true)
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') void check()
    }
    const timer = window.setInterval(check, CHECK_EVERY_MS)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  if (!updateReady) return null

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-brand-navy px-4 py-2.5 text-sm text-white shadow-lg">
      <span>{t('updateBanner.newVersion')}</span>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="inline-flex items-center gap-1.5 rounded-lg bg-white/15 px-3 py-1 font-medium hover:bg-white/25"
      >
        <RefreshCw size={14} /> {t('updateBanner.reload')}
      </button>
    </div>
  )
}
