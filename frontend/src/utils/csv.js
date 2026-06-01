/** Простой экспорт в CSV: экранирование, BOM для корректной кириллицы в Excel. */

function csvCell(value) {
  const s = value == null ? '' : String(value)
  if (/["\r\n,;]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

/** @param {Array<Array<unknown>>} rows — первая строка обычно заголовок */
export function toCsv(rows) {
  return rows.map((row) => row.map(csvCell).join(',')).join('\r\n')
}

/**
 * Сформировать CSV и инициировать скачивание файла.
 * @param {string} filename
 * @param {Array<Array<unknown>>} rows
 */
export function downloadCsv(filename, rows) {
  const csv = `\uFEFF${toCsv(rows)}`
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
