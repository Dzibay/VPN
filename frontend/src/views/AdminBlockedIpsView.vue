<script setup>
import { onMounted, ref } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import StateNote from '../components/StateNote.vue'
import { fetchJson } from '../api/client.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'

const rows = ref([])
const loading = ref(false)
const error = ref(null)
const saving = ref(false)
const saveError = ref(null)

const formIp = ref('')
const formNote = ref('')

function fmtDate(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'medium' })
}

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await fetchJson('/api/staff/blocked-ips')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function addBlockedIp() {
  saveError.value = null
  const ip = String(formIp.value ?? '').trim()
  if (!ip) {
    saveError.value = 'Укажите IP-адрес'
    return
  }
  saving.value = true
  try {
    const note = String(formNote.value ?? '').trim()
    await fetchJson('/api/staff/blocked-ips', {
      method: 'POST',
      body: JSON.stringify({ ip, note: note || null }),
    })
    formIp.value = ''
    formNote.value = ''
    await load()
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

async function removeBlockedIp(id) {
  const ok = window.confirm('Убрать IP из блокировки?')
  if (!ok) return
  saving.value = true
  saveError.value = null
  try {
    await fetchJson(`/api/staff/blocked-ips/${id}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="Блокировка IP">
    <template #headerExtras>
      <AppRefreshButton :loading="loading" @click="load" />
    </template>

    <form class="add-form glass" @submit.prevent="addBlockedIp">
      <label class="af-field">
        <span class="af-label">IP</span>
        <input
          v-model="formIp"
          type="text"
          class="af-input af-input--ip"
          autocomplete="off"
          placeholder="203.0.113.10"
          required
        />
      </label>
      <label class="af-field af-field-grow">
        <span class="af-label">Комментарий</span>
        <input
          v-model="formNote"
          type="text"
          class="af-input"
          maxlength="500"
          autocomplete="off"
          placeholder="необязательно"
        />
      </label>
      <button type="submit" class="btn-secondary" :disabled="saving || loading">
        {{ saving ? 'Сохранение…' : 'Заблокировать' }}
      </button>
    </form>

    <p v-if="saveError" class="msg-err">{{ saveError }}</p>

    <StateNote v-if="loading" loading />
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <AdminTableWrap v-else aria-label="Заблокированные IP">
      <table class="admin-table blocked-ip-table">
        <thead>
          <tr>
            <th>IP</th>
            <th>Комментарий</th>
            <th>Добавлен</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-if="rows.length === 0">
            <td colspan="4" class="muted center">Список пуст</td>
          </tr>
          <tr v-for="row in rows" :key="row.id">
            <td class="mono">{{ row.ip }}</td>
            <td>{{ row.note || '—' }}</td>
            <td class="mono nowrap">{{ fmtDate(row.created_at) }}</td>
            <td class="actions">
              <button
                type="button"
                class="btn-row-remove"
                title="Убрать IP из блокировки"
                :disabled="saving"
                @click="removeBlockedIp(row.id)"
              >
                <span class="btn-row-remove__icon" aria-hidden="true">✕</span>
                <span>Удалить</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </AdminStaffShell>
</template>

<style scoped>
.hint {
  margin: 0 0 1rem;
  font-size: 0.88rem;
  line-height: 1.45;
}

.add-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem 1rem;
  padding: 0.85rem 1rem;
  border-radius: 14px;
  margin-bottom: 1rem;
}

.af-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.af-field-grow {
  flex: 1 1 14rem;
  min-width: 10rem;
}

.af-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
}

.af-input {
  min-height: 2rem;
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text);
}

.af-input--ip {
  width: 11rem;
  font-family: ui-monospace, monospace;
}

.blocked-ip-table {
  font-size: 0.88rem;
}

.actions {
  text-align: right;
  white-space: nowrap;
  width: 1%;
}

.btn-row-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  margin: 0;
  padding: 0.3rem 0.65rem;
  border-radius: 8px;
  border: 1px solid rgba(248, 113, 113, 0.42);
  background: rgba(248, 113, 113, 0.08);
  color: var(--danger, #dc2626);
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.2;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease,
    transform 0.12s ease;
}

.btn-row-remove__icon {
  font-size: 0.72rem;
  line-height: 1;
  opacity: 0.9;
}

.btn-row-remove:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.16);
  border-color: var(--danger, #dc2626);
}

.btn-row-remove:active:not(:disabled) {
  transform: translateY(1px);
}

.btn-row-remove:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.btn-row-remove:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.center {
  text-align: center;
}

.mono {
  font-family: ui-monospace, monospace;
}

.nowrap {
  white-space: nowrap;
}

.msg-err {
  color: var(--danger, #c0392b);
  margin: 0 0 1rem;
}
</style>
