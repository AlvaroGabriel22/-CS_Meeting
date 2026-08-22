import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '@/lib/api'

/**
 * The workbook's own vocabulary, rendered for the reader.
 *
 * `Total` reads `누적` because the department decided so once — not because a
 * model was asked and might answer differently next week. `PPM` reads `PPM`
 * everywhere, and a term nobody has decided on is shown exactly as the file
 * writes it. Never a guess (ADR-0044).
 *
 * The table comes from the backend, so the screen and the exported deck agree,
 * and it is fetched once per language and kept for the session.
 */
const cache = new Map<string, Record<string, string>>()

export function useGlossary(): (text: string | null | undefined) => string {
  const { i18n } = useTranslation()
  const language = i18n.language
  const [terms, setTerms] = useState<Record<string, string>>(() => cache.get(language) ?? {})

  useEffect(() => {
    const known = cache.get(language)
    if (known) {
      setTerms(known)
      return
    }
    let active = true
    void api
      .getGlossary(language)
      .then((answer) => {
        cache.set(language, answer.terms)
        if (active) setTerms(answer.terms)
      })
      .catch(() => undefined) // no glossary is the workbook's own words: fine
    return () => {
      active = false
    }
  }, [language])

  return (text) => {
    if (!text) return text ?? ''
    return terms[text.trim()] ?? text
  }
}
