<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AdminHighlightListLink from '../components/AdminHighlightListLink.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import StaffUserIdSuggestInput from '../components/StaffUserIdSuggestInput.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson } from '../api/client.js'
import { formatTrafficWithLimit, isTrafficOverLimit } from '../utils/formatTraffic.js'
import { useTableSort } from '../utils/adminTableSort.js'
import { formatLocaleDateRu } from '../utils/formatLocaleDate.js'
import {
  formatSubscriptionConnectionOs,
  formatSubscriptionConnectionUserAgent,
} from '../util/subscriptionConnectionFormat.js'

const route = useRoute()
const router = useRouter()

const userSearchQuery = ref('')

const rows = ref([])
const rowsTotal = ref(0)
const pageLimit = 50
const offset = ref(0)
const usersCountSummary = ref(null)
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

const selectedSubscriptionDevices = computed(() => {
  const u = selectedUser.value
  if (!u) return []
  const list = u.subscription_devices
  return Array.isArray(list) ? list : []
})

function clientHighlightFromRoute() {
  const raw = route.query.highlight
  const s = raw == null ? '' : Array.isArray(raw) ? raw[0] : raw
  if (s === '') return null
  const n = Number(s)
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : null
}

const userCountWidget = computed(() => {
  if (loading.value || error.value || usersCountSummary.value == null) {
    return {
      totalDisplay: '—',
      todayRegsDisplay: '—',
      vsLabel: '',
      vsClass: '',
    }
  }
  const s = usersCountSummary.value
  const total = Number(s.users_count) || 0
  const todayRegs = Number(s.registrations_today_count) || 0
  const yesterdayRegs = Number(s.registrations_yesterday_count) || 0

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
  if (loading.value || error.value || usersCountSummary.value == null) {
    return { overallMs: null, todayMs: null }
  }
  const s = usersCountSummary.value
  const overallMs = s.registration_gap_overall_ms
  const todayMs = s.registration_gap_today_ms
  return {
    overallMs:
      overallMs != null && Number.isFinite(Number(overallMs))
        ? Number(overallMs)
        : null,
    todayMs:
      todayMs != null && Number.isFinite(Number(todayMs)) ? Number(todayMs) : null,
  }
})

const rangeLabel = computed(() => {
  const n = rows.value.length
  if (rowsTotal.value === 0) return '0 пользователей'
  const from = offset.value + 1
  const to = offset.value + n
  return `${from}–${to} из ${rowsTotal.value}`
})

const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => offset.value + rows.value.length < rowsTotal.value)

function prevPage() {
  offset.value = Math.max(0, offset.value - pageLimit)
  void load()
}

function nextPage() {
  offset.value = offset.value + pageLimit
  void load()
}

function telegramCell(u) {
  if (u.telegram_id != null && u.telegram_id !== '') {
    return String(u.telegram_id)
  }
  return '—'
}

function telegramUsernameCell(u) {
  const directUsername = u.username ?? u.user_name ?? u.telegram_username
  const props = u.telegram_properties
  const nestedUsername =
    props && typeof props === 'object'
      ? props.username ?? props.user_name ?? props.telegram_username
      : null

  const username = directUsername ?? nestedUsername
  if (username != null && username !== '') {
    const s = String(username)
    return s.startsWith('@') ? s : `@${s}`
  }

  return telegramCell(u)
}

function telegramCellTitle(u) {
  const v = telegramUsernameCell(u)
  return v === '—' ? undefined : v
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
  id: (u) => Number(u.id) || 0,
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

async function loadCountSummary() {
  try {
    usersCountSummary.value = await fetchJson('/api/users/count')
  } catch {
    usersCountSummary.value = null
  }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      limit: String(pageLimit),
      offset: String(offset.value),
    })
    const [data] = await Promise.all([
      fetchJson(`/api/users?${params.toString()}`),
      loadCountSummary(),
    ])
    rows.value = Array.isArray(data?.items) ? data.items : []
    rowsTotal.value = Number(data?.total) || 0
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
    rowsTotal.value = 0
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

function goToUserAnalytics(row) {
  const id = Number(row?.id)
  if (!Number.isFinite(id) || id < 1) return
  router.push(`/admin/users/${id}/analytics`)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="Аналитика пользователей">
    <section class="stats widgets-row" aria-live="polite">
      <div class="widgets-grid">
        <div class="stat-widget" aria-label="Число пользователей">
          <h3 class="stat-widget-title">Пользователи</h3>
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : userCountWidget.totalDisplay }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            Сегодня (МСК): {{ userCountWidget.todayRegsDisplay }}
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
              <dt>Сегодня (МСК)</dt>
              <dd>{{ formatIntervalRu(registrationGapStats.todayMs) }}</dd>
            </div>
          </dl>
          <p v-else class="stat-widget-value stat-widget-value--muted">
            {{ loading ? '…' : '—' }}
          </p>
        </div>
      </div>
    </section>

    <section class="clients-search" aria-label="Поиск пользователя">
      <label class="clients-search-label" for="clients-user-search">
        Перейти к пользователю
      </label>
      <StaffUserIdSuggestInput
        v-model="userSearchQuery"
        input-id="clients-user-search"
        placeholder="Поиск от 3 символов (id, email, @username, tg id)"
        @select="goToUserAnalytics"
      />
    </section>

    <section v-if="!loading && !error" class="stats stats--pager" aria-live="polite">
      <p class="stats-value">{{ rangeLabel }}</p>
      <div class="pager-top">
        <div class="pager-btns">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading || !canPrev"
            @click="prevPage"
          >
            Назад
          </button>
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading || !canNext"
            @click="nextPage"
          >
            Вперёд
          </button>
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
              label="ID"
              column-key="id"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
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
              label="Трафик"
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
            <td colspan="8" class="muted">Загрузка…</td>
          </tr>
          <tr v-else-if="error">
            <td colspan="8" class="error-cell">{{ error }}</td>
          </tr>
          <tr v-else-if="rowsTotal === 0">
            <td colspan="8" class="muted">Нет пользователей</td>
          </tr>
          <template v-else>
            <tr
              v-for="u in sortedRows"
              :id="'client-' + u.id"
              :key="u.id"
              class="client-row-toggle"
              :class="{
                'admin-row-highlight': highlightUserId === u.id,
                'user-row--selected': selectedUserId === u.id,
                'client-row-active-today': u.active_today,
                'client-row-has-payments': u.has_payments,
              }"
              title="Нажмите строку, чтобы открыть или закрыть карточку пользователя справа"
              @click="toggleUserRowSelect(u.id, $event)"
            >
              <td class="num mono-num">{{ u.id }}</td>
              <td class="email-cell" :title="u.email || undefined">{{ u.email ?? '—' }}</td>
              <td class="tg-cell" :title="telegramCellTitle(u)">{{ telegramUsernameCell(u) }}</td>
              <td>{{ formatLocaleDateRu(u.registered_at) }}</td>
              <td>{{ formatLocaleDateRu(u.subscription_until) }}</td>
              <td
                class="num mono-num"
                :class="{ 'traffic-over-limit': isTrafficOverLimit(u) }"
                :title="
                  isTrafficOverLimit(u) ? 'Лимит трафика исчерпан' : undefined
                "
              >
                {{
                  formatTrafficWithLimit(
                    u.total_traffic_bytes,
                    u.traffic_limit_bytes,
                  )
                }}
              </td>
              <td class="num mono-num">{{ u.subscription_devices_count ?? 0 }}</td>
              <td class="num ref-id-cell">
                <template v-if="u.referral_link_id != null">
                  <span>{{ u.referral_link_id }}</span>
                  <AdminHighlightListLink
                    list="referrals"
                    :highlight="u.referral_link_id"
                    stop-propagation
                  />
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
                      formatLocaleDateRu(selectedUser.registered_at)
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Подписка до</span>
                  <div class="tg-props-value-wrap">
                    <span class="tg-props-value">{{
                      formatLocaleDateRu(selectedUser.subscription_until)
                    }}</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Трафик / лимит</span>
                  <div class="tg-props-value-wrap">
                    <span
                      class="tg-props-value mono-num"
                      :class="{
                        'traffic-over-limit':
                          selectedUser && isTrafficOverLimit(selectedUser),
                      }"
                    >{{
                      formatTrafficWithLimit(
                        selectedUser.total_traffic_bytes,
                        selectedUser.traffic_limit_bytes,
                      )
                    }}</span>
                    <span
                      v-if="selectedUser.traffic_limit_bytes == null"
                      class="traffic-limit-hint"
                    >без лимита</span>
                  </div>
                </div>
              </li>
              <li class="tg-props-item">
                <div class="tg-props-item__grid">
                  <span class="tg-props-label">Подключения</span>
                  <div class="tg-props-value-wrap tg-props-value-wrap--devices-col">
                    <span class="tg-props-value mono-num">{{
                      selectedUser.subscription_devices_count ?? 0
                    }}</span>
                    <details
                      v-if="selectedSubscriptionDevices.length"
                      class="connections-expand panel-subscription-devices"
                    >
                      <summary class="connections-expand__summary">
                        Устройства
                      </summary>
                      <ul
                        class="connections-expand__list"
                        role="list"
                      >
                        <li
                          v-for="conn in selectedSubscriptionDevices"
                          :key="conn.id"
                          class="connections-expand__item connections-expand__item--readonly"
                        >
                          <div class="connections-expand__line mono">
                            <span class="connections-expand__os">{{
                              formatSubscriptionConnectionOs(conn.os)
                            }}</span>
                            <span
                              class="connections-expand__dot"
                              aria-hidden="true"
                            > · </span>
                            <span class="connections-expand__ua">{{
                              formatSubscriptionConnectionUserAgent(conn.user_agent)
                            }}</span>
                          </div>
                        </li>
                      </ul>
                    </details>
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
                      <AdminHighlightListLink
                        list="referrals"
                        :highlight="selectedUser.referral_link_id"
                        title="Открыть в списке реферальных ссылок"
                        aria-label="Перейти к реферальной ссылке"
                        panel
                      />
                    </template>
                    <span v-else class="tg-props-value">—</span>
                  </div>
                </div>
              </li>
            </ul>
          </section>

          <div class="user-detail-panel__logs-footer">
            <RouterLink
              class="user-detail-panel__logs-link"
              :to="`/admin/users/${selectedUser.id}/analytics`"
              title="Трафик по дням и узлам, платежи, задачи, реферальная ссылка"
            >
              Аналитика
            </RouterLink>
            <RouterLink
              class="user-detail-panel__logs-link"
              :to="{
                path: '/admin/logs',
                query: { user_id: String(selectedUser.id) },
              }"
              title="Логи с фильтром по этому пользователю"
            >
              Логи
            </RouterLink>
          </div>
        </div>
      </aside>
    </div>
  </AdminStaffShell>
</template>

<style scoped>
.stats {
  margin-bottom: 1rem;
}

.clients-search {
  margin-bottom: 1rem;
  max-width: 28rem;
}

.clients-search-label {
  display: block;
  margin-bottom: 0.4rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}

.stats--pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
}

.stats-value {
  margin: 0;
  font-size: 0.95rem;
  color: var(--text-h);
}

.pager-top {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 0.5rem;
}

.pager-btns {
  display: flex;
  gap: 0.35rem;
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
.mono-num {
  font-variant-numeric: tabular-nums;
}
.client-row-toggle {
  cursor: pointer;
}
.client-row-toggle:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
/* Рост счётчиков относительно последнего снимка до текущего UTC-дня (active_today в GET /api/users) */
tr.client-row-active-today {
  background-color: color-mix(in srgb, var(--success, #15803d) 10%, transparent);
}
tr.client-row-active-today.client-row-toggle:hover {
  background-color: color-mix(
    in srgb,
    var(--success, #15803d) 12%,
    color-mix(in srgb, var(--accent) 8%, transparent)
  );
}
/* Хотя бы одна оплата (has_payments в GET /api/users) — amber как «С оплатой» на графиках */
tr.client-row-has-payments {
  --client-payment-amber: rgb(245, 158, 11);
  background-color: color-mix(in srgb, var(--client-payment-amber) 12%, transparent);
}
tr.client-row-has-payments.client-row-toggle:hover {
  background-color: color-mix(
    in srgb,
    var(--client-payment-amber) 14%,
    color-mix(in srgb, var(--accent) 8%, transparent)
  );
}
tr.client-row-has-payments.client-row-active-today {
  background-color: color-mix(
    in srgb,
    var(--client-payment-amber) 11%,
    color-mix(in srgb, var(--success, #15803d) 10%, transparent)
  );
}
tr.client-row-has-payments.client-row-active-today.client-row-toggle:hover {
  background-color: color-mix(
    in srgb,
    var(--client-payment-amber) 13%,
    color-mix(
      in srgb,
      var(--success, #15803d) 11%,
      color-mix(in srgb, var(--accent) 8%, transparent)
    )
  );
}
.user-row--selected {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
tr.client-row-active-today.user-row--selected {
  background-color: color-mix(
    in srgb,
    var(--success, #15803d) 11%,
    color-mix(in srgb, var(--accent) 9%, transparent)
  );
}
tr.client-row-has-payments.user-row--selected {
  background-color: color-mix(
    in srgb,
    var(--client-payment-amber, rgb(245, 158, 11)) 11%,
    color-mix(in srgb, var(--accent) 9%, transparent)
  );
}
tr.client-row-has-payments.client-row-active-today.user-row--selected {
  background-color: color-mix(
    in srgb,
    var(--client-payment-amber, rgb(245, 158, 11)) 10%,
    color-mix(
      in srgb,
      var(--success, #15803d) 10%,
      color-mix(in srgb, var(--accent) 9%, transparent)
    )
  );
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
.user-detail-panel__logs-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem 1.1rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}
.user-detail-panel__logs-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent, #2563eb);
  text-decoration: none;
}
.user-detail-panel__logs-link:hover {
  color: var(--accent-hover, var(--text-h));
  text-decoration: underline;
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
.tg-props-value-wrap--devices-col {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
}
.user-detail-panel .connections-expand {
  width: 100%;
  margin: 0;
}
.user-detail-panel .connections-expand__summary {
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent);
  line-height: 1.35;
  list-style: none;
}
.user-detail-panel .connections-expand__summary::-webkit-details-marker {
  display: none;
}
.user-detail-panel .connections-expand__summary::before {
  content: '';
  display: inline-block;
  width: 0;
  height: 0;
  margin-right: 0.38em;
  border-style: solid;
  border-width: 0.28em 0 0.28em 0.42em;
  border-color: transparent transparent transparent currentColor;
  vertical-align: 0.12em;
  transition: transform 0.15s ease;
}
.user-detail-panel .connections-expand[open] .connections-expand__summary::before {
  transform: rotate(90deg);
}
.user-detail-panel .connections-expand__list {
  margin: 0.4rem 0 0;
  padding: 0.35rem 0 0 1rem;
  list-style: disc;
  font-size: 0.82rem;
  border-top: 1px dashed color-mix(in srgb, var(--muted) 40%, transparent);
}
.user-detail-panel .connections-expand__item {
  margin: 0.22rem 0;
  padding: 0;
  line-height: 1.4;
  word-break: break-word;
}
.user-detail-panel .connections-expand__item--readonly {
  display: block;
}
.user-detail-panel .connections-expand__line {
  min-width: 0;
}
.user-detail-panel .connections-expand__dot {
  color: color-mix(in srgb, var(--muted) 65%, transparent);
  font-weight: 400;
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
.user-detail-panel .tg-props-list > .tg-props-item:last-child {
  border-bottom: none;
}
/* Email: ограничение ширины, длинные адреса — с многоточием (полный текст в title) */
.email-cell {
  max-width: 10rem;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
/* Telegram ID / @username: ограничение ширины, длинные значения — с многоточием */
.tg-cell {
  max-width: 10rem;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
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
