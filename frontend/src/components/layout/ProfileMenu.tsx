import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, CreditCard, KeyRound, LogOut } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { confirmDialog } from '@/store/confirm'

/**
 * Le compte, en haut à droite, comme dans Le Comptoir Immo.
 *
 * ⚠️ CE QUI ÉTAIT EN BAS DU MENU N'Y AVAIT PAS SA PLACE. Le bandeau latéral répond à
 * « où vais-je » ; « qui suis-je » et « comment je pars » sont une autre question, et les
 * ranger sous les écrans du fonds les faisait lire comme deux écrans de plus. Un lecteur
 * qui vient d'un autre produit de la maison les cherche en haut à droite, parce que c'est
 * là qu'ils sont partout ailleurs.
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

  // Un menu se ferme quand on clique ailleurs. Sans cela il reste ouvert derrière le
  // premier clic suivant, et ce clic-là est perdu pour l'écran qu'il visait.
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

  // ⚠️ Une fenêtre du PRODUIT, jamais `window.confirm`. Se déconnecter d'un clic mal placé
  // fait perdre ce qu'un formulaire ouvert contenait, et la boîte du navigateur ne sait ni
  // nommer le compte ni distinguer « annuler » de « partir ».
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

  /** L'initiale de l'adresse, faute de mieux : ce produit ne stocke pas de nom d'affichage
   *  sur le compte. Un point d'interrogation vaut mieux qu'une lettre inventée. */
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
          {/* Qui est connecté, en toutes lettres. C'est la question à laquelle ce menu
              répond en premier, et la seule que l'avatar ne sait pas dire. */}
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
            <p className="text-sm font-medium text-gray-900 truncate">{email ?? '-'}</p>
            <p className="text-xs text-gray-500 capitalize">{role ?? ''}</p>
          </div>

          <div className="py-1">
            <button
              role="menuitem"
              onClick={() => {
                setOpen(false)
                navigate('/change-password')
              }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <KeyRound size={15} className="text-gray-400" />
              {t('password.title')}
            </button>
            {/* 🔴 RÉSERVÉ À QUI PAIE. `/billing` est un écran de la gestion du fonds :
                l'afficher à un investisseur lui proposerait une page qui le renvoie chez
                lui. Une ligne de menu qui ne mène nulle part est pire qu'une absente, elle
                laisse croire à un droit qu'on n'a pas.

                ⚠️ Et ce n'est PAS une protection : l'API refuse ces lectures d'elle-même.
                C'est de la politesse, comme le `FundOnly` du routeur. */}
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
