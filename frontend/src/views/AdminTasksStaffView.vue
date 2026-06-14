<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
import { useTableSort, appendTableSortParams } from '../utils/adminTableSort.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'

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
  {
    value: 'notify_traffic_low',
    label: 'Трафик: осталось меньше 1 ГБ (notify_traffic_low)',
  },
  {
    value: 'notify_traffic_over',
    label: 'Трафик: лимит исчерпан (notify_traffic_over)',
  },
]

const TASK_STATUS_OPTIONS = [
  { value: 'pending', label: 'pending — в очереди' },
  { value: 'completed', label: 'completed — выполнена' },
  { value: 'failed', label: 'failed — ошибка' },
]

const DELIVERY_CHANNEL_LABELS = {
  telegram: 'Telegram',
  website: 'Сайт',
  email: 'Email',
}

function formatDeliveryChannel(channel) {
  const key = String(channel ?? '').toLowerCase()
  return DELIVERY_CHANNEL_LABELS[key] ?? channel ?? '—'
}

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, type: string, user_id: number, referee_id: number | null, bonus_days: number | null, early_payment_bonus_days: number | null, paid_months: number | null, status: string, created_at: string, done_at: string | null }>>} */
const items = ref([])
const total = ref(0)

const { offset, limit, canPrev, canNext, rangeLabel, prev, next, reset } = useOffsetPagination({
  limit: 200,
  total: () => total.value,
  count: () => items.value.length,
  onChange: () => load(),
})

const modalOpen = ref(false)
const formUserId = ref('')
const formTaskType = ref('notify_sub_expire_0d')
const formRefereeId = ref('')
const formBonusDays = ref('')
const formEarlyPaymentBonusDays = ref('')
const formPaidMonths = ref('')
const createLoading = ref(false)
const createError = ref(null)

const editModalOpen = ref(false)
const editTaskId = ref(null)
const editFormTaskType = ref('notify_sub_expire_0d')
const editFormUserId = ref('')
const editFormRefereeId = ref('')
const editFormBonusDays = ref('')
const editFormEarlyPaymentBonusDays = ref('')
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
  early_payment_bonus_days: (r) =>
    r.early_payment_bonus_days == null ? -1 : Number(r.early_payment_bonus_days),
  paid_months: (r) => (r.paid_months == null ? -1 : Number(r.paid_months)),
  delivery_channel: (r) => String(r.delivery_channel ?? '').toLowerCase(),
  status: (r) => String(r.status ?? '').toLowerCase(),
  created_at: (r) => String(r.created_at ?? ''),
  done_at: (r) => String(r.done_at ?? ''),
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(items, sortAccessors, {
  server: true,
  onChange: () => {
    reset()
    void load()
  },
})

const canDeleteTask = computed(() => getSessionRole() === 'admin')

function fmtDate(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'medium' })
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
      limit: String(limit.value),
      offset: String(offset.value),
    })
    appendTableSortParams(params, sortKey.value, sortDir.value)
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

function openCreateModal() {
  createError.value = null
  formUserId.value = ''
  formTaskType.value = 'notify_sub_expire_0d'
  formRefereeId.value = ''
  formBonusDays.value = ''
  formEarlyPaymentBonusDays.value = ''
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
  const earlyPaymentBonusDays = parseOptionalNonNegInt(formEarlyPaymentBonusDays.value)
  if (earlyPaymentBonusDays === 'invalid') {
    createError.value = 'early_payment_bonus_days: целое число ≥ 0 или пусто.'
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
  if (earlyPaymentBonusDays !== undefined) {
    body.early_payment_bonus_days = earlyPaymentBonusDays
  }
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
  editFormEarlyPaymentBonusDays.value =
    row.early_payment_bonus_days != null ? String(row.early_payment_bonus_days) : ''
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
  const earlyPaymentBonusDays = parseOptionalNonNegInt(editFormEarlyPaymentBonusDays.value)
  if (earlyPaymentBonusDays === 'invalid') {
    editError.value = 'early_payment_bonus_days: целое число ≥ 0 или пусто.'
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
    early_payment_bonus_days:
      earlyPaymentBonusDays === undefined ? null : earlyPaymentBonusDays,
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
      />

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
                label="досроч."
                column-key="early_payment_bonus_days"
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
                label="Канал"
                column-key="delivery_channel"
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
                label="Даты"
                column-key="created_at"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <th class="th-actions">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="sortedRows.length === 0">
              <td colspan="11" class="muted">Нет записей</td>
            </tr>
            <template v-else>
              <tr v-for="row in sortedRows" :key="row.id">
                <td class="num">{{ row.id }}</td>
                <td class="mono-cell">{{ row.type }}</td>
                <td class="owner-user-id-cell num">
                  <span class="owner-user-id-inner">
                    <span>{{ row.user_id }}</span>
                    <AdminHighlightListLink list="users" :highlight="row.user_id" />
                  </span>
                </td>
                <td class="owner-user-id-cell num">
                  <span class="owner-user-id-inner">
                    <template v-if="row.referee_id != null">
                      <span>{{ row.referee_id }}</span>
                      <AdminHighlightListLink list="users" :highlight="row.referee_id" />
                    </template>
                    <template v-else>—</template>
                  </span>
                </td>
                <td class="num">{{ row.bonus_days ?? '—' }}</td>
                <td class="num">{{ row.early_payment_bonus_days ?? '—' }}</td>
                <td class="num">{{ row.paid_months ?? '—' }}</td>
                <td class="mono-cell" :title="row.delivery_channel">
                  {{ formatDeliveryChannel(row.delivery_channel) }}
                </td>
                <td>
                  <span class="pill pill-mono" :title="row.status">{{ row.status }}</span>
                </td>
                <td class="date-cell task-dates-cell">
                  <span class="task-dates-cell__line">{{ fmtDate(row.created_at) }}</span>
                  <span class="task-dates-cell__line">{{
                    row.done_at ? fmtDate(row.done_at) : '—'
                  }}</span>
                </td>
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

    <AppModal v-if="modalOpen" title="Новая задача" :busy="createLoading" @close="closeCreateModal">
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
            placeholder="Пусто — NULL, реферальный бонус ≥ 0"
            autocomplete="off"
          />
        </label>
        <label class="field">
          <span>early_payment_bonus_days (необязательно)</span>
          <input
            v-model="formEarlyPaymentBonusDays"
            type="text"
            inputmode="numeric"
            class="input-like"
            placeholder="Пусто — NULL; бонус за досрочную оплату ≥ 0"
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
    </AppModal>

    <AppModal
      v-if="editModalOpen"
      :title="`Задача #${editTaskId}`"
      :busy="editLoading || editDeleteLoading"
      @close="closeEditModal"
    >
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
          <span>early_payment_bonus_days</span>
          <input
            v-model="editFormEarlyPaymentBonusDays"
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
              class="btn-danger"
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
.task-dates-cell {
  white-space: normal;
  line-height: 1.35;
}
.task-dates-cell__line {
  display: block;
}
.task-dates-cell__line + .task-dates-cell__line {
  margin-top: 0.15rem;
  opacity: 0.92;
}
/* Нейтральный pill для статуса задачи: фон/границу базовый .pill (admin-ui.css) не задаёт. */
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
.btn-compact {
  padding: 0.35rem 0.65rem;
  font-size: 0.8rem;
}
</style>
