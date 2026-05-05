<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'

const route = useRoute()
const router = useRouter()
const limit = ref(50)
const offset = ref(0)
const filterUserId = ref('')
const onlyWithoutUser = ref(false)

const loading = ref(false)
const error = ref(null)
const page = ref({
  items: [],
  total: 0,
  limit: 50,
  offset: 0,
})

const HTTP_TRACE_DT_LOCALE = 'ru-RU'

function httpTraceCreatedAtTs(iso) {
  const t = Date.parse(String(iso ?? ''))
  return Number.isFinite(t) ? t : NaN
}

/** Только время в ячейке; полная дата — в title. */
function formatHttpTraceTimeOnly(iso) {
  const ts = httpTraceCreatedAtTs(iso)
  if (!Number.isFinite(ts)) return '—'
  return new Date(ts).toLocaleTimeString(HTTP_TRACE_DT_LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatHttpTraceFullDateTime(iso) {
  const ts = httpTraceCreatedAtTs(iso)
  if (!Number.isFinite(ts)) return ''
  return new Date(ts).toLocaleString(HTTP_TRACE_DT_LOCALE, {
    dateStyle: 'long',
    timeStyle: 'medium',
  })
}

function fullHttpTracePath(path) {
  return String(path ?? '')
}

/** Нормализация: при type="number" во Vue v-model иногда даёт number — без String() ломается .trim() */
function rawUserIdTrimmed() {
  const v = filterUserId.value
  if (v === null || v === undefined) return ''
  return String(v).trim()
}

function buildQueryForUrl(overrides = {}) {
  const lim = overrides.limit !== undefined ? overrides.limit : limit.value
  const off = overrides.offset !== undefined ? overrides.offset : offset.value
  const q = {
    limit: String(lim),
    offset: String(off),
  }
  const uid = rawUserIdTrimmed()
  if (uid) {
    q.user_id = uid
  }
  if (onlyWithoutUser.value) {
    q.only_without_user = '1'
  }
  return q
}

async function syncFromRoute() {
  if (route.name !== 'admin-http-logs') {
    return
  }

  const q = route.query
  const uid = q.user_id
  if (uid != null && String(uid).trim() !== '') {
    const n = Number.parseInt(String(uid), 10)
    filterUserId.value = Number.isFinite(n) && n > 0 ? String(n) : ''
  } else {
    filterUserId.value = ''
  }
  onlyWithoutUser.value =
    q.only_without_user === '1' ||
    q.only_without_user === 'true' ||
    q.only_without_user === true
  const lim = q.limit != null ? Number.parseInt(String(q.limit), 10) : 50
  limit.value =
    Number.isFinite(lim) && lim >= 1 && lim <= 200 ? lim : 50
  const off = q.offset != null ? Number.parseInt(String(q.offset), 10) : 0
  offset.value = Number.isFinite(off) && off >= 0 ? off : 0

  loading.value = true
  error.value = null
  const params = new URLSearchParams()
  params.set('limit', String(limit.value))
  params.set('offset', String(offset.value))
  const uidTrim = rawUserIdTrimmed()
  if (uidTrim) {
    params.set('user_id', uidTrim)
  }
  if (onlyWithoutUser.value) {
    params.set('only_without_user', 'true')
  }
  try {
    const data = await fetchJson(
      `/api/admin/http-request-traces?${params.toString()}`,
    )
    page.value = data
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    page.value = { items: [], total: 0, limit: limit.value, offset: offset.value }
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  router.replace({
    path: '/admin/logs',
    query: buildQueryForUrl({ offset: 0 }),
  })
}

function resetFilters() {
  filterUserId.value = ''
  onlyWithoutUser.value = false
  limit.value = 50
  router.replace({ path: '/admin/logs', query: {} })
}

function goPrev() {
  const nextOff = Math.max(0, offset.value - limit.value)
  if (nextOff === offset.value) return
  router.replace({
    path: '/admin/logs',
    query: buildQueryForUrl({ offset: nextOff }),
  })
}

function goNext() {
  const nextOff = offset.value + limit.value
  if (nextOff >= page.value.total) return
  router.replace({
    path: '/admin/logs',
    query: buildQueryForUrl({ offset: nextOff }),
  })
}

const rangeLabel = computed(() => {
  const t = page.value.total
  if (t === 0) return '0 записей'
  const from = offset.value + 1
  const to = Math.min(offset.value + page.value.items.length, t)
  return `${from}–${to} из ${t}`
})

const canNext = computed(
  () => offset.value + page.value.items.length < page.value.total,
)

const logRows = computed(() => page.value.items)

const httpTraceSortAccessors = {
  created_at: (r) => r.created_at,
  user_id: (r) => (r.user_id != null ? r.user_id : -1),
  subject_source: (r) => String(r.subject_source ?? '').toLowerCase(),
  http_method: (r) => String(r.http_method ?? '').toLowerCase(),
  path: (r) => String(r.path ?? '').toLowerCase(),
  status_code: (r) => Number(r.status_code) || 0,
  duration_ms: (r) => Number(r.duration_ms) || 0,
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(
  logRows,
  httpTraceSortAccessors,
)

watch(
  () => route.fullPath,
  () => {
    void syncFromRoute()
  },
  { immediate: true },
)
</script>

<template>
  <AdminStaffShell
    title="Логи"
  >
    <template #headerExtras>
      <div class="filters glass">
        <label class="f-label">
          <span>User ID</span>
          <input
            v-model="filterUserId"
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            autocomplete="off"
            class="f-input"
            placeholder="любой"
            :disabled="onlyWithoutUser"
          />
        </label>
        <label
          class="f-switch"
          :class="{ 'f-switch--on': onlyWithoutUser }"
        >
          <input
            v-model="onlyWithoutUser"
            type="checkbox"
            class="f-switch-native"
          />
          <span class="f-switch-track" aria-hidden="true">
            <span class="f-switch-thumb" />
          </span>
          <span class="f-switch-text">
            <span class="f-switch-title">Только анонимные</span>
            <span class="f-switch-hint">Строки без user_id в журнале</span>
          </span>
        </label>
        <label class="f-label narrow">
          <span>Строк на странице</span>
          <select v-model.number="limit" class="f-select">
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="200">200</option>
          </select>
        </label>
        <button type="button" class="btn-primary" @click="applyFilters">
          Применить
        </button>
        <button type="button" class="btn-secondary" @click="resetFilters">
          Сброс
        </button>
      </div>
    </template>

    <p v-if="loading" class="muted">Загрузка…</p>
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <div v-if="!loading && !error" class="pager-top">
      <span class="muted">{{ rangeLabel }}</span>
      <div class="pager-btns">
        <button
          type="button"
          class="btn-secondary"
          :disabled="offset <= 0"
          @click="goPrev"
        >
          Назад
        </button>
        <button type="button" class="btn-secondary" :disabled="!canNext" @click="goNext">
          Вперёд
        </button>
      </div>
    </div>

    <AdminTableWrap aria-label="Таблица журнала HTTP">
      <table class="admin-table http-trace-table">
        <thead>
          <tr>
            <AdminSortTh
              label="Время"
              column-key="created_at"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="User"
              column-key="user_id"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Источник"
              column-key="subject_source"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Метод"
              column-key="http_method"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Путь"
              column-key="path"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Статус"
              column-key="status_code"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="мс"
              column-key="duration_ms"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
          </tr>
        </thead>
        <tbody>
          <tr v-if="sortedRows.length === 0">
            <td colspan="7" class="muted center">Нет строк</td>
          </tr>
          <tr v-for="row in sortedRows" :key="row.id">
            <td
              class="mono nowrap"
              :title="formatHttpTraceFullDateTime(row.created_at)"
            >
              {{ formatHttpTraceTimeOnly(row.created_at) }}
            </td>
            <td class="mono num">
              {{
                row.user_id != null
                  ? row.user_id
                  : '—'
              }}
            </td>
            <td>{{ row.subject_source }}</td>
            <td class="mono">{{ row.http_method }}</td>
            <td class="mono">
              <span class="path-cell-inner" :title="fullHttpTracePath(row.path)">{{
                row.path
              }}</span>
            </td>
            <td class="mono num">{{ row.status_code }}</td>
            <td class="mono num">{{ Number(row.duration_ms).toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </AdminStaffShell>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  padding: 0.85rem 1rem;
  border-radius: 14px;
  margin-bottom: 1rem;
}

.f-label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
}

.f-label.narrow {
  width: auto;
}

.f-input,
.f-select {
  min-height: 2rem;
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text);
}

.f-input {
  width: 7rem;
}

/* Переключатель «без user_id»: switch + текст */
.f-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  margin: 0;
  cursor: pointer;
  user-select: none;
  padding: 0.4rem 0.75rem 0.45rem;
  border-radius: 999px;
  border: 1px solid var(--card-border);
  background: linear-gradient(
    165deg,
    color-mix(in srgb, var(--surface) 92%, transparent) 0%,
    color-mix(in srgb, var(--card-bg) 88%, transparent) 100%
  );
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 0.04);
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease;
}

.f-switch:hover {
  border-color: var(--accent-border, var(--accent));
}

.f-switch--on {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--card-border));
  box-shadow:
    inset 0 1px 0 rgb(255 255 255 / 0.05),
    0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
}

.f-switch-native {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.f-switch-track {
  position: relative;
  flex-shrink: 0;
  width: 2.65rem;
  height: 1.45rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 28%, var(--surface));
  border: 1px solid var(--card-border);
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}

.f-switch--on .f-switch-track {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--accent-hover) 90%, transparent),
    color-mix(in srgb, var(--accent) 94%, transparent)
  );
  border-color: color-mix(in srgb, var(--accent) 42%, transparent);
}

.f-switch:focus-visible {
  outline: none;
}

.f-switch:focus-visible .f-switch-track {
  box-shadow:
    0 0 0 2px var(--surface),
    0 0 0 4px var(--accent);
}

.f-switch-thumb {
  position: absolute;
  top: 50%;
  left: 0.12rem;
  width: 1.06rem;
  height: 1.06rem;
  border-radius: 50%;
  background: linear-gradient(
    180deg,
    var(--surface) 0%,
    color-mix(in srgb, var(--surface) 78%, rgb(220 220 230)) 100%
  );
  box-shadow:
    0 1px 2px rgb(0 0 0 / 0.2),
    0 0 1px rgb(0 0 0 / 0.12);
  transform: translateY(-50%);
  transition: left 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.f-switch--on .f-switch-thumb {
  left: calc(100% - 0.12rem - 1.06rem);
}

@media (prefers-reduced-motion: reduce) {
  .f-switch-track,
  .f-switch-thumb,
  .f-switch {
    transition: none;
  }
}

.f-switch-text {
  display: flex;
  flex-direction: column;
  gap: 0.08rem;
  line-height: 1.22;
}

.f-switch-title {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text-h);
  letter-spacing: -0.015em;
}

.f-switch-hint {
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--muted);
  letter-spacing: 0.02em;
}

.pager-top {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.65rem;
}

.pager-btns {
  display: flex;
  gap: 0.35rem;
}

.muted {
  color: var(--muted);
}

.msg-err {
  color: #f87171;
  margin-bottom: 0.75rem;
}

.http-trace-table {
  font-size: 0.82rem;
  width: 100%;
  max-width: 100%;
}

/* Короткие колонки — без переноса, ширина по содержимому */
.http-trace-table :is(th, td):nth-child(1),
.http-trace-table :is(th, td):nth-child(2),
.http-trace-table :is(th, td):nth-child(3),
.http-trace-table :is(th, td):nth-child(4),
.http-trace-table :is(th, td):nth-child(6),
.http-trace-table :is(th, td):nth-child(7) {
  white-space: nowrap;
  width: 1%;
}

/* Колонка "Путь" занимает оставшееся пространство таблицы */
.http-trace-table :is(th, td):nth-child(5) {
  width: 100%;
}

.path-cell-inner {
  display: block;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.35;
}

.nowrap {
  white-space: nowrap;
}

.num {
  text-align: right;
}

.center {
  text-align: center;
}

.mono {
  font-family: ui-monospace, monospace;
}
</style>
