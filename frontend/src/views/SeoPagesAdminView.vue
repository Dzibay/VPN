<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import { fetchJson, sitePublicUrl } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'

/** @type {import('vue').Ref<Array<{ id: number, path: string, title: string, views_count: number, sort_order: number }>>} */
const rows = ref([])
const loading = ref(false)
const error = ref(null)

const totalViews = computed(() =>
  rows.value.reduce((sum, row) => sum + (Number(row.views_count) || 0), 0),
)

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await fetchJson('/api/seo-pages')
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

function pageUrl(path) {
  const base = sitePublicUrl().replace(/\/$/, '')
  const p = String(path || '/')
  return `${base}${p.startsWith('/') ? p : `/${p}`}`
}

function fmtViews(n) {
  return new Intl.NumberFormat('ru-RU').format(Number(n) || 0)
}

const sortAccessors = {
  sort_order: (r) => Number(r.sort_order) || 0,
  title: (r) => String(r.title || '').toLowerCase(),
  path: (r) => String(r.path || '').toLowerCase(),
  views_count: (r) => Number(r.views_count) || 0,
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(rows, sortAccessors)

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminStaffShell title="SEO-страницы">
    <template #headerExtras>
      <div class="head-row">
        <p class="summary">
          Всего переходов: <strong>{{ fmtViews(totalViews) }}</strong>
          · страниц: <strong>{{ rows.length }}</strong>
        </p>
        <AppRefreshButton
          :busy="loading"
          @click="load"
        />
      </div>
    </template>

    <p
      v-if="error"
      class="error"
      role="alert"
    >
      {{ error }}
    </p>

    <AdminTableWrap aria-label="Таблица SEO-страниц">
      <table class="admin-table">
        <thead>
          <tr>
            <AdminSortTh
              label="№"
              column-key="sort_order"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Страница"
              column-key="title"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="URL"
              column-key="path"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Переходы"
              column-key="views_count"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td
              colspan="4"
              class="muted"
            >
              Загрузка…
            </td>
          </tr>
          <tr v-else-if="sortedRows.length === 0">
            <td
              colspan="4"
              class="muted"
            >
              SEO-страницы не найдены
            </td>
          </tr>
          <tr
            v-for="row in sortedRows"
            :key="row.id"
          >
            <td>{{ row.sort_order }}</td>
            <td>{{ row.title }}</td>
            <td>
              <a
                class="path-link"
                :href="pageUrl(row.path)"
                target="_blank"
                rel="noopener noreferrer"
              >
                {{ row.path }}
              </a>
            </td>
            <td class="num">
              {{ fmtViews(row.views_count) }}
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </AdminStaffShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.summary {
  margin: 0;
  color: var(--muted);
}

.summary strong {
  color: var(--text-h);
}

.error {
  color: #f87171;
  margin: 0 0 1rem;
}

.path-link {
  color: var(--accent);
  text-decoration: none;
  word-break: break-all;
}

.path-link:hover {
  text-decoration: underline;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.muted {
  color: var(--muted);
  text-align: center;
  padding: 1.25rem;
}
</style>
