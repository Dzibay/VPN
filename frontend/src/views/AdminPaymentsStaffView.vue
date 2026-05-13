<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, user_id: number, amount: string | number, months: number, provider: string, payment_kind: string, external_id: string | null, created_at: string }>>} */
const items = ref([])
const total = ref(0)
const limit = 200
const offset = ref(0)

const sortAccessors = {
  id: (r) => Number(r.id) || 0,
  user_id: (r) => Number(r.user_id) || 0,
  amount: (r) => Number(r.amount) || 0,
  months: (r) => Number(r.months) || 0,
  provider: (r) => String(r.provider ?? '').toLowerCase(),
  payment_kind: (r) => String(r.payment_kind ?? '').toLowerCase(),
  external_id: (r) => String(r.external_id ?? '').toLowerCase(),
  created_at: (r) => String(r.created_at ?? ''),
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

function formatAmount(v) {
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

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

function paymentKindLabel(k) {
  const s = String(k ?? '')
  if (s === 'subscription') return 'Подписка'
  if (s === 'one_time') return 'Разовая'
  return s || '—'
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset.value),
    })
    const data = await fetchJson(`/api/admin/payments?${params.toString()}`)
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
  <AdminStaffShell title="Платежи">
    <template #headerExtras>
      <div class="head-row">
        <h2 class="section-heading">Журнал платежей</h2>
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

      <AdminTableWrap aria-label="Платежи">
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
                label="Пользователь"
                column-key="user_id"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Сумма"
                column-key="amount"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Мес."
                column-key="months"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Тип"
                column-key="payment_kind"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Провайдер"
                column-key="provider"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Внешний id"
                column-key="external_id"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Создан"
                column-key="created_at"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
            </tr>
          </thead>
          <tbody>
            <tr v-if="sortedRows.length === 0">
              <td colspan="8" class="muted">Нет записей</td>
            </tr>
            <template v-else>
              <tr v-for="row in sortedRows" :key="row.id">
                <td class="num">{{ row.id }}</td>
                <td class="num">{{ row.user_id }}</td>
                <td class="num">{{ formatAmount(row.amount) }}</td>
                <td class="num">{{ row.months }}</td>
                <td>
                  <span class="pill pill-mono" :title="row.payment_kind">{{
                    paymentKindLabel(row.payment_kind)
                  }}</span>
                </td>
                <td>
                  <span class="pill pill-mono" :title="row.provider">{{ row.provider }}</span>
                </td>
                <td class="mono-cell" :title="row.external_id || ''">
                  {{ row.external_id || '—' }}
                </td>
                <td class="date-cell">{{ fmtDate(row.created_at) }}</td>
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
  max-width: 28rem;
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
