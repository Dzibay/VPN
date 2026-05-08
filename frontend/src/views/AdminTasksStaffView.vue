<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, type: string, user_id: number, referee_id: number | null, bonus_days: number | null, paid_months: number | null, status: string, created_at: string, done_at: string | null }>>} */
const items = ref([])
const total = ref(0)
const limit = 200
const offset = ref(0)

const sortAccessors = {
  id: (r) => Number(r.id) || 0,
  type: (r) => String(r.type ?? '').toLowerCase(),
  user_id: (r) => Number(r.user_id) || 0,
  referee_id: (r) => (r.referee_id == null ? -1 : Number(r.referee_id)),
  bonus_days: (r) => (r.bonus_days == null ? -1 : Number(r.bonus_days)),
  paid_months: (r) => (r.paid_months == null ? -1 : Number(r.paid_months)),
  status: (r) => String(r.status ?? '').toLowerCase(),
  created_at: (r) => String(r.created_at ?? ''),
  done_at: (r) => String(r.done_at ?? ''),
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(items, sortAccessors)

const rangeLabel = computed(() => {
  const n = items.value.length
  if (total.value === 0) return '0 записей'
  const from = offset.value + 1
  const to = offset.value + n
  return `${from}–${to} из ${total.value}`
})

const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => offset.value + items.value.length < total.value)

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'medium',
    })
  } catch {
    return String(iso)
  }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset.value),
    })
    const data = await fetchJson(`/api/admin/tasks?${params.toString()}`)
    items.value = Array.isArray(data?.items) ? data.items : []
    total.value = Number(data?.total) || 0
  } catch (e) {
    error.value = e.message || String(e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function prevPage() {
  offset.value = Math.max(0, offset.value - limit)
  void load()
}

function nextPage() {
  offset.value = offset.value + limit
  void load()
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="Задачи">
    <template #headerExtras>
      <div class="head-row">
        <h2 class="section-heading">Очередь задач</h2>
        <div class="head-actions">
          <button type="button" class="btn-secondary" :disabled="loading" @click="load">
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </template>

    <p v-if="loading && items.length === 0" class="muted">Загрузка…</p>
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <template v-else>
      <section class="stats" aria-live="polite">
        <p class="stats-value">{{ rangeLabel }}</p>
      </section>

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

      <AdminTableWrap aria-label="Задачи">
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
                label="Тип"
                column-key="type"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="user_id"
                column-key="user_id"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="referee"
                column-key="referee_id"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="bonus дн."
                column-key="bonus_days"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="мес."
                column-key="paid_months"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Статус"
                column-key="status"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Создана"
                column-key="created_at"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Завершена"
                column-key="done_at"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
            </tr>
          </thead>
          <tbody>
            <tr v-if="sortedRows.length === 0">
              <td colspan="9" class="muted">Нет записей</td>
            </tr>
            <template v-else>
              <tr v-for="row in sortedRows" :key="row.id">
                <td class="num">{{ row.id }}</td>
                <td class="mono-cell">{{ row.type }}</td>
                <td class="num">{{ row.user_id }}</td>
                <td class="num">{{ row.referee_id ?? '—' }}</td>
                <td class="num">{{ row.bonus_days ?? '—' }}</td>
                <td class="num">{{ row.paid_months ?? '—' }}</td>
                <td>
                  <span class="pill pill-mono" :title="row.status">{{ row.status }}</span>
                </td>
                <td class="date-cell">{{ fmtDate(row.created_at) }}</td>
                <td class="date-cell">{{ fmtDate(row.done_at) }}</td>
              </tr>
            </template>
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
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}
.section-heading {
  margin: 0;
  font-size: 1.05rem;
  color: var(--text-h);
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.sub {
  margin: 0 0 0.75rem;
  font-size: 0.85rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 52rem;
}
.inline-code {
  font-family: ui-monospace, monospace;
  font-size: 0.88em;
  padding: 0.05rem 0.25rem;
  border-radius: 4px;
  background: var(--surface);
}
.stats {
  margin-bottom: 1rem;
}
.stats-value {
  margin: 0;
  font-size: 0.95rem;
  color: var(--text-h);
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
  color: var(--danger);
  margin-bottom: 0.75rem;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.mono-cell {
  font-family: ui-monospace, monospace;
  font-size: 0.78rem;
  word-break: break-all;
  max-width: 14rem;
}
.date-cell {
  white-space: nowrap;
  font-size: 0.8rem;
  color: var(--muted);
}
.pill {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--surface);
  border: 1px solid var(--card-border);
  color: var(--muted);
}
.pill-mono {
  font-family: ui-monospace, monospace;
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0.02em;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
