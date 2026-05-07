<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<{ hours_window?: number, probe_interval_seconds_hint?: number, servers?: unknown[] } | null>} */
const bundle = ref(null)
const hours = ref(24)

/** @type {number | null} */
let pollTimer = null

const hourOptions = [
  { value: 6, label: '6 ч' },
  { value: 24, label: '24 ч' },
  { value: 72, label: '3 суток' },
  { value: 168, label: '7 суток' },
]

const rows = computed(() => {
  const s = bundle.value?.servers
  return Array.isArray(s) ? s : []
})

const probeHint = computed(() =>
  Math.max(30, Number(bundle.value?.probe_interval_seconds_hint) || 45),
)

const sortAccessors = {
  host: (r) => `${String(r.host ?? '')}:${Number(r.port) || 0}`.toLowerCase(),
  vpn_ok_percent: (r) => Number(r.vpn_ok_percent) || 0,
  samples_total: (r) => Number(r.samples_total) || 0,
  last_probe_ts: (r) => Number(r.last_probe_ts) || 0,
  provision_ready: (r) => (r.provision_ready ? 1 : 0),
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(rows, sortAccessors)

function formatTs(ts) {
  if (ts == null || Number.isNaN(Number(ts))) return '—'
  return new Date(Number(ts) * 1000).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function fmtPct(v) {
  if (v == null || v === '') return '—'
  return `${Number(v).toFixed(1)} %`
}

function clearPoll() {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function schedulePoll() {
  clearPoll()
  const sec = Math.min(120, Math.max(25, probeHint.value + 3))
  pollTimer = window.setInterval(() => {
    void load(false)
  }, sec * 1000)
}

/**
 * @param {boolean} showLoading
 */
async function load(showLoading = true) {
  if (showLoading) loading.value = true
  error.value = null
  try {
    const data = await fetchJson(
      `/api/servers/reachability-summary?hours=${encodeURIComponent(hours.value)}`,
    )
    bundle.value = data
    schedulePoll()
  } catch (e) {
    error.value = e.message || String(e)
    bundle.value = null
    clearPoll()
  } finally {
    loading.value = false
  }
}

watch(hours, () => {
  void load(true)
})

onMounted(() => {
  void load(true)
})

onBeforeUnmount(() => {
  clearPoll()
})
</script>

<template>
  <AdminStaffShell title="Доступность серверов">
    <template #headerExtras>
      <div class="head-row">
        <div class="head-actions">
          <label class="hours-label">
            Окно
            <select v-model.number="hours" class="hours-select">
              <option v-for="o in hourOptions" :key="o.value" :value="o.value">
                {{ o.label }}
              </option>
            </select>
          </label>
          <button type="button" class="btn-secondary" :disabled="loading" @click="load(true)">
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </template>

    <p v-if="loading && !sortedRows.length" class="muted">Загрузка…</p>
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <template v-else>
      <p v-if="sortedRows.length === 0" class="muted">
        Нет серверов в базе или ещё нет снимков в Redis (подождите один цикл планировщика).
      </p>
      <AdminTableWrap v-else aria-label="Доступность VPN-узлов">
        <table class="admin-table">
          <thead>
            <tr>
              <AdminSortTh
                label="Узел"
                column-key="host"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Готов"
                column-key="provision_ready"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Снимков"
                column-key="samples_total"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="VPN TCP OK"
                column-key="vpn_ok_percent"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <th class="admin-th admin-th--num">
                <span class="admin-th__static">Мс (ср.)</span>
              </th>
              <th class="admin-th admin-th--num">
                <span class="admin-th__static">NE</span>
              </th>
              <th class="admin-th admin-th--num">
                <span class="admin-th__static">Exit</span>
              </th>
              <AdminSortTh
                label="Последний зонд"
                column-key="last_probe_ts"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <th class="admin-th">
                <span class="admin-th__static">Сейчас</span>
              </th>
              <th class="admin-th row-actions-head">
                <span class="admin-th__static">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sortedRows" :key="row.server_id">
              <td>
                <span class="mono">{{ row.host }}:{{ row.port }}</span>
                <span v-if="row.name" class="muted name-tag">{{ row.name }}</span>
              </td>
              <td class="num">{{ row.provision_ready ? 'Да' : 'Нет' }}</td>
              <td class="num">{{ Number(row.samples_total || 0).toLocaleString('ru-RU') }}</td>
              <td class="num">{{ fmtPct(row.vpn_ok_percent) }}</td>
              <td class="num">
                {{
                  row.avg_vpn_latency_ms != null
                    ? Number(row.avg_vpn_latency_ms).toLocaleString('ru-RU', {
                        maximumFractionDigits: 1,
                      })
                    : '—'
                }}
              </td>
              <td class="num">{{ fmtPct(row.ne_ok_percent) }}</td>
              <td class="num">{{ fmtPct(row.exit_ok_percent) }}</td>
              <td class="num muted">{{ formatTs(row.last_probe_ts) }}</td>
              <td>
                <span
                  v-if="row.last_vpn_ok === true"
                  class="pill pill--ok"
                  title="Последний TCP к VPN-порту успешен"
                  >OK</span>
                <span
                  v-else-if="row.last_vpn_ok === false"
                  class="pill pill--bad"
                  title="Последний TCP к VPN-порту не удался"
                  >Нет</span>
                <span v-else class="muted">—</span>
              </td>
              <td class="row-actions">
                <RouterLink
                  class="link-action"
                  :to="{ path: '/admin/analytics', query: { server: String(row.server_id) } }"
                >
                  Нагрузка
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </AdminTableWrap>
    </template>
  </AdminStaffShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.head-text {
  flex: 1 1 22rem;
  margin: 0;
  line-height: 1.45;
}

.head-actions {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.hours-label {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9rem;
}

.hours-select {
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.12));
  background: var(--surface-2, rgba(0, 0, 0, 0.25));
  color: inherit;
}

.mono {
  font-family: ui-monospace, monospace;
  font-size: 0.88rem;
}

.name-tag {
  display: block;
  font-size: 0.82rem;
  margin-top: 0.15rem;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.inline {
  font-family: ui-monospace, monospace;
  font-size: 0.85em;
}

.pill {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.pill--ok {
  background: rgba(46, 204, 113, 0.18);
  color: #7bed9f;
}

.pill--bad {
  background: rgba(231, 76, 60, 0.2);
  color: #ffb4a8;
}

.link-action {
  font-size: 0.88rem;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
