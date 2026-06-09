import { sitePublicUrl } from '../../api/client.js'

export const SERVICE_NAME = 'Подорожник'
export const LEGAL_EFFECTIVE_DATE = '09.06.2026'
export const TELEGRAM_BOT = '@PodoroznikVPN_bot'
export const SUPPORT_TELEGRAM = TELEGRAM_BOT
export const SUPPORT_EMAIL = 'support@podorozhnik-connect.ru'
export const OPERATOR_NAME = 'Балыбин Антон Денисович'
export const OPERATOR_INN = '524929428660'
export const DISPUTE_JURISDICTION = 'г. Санкт-Петербург, Российская Федерация'

export const LEGAL_FOOTER_LINKS = [
  { to: '/terms', label: 'Лицензионная оферта' },
  { to: '/privacy', label: 'Конфиденциальность' },
  { to: '/consent', label: 'Обработка ПД' },
  { to: '/refund', label: 'Возврат платежей' },
  { to: '/cookies', label: 'Cookies' },
  { to: '/marketing', label: 'Рекламная рассылка' },
]

export function siteHostname() {
  const url = sitePublicUrl()
  if (url) {
    try {
      return new URL(url).hostname
    } catch {
      /* fall through */
    }
  }
  if (typeof window !== 'undefined') return window.location.hostname
  return 'podorozhnik-connect.ru'
}

function siteUrl() {
  return sitePublicUrl() || `https://${siteHostname()}`
}

export function fill(text) {
  return text
    .replaceAll('{{SERVICE_NAME}}', SERVICE_NAME)
    .replaceAll('{{DOMAIN}}', siteHostname())
    .replaceAll('{{SITE_URL}}', siteUrl())
    .replaceAll('{{TELEGRAM_BOT}}', TELEGRAM_BOT)
    .replaceAll('{{SUPPORT_TELEGRAM}}', SUPPORT_TELEGRAM)
    .replaceAll('{{SUPPORT_EMAIL}}', SUPPORT_EMAIL)
    .replaceAll('{{OPERATOR_NAME}}', OPERATOR_NAME)
    .replaceAll('{{OPERATOR_INN}}', OPERATOR_INN)
    .replaceAll('{{DISPUTE_JURISDICTION}}', DISPUTE_JURISDICTION)
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
  return {
    ...doc,
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
