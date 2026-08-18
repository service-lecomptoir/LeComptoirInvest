import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import fr from './locales/fr.json'
import en from './locales/en.json'

/**
 * ⚠️ THE ENGLISH CATALOGUE IS WRITTEN BY HAND, and it is never generated from the French
 * one. The sister product's `i18n:sync` copies the French text into `en.json` when no
 * translation key is available, and the completeness check then passes on a file that is
 * entirely French. A green check over an untranslated catalogue is worse than a red one —
 * it is the only state in which nobody ever looks again. `npm run i18n:check` refuses an
 * English string identical to its French counterpart for exactly that reason.
 *
 * The storage key is shared with the rest of the house so somebody who picked English in
 * one product does not have to pick it again in the next.
 */
export const LANG_STORAGE_KEY = 'lecomptoir-lang'

export const SUPPORTED_LANGS = [
  { code: 'fr', label: 'Français' },
  { code: 'en', label: 'English' },
] as const

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { fr: { translation: fr }, en: { translation: en } },
    fallbackLng: 'fr',
    supportedLngs: SUPPORTED_LANGS.map((l) => l.code),
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: LANG_STORAGE_KEY,
      caches: ['localStorage'],
    },
  })

export default i18n
