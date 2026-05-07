<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import MultiSelectDropdown from '../components/MultiSelectDropdown.vue'
import { fetchJson } from '../api/client.js'
import { getSessionRole } from '../auth/session.js'
import { useTableSort } from '../utils/adminTableSort.js'

const route = useRoute()
const router = useRouter()
const limit = ref(50)
const offset = ref(0)
const filterUserId = ref('')
const filterPathContains = ref('')
const filterStatusCodes = ref([])
const filterSubjectSources = ref([])

const loading = ref(false)
const error = ref(null)
const deleting = ref(false)
const selectedIds = ref([])
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
  const pathTrim = String(filterPathContains.value ?? '').trim()
  if (pathTrim) {
    q.path_contains = pathTrim
  }
  if (filterStatusCodes.value.length > 0) {
    q.status_code = [...filterStatusCodes.value]
  }
  if (filterSubjectSources.value.length > 0) {
    q.subject_source = [...filterSubjectSources.value]
  }
  return q
}

function queryValues(raw) {
  if (Array.isArray(raw)) return raw.map((v) => String(v).trim()).filter(Boolean)
  if (raw == null) return []
  const s = String(raw).trim()
  return s ? [s] : []
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
  filterStatusCodes.value = queryValues(q.status_code).filter((v) => {
    const n = Number.parseInt(v, 10)
    return Number.isFinite(n) && n >= 100 && n <= 599
  })
  filterSubjectSources.value = queryValues(q.subject_source).slice(0, 20)
  const pcf = q.path_contains
  filterPathContains.value =
    pcf != null && String(pcf).trim() !== '' ? String(pcf).trim() : ''
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
  for (const status of filterStatusCodes.value) params.append('status_code', status)
  for (const source of filterSubjectSources.value) params.append('subject_source', source)
  const pathTrimSync = String(filterPathContains.value ?? '').trim()
  if (pathTrimSync) {
    params.set('path_contains', pathTrimSync)
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
  filterPathContains.value = ''
  filterStatusCodes.value = []
  filterSubjectSources.value = []
  limit.value = 50
  router.replace({ path: '/admin/logs', query: {} })
}

async function deleteSelected() {
  if (!canDeleteLogs.value || selectedIds.value.length === 0 || deleting.value) return
  const ok = window.confirm(
    `Удалить выбранные логи (${selectedIds.value.length})? Действие необратимо.`,
  )
  if (!ok) return
  deleting.value = true
  error.value = null
  try {
    await fetchJson('/api/admin/http-request-traces', {
      method: 'DELETE',
      body: JSON.stringify({ ids: selectedIds.value }),
    })
    selectedIds.value = []
    await syncFromRoute()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    deleting.value = false
  }
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
const rowIdsOnPage = computed(() => sortedRows.value.map((row) => Number(row.id)))
const allSelectedOnPage = computed(() => {
  if (rowIdsOnPage.value.length === 0) return false
  return rowIdsOnPage.value.every((id) => selectedIds.value.includes(id))
})

function toggleSelectAllOnPage() {
  if (allSelectedOnPage.value) {
    const remove = new Set(rowIdsOnPage.value)
    selectedIds.value = selectedIds.value.filter((id) => !remove.has(id))
    return
  }
  selectedIds.value = Array.from(
    new Set([...selectedIds.value, ...rowIdsOnPage.value]),
  )
}

const sourceFilterOptions = computed(() => {
  const common = [
    'subscription_token',
    'anonymous',
    'jwt_admin',
    'jwt_manager',
    'jwt_user',
    'login_password',
    'register_email',
    'telegram_bot_topic_lookup',
    'telegram_bot_profile_patch',
  ]
  const dynamic = page.value.items
    .map((r) => String(r.subject_source ?? '').trim())
    .filter((v) => v.length > 0)
  return Array.from(new Set([...common, ...dynamic]))
})
const statusFilterOptions = [
  '200',
  '201',
  '204',
  '301',
  '302',
  '400',
  '401',
  '403',
  '404',
  '422',
  '500',
  '502',
  '503',
]

const logRows = computed(() => page.value.items)
const canDeleteLogs = computed(() => getSessionRole() === 'admin')

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

watch(
  () => rowIdsOnPage.value,
  (ids) => {
    const keep = new Set(ids)
    selectedIds.value = selectedIds.value.filter((id) => keep.has(id))
  },
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
          />
        </label>
        <label class="f-label f-label--path">
          <span>Путь содержит</span>
          <input
            v-model="filterPathContains"
            type="text"
            class="f-input f-input--path"
            autocomplete="off"
            placeholder="например /login"
            spellcheck="false"
          />
        </label>
        <label class="f-label narrow">
          <span>Статус</span>
          <MultiSelectDropdown
            v-model="filterStatusCodes"
            :options="statusFilterOptions"
            all-label="любой"
          />
        </label>
        <label class="f-label">
          <span>Источник</span>
          <MultiSelectDropdown
            v-model="filterSubjectSources"
            :options="sourceFilterOptions"
            all-label="любой"
          />
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
          v-if="canDeleteLogs"
          type="button"
          class="btn-danger"
          :disabled="selectedIds.length === 0 || deleting"
          @click="deleteSelected"
        >
          {{ deleting ? 'Удаление…' : `Удалить выбранные (${selectedIds.length})` }}
        </button>
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
      <table class="admin-table http-trace-table" :class="{ 'http-trace-table--no-select': !canDeleteLogs }">
        <thead>
          <tr>
            <th v-if="canDeleteLogs" class="th-select">
              <input
                type="checkbox"
                :checked="allSelectedOnPage"
                :disabled="rowIdsOnPage.length === 0"
                @change="toggleSelectAllOnPage"
              />
            </th>
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
            <td :colspan="canDeleteLogs ? 8 : 7" class="muted center">Нет строк</td>
          </tr>
          <tr v-for="row in sortedRows" :key="row.id">
            <td v-if="canDeleteLogs" class="td-select">
              <input
                v-model="selectedIds"
                type="checkbox"
                :value="row.id"
              />
            </td>
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

.f-label--path {
  flex: 1 1 14rem;
  min-width: 10rem;
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

.f-input--path {
  width: 100%;
  min-width: 12rem;
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

.btn-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0.55rem 1.15rem;
  border-radius: var(--radius-lg);
  border: none;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, #ef4444 92%, white) 0%,
    color-mix(in srgb, #dc2626 94%, black) 100%
  );
  color: #fff;
  box-shadow: var(--shadow-sm);
  transition:
    filter 0.2s ease,
    transform 0.15s ease,
    box-shadow 0.2s ease;
}

.btn-danger:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-md);
}

.btn-danger:active:not(:disabled) {
  transform: translateY(1px);
}

.btn-danger:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring), var(--shadow-sm);
}

.btn-danger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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
.http-trace-table :is(th, td):nth-child(5),
.http-trace-table :is(th, td):nth-child(7),
.http-trace-table :is(th, td):nth-child(8) {
  white-space: nowrap;
  width: 1%;
}

/* Колонка "Путь" занимает оставшееся пространство таблицы */
.http-trace-table :is(th, td):nth-child(6) {
  width: 100%;
}

/* Вариант без колонки выбора (manager): индексы колонок сдвинуты на -1 */
.http-trace-table--no-select :is(th, td):nth-child(1),
.http-trace-table--no-select :is(th, td):nth-child(2),
.http-trace-table--no-select :is(th, td):nth-child(3),
.http-trace-table--no-select :is(th, td):nth-child(4),
.http-trace-table--no-select :is(th, td):nth-child(6),
.http-trace-table--no-select :is(th, td):nth-child(7) {
  white-space: nowrap;
  width: 1%;
}

.http-trace-table--no-select :is(th, td):nth-child(5) {
  width: 100%;
}

.th-select,
.td-select {
  width: 1%;
  text-align: center;
  white-space: nowrap;
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
