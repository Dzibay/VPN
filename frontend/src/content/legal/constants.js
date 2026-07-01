import { sitePublicUrl } from '../../api/client.js'

const FRONTEND_BRAND = String(import.meta.env.VITE_BRAND || '').trim().toLowerCase()
const isHalyalBrand = FRONTEND_BRAND === 'halyal'

const BRAND_DEFAULTS = {
  podorozhnik: {
    serviceName: 'Подорожник',
    telegramBot: 'PodoroznikVPN_bot',
    defaultHost: 'podorozhnik-connect.ru',
    supportEmail: 'support@podorozhnik-connect.ru',
  },
  halyal: {
    serviceName: 'Halyal VPN',
    telegramBot: 'HalyalConnect_bot',
    defaultHost: 'halyal-connect.ru',
    supportEmail: 'support@halyal-connect.ru',
  },
}

const brandDefaults = isHalyalBrand ? BRAND_DEFAULTS.halyal : BRAND_DEFAULTS.podorozhnik

function envTrim(key) {
  const raw = import.meta.env[key]
  return typeof raw === 'string' ? raw.trim() : ''
}

function normalizeTelegramBot(raw) {
  const value = (raw || '').trim()
  if (!value) return ''
  return value.startsWith('@') ? value : `@${value}`
}

export const SERVICE_NAME = envTrim('VITE_LEGAL_SERVICE_NAME') || brandDefaults.serviceName
export const LEGAL_EFFECTIVE_DATE = '09.06.2026'
export const TELEGRAM_BOT = normalizeTelegramBot(
  envTrim('VITE_TELEGRAM_BOT_USERNAME') || brandDefaults.telegramBot,
)
export const SUPPORT_TELEGRAM = TELEGRAM_BOT
export const SUPPORT_EMAIL =
  envTrim('VITE_SUPPORT_EMAIL') || brandDefaults.supportEmail
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
  return brandDefaults.defaultHost
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
