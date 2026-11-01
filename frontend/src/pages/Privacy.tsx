import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, LogIn } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { LogoMark } from '@/components/common/Logo'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { Card, Loading, Notice } from '@/components/common/Primitives'
import { Subprocessors } from '@/components/terms/Subprocessors'
import { TermsBody } from '@/components/terms/TermsReader'
import { usePrivacyNotice } from '@/lib/terms'

/**
 * « Confidentialité et mentions légales », public: read without an account, from the
 * sign-in page, the public pages and the account menu (the owner, 1 Nov 2026).
 *
 * 🔴 ALICE HOLDS THE TEXT (`kind = "prv"`), THIS PAGE DRAWS IT: one text for every product
 * of the house, the contact address inside it, read by anybody and accepted by nobody. No
 * word of it is written in this product.
 *
 * ⚠️ NOT PUBLISHED YET IS NOT AN ERROR. The first text is a draft the owner has a lawyer
 * read: until it is published Alice answers 404, and the page says the text is being
 * published, without a red block. The list of sub-processors stands under it either way.
 */
export default function Privacy() {
  const { t, i18n } = useTranslation()
  const signedIn = useAuthStore((s) => s.isAuthenticated)
  const language = i18n.resolvedLanguage || i18n.language || 'fr'
  const notice = usePrivacyNotice(language)

  // ⚠️ OUTSIDE THE SHELL, like the sign-in page: it names its own tab.
  useEffect(() => {
    document.title = `Le Comptoir Invest | ${t('privacy.title')}`
  }, [t, i18n.language])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-brand-navy text-white">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <Link to="/" className="flex min-w-0 items-center gap-2">
            <LogoMark size={30} className="shrink-0 rounded-md ring-1 ring-white/25 text-brand-teal" />
            <span className="truncate text-base font-semibold tracking-tight">
              {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
            </span>
          </Link>
          <span className="flex-1" />
          <LanguageSwitcher dark />
          {!signedIn && (
            <Link
              to="/login"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/25 px-3 py-1.5 text-sm hover:bg-white/10"
            >
              <LogIn size={15} />
              <span className="hidden sm:inline">{t('pricing.signIn')}</span>
              <span className="sr-only sm:hidden">{t('pricing.signIn')}</span>
            </Link>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-5 px-4 py-8">
        <Link to="/" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-brand-navy">
          <ArrowLeft size={14} /> {t('privacy.back')}
        </Link>
        <h1 className="text-2xl font-bold text-brand-navy">{t('privacy.title')}</h1>

        <Card>
          <div className="p-4 sm:p-6">
            {notice.state === 'loading' ? (
              <Loading label={t('privacy.loading')} />
            ) : notice.state === 'none' ? (
              <Notice tone="info" title={t('privacy.notPublishedTitle')}>
                {t('privacy.notPublished')}
              </Notice>
            ) : notice.state === 'unavailable' ? (
              <Notice tone="warn" title={t('privacy.unavailableTitle')}>
                {t('privacy.unavailable')}
              </Notice>
            ) : (
              // A table of the text scrolls in its own frame on a phone, never the page.
              <div className="overflow-x-auto">
                <TermsBody text={notice.text} scroll={false} />
              </div>
            )}
          </div>
        </Card>

        <Subprocessors />
      </main>
      <footer className="mx-auto max-w-3xl px-4 pb-8 text-xs text-gray-400">
        © {new Date().getFullYear()} {t('brand.full')}
      </footer>
    </div>
  )
}
