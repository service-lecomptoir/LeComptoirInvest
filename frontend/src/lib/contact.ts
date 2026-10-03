import { useEffect, useState } from 'react'
import { apiClient } from '@/api/client'

/**
 * The address the public pages give a visitor to write to, held in Alice (Communication
 * screen, tab Alice) and relayed by this product's server (`/public/contact`).
 *
 * 🔴 IT WAS A CONSTANT HERE (the manager, 3 Oct 2026: « je dois avoir un endroit pour
 * modifier cette adresse avec une vue »): moving to a new domain meant a deployment.
 *
 * ⚠️ NOTHING IS SHOWN BEFORE THE ANSWER, AND NOTHING WHEN THERE IS NONE: an address
 * guessed here would be a second source. The sentences that name it say none instead.
 * Asked once per page load and shared by every component that reads it.
 */
let asked: Promise<string> | null = null

function ask(): Promise<string> {
  if (!asked) {
    asked = apiClient
      .get<{ contact_email?: string | null }>('/public/contact')
      .then(r => (r.data?.contact_email || '').trim())
      .catch(() => {
        asked = null // a failure is asked again next time, never remembered as « none »
        return ''
      })
  }
  return asked
}

export function useContactEmail(): string {
  const [email, setEmail] = useState('')
  useEffect(() => {
    let live = true
    ask().then(e => { if (live) setEmail(e) })
    return () => { live = false }
  }, [])
  return email
}
