import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookMarked, ChevronDown, CreditCard, LogOut, UserRound } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { confirmDialog } from '@/store/confirm'

/**
 * The account, top right, as in Le Comptoir Immo.
 *
 * ⚠️ WHAT WAS AT THE BOTTOM OF THE MENU DID NOT BELONG THERE. The side bar answers
 * « où vais-je » ; « qui suis-je » and « comment je pars » are another question, and filing
 * them under the screens of the fund made them read as two more screens. A reader coming
 * from another product of the house looks for them at the top right, because that is where
 * they are everywhere else.
 */
export function ProfileMenu() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const email = useAuthStore((state) => state.email)
  const role = useAuthStore((state) => state.role)
  const logout = useAuthStore((state) => state.logout)
  const seesWholeFund = useAuthStore((state) => state.seesWholeFund)

  // A menu closes when one clicks elsewhere. Without that it stays open behind the
  // next click, and that click is lost for the screen it was aimed at.
  useEffect(() => {
    if (!open) return
    const outside = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  // ⚠️ A window of the PRODUCT, never `window.confirm`. Signing out on a misplaced click
  // loses what an open form held, and the box of the browser can neither name the account
  // nor tell « annuler » from « partir ».
  const signOut = async () => {
    setOpen(false)
    const ok = await confirmDialog({
      title: t('signOut.title'),
      message: email ? t('signOut.messageWithAccount', { email }) : t('signOut.message'),
      confirmLabel: t('common.signOut'),
    })
    if (!ok) return
    logout()
    navigate('/login')
  }

  /** The initial of the address, for want of better: this product stores no display name
   *  on the account. A question mark is worth more than an invented letter. */
  const initial = email?.trim().charAt(0).toUpperCase() || '?'

  return (
    <div className="relative" ref={box}>
      <button
        onClick={() => setOpen((was) => !was)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('profile.open')}
        className="flex items-center gap-1.5 px-1.5 py-1 rounded-xl hover:bg-gray-100 transition-colors"
      >
        <span className="w-8 h-8 rounded-full bg-brand-navy/10 text-brand-navy text-sm font-semibold grid place-items-center">
          {initial}
        </span>
        <ChevronDown
          size={14}
          className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-60 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-50"
        >
          {/* Who is signed in, in full. That is the question this menu answers
              first, and the only one the avatar cannot say. */}
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
            <p className="text-sm font-medium text-gray-900 truncate">{email ?? '-'}</p>
            <p className="text-xs text-gray-500 capitalize">{role ?? ''}</p>
          </div>

          <div className="py-1">
            <button
              role="menuitem"
              onClick={() => {
                setOpen(false)
                navigate('/profile')
              }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <UserRound size={15} className="text-gray-400" />
              {t('profile.title')}
            </button>
            {/* 🔴 RESERVED FOR WHOEVER PAYS. `/billing` is a screen of the management of the fund:
                showing it to an investor would offer them a page that sends them back
                home. A menu line that leads nowhere is worse than a missing one, it lets
                one believe in a right one does not have.

                ⚠️ And it is NOT a protection: the API refuses these reads by itself.
                It is politeness, like the `FundOnly` of the router. */}
            {seesWholeFund && (
              <button
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  navigate('/billing')
                }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <CreditCard size={15} className="text-gray-400" />
                {t('nav.billing')}
              </button>
            )}
            {/* The guide, for every account, as in the sibling products' account menu. It
                shows the fund's screens to the fund and the investor's to the investor. */}
            <button
              role="menuitem"
              onClick={() => {
                setOpen(false)
                navigate('/guide')
              }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <BookMarked size={15} className="text-gray-400" />
              {t('guide.title')}
            </button>
            <div className="border-t border-gray-100 my-1" />
            <button
              role="menuitem"
              onClick={signOut}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
            >
              <LogOut size={15} className="text-red-400" />
              {t('common.signOut')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
