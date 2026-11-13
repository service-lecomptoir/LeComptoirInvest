import { createContext } from 'react'
import type { TermsStatus } from '@/api/terms'

/**
 * The status the gate read (`TermsGate`), handed to the application it draws: the banner
 * announcing a new version during its notice (`UpcomingTermsBanner`) reads it, never a
 * second request. Null outside the gate, or when the server did not answer.
 */
export const TermsStatusContext = createContext<TermsStatus | null>(null)
