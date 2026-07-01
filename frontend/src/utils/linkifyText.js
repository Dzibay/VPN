/** Знаки пунктуации, которые часто стоят сразу после URL в русском тексте. */
const TRAILING_URL_PUNCT_RE = /[.,;:!?)}\]'»]+$/u

/**
 * Убирает хвостовую пунктуацию из URL, чтобы «https://site.ru/refund.» не ломала переход.
 * @param {string} url
 */
export function trimUrlTrailingPunctuation(url) {
  let href = url
  let trailing = ''
  for (;;) {
    const match = href.match(TRAILING_URL_PUNCT_RE)
    if (!match) break
    trailing = match[0] + trailing
    href = href.slice(0, -match[0].length)
  }
  return { href, trailing }
}

/**
 * Превращает http(s)/mailto ссылки в <a>, экранируя остальной текст.
 * @param {string} text
 */
export function linkifyText(text) {
  if (!text) return ''
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  return escaped.replace(
    /(https?:\/\/[^\s<]+|mailto:[^\s<]+)/g,
    (rawUrl) => {
      const { href, trailing } = trimUrlTrailingPunctuation(rawUrl)
      if (!href) return rawUrl
      return (
        `<a href="${href}" target="_blank" rel="noopener noreferrer">${href}</a>${trailing}`
      )
    },
  )
}
