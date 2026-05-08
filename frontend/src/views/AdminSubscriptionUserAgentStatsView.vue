<script setup>
import { onMounted, ref } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'

const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ user_agent: string, os: string, connected_users: number, users_with_traffic: number, users_over_100mb: number, active_users_today: number }>>} */
const items = ref([])

const sortAccessors = {
  user_agent: (r) => String(r.user_agent ?? '').toLowerCase(),
  os: (r) => String(r.os ?? '').toLowerCase(),
  connected_users: (r) => Number(r.connected_users) || 0,
  users_with_traffic: (r) => Number(r.users_with_traffic) || 0,
  users_over_100mb: (r) => Number(r.users_over_100mb) || 0,
  active_users_today: (r) => Number(r.active_users_today) || 0,
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(
  items,
  sortAccessors,
)

async function load() {
  loading.value = true
  error.value = null
  try {
    const data = await fetchJson('/api/admin/subscription-devices/stats-by-user-agent')
    const list = Array.isArray(data?.items) ? data.items : []
    items.value = list.map((r) => ({
      user_agent: String(r.user_agent ?? ''),
      os: String(r.os ?? ''),
      connected_users: Number(r.connected_users) || 0,
      users_with_traffic: Number(r.users_with_traffic) || 0,
      users_over_100mb: Number(r.users_over_100mb) || 0,
      active_users_today: Number(r.active_users_today) || 0,
    }))
  } catch (e) {
    error.value = e.message || String(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="Подключения по User-Agent">
    <template #headerExtras>
      <div class="head-row">
        <div class="head-actions">
          <button type="button" class="btn-secondary" :disabled="loading" @click="load">
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </template>

    <p v-if="loading" class="muted">Загрузка…</p>
    <p v-else-if="error" class="msg-err">{{ error }}</p>

    <template v-else>
      <p v-if="sortedRows.length === 0" class="muted">Нет записей устройств с непустым User-Agent.</p>
      <AdminTableWrap v-else aria-label="Статистика по User-Agent">
        <table class="admin-table">
          <thead>
            <tr>
              <AdminSortTh
                label="User-Agent"
                column-key="user_agent"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="ОС"
                column-key="os"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Пользователей с подключением"
                column-key="connected_users"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="С трафиком"
                column-key="users_with_traffic"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label=">100MB"
                column-key="users_over_100mb"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
              <AdminSortTh
                label="Активные сегодня"
                column-key="active_users_today"
                align="right"
                :sort-key="sortKey"
                :sort-dir="sortDir"
                @sort="toggleSort"
              />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in sortedRows"
              :key="`${row.user_agent}\u0000${row.os}`"
            >
              <td class="ua-cell" :title="row.user_agent">
                {{ row.user_agent }}
              </td>
              <td class="os-cell">
                {{ row.os.trim() ? row.os : '—' }}
              </td>
              <td class="num">
                {{ row.connected_users.toLocaleString('ru-RU') }}
              </td>
              <td class="num">
                {{ row.users_with_traffic.toLocaleString('ru-RU') }}
              </td>
              <td class="num">
                {{ row.users_over_100mb.toLocaleString('ru-RU') }}
              </td>
              <td class="num">
                {{ row.active_users_today.toLocaleString('ru-RU') }}
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
  flex: 1 1 18rem;
  margin: 0;
  line-height: 1.45;
}

.head-actions {
  flex: 0 0 auto;
}

.ua-cell {
  max-width: 36rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, monospace;
  font-size: 0.85rem;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
