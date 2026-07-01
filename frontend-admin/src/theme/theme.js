import { ref } from 'vue'

const THEME_KEY = 'STAFF_ADMIN_THEME'
const MODES = new Set(['system', 'light', 'dark'])

export const themeMode = ref(readStoredTheme())
export const resolvedTheme = ref(resolveTheme(themeMode.value))

let mediaQuery = null

function readStoredTheme() {
  try {
    const raw = localStorage.getItem(THEME_KEY)
    return MODES.has(raw) ? raw : 'system'
  } catch (_) {
    return 'system'
  }
}

function resolveTheme(mode) {
  if (mode === 'light' || mode === 'dark') return mode
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme() {
  const resolved = resolveTheme(themeMode.value)
  resolvedTheme.value = resolved
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.dataset.theme = resolved
  root.dataset.themeChoice = themeMode.value
  root.style.colorScheme = resolved
}

export function setThemeMode(mode) {
  themeMode.value = MODES.has(mode) ? mode : 'system'
  try {
    localStorage.setItem(THEME_KEY, themeMode.value)
  } catch (_) {
    // ignore storage failures
  }
  applyTheme()
}

export function initTheme() {
  applyTheme()
  if (typeof window === 'undefined' || !window.matchMedia) return
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener?.('change', () => {
    if (themeMode.value === 'system') applyTheme()
  })
}

