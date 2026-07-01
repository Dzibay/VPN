import { getProjectLegalTokens } from '../../composables/useProjectLegal.js'

export const LEGAL_FOOTER_LINKS = [
  { to: '/terms', label: 'Лицензионная оферта' },
  { to: '/privacy', label: 'Конфиденциальность' },
  { to: '/consent', label: 'Обработка ПД' },
  { to: '/refund', label: 'Возврат платежей' },
  { to: '/cookies', label: 'Cookies' },
  { to: '/marketing', label: 'Рекламная рассылка' },
]

/** @typedef {{
 *   serviceName: string,
 *   siteUrl: string,
 *   domain: string,
 *   telegramBot: string,
 *   supportTelegram: string,
 *   supportEmail: string,
 *   operatorName: string,
 *   operatorInn: string,
 *   disputeJurisdiction: string,
 *   effectiveDate: string,
 * }} ProjectLegalTokens */

function tokens() {
  return getProjectLegalTokens()
}

/** @deprecated Используйте getProjectLegalTokens() после ensureProjectLegalLoaded(). */
export function getSupportTelegramHandle() {
  const t = getProjectLegalTokens()
  return t.supportTelegram || t.telegramBot
}

export function siteHostname() {
  return tokens().domain
}

function siteUrl() {
  const fromTokens = tokens().siteUrl
  return fromTokens || (tokens().domain ? `https://${tokens().domain}` : '')
}

export function fill(text) {
  const t = tokens()
  return text
    .replaceAll('{{SERVICE_NAME}}', t.serviceName)
    .replaceAll('{{DOMAIN}}', t.domain)
    .replaceAll('{{SITE_URL}}', siteUrl())
    .replaceAll('{{TELEGRAM_BOT}}', t.telegramBot)
    .replaceAll('{{SUPPORT_TELEGRAM}}', t.supportTelegram || t.telegramBot)
    .replaceAll('{{SUPPORT_EMAIL}}', t.supportEmail)
    .replaceAll('{{OPERATOR_NAME}}', t.operatorName)
    .replaceAll('{{OPERATOR_INN}}', t.operatorInn)
    .replaceAll('{{DISPUTE_JURISDICTION}}', t.disputeJurisdiction)
}

function fillBlock(block) {
  if (!block) return block
  return {
    ...block,
    text: block.text ? fill(block.text) : undefined,
    paragraphs: block.paragraphs?.map(fill),
    list: block.list?.map(fill),
  }
}

export function fillDoc(doc) {
  const effectiveDate = tokens().effectiveDate
  return {
    ...doc,
    effectiveDate: effectiveDate || doc.effectiveDate,
    subtitle: doc.subtitle ? fill(doc.subtitle) : undefined,
    intro: doc.intro ? fill(doc.intro) : undefined,
    disclaimer: doc.disclaimer ? fill(doc.disclaimer) : undefined,
    outro: doc.outro ? fill(doc.outro) : undefined,
    contact: doc.contact
      ? {
          ...doc.contact,
          title: doc.contact.title ? fill(doc.contact.title) : undefined,
          items: doc.contact.items?.map((item) => ({
            ...item,
            label: fill(item.label),
            value: fill(item.value),
            href: item.href ? fill(item.href) : undefined,
          })),
        }
      : undefined,
    sections: doc.sections?.map((section) => ({
      ...section,
      heading: section.heading ? fill(section.heading) : undefined,
      paragraphs: section.paragraphs?.map(fill),
      list: section.list?.map(fill),
      paragraphsAfter: section.paragraphsAfter?.map(fill),
      listAfter: section.listAfter?.map(fill),
      callout: fillBlock(section.callout),
      subsections: section.subsections?.map((sub) => ({
        ...sub,
        heading: sub.heading ? fill(sub.heading) : undefined,
        paragraphs: sub.paragraphs?.map(fill),
        list: sub.list?.map(fill),
        callout: fillBlock(sub.callout),
      })),
    })),
    paragraphs: doc.paragraphs?.map(fill),
    list: doc.list?.map(fill),
  }
}
