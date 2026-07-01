import { fetchJson } from '../api/client.js'

/** @typedef {import('../content/legal/constants.js').ProjectLegalTokens} ProjectLegalTokens */

/** @type {ProjectLegalTokens | null} */
let cachedTokens = null

/** @type {Promise<ProjectLegalTokens> | null} */
let loadPromise = null

const EMPTY_TOKENS = {
  serviceName: '',
  siteUrl: '',
  domain: '',
  telegramBot: '',
  supportTelegram: '',
  supportEmail: '',
  operatorName: '',
  operatorInn: '',
  disputeJurisdiction: '',
  effectiveDate: '',
  trialDays: 1,
  trialExtraDaysReferral: 2,
  trialDaysWithReferral: 5,
  trialTrafficLimitGib: 20,
}

function hostnameFallback() {
  if (typeof window !== 'undefined') return window.location.hostname
  return ''
}

function siteUrlFallback() {
  const base = import.meta.env.VITE_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? ''
  if (base) return base
  if (typeof window !== 'undefined') return window.location.origin
  return ''
}

/**
 * @param {Record<string, unknown> | null | undefined} legal
 * @returns {ProjectLegalTokens}
 */
function tokensFromApiLegal(legal) {
  if (!legal || typeof legal !== 'object') {
    return {
      ...EMPTY_TOKENS,
      domain: hostnameFallback(),
      siteUrl: siteUrlFallback(),
    }
  }

  const siteUrl = String(legal.site_url || siteUrlFallback()).trim()
  let domain = String(legal.domain || '').trim()
  if (!domain && siteUrl) {
    try {
      domain = new URL(siteUrl).hostname
    } catch {
      domain = hostnameFallback()
    }
  }
  if (!domain) domain = hostnameFallback()

  return {
    serviceName: String(legal.service_name || '').trim(),
    siteUrl,
    domain,
    telegramBot: String(legal.telegram_bot || '').trim(),
    supportTelegram: String(legal.support_telegram || legal.telegram_bot || '').trim(),
    supportEmail: String(legal.support_email || '').trim(),
    operatorName: String(legal.operator_name || '').trim(),
    operatorInn: String(legal.operator_inn || '').trim(),
    disputeJurisdiction: String(legal.dispute_jurisdiction || '').trim(),
    effectiveDate: String(legal.effective_date || '').trim(),
    trialDays: Number(legal.trial_days_after_registration) || 1,
    trialExtraDaysReferral: Number(legal.trial_extra_days_referral_registration) || 2,
    trialDaysWithReferral: Number(legal.trial_days_with_referral) || 5,
    trialTrafficLimitGib: Number(legal.trial_traffic_limit_gib) || 20,
  }
}

/**
 * @returns {Promise<ProjectLegalTokens>}
 */
export async function ensureProjectLegalLoaded() {
  if (cachedTokens) return cachedTokens
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    try {
      const payload = await fetchJson('/api/public/project-legal')
      cachedTokens = tokensFromApiLegal(payload)
    } catch {
      try {
        const links = await fetchJson('/api/public/site-links')
        cachedTokens = tokensFromApiLegal(links?.legal)
      } catch {
        cachedTokens = {
          ...EMPTY_TOKENS,
          domain: hostnameFallback(),
          siteUrl: siteUrlFallback(),
        }
      }
    }
    return cachedTokens
  })()

  return loadPromise
}

/** @returns {ProjectLegalTokens} */
export function getProjectLegalTokens() {
  return cachedTokens ?? {
    ...EMPTY_TOKENS,
    domain: hostnameFallback(),
    siteUrl: siteUrlFallback(),
  }
}

export function resetProjectLegalCache() {
  cachedTokens = null
  loadPromise = null
}

/** @param {Record<string, unknown> | null | undefined} legal */
export function applyProjectLegalFromSiteLinks(legal) {
  if (!legal || typeof legal !== 'object') return
  cachedTokens = tokensFromApiLegal(legal)
}
