import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import ptBR from './locales/pt-BR.json'
import ko from './locales/ko.json'
import type { Language } from '@/types/api'

export const LANGUAGES: { code: Language; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'pt-BR', label: 'Português (BR)' },
  { code: 'ko', label: '한국어' },
]

const STORAGE_KEY = 'cs-meeting:language'

function initialLanguage(): Language {
  const stored = localStorage.getItem(STORAGE_KEY) as Language | null
  if (stored && LANGUAGES.some((item) => item.code === stored)) return stored
  return 'en'
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    'pt-BR': { translation: ptBR },
    ko: { translation: ko },
  },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

/**
 * UI strings are translated here (static i18n).  Content written by the user
 * — issue reports — goes through the AI translation service instead, so the
 * two concerns never mix.
 */
export function setLanguage(language: Language) {
  localStorage.setItem(STORAGE_KEY, language)
  document.documentElement.lang = language
  return i18n.changeLanguage(language)
}

document.documentElement.lang = i18n.language

export default i18n
