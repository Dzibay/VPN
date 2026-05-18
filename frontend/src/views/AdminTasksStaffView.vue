<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import StaffUserIdSuggestInput from '../components/StaffUserIdSuggestInput.vue'
import { fetchJson } from '../api/client.js'
import { getSessionRole } from '../auth/session.js'
import { useTableSort } from '../utils/adminTableSort.js'

const TASK_TYPE_OPTIONS = [
  { value: 'notify_ref_reg', label: 'Регистрация по реф. ссылке (notify_ref_reg)' },
  { value: 'notify_ref_pay', label: 'Оплата рефералом (notify_ref_pay)' },
  { value: 'notify_payment', label: 'Оплата подписки (notify_payment)' },
  {
    value: 'notify_sub_expire_3d',
    label: 'Подписка: за 3 дня до конца (notify_sub_expire_3d)',
  },
  {
    value: 'notify_sub_expire_1d',
    label: 'Подписка: за 1 день до конца (notify_sub_expire_1d)',
  },
  {
    value: 'notify_sub_expire_0d',
    label: 'Подписка: последний день (notify_sub_expire_0d)',
  },
  { value: 'notify_sub_expire', label: 'Подписка уже истекла (notify_sub_expire)' },
  {
    value: 'notify_sub_expired_7d',
    label: 'Подписка истекла 7 дней назад (notify_sub_expired_7d)',
  },
  {
    value: 'notify_reg_1h_has_traffic',
    label: 'Через ~1 ч после регистрации: есть трафик (notify_reg_1h_has_traffic)',
  },
  {
    value: 'notify_reg_1h_no_traffic',
    label: 'Через ~1 ч после регистрации: нет трафика (notify_reg_1h_no_traffic)',
  },
]

const TASK_STATUS_OPTIONS = [
  { value: 'pending', label: 'pending — в очереди' },
  { value: 'completed', label: 'completed — выполнена' },
  { value: 'failed', label: 'failed — ошибка' },
]

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, type: string, user_id: number, referee_id: number | null, bonus_days: number | null, paid_months: number | null, status: string, created_at: string, done_at: string | null }>>} */
const items = ref([])
const total = ref(0)
const limit = 200
const offset = ref(0)

const modalOpen = ref(false)
const formUserId = ref('')
const formTaskType = ref('notify_sub_expire_0d')
const formRefereeId = ref('')
const formBonusDays = ref('')
const formPaidMonths = ref('')
const createLoading = ref(false)
const createError = ref(null)

const editModalOpen = ref(false)
const editTaskId = ref(null)
const editFormTaskType = ref('notify_sub_expire_0d')
const editFormUserId = ref('')
const editFormRefereeId = ref('')
const editFormBonusDays = ref('')
const editFormPaidMonths = ref('')
const editFormStatus = ref('pending')
const editFormDoneAt = ref('')
const editLoading = ref(false)
const editDeleteLoading = ref(false)
const editError = ref(null)

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
const canDeleteTask = computed(() => getSessionRole() === 'admin')

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

/** ISO с сервера → значение для input[type=datetime-local] (локальное время браузера). */
function toDatetimeLocalValue(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
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

function openCreateModal() {
  createError.value = null
  formUserId.value = ''
  formTaskType.value = 'notify_sub_expire_0d'
  formRefereeId.value = ''
  formBonusDays.value = ''
  formPaidMonths.value = ''
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

/** @returns {number | undefined | 'invalid'} */
function parseOptionalPositiveInt(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return undefined
  const n = Number.parseInt(s, 10)
  if (!Number.isFinite(n) || n < 1) return 'invalid'
  return n
}

/** @returns {number | undefined | 'invalid'} */
function parseOptionalNonNegInt(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return undefined
  const n = Number.parseInt(s, 10)
  if (!Number.isFinite(n) || n < 0) return 'invalid'
  return n
}

async function submitCreateTask() {
  const uid = parseFormUserId()
  if (!Number.isFinite(uid) || uid < 1) {
    createError.value = 'Укажите корректный User ID (целое число ≥ 1).'
    return
  }
  const refereeId = parseOptionalPositiveInt(formRefereeId.value)
  if (refereeId === 'invalid') {
    createError.value = 'referee_id: целое число ≥ 1 или пусто.'
    return
  }
  const bonusDays = parseOptionalNonNegInt(formBonusDays.value)
  if (bonusDays === 'invalid') {
    createError.value = 'bonus_days: целое число ≥ 0 или пусто.'
    return
  }
  const paidMonths = parseOptionalPositiveInt(formPaidMonths.value)
  if (paidMonths === 'invalid') {
    createError.value = 'paid_months: целое число ≥ 1 или пусто.'
    return
  }

  const body = {
    user_id: uid,
    task_type: formTaskType.value,
  }
  if (refereeId !== undefined) body.referee_id = refereeId
  if (bonusDays !== undefined) body.bonus_days = bonusDays
  if (paidMonths !== undefined) body.paid_months = paidMonths

  createLoading.value = true
  createError.value = null
  try {
    await fetchJson('/api/admin/tasks', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    modalOpen.value = false
    await load()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    createLoading.value = false
  }
}

function openEditModal(row) {
  editError.value = null
  editTaskId.value = row.id
  editFormTaskType.value = row.type
  editFormUserId.value = String(row.user_id)
  editFormRefereeId.value = row.referee_id != null ? String(row.referee_id) : ''
  editFormBonusDays.value = row.bonus_days != null ? String(row.bonus_days) : ''
  editFormPaidMonths.value = row.paid_months != null ? String(row.paid_months) : ''
  editFormStatus.value = row.status
  editFormDoneAt.value = toDatetimeLocalValue(row.done_at)
  editModalOpen.value = true
}

function closeEditModal() {
  if (editLoading.value || editDeleteLoading.value) return
  editModalOpen.value = false
  editError.value = null
  editTaskId.value = null
}

async function submitEditTask() {
  if (editTaskId.value == null || editDeleteLoading.value) return
  const uid = Number.parseInt(String(editFormUserId.value ?? '').trim(), 10)
  if (!Number.isFinite(uid) || uid < 1) {
    editError.value = 'User ID: целое число ≥ 1.'
    return
  }
  const refereeId = parseOptionalPositiveInt(editFormRefereeId.value)
  if (refereeId === 'invalid') {
    editError.value = 'referee_id: целое число ≥ 1 или пусто.'
    return
  }
  const bonusDays = parseOptionalNonNegInt(editFormBonusDays.value)
  if (bonusDays === 'invalid') {
    editError.value = 'bonus_days: целое число ≥ 0 или пусто.'
    return
  }
  const paidMonths = parseOptionalPositiveInt(editFormPaidMonths.value)
  if (paidMonths === 'invalid') {
    editError.value = 'paid_months: целое число ≥ 1 или пусто.'
    return
  }

  const doneTrim = String(editFormDoneAt.value ?? '').trim()

  const body = {
    task_type: editFormTaskType.value,
    user_id: uid,
    referee_id: refereeId === undefined ? null : refereeId,
    bonus_days: bonusDays === undefined ? null : bonusDays,
    paid_months: paidMonths === undefined ? null : paidMonths,
    status: editFormStatus.value,
  }
  if (doneTrim) {
    const d = new Date(doneTrim)
    if (Number.isNaN(d.getTime())) {
      editError.value = 'Некорректная дата/время в «Завершена».'
      return
    }
    body.done_at = d.toISOString()
  }

  editLoading.value = true
  editError.value = null
  try {
    await fetchJson(`/api/admin/tasks/${editTaskId.value}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    editModalOpen.value = false
    editTaskId.value = null
    await load()
  } catch (e) {
    editError.value = e.message || String(e)
  } finally {
    editLoading.value = false
  }
}

async function deleteEditTask() {
  if (!canDeleteTask.value || editTaskId.value == null || editLoading.value) return
  const id = editTaskId.value
  const ok = window.confirm(`Удалить задачу #${id}? Действие необратимо.`)
  if (!ok) return
  editDeleteLoading.value = true
  editError.value = null
  try {
    await fetchJson(`/api/admin/tasks/${id}`, { method: 'DELETE' })
    editModalOpen.value = false
    editTaskId.value = null
    await load()
  } catch (e) {
    editError.value = e.message || String(e)
  } finally {
    editDeleteLoading.value = false
  }
}

function editTaskIdFromQuery() {
  const raw = route.query.edit_task_id
  const s = raw == null ? '' : Array.isArray(raw) ? raw[0] : String(raw)
  const n = Number.parseInt(s, 10)
  return Number.isFinite(n) && n >= 1 ? n : null
}

async function tryOpenTaskFromQuery() {
  const tid = editTaskIdFromQuery()
  if (tid == null || editModalOpen.value) return
  let row = items.value.find((r) => r.id === tid)
  if (!row) {
    try {
      row = await fetchJson(`/api/admin/tasks/${tid}`)
    } catch {
      return
    }
  }
  openEditModal(row)
  const q = { ...route.query }
  delete q.edit_task_id
  await router.replace({ path: route.path, query: q })
}

watch(
  () =>
    `${editTaskIdFromQuery() ?? ''}:${loading.value}:${items.value.map((r) => r.id).join(',')}`,
  async () => {
    if (loading.value) return
    await nextTick()
    await tryOpenTaskFromQuery()
  },
  { flush: 'post' },
)

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
          <button type="button" class="btn-primary" @click="openCreateModal">
            Создать задачу
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
              <th class="th-actions">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="sortedRows.length === 0">
              <td colspan="10" class="muted">Нет записей</td>
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
                <td class="td-actions">
                  <button
                    type="button"
                    class="btn-secondary btn-compact"
                    @click="openEditModal(row)"
                  >
                    Изменить
                  </button>
                </td>
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
          aria-labelledby="tasks-create-modal-title"
          @click.stop
        >
          <h2 id="tasks-create-modal-title" class="modal-title">Новая задача</h2>
          <form class="modal-form" @submit.prevent="submitCreateTask">
            <label class="field">
              <span>User ID</span>
              <StaffUserIdSuggestInput
                v-model="formUserId"
                input-id="tasks-create-user-id"
                placeholder="Поиск от 3 символов (email, @username, tg id)"
              />
            </label>
            <label class="field">
              <span>Тип задачи</span>
              <select v-model="formTaskType" class="input-like">
                <option v-for="opt in TASK_TYPE_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>referee_id (необязательно)</span>
              <StaffUserIdSuggestInput
                v-model="formRefereeId"
                input-id="tasks-create-referee-id"
                placeholder="Поиск от 3 символов (email, @username, tg id)"
              />
            </label>
            <p class="field-hint">Для notify_ref_reg / notify_ref_pay — второй пользователь в сценарии.</p>
            <label class="field">
              <span>bonus_days (необязательно)</span>
              <input
                v-model="formBonusDays"
                type="text"
                inputmode="numeric"
                class="input-like"
                placeholder="Пусто — NULL, целое ≥ 0"
                autocomplete="off"
              />
            </label>
            <label class="field">
              <span>paid_months (необязательно)</span>
              <input
                v-model="formPaidMonths"
                type="text"
                inputmode="numeric"
                class="input-like"
                placeholder="Пусто — NULL; для notify_payment ≥ 1"
                autocomplete="off"
              />
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

    <Teleport to="body">
      <div
        v-if="editModalOpen"
        class="modal-backdrop modal-backdrop-top"
        role="presentation"
        @click.self="closeEditModal"
      >
        <div
          class="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="tasks-edit-modal-title"
          @click.stop
        >
          <h2 id="tasks-edit-modal-title" class="modal-title">
            Задача #{{ editTaskId }}
          </h2>
          <form class="modal-form" @submit.prevent="submitEditTask">
            <label class="field">
              <span>Тип задачи</span>
              <select v-model="editFormTaskType" class="input-like">
                <option v-for="opt in TASK_TYPE_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>User ID</span>
              <StaffUserIdSuggestInput
                v-model="editFormUserId"
                input-id="tasks-edit-user-id"
                placeholder="Поиск от 3 символов (email, @username, tg id)"
              />
            </label>
            <label class="field">
              <span>referee_id</span>
              <StaffUserIdSuggestInput
                v-model="editFormRefereeId"
                input-id="tasks-edit-referee-id"
                placeholder="Поиск от 3 символов (email, @username, tg id)"
              />
            </label>
            <label class="field">
              <span>bonus_days</span>
              <input
                v-model="editFormBonusDays"
                type="text"
                inputmode="numeric"
                class="input-like"
                placeholder="Пусто — NULL"
                autocomplete="off"
              />
            </label>
            <label class="field">
              <span>paid_months</span>
              <input
                v-model="editFormPaidMonths"
                type="text"
                inputmode="numeric"
                class="input-like"
                placeholder="Пусто — NULL"
                autocomplete="off"
              />
            </label>
            <label class="field">
              <span>Статус</span>
              <select v-model="editFormStatus" class="input-like">
                <option v-for="opt in TASK_STATUS_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>Завершена (локальное время)</span>
              <input v-model="editFormDoneAt" type="datetime-local" class="input-like" />
            </label>
            <p v-if="editError" class="form-err">{{ editError }}</p>
            <div class="modal-actions modal-actions-split">
              <div class="modal-actions-left">
                <button
                  v-if="canDeleteTask"
                  type="button"
                  class="btn-danger-modal"
                  :disabled="editLoading || editDeleteLoading"
                  @click="deleteEditTask"
                >
                  {{ editDeleteLoading ? 'Удаление…' : 'Удалить' }}
                </button>
              </div>
              <div class="modal-actions-right">
                <button
                  type="button"
                  class="btn-secondary"
                  :disabled="editLoading || editDeleteLoading"
                  @click="closeEditModal"
                >
                  Отмена
                </button>
                <button type="submit" class="btn-primary" :disabled="editLoading || editDeleteLoading">
                  {{ editLoading ? 'Сохранение…' : 'Сохранить' }}
                </button>
              </div>
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
.th-actions {
  width: 1%;
  text-align: right;
  white-space: nowrap;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
}
.td-actions {
  text-align: right;
  vertical-align: middle;
}
.btn-compact {
  padding: 0.35rem 0.65rem;
  font-size: 0.8rem;
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
.modal-backdrop-top {
  z-index: 55;
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
.mono-inline {
  font-family: ui-monospace, monospace;
  font-size: 0.88em;
}
.field-hint {
  margin: -0.55rem 0 0.65rem;
  font-size: 0.76rem;
  color: var(--muted);
  line-height: 1.35;
}
.modal-form .field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}
.modal-form .field > span {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}
.input-like {
  font: inherit;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
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
.modal-actions-split {
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.modal-actions-right {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.btn-danger-modal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-lg, 10px);
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
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.08));
}
.btn-danger-modal:hover:not(:disabled) {
  filter: brightness(1.06);
}
.btn-danger-modal:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
