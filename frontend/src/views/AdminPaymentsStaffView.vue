<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import StaffUserIdSuggestInput from '../components/StaffUserIdSuggestInput.vue'
import { fetchJson } from '../api/client.js'
import { getSessionRole } from '../auth/session.js'
import { useTableSort } from '../utils/adminTableSort.js'

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
/** @type {import('vue').Ref<Array<{ id: number, user_id: number | null, amount: string | number, months: number, provider: string, payment_kind: string, tribute_webhook: Record<string, unknown> | null, created_at: string }>>} */
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
  tribute_webhook: (r) => JSON.stringify(r.tribute_webhook ?? '').toLowerCase(),
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

function tributeWebhookPreview(webhook) {
  if (!webhook || typeof webhook !== 'object') return '—'
  const name = webhook.name
  if (name) return String(name)
  try {
    const s = JSON.stringify(webhook)
    return s.length > 80 ? `${s.slice(0, 77)}…` : s
  } catch {
    return '—'
  }
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
      createError.value = 'Дубликат платежа (такой webhook уже был). Запись не создана.'
      return
    }
    modalOpen.value = false
    offset.value = 0
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
            v-if="canDeletePayments"
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
                label="Webhook Tribute"
                column-key="tribute_webhook"
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
              <tr v-for="row in sortedRows" :key="row.id">
                <td v-if="canDeletePayments" class="td-select">
                  <input
                    v-model="selectedIds"
                    type="checkbox"
                    :value="row.id"
                  />
                </td>
                <td class="num">{{ row.id }}</td>
                <td class="owner-user-id-cell num">
                  <span class="owner-user-id-inner">
                    <template v-if="row.user_id != null">
                      <span>{{ row.user_id }}</span>
                      <RouterLink
                        class="ref-open-in-list"
                        :to="{
                          path: '/admin/users/analytics',
                          query: { highlight: String(row.user_id) },
                        }"
                        title="Открыть этого пользователя в списке клиентов"
                        aria-label="Перейти к пользователю в таблице клиентов"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" x2="21" y1="14" y2="3" /></svg>
                      </RouterLink>
                    </template>
                    <template v-else>—</template>
                  </span>
                </td>
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
                <td
                  class="mono-cell"
                  :title="row.tribute_webhook ? JSON.stringify(row.tribute_webhook) : ''"
                >
                  {{ tributeWebhookPreview(row.tribute_webhook) }}
                </td>
                <td class="date-cell">{{ fmtDate(row.created_at) }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </AdminTableWrap>
    </template>

    <Teleport to="body">
      <div
        v-if="modalOpen"
        class="modal-backdrop"
        role="presentation"
        @click.self="closeCreateModal"
      >
        <div
          class="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="payments-create-modal-title"
          @click.stop
        >
          <h2 id="payments-create-modal-title" class="modal-title">Новый платёж</h2>
          <form class="modal-form" @submit.prevent="submitCreatePayment">
            <label class="field field-user">
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
        </div>
      </div>
    </Teleport>
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
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 12, 9, 0.55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1rem, 4vh, 2.5rem) 1rem;
  z-index: 50;
}
.modal {
  width: 100%;
  max-width: 520px;
  max-height: min(90dvh, 720px);
  overflow-y: auto;
  padding: 1.35rem 1.45rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg);
}
.modal-title {
  margin: 0 0 0.5rem;
  font-size: 1.1rem;
  color: var(--text-h);
}
.modal-lead {
  margin: 0 0 1rem;
  font-size: 0.8rem;
  color: var(--muted);
  line-height: 1.45;
}
.modal-form .field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}
.modal-form .field > span:first-child {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}
.field-user {
  margin-bottom: 1rem;
}
.field-hint {
  margin: 0.15rem 0 0;
  font-size: 0.76rem;
  font-weight: 400;
  color: var(--muted);
  line-height: 1.35;
}
.input-like {
  font: inherit;
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
}
.input-like:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--text-h) 38%, var(--card-border));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--text-h) 14%, transparent);
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
.form-err {
  margin: 0 0 0.65rem;
  font-size: 0.85rem;
  color: var(--danger);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
  margin-top: 0.5rem;
}
.th-select,
.td-select {
  width: 1%;
  text-align: center;
  white-space: nowrap;
}
.owner-user-id-cell {
  text-align: right;
  vertical-align: middle;
}
.owner-user-id-inner {
  display: inline-flex;
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
</style>
