<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminHighlightListLink from '../components/AdminHighlightListLink.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import AppModal from '../components/AppModal.vue'
import AppPager from '../components/AppPager.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import StaffUserIdSuggestInput from '../components/StaffUserIdSuggestInput.vue'
import StateNote from '../components/StateNote.vue'
import { fetchJson } from '../api/client.js'
import { getSessionRole } from '../auth/session.js'
import { useOffsetPagination } from '../composables/useOffsetPagination.js'
import { useTableSort } from '../utils/adminTableSort.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'

const loading = ref(false)
const error = ref(null)
const deleting = ref(false)
const selectedIds = ref([])
const modalOpen = ref(false)
const createLoading = ref(false)
const createError = ref(null)
const formUserId = ref('')
const formMonths = ref('1')
const formAmountRub = ref('')
const formPaymentKind = ref('one_time')
const formCreatedAt = ref('')
/** @type {import('vue').Ref<Array<{ id: number, user_id: number | null, amount: string | number, net_amount: string | number, months: number, provider: string, payment_kind: string, provider_webhook: Record<string, unknown> | null, created_at: string }>>} */
const items = ref([])
const total = ref(0)
const expandedPaymentId = ref(null)

const { offset, limit, canPrev, canNext, rangeLabel, prev, next, reset } = useOffsetPagination({
  limit: 200,
  total: () => total.value,
  count: () => items.value.length,
  onChange: () => load(),
})

const sortAccessors = {
  id: (r) => Number(r.id) || 0,
  user_id: (r) => Number(r.user_id) || 0,
  amount: (r) => Number(r.amount) || 0,
  net_amount: (r) => Number(r.net_amount ?? r.amount) || 0,
  months: (r) => Number(r.months) || 0,
  provider: (r) => String(r.provider ?? '').toLowerCase(),
  payment_kind: (r) => String(r.payment_kind ?? '').toLowerCase(),
  created_at: (r) => String(r.created_at ?? ''),
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(items, sortAccessors)

const canDeletePayments = computed(() => getSessionRole() === 'admin')
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

function formatAmount(v) {
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtDate(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'medium' })
}

function formatWebhookFull(webhook) {
  if (!webhook || typeof webhook !== 'object') return '—'
  try {
    return JSON.stringify(webhook, null, 2)
  } catch {
    return String(webhook)
  }
}

function togglePaymentRow(row, event) {
  const target = event?.target
  if (target instanceof HTMLElement && target.closest('input, a, button, label')) {
    return
  }
  const id = Number(row.id)
  expandedPaymentId.value = expandedPaymentId.value === id ? null : id
}

function paymentKindLabel(k) {
  const s = String(k ?? '')
  if (s === 'subscription') return 'Подписка'
  if (s === 'one_time') return 'Разовая'
  return s || '—'
}

/** Локальное время браузера → значение для input[type=datetime-local]. */
function toDatetimeLocalValue(isoOrDate) {
  const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function nowDatetimeLocal() {
  return toDatetimeLocalValue(new Date())
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      limit: String(limit.value),
      offset: String(offset.value),
    })
    const data = await fetchJson(`/api/admin/payments?${params.toString()}`)
    items.value = Array.isArray(data?.items) ? data.items : []
    total.value = Number(data?.total) || 0
    expandedPaymentId.value = null
  } catch (e) {
    error.value = e.message || String(e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  createError.value = null
  formUserId.value = ''
  formMonths.value = '1'
  formAmountRub.value = ''
  formPaymentKind.value = 'one_time'
  formCreatedAt.value = nowDatetimeLocal()
  modalOpen.value = true
}

function closeCreateModal() {
  if (createLoading.value) return
  modalOpen.value = false
  createError.value = null
}

function parseFormUserId() {
  const s = String(formUserId.value ?? '').trim()
  if (!s) return NaN
  return Number.parseInt(s, 10)
}

async function deleteSelected() {
  if (!canDeletePayments.value || selectedIds.value.length === 0 || deleting.value) return
  const ok = window.confirm(
    `Удалить выбранные платежи (${selectedIds.value.length})? Действие необратимо.`,
  )
  if (!ok) return
  deleting.value = true
  error.value = null
  try {
    await fetchJson('/api/admin/payments', {
      method: 'DELETE',
      body: JSON.stringify({ ids: selectedIds.value }),
    })
    selectedIds.value = []
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    deleting.value = false
  }
}

async function submitCreatePayment() {
  const uid = parseFormUserId()
  if (!Number.isFinite(uid) || uid < 1) {
    createError.value = 'Укажите корректный User ID (целое число ≥ 1).'
    return
  }
  const months = Number.parseInt(String(formMonths.value ?? '').trim(), 10)
  if (!Number.isFinite(months) || months < 1 || months > 120) {
    createError.value = 'Месяцев: целое число от 1 до 120.'
    return
  }
  const amountRaw = String(formAmountRub.value ?? '').trim().replace(',', '.')
  const amountRub = Number.parseFloat(amountRaw)
  if (!Number.isFinite(amountRub) || amountRub <= 0) {
    createError.value = 'Сумма: положительное число (рубли).'
    return
  }

  const createdTrim = String(formCreatedAt.value ?? '').trim()
  if (!createdTrim) {
    createError.value = 'Укажите дату и время платежа.'
    return
  }
  const createdDate = new Date(createdTrim)
  if (Number.isNaN(createdDate.getTime())) {
    createError.value = 'Некорректная дата и время.'
    return
  }

  const body = {
    user_id: uid,
    months,
    amount_rub: amountRub,
    payment_kind: formPaymentKind.value,
    created_at: createdDate.toISOString(),
  }

  createLoading.value = true
  createError.value = null
  try {
    const res = await fetchJson('/api/admin/payments', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (res?.duplicate) {
      createError.value = 'Дубликат платежа. Запись не создана.'
      return
    }
    modalOpen.value = false
    reset()
    await load()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    createLoading.value = false
  }
}

watch(
  () => rowIdsOnPage.value,
  (ids) => {
    const keep = new Set(ids)
    selectedIds.value = selectedIds.value.filter((id) => keep.has(id))
  },
)

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
          <button type="button" class="btn-primary" @click="openCreateModal">
            Создать платёж
          </button>
          <AppRefreshButton :busy="loading" @click="load" />
        </div>
      </div>
    </template>

    <StateNote v-if="loading && items.length === 0" loading />
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <template v-else>
      <AppPager
        :range-label="rangeLabel"
        :can-prev="canPrev"
        :can-next="canNext"
        :loading="loading"
        @prev="prev"
        @next="next"
      >
        <template v-if="canDeletePayments" #actions>
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

      <AdminTableWrap aria-label="Платежи">
        <table class="admin-table payments-table" :class="{ 'payments-table--no-select': !canDeletePayments }">
          <thead>
            <tr>
              <th v-if="canDeletePayments" class="th-select">
                <input
                  type="checkbox"
                  :checked="allSelectedOnPage"
                  :disabled="rowIdsOnPage.length === 0"
                  @change="toggleSelectAllOnPage"
                />
              </th>
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
                label="После комиссии"
                column-key="net_amount"
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
              <td :colspan="canDeletePayments ? 9 : 8" class="muted">Нет записей</td>
            </tr>
            <template v-else>
              <template v-for="row in sortedRows" :key="row.id">
                <tr
                  class="payment-row"
                  :class="{ 'payment-row--expanded': expandedPaymentId === row.id }"
                  @click="togglePaymentRow(row, $event)"
                >
                  <td v-if="canDeletePayments" class="td-select" @click.stop>
                    <input
                      v-model="selectedIds"
                      type="checkbox"
                      :value="row.id"
                    />
                  </td>
                  <td class="num">{{ row.id }}</td>
                  <td class="owner-user-id-cell num" @click.stop>
                    <span class="owner-user-id-inner">
                      <template v-if="row.user_id != null">
                        <span>{{ row.user_id }}</span>
                        <AdminHighlightListLink list="users" :highlight="row.user_id" />
                      </template>
                      <template v-else>—</template>
                    </span>
                  </td>
                  <td class="num">{{ formatAmount(row.amount) }}</td>
                  <td class="num">{{ formatAmount(row.net_amount ?? row.amount) }}</td>
                  <td class="num">{{ row.months }}</td>
                  <td>
                    <span class="pill pill-mono" :title="row.payment_kind">{{
                      paymentKindLabel(row.payment_kind)
                    }}</span>
                  </td>
                  <td>
                    <span class="pill pill-mono" :title="row.provider">{{ row.provider }}</span>
                  </td>
                  <td class="date-cell">{{ fmtDate(row.created_at) }}</td>
                </tr>
                <tr v-if="expandedPaymentId === row.id" class="payment-detail-row">
                  <td :colspan="canDeletePayments ? 9 : 8">
                    <div class="webhook-detail">
                      <p class="webhook-detail-label">Webhook провайдера</p>
                      <pre class="webhook-json">{{ formatWebhookFull(row.provider_webhook) }}</pre>
                    </div>
                  </td>
                </tr>
              </template>
            </template>
          </tbody>
        </table>
      </AdminTableWrap>
    </template>

    <AppModal v-if="modalOpen" title="Новый платёж" :busy="createLoading" @close="closeCreateModal">
      <form class="modal-form" @submit.prevent="submitCreatePayment">
        <label class="field">
          <span>User ID</span>
          <StaffUserIdSuggestInput
            v-model="formUserId"
            input-id="payments-create-user-id"
            placeholder="Поиск от 3 символов (email, @username, tg id)"
          />
        </label>
        <label class="field">
          <span>Тип оплаты</span>
          <select v-model="formPaymentKind" class="input-like">
            <option value="one_time">Разовая (one_time)</option>
            <option value="subscription">Подписка (subscription)</option>
          </select>
        </label>
        <label class="field">
          <span>Месяцев</span>
          <input
            v-model="formMonths"
            type="text"
            inputmode="numeric"
            class="input-like"
            placeholder="1–120"
            autocomplete="off"
          />
        </label>
        <label class="field">
          <span>Сумма, ₽</span>
          <input
            v-model="formAmountRub"
            type="text"
            inputmode="decimal"
            class="input-like"
            placeholder="Например 199"
            autocomplete="off"
          />
        </label>
        <label class="field">
          <span>Дата и время платежа</span>
          <input
            v-model="formCreatedAt"
            type="datetime-local"
            class="input-like"
            required
          />
          <span class="field-hint">Локальное время браузера; в БД сохраняется как UTC.</span>
        </label>
        <p v-if="createError" class="form-err">{{ createError }}</p>
        <div class="modal-actions">
          <button
            type="button"
            class="btn-secondary"
            :disabled="createLoading"
            @click="closeCreateModal"
          >
            Отмена
          </button>
          <button type="submit" class="btn-primary" :disabled="createLoading">
            {{ createLoading ? 'Создание…' : 'Создать' }}
          </button>
        </div>
      </form>
    </AppModal>
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
.payment-row {
  cursor: pointer;
}
.payment-row:hover td {
  background: color-mix(in srgb, var(--text-h) 4%, transparent);
}
.payment-row--expanded td {
  background: color-mix(in srgb, var(--accent, #58d68d) 8%, transparent);
}
.payment-detail-row td {
  padding: 0;
  border-bottom: 1px solid var(--card-border);
  background: var(--surface);
}
.webhook-detail {
  padding: 0.75rem 1rem 1rem;
}
.webhook-detail-label {
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.webhook-json {
  margin: 0;
  padding: 0.75rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface) 88%, black);
  font-family: ui-monospace, monospace;
  font-size: 0.76rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 24rem;
  overflow: auto;
}
.date-cell {
  white-space: nowrap;
  font-size: 0.8rem;
  color: var(--muted);
}
/* Нейтральный pill: фон/границу базовый .pill (admin-ui.css) не задаёт. */
.pill-mono {
  background: var(--surface);
  border: 1px solid var(--card-border);
  color: var(--muted);
  font-family: ui-monospace, monospace;
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0.02em;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
}
.owner-user-id-cell {
  text-align: right;
}
/* Подсказка под полем даты внутри label (свой отступ, не как у глобального .field-hint). */
.field-hint {
  margin: 0.15rem 0 0;
  font-size: 0.76rem;
  font-weight: 400;
  color: var(--muted);
  line-height: 1.35;
}
.modal-form :deep(.staff-user-suggest-input) {
  min-height: auto;
  padding: 0.5rem 0.65rem 0.5rem 2.45rem;
  border-radius: 10px;
  font-size: inherit;
}
.modal-form :deep(.suggest-input-icon) {
  left: 0.65rem;
}
.modal-form :deep(.suggest-input-icon svg) {
  width: 16px;
  height: 16px;
}
.modal-form :deep(.suggest-panel) {
  z-index: 60;
}
</style>
