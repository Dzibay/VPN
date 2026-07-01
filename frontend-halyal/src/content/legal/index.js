import { fillDoc } from './constants.js'
import { terms } from './terms.js'
import { privacy } from './privacy.js'
import { pdPolicy } from './pdPolicy.js'
import { refund } from './refund.js'
import { cookies } from './cookies.js'
import { marketing } from './marketing.js'

export * from './constants.js'

/** @type {Record<string, object>} */
const LEGAL_DOCUMENTS = {
  terms,
  privacy,
  consent: pdPolicy,
  refund,
  cookies,
  marketing,
}

export function getLegalDocument(id) {
  const doc = LEGAL_DOCUMENTS[id]
  if (!doc) return null
  return fillDoc(doc)
}

export function getLegalDocumentTitle(id) {
  return LEGAL_DOCUMENTS[id]?.title ?? 'Документ'
}

export function getAllLegalDocumentIds() {
  return Object.keys(LEGAL_DOCUMENTS)
}
