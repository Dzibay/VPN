<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { isAdminRole } from '../auth/permissions.js'
import { getSessionRole } from '../auth/session.js'
import { fetchJson } from '../api/client.js'
import { formatTrafficBytes } from '../utils/formatTraffic.js'
import { useTableSort } from '../utils/adminTableSort.js'

const route = useRoute()

const rows = ref([])
const loading = ref(false)
const error = ref(null)

/** id пользователя: подсветка строки после перехода из других разделов */
const highlightUserId = ref(null)

/** Выбранная строка: справа панель с полными данными и telegram_properties */
const selectedUserId = ref(null)

const selectedUser = computed(() => {
  const id = selectedUserId.value
  if (id == null) return null
  return sortedRows.value.find((u) => u.id === id) ?? null
})

function clientHighlightFromRoute() {
  const raw = route.query.highlight
  const s = raw == null ? '' : Array.isArray(raw) ? raw[0] : raw
  if (s === '') return null
  const n = Number(s)
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : null
}

const isFullAdmin = computed(() => isAdminRole(getSessionRole()))

/** Календарный день UTC как одно число для сравнения. */
function utcCalendarDayKey(d) {
  return (
    d.getUTCFullYear() * 10000 + (d.getUTCMonth() + 1) * 100 + d.getUTCDate()
  )
}

function countRegistrationsOnUtcDay(userRows, dayKey) {
  let n = 0
  for (const u of userRows) {
    if (u.registered_at == null || u.registered_at === '') continue
    const t = new Date(u.registered_at)
    if (!Number.isFinite(t.getTime())) continue
    if (utcCalendarDayKey(t) === dayKey) n += 1
  }
  return n
}

const userCountWidget = computed(() => {
  if (loading.value || error.value) {
    return {
      totalDisplay: '—',
      todayRegsDisplay: '—',
      vsLabel: '',
      vsClass: '',
    }
  }
  const total = rows.value.length
  const now = new Date()
  const todayKey = utcCalendarDayKey(now)
  const prevUtc = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
  prevUtc.setUTCDate(prevUtc.getUTCDate() - 1)
  const yesterdayKey = utcCalendarDayKey(prevUtc)

  const todayRegs = countRegistrationsOnUtcDay(rows.value, todayKey)
  const yesterdayRegs = countRegistrationsOnUtcDay(rows.value, yesterdayKey)

  let vsLabel = ''
  let vsClass = 'stat-delta--muted'
  if (yesterdayRegs > 0) {
    const pct = ((todayRegs - yesterdayRegs) / yesterdayRegs) * 100
    const r = Math.round(pct * 10) / 10
    if (Math.abs(r) < 0.05) {
      vsLabel = 'к вчера: 0%'
      vsClass = 'stat-delta--neutral'
    } else if (r > 0) {
      vsLabel = `к вчера: ↑ ${formatPercentRu(r)}%`
      vsClass = 'stat-delta--up'
    } else {
      vsLabel = `к вчера: ↓ ${formatPercentRu(Math.abs(r))}%`
      vsClass = 'stat-delta--down'
    }
  } else {
    vsLabel = 'к вчера: —'
    vsClass = 'stat-delta--muted'
  }

  return {
    totalDisplay: total.toLocaleString('ru-RU'),
    todayRegsDisplay: String(todayRegs),
    vsLabel,
    vsClass,
  }
})

function meanRegistrationGapMs(sortedAsc) {
  if (sortedAsc.length < 2) return null
  let sum = 0
  let n = 0
  for (let i = 1; i < sortedAsc.length; i++) {
    const g = sortedAsc[i].getTime() - sortedAsc[i - 1].getTime()
    if (g >= 0) {
      sum += g
      n += 1
    }
  }
  return n > 0 ? sum / n : null
}

/** Человекочитаемый интервал; ru — запятая в десятичных. */
function formatIntervalRu(ms) {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '—'
  const sec = ms / 1000
  const min = sec / 60
  const hr = min / 60
  const day = hr / 24
  const dec = (x) => String(x).replace('.', ',')
  if (day >= 1) return `${dec(day.toFixed(1))} сут.`
  if (hr >= 1) return `${dec(hr.toFixed(1))} ч`
  if (min >= 1) return `${Math.round(min)} мин`
  return `${Math.round(sec)} с`
}

function formatPercentRu(x) {
  return String(Math.round(x * 10) / 10).replace('.', ',')
}

const registrationGapStats = computed(() => {
  if (loading.value || error.value) {
    return { overallMs: null, todayMs: null }
  }

  const times = rows.value
    .map((u) => {
      if (u.registered_at == null || u.registered_at === '') return null
      const t = new Date(u.registered_at)
      return Number.isFinite(t.getTime()) ? t : null
    })
    .filter(Boolean)
    .sort((a, b) => a.getTime() - b.getTime())

  const overallMs = meanRegistrationGapMs(times)
  const todayKey = utcCalendarDayKey(new Date())
  const todayTimes = times.filter((t) => utcCalendarDayKey(t) === todayKey)
  const todayMs = meanRegistrationGapMs(todayTimes)

  return { overallMs, todayMs }
})

function formatDate(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return String(d)
  }
}

function telegramCell(u) {
  if (u.telegram_id != null && u.telegram_id !== '') {
    return String(u.telegram_id)
  }
  return '—'
}

function toggleUserRowSelect(userId, event) {
  if (event?.target?.closest?.('a, button')) return
  selectedUserId.value = selectedUserId.value === userId ? null : userId
}

function clearUserSelection() {
  selectedUserId.value = null
}

/** Стабильный порядок ключей для отображения telegram_properties */
function telegramPropsEntries(u) {
  const p = u.telegram_properties
  if (!p || typeof p !== 'object') return []
  return Object.entries(p).sort(([a], [b]) =>
    a.localeCompare(b, 'ru', { sensitivity: 'base' }),
  )
}

/** Свойства Telegram для выбранной строки (под telegram_id в панели) */
const selectedTelegramPropsEntries = computed(() => {
  const u = selectedUser.value
  if (!u) return []
  return telegramPropsEntries(u)
})

const TG_PROP_LABELS = {
  username: 'Ник',
  first_name: 'Имя',
  last_name: 'Фамилия',
  topic_id: 'Topic_ID',
}

function telegramPropLabel(key) {
  if (Object.hasOwn(TG_PROP_LABELS, key)) return TG_PROP_LABELS[key]
  return key
    .split('_')
    .map((w) =>
      w.length ? w.slice(0, 1).toUpperCase() + w.slice(1).toLowerCase() : '',
    )
    .join(' ')
}

function formatTelegramPropValue(v) {
  if (v == null) return '—'
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v, null, 2)
    } catch {
      return String(v)
    }
  }
  return String(v)
}

/** Строковое значение для ячейки (ник с @ и т.д.) */
function formatTelegramPropDisplay(key, val) {
  if (val == null || val === '') return '—'
  if (typeof val === 'object') return formatTelegramPropValue(val)
  const s = String(val)
  if (
    (key === 'username' || key === 'user_name') &&
    s.length > 0 &&
    !s.startsWith('@')
  ) {
    return `@${s}`
  }
  return s
}

const clientSortAccessors = {
  email: (u) => String(u.email ?? '').toLowerCase(),
  telegram: (u) => u.telegram_id ?? -1,
  registered_at: (u) => Date.parse(u.registered_at) || 0,
  subscription_until: (u) => Date.parse(u.subscription_until) || 0,
  traffic: (u) => Number(u.total_traffic_bytes) || 0,
  devices: (u) => Number(u.subscription_devices_count) || 0,
  referral_link_id: (u) => (u.referral_link_id != null ? u.referral_link_id : -1),
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(
  rows,
  clientSortAccessors,
)

watch(rows, (list) => {
  const id = selectedUserId.value
  if (id != null && !list.some((u) => u.id === id)) selectedUserId.value = null
})

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await fetchJson('/api/users')
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () =>
    `${loading.value}:${
      route.query.highlight ?? ''
    }:${rows.value.map((u) => u.id).join(',')}`,
  async () => {
    if (loading.value) return
    const hid = clientHighlightFromRoute()
    highlightUserId.value = null
    if (hid == null) return
    if (!rows.value.some((u) => u.id === hid)) return
    await nextTick()
    const el = document.getElementById(`client-${hid}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    highlightUserId.value = hid
    window.setTimeout(() => {
      if (highlightUserId.value === hid) highlightUserId.value = null
    }, 3400)
  },
  { flush: 'post' },
)

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminPageShell>
    <AdminPageHeader
      title="Аналитика пользователей"
      :tabs-aria-label="isFullAdmin ? 'Разделы админки' : 'Раздел менеджера'"
    >
      <template #back>
        <RouterLink v-if="isFullAdmin" class="back" to="/admin/users">
          ← Управление данными
        </RouterLink>
        <RouterLink v-else class="back" to="/cabinet">← Личный кабинет</RouterLink>
      </template>
      <template #tabs>
        <template v-if="isFullAdmin">
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users' }"
            :to="{ path: '/admin/users' }"
          >
            Пользователи
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-servers' }"
            :to="{ path: '/admin/servers' }"
          >
            Серверы
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
            :to="{ path: '/admin/users/analytics' }"
          >
            Клиенты
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
            :to="{ path: '/admin/users/registrations-by-date' }"
          >
            Статистика по дням
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-analytics' }"
            :to="{ path: '/admin/analytics' }"
          >
            Нагрузка
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-funnel' }"
            :to="{ path: '/admin/funnel' }"
          >
            Воронка
          </RouterLink>
          <RouterLink class="tab" :to="{ path: '/admin/referrals' }">
            Реферальные токены
          </RouterLink>
        </template>
        <template v-else>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
            :to="{ path: '/admin/users/analytics' }"
          >
            Клиенты
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
            :to="{ path: '/admin/users/registrations-by-date' }"
          >
            Статистика по дням
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-funnel' }"
            :to="{ path: '/admin/funnel' }"
          >
            Воронка
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-referrals' }"
            :to="{ path: '/admin/referrals' }"
          >
            Реферальные токены
          </RouterLink>
        </template>
      </template>
      <div class="head-row">
        <h2 class="section-heading">Сводка по учётным записям и трафику</h2>
        <div class="head-actions">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading"
            @click="load"
          >
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </AdminPageHeader>

    <section class="stats widgets-row" aria-live="polite">
      <div class="widgets-grid">
        <div class="stat-widget" aria-label="Число пользователей">
          <h3 class="stat-widget-title">Пользователи</h3>
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : userCountWidget.totalDisplay }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            Сегодня: {{ userCountWidget.todayRegsDisplay }}
          </p>
          <p
            v-if="!loading && !error && userCountWidget.vsLabel"
            class="stat-widget-delta"
            :class="userCountWidget.vsClass"
          >
            {{ userCountWidget.vsLabel }}
          </p>
        </div>
        <div class="stat-widget" aria-label="Интервал между регистрациями">
          <h3 class="stat-widget-title">Интервал регистраций</h3>
          <dl v-if="!loading && !error" class="stat-widget-split">
            <div>
              <dt>Всего</dt>
              <dd>{{ formatIntervalRu(registrationGapStats.overallMs) }}</dd>
            </div>
            <div>
              <dt>Сегодня (UTC)</dt>
              <dd>{{ formatIntervalRu(registrationGapStats.todayMs) }}</dd>
            </div>
          </dl>
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </div>
      </div>
    </section>

    <div
      class="analytics-main"
      :class="{ 'analytics-main--split': selectedUser }"
    >
      <div class="analytics-main__table">
        <AdminTableWrap aria-label="Таблица аналитики пользователей">
          <table class="admin-table">
        <thead>
          <tr>
            <AdminSortTh
              label="Email"
              column-key="email"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Telegram ID"
              column-key="telegram"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Регистрация"
              column-key="registered_at"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Подписка до"
              column-key="subscription_until"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Трафик (всего)"
              column-key="traffic"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Устройства"
              column-key="devices"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="ID реф. ссылки"
              column-key="referral_link_id"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="7" class="muted">Загрузка…</td>
          </tr>
          <tr v-else-if="error">
            <td colspan="7" class="error-cell">{{ error }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="7" class="muted">Нет пользователей</td>
          </tr>
          <template v-else>
            <tr
              v-for="u in sortedRows"
              :id="'client-' + u.id"
              :key="u.id"
              class="client-row-toggle"
              :class="{
                'client-row-highlight': highlightUserId === u.id,
                'user-row--selected': selectedUserId === u.id,
              }"
              title="Нажмите строку, чтобы открыть или закрыть карточку пользователя справа"
              @click="toggleUserRowSelect(u.id, $event)"
            >
              <td class="email-cell" :title="u.email || undefined">{{ u.email ?? '—' }}</td>
              <td class="tg-cell">{{ telegramCell(u) }}</td>
              <td>{{ formatDate(u.registered_at) }}</td>
              <td>{{ formatDate(u.subscription_until) }}</td>
              <td class="num mono-num">{{ formatTrafficBytes(u.total_traffic_bytes) }}</td>
              <td class="num mono-num">{{ u.subscription_devices_count ?? 0 }}</td>
              <td class="num ref-id-cell">
                <template v-if="u.referral_link_id != null">
                  <span>{{ u.referral_link_id }}</span>
                  <RouterLink
                    class="ref-open-in-list"
                    :to="{
                      path: '/admin/referrals',
                      query: { highlight: String(u.referral_link_id) },
                    }"
                    title="Открыть эту запись в списке реферальных ссылок"
                    aria-label="Перейти к реферальной ссылке в таблице токенов"
                    @click.stop
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" x2="21" y1="14" y2="3" /></svg>
                  </RouterLink>
                </template>
                <template v-else>—</template>
              </td>
            </tr>
          </template>
        </tbody>
          </table>
        </AdminTableWrap>
      </div>

      <aside
        v-if="selectedUser"
        class="user-detail-panel"
        aria-label="Полные данные выбранного пользователя"
      >
        <div class="user-detail-panel__chrome">
          <header class="user-detail-panel__top">
            <h2 class="user-detail-panel__heading">
              Пользователь
              <span class="user-detail-panel__id mono-num">#{{ selectedUser.id }}</span>
            </h2>
            <button
              type="button"
              class="user-detail-panel__close"
              title="Закрыть панель"
              aria-label="Закрыть панель"
              @click="clearUserSelection"
            >
              ×
            </button>
          </header>

          <section class="user-detail-block" aria-labelledby="user-detail-table-heading">
            <ul class="tg-props-list">
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Email</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value">{{ selectedUser.email ?? '—' }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Telegram ID</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value mono-num">{{ telegramCell(selectedUser) }}</span>
                  </div>
                </div>
              </li>
              <li
                v-for="([key, val], idx) in selectedTelegramPropsEntries"
                :key="'tg-prop-' + key"
                class="tg-props-item tg-props-item--telegram-prop"
                :class="{
                  'tg-props-item--telegram-run-end':
                    idx === selectedTelegramPropsEntries.length - 1,
                }"
              >
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">{{ telegramPropLabel(key) }}</span>
                  <div class="tg-props-value-wrap">
                    <pre
                      v-if="typeof val === 'object' && val !== null"
                      class="tg-props-pre"
                    >{{ formatTelegramPropValue(val) }}</pre>
                    <span v-else class="tg-props-value">{{
                      formatTelegramPropDisplay(key, val)
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Регистрация</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value">{{
                      formatDate(selectedUser.registered_at)
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Подписка до</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value">{{
                      formatDate(selectedUser.subscription_until)
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Трафик (всего)</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value mono-num">{{
                      formatTrafficBytes(selectedUser.total_traffic_bytes)
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Устройства</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value mono-num">{{
                      selectedUser.subscription_devices_count ?? 0
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">ID реф. ссылки</span>
                  <div class="tg-props-value-wrap tg-props-value-wrap--row">
                    <template v-if="selectedUser.referral_link_id != null">
                      <span class="tg-props-value mono-num">{{
                        selectedUser.referral_link_id
                      }}</span>
                      <RouterLink
                        class="ref-open-in-list ref-open-in-list--panel"
                        :to="{
                          path: '/admin/referrals',
                          query: { highlight: String(selectedUser.referral_link_id) },
                        }"
                        title="Открыть в списке реферальных ссылок"
                        aria-label="Перейти к реферальной ссылке"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" x2="21" y1="14" y2="3" /></svg>
                      </RouterLink>
                    </template>
                    <span v-else class="tg-props-value">—</span>
                  </div>
                </div>
              </li>
            </ul>
          </section>
        </div>
      </aside>
    </div>
  </AdminPageShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem 1rem;
}

.section-heading {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stats {
  margin-bottom: 1rem;
}
.widgets-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
@media (max-width: 640px) {
  .widgets-grid {
    grid-template-columns: 1fr;
  }
}
.stat-widget {
  padding: 1rem 1.1rem;
  border-radius: 10px;
  border: 1px solid var(--nav-border);
  background: var(--surface, color-mix(in srgb, var(--bg) 92%, var(--text) 8%));
}
.stat-widget-title {
  margin: 0 0 0.65rem;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  font-weight: 600;
}
.stat-widget-value {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
  color: var(--text-h);
}
.stat-widget-value--muted {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--muted);
}
.stat-widget-meta {
  margin: 0.4rem 0 0;
  font-size: 0.86rem;
  color: var(--muted);
}
.stat-widget-delta {
  margin: 0.2rem 0 0;
  font-size: 0.86rem;
  font-weight: 600;
}
.stat-delta--up {
  color: var(--success, #2e7d32);
}
.stat-delta--down {
  color: var(--danger, #c62828);
}
.stat-delta--neutral {
  color: var(--muted);
}
.stat-delta--muted {
  color: var(--muted);
  font-weight: 500;
}
.stat-widget-split {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem 1rem;
  margin: 0;
}
.stat-widget-split div {
  margin: 0;
  min-width: 0;
}
.stat-widget-split dt {
  margin: 0 0 0.2rem;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  font-weight: 600;
}
.stat-widget-split dd {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: var(--text-h);
  word-break: break-word;
}

.ref-id-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
}
.ref-open-in-list {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 0.1rem;
  padding: 0.12rem;
  border-radius: 6px;
  color: var(--accent);
  line-height: 0;
  transition: background 0.15s ease, color 0.15s ease;
}
.ref-open-in-list:hover {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--text-h);
}
.ref-open-in-list:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.admin-table tbody tr.client-row-highlight td {
  animation: clientRowHighlight 3.2s ease-out forwards;
}
@keyframes clientRowHighlight {
  0% {
    background-color: color-mix(in srgb, var(--accent) 30%, transparent);
  }
  35% {
    background-color: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  100% {
    background-color: transparent;
  }
}
.mono-num {
  font-variant-numeric: tabular-nums;
}
.client-row-toggle {
  cursor: pointer;
}
.client-row-toggle:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.user-row--selected {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.analytics-main {
  width: 100%;
}
.analytics-main:not(.analytics-main--split) {
  display: block;
}
/**
 * Таблица слева (minmax — горизонтальный скролл только внутри обёртки),
 * панель справа фиксированной ширины + sticky по вертикали страницы.
 */
.analytics-main--split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(268px, 30vw, 360px);
  gap: 1rem;
  align-items: start;
}
.analytics-main__table {
  min-width: 0;
}
.user-detail-panel {
  position: sticky;
  top: 1rem;
  max-height: calc(100vh - 2rem);
  overflow-y: auto;
  align-self: start;
  width: 100%;
  min-width: 0;
  -webkit-overflow-scrolling: touch;
}
@media (max-width: 768px) {
  .analytics-main--split {
    grid-template-columns: 1fr;
  }
  .user-detail-panel {
    position: relative;
    top: auto;
    max-height: none;
    margin-top: 0.25rem;
  }
}
.user-detail-panel__chrome {
  padding: 0.65rem 0.75rem 0.75rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
  box-sizing: border-box;
  font-size: 0.9rem;
  color: var(--text);
}
.user-detail-panel__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin: 0 0 0.85rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}
.user-detail-panel__heading {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.25;
  color: var(--text);
}
.user-detail-panel__id {
  font-weight: 700;
  color: var(--text-h);
}
.user-detail-panel__close {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg) 92%, var(--text) 4%);
  color: var(--muted);
  font-size: 1.35rem;
  line-height: 1;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;
}
.user-detail-panel__close:hover {
  color: var(--text-h);
  border-color: var(--accent-border, var(--border));
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.user-detail-panel .user-detail-block {
  margin: 0 0 0.5rem;
}
.user-detail-panel .user-detail-block:last-child {
  margin-bottom: 0;
}
.user-detail-panel .user-detail-block__title {
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  font-weight: 700;
}
.tg-props-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.user-detail-panel .tg-props-item__grid {
  display: grid;
  grid-template-columns: minmax(8.5rem, 30%) 1fr;
  gap: 0.35rem 0.75rem;
  padding: 0.65rem 0;
  align-items: start;
}
@media (max-width: 520px) {
  .user-detail-panel .tg-props-item__grid {
    grid-template-columns: 1fr;
    gap: 0.2rem;
  }
}
.user-detail-panel .tg-props-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  font-weight: 700;
  line-height: 1.25;
}
.tg-props-value-wrap {
  min-width: 0;
}
.tg-props-value-wrap--row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
}
.ref-open-in-list--panel {
  margin-left: 0;
}
.user-detail-panel .tg-props-value {
  display: block;
  color: var(--text);
  font-weight: 400;
  font-size: 0.9rem;
  word-break: break-word;
  line-height: 1.35;
}
.user-detail-panel .tg-props-pre {
  margin: 0;
  padding: 0.45rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 90%, var(--text) 5%);
  white-space: pre-wrap;
  font-size: 0.85rem;
  font-family: ui-monospace, 'Cascadia Code', monospace;
  color: var(--text);
  line-height: 1.35;
}
/* Строки как в admin-table; между telegram_properties без линий, блок закрывается перед «Регистрация» */
.user-detail-panel .tg-props-list > .tg-props-item {
  border-bottom: 1px solid var(--border);
}
.user-detail-panel .tg-props-list > .tg-props-item:has(+ .tg-props-item--telegram-prop) {
  border-bottom: none;
}
.user-detail-panel .tg-props-list > .tg-props-item:has(+ .tg-props-item--telegram-prop) .tg-props-item__grid {
  padding-bottom: 0.35rem;
}
.user-detail-panel .tg-props-list > .tg-props-item--telegram-prop:not(.tg-props-item--telegram-run-end) {
  border-bottom: none;
}
.user-detail-panel .tg-props-list > .tg-props-item--telegram-prop .tg-props-item__grid {
  padding-top: 0.35rem;
  padding-bottom: 0.35rem;
}
/* Email: ограничение ширины, длинные адреса — с многоточием (полный текст в title) */
.email-cell {
  max-width: 14rem;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
/* Одна строка по ширине контента; на узком экране таблица скроллится в AdminTableWrap */
.tg-cell {
  white-space: nowrap;
  vertical-align: middle;
}
.muted {
  color: var(--muted);
}
.error-cell {
  color: var(--danger, #c62828);
}
</style>
