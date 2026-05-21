/** Календарная дата/время в локали ru-RU; пустое значение → «—». */
export function formatLocaleDateRu(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return String(d)
  }
}
