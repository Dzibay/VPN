<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import AppPager from '../components/AppPager.vue'
import MultiSelectDropdown from '../components/MultiSelectDropdown.vue'
import StateNote from '../components/StateNote.vue'
import { fetchJson } from '../api/client.js'
import { getSessionRole } from '../auth/session.js'
import { useTableSort } from '../utils/adminTableSort.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'

const route = useRoute()
const router = useRouter()
const limit = ref(50)
const offset = ref(0)
const filterUserId = ref('')
const filterClientIp = ref('')
const filterPathContains = ref('')
const filterStatusCodes = ref([])
const filterSubjectSources = ref([])
const filterTraceDate = ref('')
const filterTimeFrom = ref('')
const filterTimeTo = ref('')

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

function httpTraceCreatedAtTs(iso) {
  const t = Date.parse(String(iso ?? ''))
  return Number.isFinite(t) ? t : NaN
}

/** Дата и время в ячейке (две строки); развёрнутый формат — в title. */
function formatHttpTraceDate(iso) {
  const ts = httpTraceCreatedAtTs(iso)
  if (!Number.isFinite(ts)) return '—'
  return new Date(ts).toLocaleDateString('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function formatHttpTraceTime(iso) {
  const ts = httpTraceCreatedAtTs(iso)
  if (!Number.isFinite(ts)) return ''
  return new Date(ts).toLocaleTimeString('ru-RU', {
    timeZone: 'Europe/Moscow',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatHttpTraceFullDateTime(iso) {
  const ts = httpTraceCreatedAtTs(iso)
  if (!Number.isFinite(ts)) return ''
  return formatMskApiDateTime(ts, { dateStyle: 'long', timeStyle: 'medium' })
}

function fullHttpTracePath(path) {
  return String(path ?? '')
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const ISO_TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/

function normalizeTraceDate(raw) {
  const s = String(raw ?? '').trim()
  return ISO_DATE_RE.test(s) ? s : ''
}

function normalizeTraceTime(raw) {
  const s = String(raw ?? '').trim()
  return ISO_TIME_RE.test(s) ? s : ''
}

/** День + опциональный интервал времени (локальное время браузера) → ISO UTC для API. */
function buildHttpTraceCreatedRange(dateStr, timeFromStr, timeToStr) {
  const date = normalizeTraceDate(dateStr)
  if (!date) {
    return { createdFrom: null, createdTo: null, error: null }
  }
  const timeFrom = normalizeTraceTime(timeFromStr)
  const timeTo = normalizeTraceTime(timeToStr)
  const from = new Date(`${date}T${timeFrom || '00:00'}`)
  const to = new Date(`${date}T${timeTo || '23:59'}`)
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
    return {
      createdFrom: null,
      createdTo: null,
      error: 'Некорректная дата или время в фильтре',
    }
  }
  to.setSeconds(59, 999)
  if (from.getTime() > to.getTime()) {
    return {
      createdFrom: null,
      createdTo: null,
      error: 'Время «с» не может быть позже времени «до»',
    }
  }
  return {
    createdFrom: from.toISOString(),
    createdTo: to.toISOString(),
    error: null,
  }
}

const httpTraceCreatedRange = computed(() =>
  buildHttpTraceCreatedRange(
    filterTraceDate.value,
    filterTimeFrom.value,
    filterTimeTo.value,
  ),
)

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
  const ipTrim = String(filterClientIp.value ?? '').trim()
  if (ipTrim) {
    q.client_ip = ipTrim
  }
  if (filterStatusCodes.value.length > 0) {
    q.status_code = [...filterStatusCodes.value]
  }
  if (filterSubjectSources.value.length > 0) {
    q.subject_source = [...filterSubjectSources.value]
  }
  const traceDate = normalizeTraceDate(filterTraceDate.value)
  if (traceDate) {
    q.trace_date = traceDate
    const timeFrom = normalizeTraceTime(filterTimeFrom.value)
    const timeTo = normalizeTraceTime(filterTimeTo.value)
    if (timeFrom) q.time_from = timeFrom
    if (timeTo) q.time_to = timeTo
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
  const ipf = q.client_ip
  filterClientIp.value =
    ipf != null && String(ipf).trim() !== '' ? String(ipf).trim() : ''
  filterTraceDate.value = normalizeTraceDate(q.trace_date)
  filterTimeFrom.value = normalizeTraceTime(q.time_from)
  filterTimeTo.value = normalizeTraceTime(q.time_to)
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
  const ipTrimSync = String(filterClientIp.value ?? '').trim()
  if (ipTrimSync) {
    params.set('client_ip', ipTrimSync)
  }
  const range = buildHttpTraceCreatedRange(
    filterTraceDate.value,
    filterTimeFrom.value,
    filterTimeTo.value,
  )
  if (range.error) {
    error.value = range.error
    page.value = { items: [], total: 0, limit: limit.value, offset: offset.value }
    loading.value = false
    return
  }
  if (range.createdFrom) {
    params.set('created_from', range.createdFrom)
  }
  if (range.createdTo) {
    params.set('created_to', range.createdTo)
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
  const range = httpTraceCreatedRange.value
  if (range.error) {
    error.value = range.error
    return
  }
  error.value = null
  router.replace({
    path: '/admin/logs',
    query: buildQueryForUrl({ offset: 0 }),
  })
}

function resetFilters() {
  filterUserId.value = ''
  filterClientIp.value = ''
  filterPathContains.value = ''
  filterStatusCodes.value = []
  filterSubjectSources.value = []
  filterTraceDate.value = ''
  filterTimeFrom.value = ''
  filterTimeTo.value = ''
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
  client_ip: (r) => String(r.client_ip ?? '').toLowerCase(),
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
        <label class="f-label">
          <span>IP</span>
          <input
            v-model="filterClientIp"
            type="text"
            class="f-input f-input--ip"
            autocomplete="off"
            placeholder="203.0.113"
            spellcheck="false"
          />
        </label>
        <label class="f-label narrow">
          <span>День</span>
          <input
            v-model="filterTraceDate"
            type="date"
            class="f-input f-input--date"
            autocomplete="off"
          />
        </label>
        <label class="f-label narrow" :class="{ 'f-label--disabled': !filterTraceDate }">
          <span>С</span>
          <input
            v-model="filterTimeFrom"
            type="time"
            class="f-input f-input--time"
            :disabled="!filterTraceDate"
            step="60"
          />
        </label>
        <label class="f-label narrow" :class="{ 'f-label--disabled': !filterTraceDate }">
          <span>До</span>
          <input
            v-model="filterTimeTo"
            type="time"
            class="f-input f-input--time"
            :disabled="!filterTraceDate"
            step="60"
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

    <StateNote v-if="loading" loading />
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <AppPager
      v-if="!loading && !error"
      :range-label="rangeLabel"
      :can-prev="offset > 0"
      :can-next="canNext"
      @prev="goPrev"
      @next="goNext"
    >
      <template v-if="canDeleteLogs" #actions>
        <button
          type="button"
          class="btn-danger"
          :disabled="selectedIds.length === 0 || deleting"
          @click="deleteSelected"
        >
          {{ deleting ? 'Удаление…' : `Удалить выбранные (${selectedIds.length})` }}
        </button>
      </template>
    </AppPager>

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
              label="IP"
              column-key="client_ip"
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
              class="th-method"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Путь"
              column-key="path"
              class="th-path"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Статус"
              column-key="status_code"
              align="right"
              class="th-status"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="мс"
              column-key="duration_ms"
              align="right"
              class="th-ms"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
          </tr>
        </thead>
        <tbody>
          <tr v-if="sortedRows.length === 0">
            <td :colspan="canDeleteLogs ? 9 : 8" class="muted center">Нет строк</td>
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
              class="mono td-datetime"
              :title="formatHttpTraceFullDateTime(row.created_at)"
            >
              <span class="dt-date">{{ formatHttpTraceDate(row.created_at) }}</span>
              <span class="dt-time">{{ formatHttpTraceTime(row.created_at) }}</span>
            </td>
            <td class="mono num td-user">
              {{
                row.user_id != null
                  ? row.user_id
                  : '—'
              }}
            </td>
            <td class="mono nowrap td-ip">{{ row.client_ip || '—' }}</td>
            <td class="td-source">{{ row.subject_source }}</td>
            <td class="mono td-method">{{ row.http_method }}</td>
            <td class="mono td-path">
              <span class="path-cell-inner" :title="fullHttpTracePath(row.path)">{{
                row.path
              }}</span>
            </td>
            <td class="mono num td-status">{{ row.status_code }}</td>
            <td class="mono num td-ms">{{ Number(row.duration_ms).toFixed(1) }}</td>
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

.f-input--ip {
  width: 10.5rem;
  font-family: ui-monospace, monospace;
}

.f-input--path {
  width: 100%;
  min-width: 12rem;
}

.f-input--date {
  width: 10.5rem;
}

.f-input--time {
  width: 6.5rem;
}

.f-label--disabled {
  opacity: 0.55;
}

.http-trace-table {
  font-size: 0.82rem;
  width: 100%;
  max-width: 100%;
}

.http-trace-table :is(.td-datetime, .td-user, .td-ip, .td-method, .td-status, .td-ms, .th-method, .th-status, .th-ms) {
  white-space: nowrap;
  width: 1%;
}

.http-trace-table :is(.td-path, .th-path) {
  width: 100%;
}

.td-datetime {
  line-height: 1.25;
  vertical-align: top;
}

.dt-date,
.dt-time {
  display: block;
}

.dt-time {
  color: var(--muted);
  font-size: 0.78em;
}

.td-method,
.th-method {
  max-width: 3.25rem;
  padding-left: 0.35rem;
  padding-right: 0.35rem;
  text-align: center;
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
