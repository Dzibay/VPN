<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { fetchJson, subscriptionPublicUrl } from '../api/client.js'

const route = useRoute()

const section = computed(() =>
  route.query.tab === 'servers' ? 'servers' : 'users',
)

const users = ref([])
const usersCount = ref(null)
const usersLoading = ref(false)
const usersError = ref(null)

const servers = ref([])
const serversCount = ref(null)
const serversLoading = ref(false)
const serversError = ref(null)

const modalOpen = ref(false)
const creating = ref(false)
const createError = ref(null)

const formTelegramId = ref('')
const formSubUntil = ref('')

const formName = ref('')
const formHost = ref('')
const formPort = ref(443)
const formCountry = ref('')
const formActive = ref(true)
/** Override label instance в Prometheus; пусто — host + порт из PROVISION_NODE_EXPORTER_PORT API (часто 9100) */
const formPrometheusInstance = ref('')
const formNetworkCapMbps = ref('')
const formRealityDest = ref('')
const formRealityServerNames = ref('')
const formRealityFingerprint = ref('')
const formVlessFlow = ref('')
const formRealityShortId = ref('')
const formVlessUuid = ref('')
const formRealityPublicKey = ref('')
const formRealityPrivateKey = ref('')
/** Вкладки модалки сервера: общие параметры | VLESS+REALITY */
const serverModalTab = ref('general')
/** null — создание сервера; иначе id для PATCH */
const editingServerId = ref(null)

const DEFAULT_REALITY_DEST = 'www.amazon.com:443'
const DEFAULT_REALITY_SERVER_NAMES = 'www.amazon.com,amazon.com'
const DEFAULT_REALITY_FINGERPRINT = 'chrome'
const DEFAULT_VLESS_FLOW = 'xtls-rprx-vision'

function randomShortIdHex() {
  const a = new Uint8Array(4)
  crypto.getRandomValues(a)
  return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
}

function applyDefaultProxyFields() {
  formRealityDest.value = DEFAULT_REALITY_DEST
  formRealityServerNames.value = DEFAULT_REALITY_SERVER_NAMES
  formRealityFingerprint.value = DEFAULT_REALITY_FINGERPRINT
  formVlessFlow.value = DEFAULT_VLESS_FLOW
  formRealityShortId.value = randomShortIdHex()
  formRealityPrivateKey.value = ''
}
const serverProvisioningId = ref(null)
const serverProvisionResetId = ref(null)
const serverReconcileId = ref(null)
const serverXrayId = ref(null)
const serverPrometheusId = ref(null)
const serverCleanupId = ref(null)
const provisionActionError = ref(null)

const loadSyncLoading = ref(false)
const loadSyncError = ref(null)
const loadSyncOk = ref(null)

/** Какая строка серверов: открыто выпадающее меню действий */
const serverMenuOpenId = ref(null)
/** Кнопка-триггер (для fixed-позиции панели в Teleport) */
const serverMenuAnchorEl = ref(null)
const serverMenuPanelEl = ref(null)
const serverMenuFloatStyle = ref({})

const serverMenuTarget = computed(() => {
  const id = serverMenuOpenId.value
  if (id == null) return null
  return servers.value.find((x) => x.id === id) ?? null
})

async function updateServerMenuPosition() {
  const btn = serverMenuAnchorEl.value
  if (!(btn instanceof HTMLElement) || serverMenuOpenId.value == null) return
  await nextTick()
  const r = btn.getBoundingClientRect()
  const gap = 6
  const menuMin = 216
  const w = Math.max(menuMin, r.width)
  let left = r.right - w
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8))
  const h = serverMenuPanelEl.value?.offsetHeight ?? 300
  let top = r.bottom + gap
  if (top + h > window.innerHeight - 8) {
    top = Math.max(8, r.top - gap - h)
  }
  serverMenuFloatStyle.value = {
    position: 'fixed',
    top: `${top}px`,
    left: `${left}px`,
    minWidth: `${w}px`,
    zIndex: 2000,
  }
}

function closeServerMenu() {
  serverMenuOpenId.value = null
  serverMenuAnchorEl.value = null
}

/**
 * Действие из Teleport-меню: сначала снимаем текущий server с computed, потом закрываем меню —
 * иначе после closeServerMenu() serverMenuTarget уже null.
 */
function withOpenServerMenu(fn) {
  const s = serverMenuTarget.value
  closeServerMenu()
  if (s) fn(s)
}

function toggleServerMenu(s, e) {
  const id = s.id
  if (serverMenuOpenId.value === id) {
    closeServerMenu()
    return
  }
  serverMenuAnchorEl.value =
    e?.currentTarget instanceof HTMLElement ? e.currentTarget : null
  serverMenuOpenId.value = id
  requestAnimationFrame(() => {
    void updateServerMenuPosition()
  })
}

function onServerMenuDocClick(ev) {
  if (!(ev.target instanceof Node)) return
  if (
    ev.target.closest('.server-row-dropdown') ||
    ev.target.closest('.server-actions-dropdown-panel')
  ) {
    return
  }
  closeServerMenu()
}

function onServerMenuEscape(e) {
  if (e.key === 'Escape') closeServerMenu()
}

function onServerMenuScrollResize() {
  if (serverMenuOpenId.value != null) void updateServerMenuPosition()
}

onMounted(() => {
  document.addEventListener('click', onServerMenuDocClick)
  document.addEventListener('keydown', onServerMenuEscape)
  document.addEventListener('scroll', onServerMenuScrollResize, true)
  window.addEventListener('resize', onServerMenuScrollResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onServerMenuDocClick)
  document.removeEventListener('keydown', onServerMenuEscape)
  document.removeEventListener('scroll', onServerMenuScrollResize, true)
  window.removeEventListener('resize', onServerMenuScrollResize)
})

watch(serverMenuTarget, (s) => {
  if (serverMenuOpenId.value != null && s == null) closeServerMenu()
})

const loading = computed(() =>
  section.value === 'users' ? usersLoading.value : serversLoading.value,
)
const error = computed(() =>
  section.value === 'users' ? usersError.value : serversError.value,
)

async function loadUsers() {
  usersLoading.value = true
  usersError.value = null
  try {
    const [list, countRes] = await Promise.all([
      fetchJson('/api/users'),
      fetchJson('/api/users/count'),
    ])
    users.value = list
    usersCount.value = countRes.users_count
  } catch (e) {
    usersError.value = e.message || String(e)
    users.value = []
    usersCount.value = null
  } finally {
    usersLoading.value = false
  }
}

async function loadServers() {
  serversLoading.value = true
  serversError.value = null
  try {
    const [list, countRes] = await Promise.all([
      fetchJson('/api/servers'),
      fetchJson('/api/servers/count'),
    ])
    servers.value = list
    serversCount.value = countRes.servers_count
  } catch (e) {
    serversError.value = e.message || String(e)
    servers.value = []
    serversCount.value = null
  } finally {
    serversLoading.value = false
  }
}

async function syncServerLoadFromPrometheus() {
  loadSyncLoading.value = true
  loadSyncError.value = null
  loadSyncOk.value = null
  try {
    const res = await fetchJson('/api/servers/sync-load-from-prometheus', {
      method: 'POST',
    })
    loadSyncOk.value = `Загрузка обновлена: удачно ${res.updated}, с ошибками ${res.failed}.`
    await loadServers()
  } catch (e) {
    loadSyncError.value = e.message || String(e)
  } finally {
    loadSyncLoading.value = false
  }
}

watch(
  section,
  (s) => {
    modalOpen.value = false
    editingServerId.value = null
    serverModalTab.value = 'general'
    closeServerMenu()
    loadSyncOk.value = null
    loadSyncError.value = null
    if (s === 'users') loadUsers()
    else loadServers()
  },
  { immediate: true },
)

function openModal() {
  createError.value = null
  editingServerId.value = null
  serverModalTab.value = 'general'
  if (section.value === 'users') {
    formTelegramId.value = ''
    formSubUntil.value = ''
  } else {
    formName.value = ''
    formHost.value = ''
    formPort.value = 443
    formCountry.value = ''
    formActive.value = true
    formPrometheusInstance.value = ''
    formNetworkCapMbps.value = ''
    formVlessUuid.value = ''
    formRealityPublicKey.value = ''
    applyDefaultProxyFields()
  }
  modalOpen.value = true
}

function openEditServer(s) {
  createError.value = null
  editingServerId.value = s.id
  serverModalTab.value = 'general'
  formName.value = s.name ?? ''
  formHost.value = s.host
  formPort.value = s.port
  formCountry.value = s.country ?? ''
  formActive.value = Boolean(s.is_active)
  formPrometheusInstance.value =
    (s.prometheus_instance && String(s.prometheus_instance).trim()) || ''
  formNetworkCapMbps.value =
    s.network_cap_mbps != null ? String(s.network_cap_mbps) : ''
  formRealityDest.value =
    (s.reality_dest && String(s.reality_dest).trim()) || DEFAULT_REALITY_DEST
  formRealityServerNames.value =
    (s.reality_server_names && String(s.reality_server_names).trim()) ||
    DEFAULT_REALITY_SERVER_NAMES
  formRealityFingerprint.value =
    (s.reality_fingerprint && String(s.reality_fingerprint).trim()) ||
    DEFAULT_REALITY_FINGERPRINT
  formVlessFlow.value =
    (s.vless_flow && String(s.vless_flow).trim()) || DEFAULT_VLESS_FLOW
  formRealityShortId.value =
    (s.reality_short_id && String(s.reality_short_id).trim()) ||
    randomShortIdHex()
  formVlessUuid.value = s.vless_uuid ?? ''
  formRealityPublicKey.value = s.reality_public_key ?? ''
  formRealityPrivateKey.value = s.reality_private_key ?? ''
  modalOpen.value = true
}

function closeModal() {
  if (creating.value) return
  modalOpen.value = false
  editingServerId.value = null
  serverModalTab.value = 'general'
}

function subscriptionDateOrNull(dateStr) {
  if (!dateStr || !String(dateStr).trim()) return null
  const s = String(dateStr).trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
  return s
}

function normalizeTelegramId(raw) {
  let t = String(raw ?? '').trim()
  if (t.startsWith('@')) t = t.slice(1).trim()
  return t === '' ? null : `@${t}`
}

function normalizePort(raw) {
  const n = Number.parseInt(String(raw ?? ''), 10)
  if (Number.isNaN(n)) return 443
  return Math.min(65535, Math.max(1, n))
}

/** Тариф Мбит/с: пусто → null; иначе 1…1e6 */
function normalizeNetworkCapMbps(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return null
  const n = Number.parseInt(s, 10)
  if (Number.isNaN(n) || n < 1) return null
  return Math.min(1_000_000, n)
}

async function submitCreateUser() {
  creating.value = true
  createError.value = null
  try {
    await fetchJson('/api/users', {
      method: 'POST',
      body: JSON.stringify({
        telegram_id: normalizeTelegramId(formTelegramId.value),
        subscription_until: subscriptionDateOrNull(formSubUntil.value),
      }),
    })
    modalOpen.value = false
    await loadUsers()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

async function submitSaveServer() {
  creating.value = true
  createError.value = null
  try {
    const country = String(formCountry.value ?? '').trim()
    if (!country) {
      createError.value = 'Укажите страну'
      serverModalTab.value = 'general'
      return
    }
    if (editingServerId.value == null) {
      const h = String(formHost.value ?? '').trim()
      if (!h) {
        createError.value = 'Укажите host'
        serverModalTab.value = 'general'
        return
      }
    }
    if (editingServerId.value != null) {
      const patch = {
        name: String(formName.value ?? '').trim() || null,
        country,
        is_active: formActive.value,
      }
      const rd = String(formRealityDest.value ?? '').trim()
      if (rd) patch.reality_dest = rd
      const rsn = String(formRealityServerNames.value ?? '').trim()
      if (rsn) patch.reality_server_names = rsn
      const rfp = String(formRealityFingerprint.value ?? '').trim()
      if (rfp) patch.reality_fingerprint = rfp
      const vf = String(formVlessFlow.value ?? '').trim()
      if (vf) patch.vless_flow = vf
      const rsid = String(formRealityShortId.value ?? '').trim().toLowerCase()
      if (rsid) patch.reality_short_id = rsid
      const rpk = String(formRealityPrivateKey.value ?? '').trim()
      if (rpk) patch.reality_private_key = rpk
      const pinst = String(formPrometheusInstance.value ?? '').trim()
      patch.prometheus_instance = pinst || null
      patch.network_cap_mbps = normalizeNetworkCapMbps(formNetworkCapMbps.value)
      await fetchJson(`/api/servers/${editingServerId.value}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
    } else {
      const createBody = {
        name: String(formName.value ?? '').trim() || null,
        host: String(formHost.value ?? '').trim(),
        port: normalizePort(formPort.value),
        country,
        is_active: formActive.value,
      }
      const rd = String(formRealityDest.value ?? '').trim()
      if (rd) createBody.reality_dest = rd
      const rsn = String(formRealityServerNames.value ?? '').trim()
      if (rsn) createBody.reality_server_names = rsn
      const rfp = String(formRealityFingerprint.value ?? '').trim()
      if (rfp) createBody.reality_fingerprint = rfp
      const vf = String(formVlessFlow.value ?? '').trim()
      if (vf) createBody.vless_flow = vf
      const rsid = String(formRealityShortId.value ?? '').trim().toLowerCase()
      if (rsid) createBody.reality_short_id = rsid
      const pinst = String(formPrometheusInstance.value ?? '').trim()
      if (pinst) createBody.prometheus_instance = pinst
      const cap = normalizeNetworkCapMbps(formNetworkCapMbps.value)
      if (cap != null) createBody.network_cap_mbps = cap
      await fetchJson('/api/servers', {
        method: 'POST',
        body: JSON.stringify(createBody),
      })
    }
    modalOpen.value = false
    editingServerId.value = null
    await loadServers()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

function formatDate(value) {
  if (!value) return '—'
  const s = String(value)
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (m) {
    return `${m[3]}.${m[2]}.${m[1]}`
  }
  try {
    return new Date(s).toLocaleDateString()
  } catch {
    return s
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    /* ignore */
  }
}

function formatProvisionStatus(status) {
  const key = String(status ?? '').toLowerCase()
  const labels = {
    idle: 'Нет задачи',
    queued: 'В очереди',
    running: 'Установка…',
    success: 'Готово',
    failed: 'Ошибка',
  }
  return labels[key] ?? status ?? '—'
}

function canEnqueueProvision(s) {
  if (!s) return false
  const st = s.provision_status
  if (st === 'queued' || st === 'running') return false
  if (st === 'success' && s.provision_ready) return false
  return true
}

function canResetProvision(s) {
  if (!s) return false
  const st = s.provision_status
  return st === 'queued' || st === 'running'
}

/** Повторный прогон скрипта на узле (xray + node_exporter), пока нет задачи в очереди. */
function canEnqueueReconcile(s) {
  if (!s) return false
  const st = s.provision_status
  return st !== 'queued' && st !== 'running'
}

function isServerProvisionBusy(s) {
  if (!s) return false
  const id = s.id
  return (
    serverProvisioningId.value === id ||
    serverReconcileId.value === id ||
    serverProvisionResetId.value === id ||
    serverXrayId.value === id ||
    serverPrometheusId.value === id ||
    serverCleanupId.value === id
  )
}

async function enqueueProvision(s) {
  provisionActionError.value = null
  serverProvisioningId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision`, { method: 'POST' })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverProvisioningId.value = null
  }
}

async function resetProvisionQueue(s) {
  provisionActionError.value = null
  serverProvisionResetId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision/reset`, { method: 'POST' })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverProvisionResetId.value = null
  }
}

async function enqueueReconcile(s) {
  provisionActionError.value = null
  serverReconcileId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision/reconcile`, {
      method: 'POST',
    })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverReconcileId.value = null
  }
}

async function enqueueProvisionXray(s) {
  provisionActionError.value = null
  serverXrayId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision/xray`, { method: 'POST' })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverXrayId.value = null
  }
}

async function enqueueProvisionPrometheus(s) {
  provisionActionError.value = null
  serverPrometheusId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision/prometheus`, {
      method: 'POST',
    })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverPrometheusId.value = null
  }
}

async function enqueueProvisionCleanup(s) {
  if (
    !window.confirm(
      'Удалить на узле Xray и node_exporter (включая конфиги xray) и сбросить в БД ключи REALITY и адрес Prometheus?',
    )
  ) {
    return
  }
  provisionActionError.value = null
  serverCleanupId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision/cleanup`, { method: 'POST' })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverCleanupId.value = null
  }
}

const sectionTitle = computed(() =>
  section.value === 'users' ? 'Пользователи' : 'Серверы',
)

const sectionSub = computed(() =>
  section.value === 'users'
    ? 'Токен подписки создаётся на сервере'
    : 'Провижининг по SSH: отдельно Xray, отдельно Prometheus (node_exporter), полный прогон, обновление и очистка узла. Нужны Redis и воркер RQ.',
)

const serverModalTitle = computed(() =>
  editingServerId.value != null ? 'Редактировать сервер' : 'Новый сервер',
)

const addButtonLabel = computed(() =>
  section.value === 'users' ? 'Новый пользователь' : 'Новый сервер',
)

const statsTitle = computed(() =>
  section.value === 'users' ? 'Пользователей в базе' : 'Серверов в базе',
)

const statsValue = computed(() =>
  section.value === 'users' ? usersCount.value : serversCount.value,
)
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <h1 class="page-title">Управление данными</h1>
      <nav class="admin-tabs" aria-label="Таблицы">
        <RouterLink
          class="tab"
          :class="{ 'tab-active': section === 'users' }"
          :to="{ path: '/admin' }"
        >
          Пользователи
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': section === 'servers' }"
          :to="{ path: '/admin', query: { tab: 'servers' } }"
        >
          Серверы
        </RouterLink>
      </nav>
      <div class="head-row">
        <h2 class="section-heading">{{ sectionTitle }}</h2>
        <div class="head-actions">
          <button
            v-if="section === 'servers'"
            type="button"
            class="btn-secondary"
            :disabled="loadSyncLoading || serversLoading"
            @click="syncServerLoadFromPrometheus"
          >
            {{
              loadSyncLoading ? 'Обновление загрузки…' : 'Обновить загрузку (Prometheus)'
            }}
          </button>
          <button type="button" class="btn-primary" @click="openModal">
            {{ addButtonLabel }}
          </button>
        </div>
      </div>
      <p class="sub">{{ sectionSub }}</p>
    </header>

    <section class="stats" aria-live="polite">
      <h3 class="stats-title">{{ statsTitle }}</h3>
      <p v-if="loading" class="stats-value muted">Загрузка…</p>
      <p v-else-if="error" class="stats-value error" :title="error">
        Не удалось загрузить
      </p>
      <p v-else class="stats-value">{{ statsValue }}</p>
    </section>

    <!-- Пользователи -->
    <template v-if="section === 'users'">
      <div v-if="!usersLoading && usersError" class="card err">
        {{ usersError }}
        <button type="button" class="btn-secondary" @click="loadUsers">
          Повторить
        </button>
      </div>
      <div
        v-else-if="!usersLoading && users.length === 0"
        class="card muted"
      >
        Пока нет пользователей. Создайте первого.
      </div>
      <div v-else-if="!usersLoading" class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Telegram</th>
              <th>Подписка до</th>
              <th>Токен</th>
              <th>Ссылка подписки</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.telegram_id ?? '—' }}</td>
              <td>{{ formatDate(u.subscription_until) }}</td>
              <td class="mono">
                <span class="token" :title="u.token">{{ u.token }}</span>
                <button
                  type="button"
                  class="btn-secondary btn-tiny"
                  @click="copyText(u.token)"
                >
                  Копировать
                </button>
              </td>
              <td class="link-cell">
                <a
                  class="sub-link"
                  :href="subscriptionPublicUrl(u.token)"
                  target="_blank"
                  rel="noopener"
                >{{ subscriptionPublicUrl(u.token) }}</a>
                <button
                  type="button"
                  class="btn-secondary btn-tiny"
                  @click="copyText(subscriptionPublicUrl(u.token))"
                >
                  Копировать
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Серверы -->
    <template v-else>
      <div v-if="!serversLoading && serversError" class="card err">
        {{ serversError }}
        <button type="button" class="btn-secondary" @click="loadServers">
          Повторить
        </button>
      </div>
      <div
        v-else-if="!serversLoading && servers.length === 0"
        class="card muted"
      >
        Пока нет серверов. Добавьте первый узел.
      </div>
      <div v-else-if="!serversLoading" class="servers-table-block">
        <p v-if="loadSyncOk" class="provision-banner provision-banner--ok">
          {{ loadSyncOk }}
        </p>
        <p v-if="loadSyncError" class="provision-banner">
          {{ loadSyncError }}
        </p>
        <p v-if="provisionActionError" class="provision-banner">
          {{ provisionActionError }}
        </p>
        <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Страна</th>
              <th>Нагрузка</th>
              <th>Тариф Мбит/с</th>
              <th>Host</th>
              <th>Статус</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in servers" :key="s.id">
              <td>{{ s.id }}</td>
              <td>{{ s.name ?? '—' }}</td>
              <td>{{ s.country || '—' }}</td>
              <td class="mono">
                {{ s.load_percent ?? 0 }}%
                <span
                  class="load-bar"
                  :style="{
                    '--load': Math.min(100, Math.max(0, s.load_percent ?? 0)),
                  }"
                  aria-hidden="true"
                />
              </td>
              <td class="mono tabular">
                {{ s.network_cap_mbps != null ? s.network_cap_mbps : '—' }}
              </td>
              <td class="mono">{{ s.host }}</td>
              <td>{{ formatProvisionStatus(s.provision_status) }}</td>
              <td class="row-actions">
                <div class="server-row-dropdown">
                  <button
                    type="button"
                    class="btn-dropdown-trigger btn-secondary btn-tiny"
                    :aria-expanded="serverMenuOpenId === s.id"
                    aria-haspopup="menu"
                    :aria-controls="'server-actions-' + s.id"
                    @click.stop="toggleServerMenu(s, $event)"
                  >
                    Действия
                    <span class="btn-dropdown-chevron" aria-hidden="true">▾</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>
    </template>

    <Teleport to="body">
      <div
        v-if="serverMenuOpenId != null && serverMenuTarget"
        :id="'server-actions-' + serverMenuOpenId"
        ref="serverMenuPanelEl"
        class="dropdown-panel server-actions-dropdown-panel"
        :style="serverMenuFloatStyle"
        role="menu"
        aria-label="Действия с сервером"
      >
        <RouterLink
          class="dropdown-item"
          role="menuitem"
          :to="{
            path: '/admin/analytics',
            query: { server: serverMenuTarget.id },
          }"
          @click="closeServerMenu"
        >
          Графики
        </RouterLink>
        <button
          type="button"
          class="dropdown-item"
          role="menuitem"
          @click="withOpenServerMenu(openEditServer)"
        >
          Правка
        </button>
        <div class="dropdown-sep" role="separator" />
        <button
          type="button"
          class="dropdown-item dropdown-item--primary"
          role="menuitem"
          :disabled="
            !canEnqueueProvision(serverMenuTarget) ||
            isServerProvisionBusy(serverMenuTarget)
          "
          :title="canEnqueueProvision(serverMenuTarget) ? 'Xray + node_exporter (если включено в настройках воркера)' : 'Недоступно: уже готов или задача в работе'"
          @click="withOpenServerMenu(enqueueProvision)"
        >
          {{
            serverProvisioningId === serverMenuTarget.id
              ? 'Полная установка…'
              : 'Полная установка'
          }}
        </button>
        <button
          type="button"
          class="dropdown-item"
          role="menuitem"
          :disabled="
            !canEnqueueReconcile(serverMenuTarget) ||
            isServerProvisionBusy(serverMenuTarget)
          "
          title="Повторно всё: xray, REALITY, node_exporter (как в полной установке)"
          @click="withOpenServerMenu(enqueueReconcile)"
        >
          {{
            serverReconcileId === serverMenuTarget.id
              ? 'Обновление…'
              : 'Обновить всё'
          }}
        </button>
        <button
          type="button"
          class="dropdown-item"
          role="menuitem"
          :disabled="
            !canEnqueueReconcile(serverMenuTarget) ||
            isServerProvisionBusy(serverMenuTarget)
          "
          title="Только Xray и конфиг VLESS+REALITY"
          @click="withOpenServerMenu(enqueueProvisionXray)"
        >
          {{
            serverXrayId === serverMenuTarget.id ? 'Xray…' : 'Xray'
          }}
        </button>
        <button
          type="button"
          class="dropdown-item"
          role="menuitem"
          :disabled="
            !canEnqueueReconcile(serverMenuTarget) ||
            isServerProvisionBusy(serverMenuTarget)
          "
          title="Только node_exporter для Prometheus"
          @click="withOpenServerMenu(enqueueProvisionPrometheus)"
        >
          {{
            serverPrometheusId === serverMenuTarget.id
              ? 'Prometheus…'
              : 'Prometheus'
          }}
        </button>
        <div class="dropdown-sep" role="separator" />
        <button
          type="button"
          class="dropdown-item dropdown-item--danger"
          role="menuitem"
          :disabled="
            !canEnqueueReconcile(serverMenuTarget) ||
            isServerProvisionBusy(serverMenuTarget)
          "
          title="Снять ПО с узла и очистить ключи/метрики в БД"
          @click="withOpenServerMenu(enqueueProvisionCleanup)"
        >
          {{
            serverCleanupId === serverMenuTarget.id ? 'Очистка…' : 'Очистить'
          }}
        </button>
        <button
          v-if="canResetProvision(serverMenuTarget)"
          type="button"
          class="dropdown-item"
          role="menuitem"
          :disabled="
            serverProvisionResetId === serverMenuTarget.id ||
            isServerProvisionBusy(serverMenuTarget)
          "
          title="Если воркер упал, а статус «в очереди» или «установка» — сбросить и поставить задачу снова"
          @click="withOpenServerMenu(resetProvisionQueue)"
        >
          {{
            serverProvisionResetId === serverMenuTarget.id
              ? 'Сброс…'
              : 'Сброс очереди'
          }}
        </button>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="modalOpen"
        class="modal-backdrop"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="
          section === 'users' ? 'modal-user' : 'modal-server-title'
        "
        @click.self="closeModal"
      >
        <div v-if="section === 'users'" class="modal">
          <h2 id="modal-user">Новый пользователь</h2>
          <form class="form" @submit.prevent="submitCreateUser">
            <label class="field">
              <span>Telegram (необязательно)</span>
              <div class="input-with-at">
                <span class="input-at" aria-hidden="true">@</span>
                <input
                  v-model="formTelegramId"
                  type="text"
                  inputmode="text"
                  autocomplete="off"
                  autocapitalize="none"
                  spellcheck="false"
                  placeholder="username"
                />
              </div>
            </label>
            <label class="field">
              <span>Подписка до (необязательно)</span>
              <input v-model="formSubUntil" type="date" />
            </label>
            <p v-if="createError" class="form-err">{{ createError }}</p>
            <div class="modal-actions">
              <button
                type="button"
                class="btn-secondary"
                :disabled="creating"
                @click="closeModal"
              >
                Отмена
              </button>
              <button
                type="submit"
                class="btn-primary"
                :disabled="creating"
              >
                {{ creating ? 'Создание…' : 'Создать' }}
              </button>
            </div>
          </form>
        </div>
        <div v-else class="modal modal-server">
          <h2 id="modal-server-title">{{ serverModalTitle }}</h2>
          <div
            class="modal-tabs"
            role="tablist"
            aria-label="Разделы формы сервера"
          >
            <button
              type="button"
              role="tab"
              class="modal-tab"
              :class="{ 'modal-tab-active': serverModalTab === 'general' }"
              :aria-selected="serverModalTab === 'general'"
              @click="serverModalTab = 'general'"
            >
              Общие
            </button>
            <button
              type="button"
              role="tab"
              class="modal-tab"
              :class="{ 'modal-tab-active': serverModalTab === 'proxy' }"
              :aria-selected="serverModalTab === 'proxy'"
              @click="serverModalTab = 'proxy'"
            >
              Прокси (VLESS+REALITY)
            </button>
          </div>
          <form class="form" @submit.prevent="submitSaveServer">
            <div
              v-show="serverModalTab === 'general'"
              class="form-section"
            >
              <label class="field">
                <span>Название (необязательно)</span>
                <input
                  v-model="formName"
                  type="text"
                  autocomplete="off"
                  placeholder="Например, AMS-1"
                />
              </label>
              <label class="field">
                <span>Страна</span>
                <input
                  v-model="formCountry"
                  type="text"
                  required
                  autocomplete="off"
                  placeholder="NL, США или полное название"
                />
              </label>
              <label v-if="editingServerId == null" class="field">
                <span>Host</span>
                <input
                  v-model="formHost"
                  type="text"
                  required
                  autocomplete="off"
                  autocapitalize="none"
                  spellcheck="false"
                  placeholder="IP или домен VPS"
                />
              </label>
              <div v-else class="field field-readonly">
                <span>Host:порт</span>
                <p class="readonly-value mono">{{ formHost }}:{{ formPort }}</p>
              </div>
              <label v-if="editingServerId == null" class="field">
                <span>Порт inbound</span>
                <input
                  v-model.number="formPort"
                  type="number"
                  min="1"
                  max="65535"
                  required
                />
              </label>
              <label class="field field-check">
                <input v-model="formActive" type="checkbox" />
                <span>Активен (учитывать в подписке)</span>
              </label>
              <label class="field">
                <span>Prometheus instance (node_exporter)</span>
                <input
                  v-model="formPrometheusInstance"
                  type="text"
                  autocomplete="off"
                  autocapitalize="none"
                  spellcheck="false"
                  placeholder="Напр. 72.56.110.181:9100 — как label instance в Prometheus"
                />
              </label>
              <label class="field">
                <span>Тариф канала (Мбит/с)</span>
                <input
                  v-model="formNetworkCapMbps"
                  type="number"
                  min="1"
                  max="1000000"
                  step="1"
                  autocomplete="off"
                  placeholder="Напр. 200 — верх шкалы графика сети в аналитике"
                />
                <span class="field-hint"
                  >Пусто — шкала по скорости порта из метрик. Задано — потолок по тарифу.</span
                >
              </label>
            </div>
            <div
              v-show="serverModalTab === 'proxy'"
              class="form-section"
            >
              <p class="field-hint">
                По умолчанию — маскировка под Amazon (REALITY). После «Установить
                ПО» ключи попадут в БД.
              </p>
              <div v-if="editingServerId != null" class="field field-readonly">
                <span>VLESS UUID</span>
                <p class="readonly-value mono break-all">{{ formVlessUuid }}</p>
              </div>
              <div v-if="editingServerId != null" class="field field-readonly">
                <span>REALITY public (pbk)</span>
                <p class="readonly-value mono break-all">
                  {{ formRealityPublicKey || '—' }}
                </p>
              </div>
              <label class="field">
                <span>REALITY dest (маскировка)</span>
                <input
                  v-model="formRealityDest"
                  type="text"
                  autocomplete="off"
                />
              </label>
              <label class="field">
                <span>serverNames (через запятую)</span>
                <input
                  v-model="formRealityServerNames"
                  type="text"
                  autocomplete="off"
                />
              </label>
              <label class="field">
                <span>shortId REALITY (hex)</span>
                <input
                  v-model="formRealityShortId"
                  type="text"
                  autocomplete="off"
                  autocapitalize="none"
                  spellcheck="false"
                />
              </label>
              <label class="field">
                <span>fingerprint (uTLS)</span>
                <input
                  v-model="formRealityFingerprint"
                  type="text"
                  autocomplete="off"
                />
              </label>
              <label class="field">
                <span>VLESS flow</span>
                <input
                  v-model="formVlessFlow"
                  type="text"
                  autocomplete="off"
                />
              </label>
              <label v-if="editingServerId != null" class="field">
                <span>Приватный ключ REALITY (необязательно)</span>
                <input
                  v-model="formRealityPrivateKey"
                  type="text"
                  autocomplete="off"
                  spellcheck="false"
                  class="mono"
                />
              </label>
            </div>
            <p v-if="createError" class="form-err">{{ createError }}</p>
            <div class="modal-actions">
              <button
                type="button"
                class="btn-secondary"
                :disabled="creating"
                @click="closeModal"
              >
                Отмена
              </button>
              <button
                type="submit"
                class="btn-primary"
                :disabled="creating"
              >
                {{
                  creating
                    ? 'Сохранение…'
                    : editingServerId != null
                      ? 'Сохранить'
                      : 'Добавить'
                }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2.5rem;
}
.head {
  margin-bottom: 1rem;
}
.back {
  display: inline-block;
  margin-bottom: 0.5rem;
  color: var(--muted);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.2s ease;
}

.back:hover {
  color: var(--accent);
}

.page-title {
  font-size: 1.65rem;
  margin: 0 0 0.65rem;
  letter-spacing: -0.02em;
  color: var(--text-h);
}

.admin-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}

.tab {
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 600;
  text-decoration: none;
  color: var(--muted);
  border: 1px solid var(--card-border);
  background: var(--surface);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.tab:hover {
  color: var(--accent);
  border-color: var(--accent-border);
}

.tab-active {
  color: var(--on-accent);
  background: var(--accent);
  border-color: var(--accent);
}

.tab-active:hover {
  color: var(--on-accent);
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.section-heading {
  font-size: 1.25rem;
  margin: 0;
  letter-spacing: -0.02em;
  font-weight: 700;
  color: var(--text-h);
}
.sub {
  color: var(--muted);
  margin: 0.35rem 0 0;
  font-size: 0.9rem;
}
.stats {
  margin: 0 0 1rem;
  max-width: 240px;
  padding: 0.9rem 1.1rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
}
.stats-title {
  margin: 0 0 0.35rem;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.stats-value {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
}
.stats-value.muted {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--muted);
}
.stats-value.error {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--danger);
}
.card {
  padding: 1rem 1.15rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
}
.card.err {
  border-color: var(--danger);
  background: var(--danger-soft);
  color: var(--danger);
}
.card.muted {
  color: var(--muted);
}
.table-wrap {
  overflow-x: auto;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.table th,
.table td {
  padding: 0.65rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  color: var(--text);
}
.table th {
  color: var(--muted);
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.06em;
}
.mono {
  font-family: var(--mono);
  font-size: 0.8rem;
  color: var(--text-h);
}

.load-bar {
  display: block;
  height: 4px;
  margin-top: 0.35rem;
  width: calc(5.5rem * var(--load, 0) / 100);
  max-width: 5.5rem;
  min-width: 2px;
  border-radius: 2px;
  background: var(--accent);
  opacity: 0.9;
}

.row-actions {
  vertical-align: middle;
  white-space: nowrap;
}

.server-row-dropdown {
  position: relative;
  display: inline-block;
}

.btn-dropdown-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  min-width: 6.75rem;
}

.btn-dropdown-chevron {
  font-size: 0.62rem;
  opacity: 0.75;
  line-height: 1;
}

.dropdown-panel {
  min-width: 13.5rem;
  padding: 0.4rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-md);
}

.server-actions-dropdown-panel {
  max-height: min(70vh, 28rem);
  overflow-y: auto;
}

.dropdown-sep {
  height: 1px;
  margin: 0.35rem 0.25rem;
  background: var(--border);
  border: none;
  padding: 0;
}

.dropdown-item {
  display: flex;
  width: 100%;
  align-items: center;
  text-align: left;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0.5rem 0.65rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-h);
  cursor: pointer;
  text-decoration: none;
  box-sizing: border-box;
}

.dropdown-item:hover:not(:disabled) {
  background: var(--surface);
}

.dropdown-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.dropdown-item--primary {
  color: var(--accent-hover);
}

.dropdown-item--danger {
  color: var(--danger);
}

.servers-table-block {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.provision-banner {
  margin: 0;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  font-size: 0.88rem;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid var(--danger);
}

.provision-banner--ok {
  color: var(--text-h);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.field-readonly .readonly-value {
  margin: 0;
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  border: 1px dashed var(--card-border);
  background: var(--surface);
  font-size: 0.88rem;
  color: var(--text-h);
}

.break-all {
  word-break: break-all;
}

.field-hint {
  margin: 0;
  font-size: 0.8rem;
  color: var(--muted);
  line-height: 1.45;
}

.mono .btn-secondary,
.link-cell .btn-secondary {
  margin-top: 0.45rem;
  margin-right: 0.35rem;
}
.token {
  display: block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.link-cell {
  font-size: 0.78rem;
}
.sub-link {
  display: inline-block;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--accent);
  font-weight: 600;
  vertical-align: middle;
  transition: color 0.2s ease;
}

.sub-link:hover {
  color: var(--accent-hover);
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(26, 18, 38, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1rem, 4vh, 2.5rem) 1rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  z-index: 50;
  box-sizing: border-box;
}

@media (prefers-color-scheme: dark) {
  .modal-backdrop {
    background: rgba(8, 6, 12, 0.72);
  }
}

.modal {
  width: 100%;
  max-width: 420px;
  max-height: min(90vh, calc(100dvh - 2 * clamp(1rem, 4vh, 2.5rem)));
  padding: 1.35rem 1.45rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg);
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  flex-shrink: 0;
  box-sizing: border-box;
}

.modal-server {
  max-width: 460px;
}

.modal-tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 1rem;
  padding-bottom: 0.65rem;
  border-bottom: 1px solid var(--card-border);
}

.modal-tab {
  flex: 1;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.25;
  padding: 0.5rem 0.45rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--muted);
  cursor: pointer;
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.modal-tab:hover {
  color: var(--accent);
  border-color: var(--accent-border);
}

.modal-tab-active {
  color: var(--on-accent);
  background: var(--accent);
  border-color: var(--accent);
}

.modal-tab-active:hover {
  color: var(--on-accent);
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-height: 0;
}

.modal h2 {
  margin: 0 0 0.85rem;
  font-size: 1.15rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--muted);
}

.field.field-check {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
}

.field.field-check input[type='checkbox'] {
  width: 1rem;
  height: 1rem;
  accent-color: var(--accent);
}

.field.field-check span {
  font-weight: 600;
  color: var(--text);
}

.field input[type='date'],
.field input[type='text'],
.field input[type='number'] {
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-weight: 400;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.field input[type='date']:focus,
.field input[type='text']:focus,
.field input[type='number']:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.input-with-at {
  display: flex;
  align-items: stretch;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  overflow: hidden;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.input-with-at:focus-within {
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.input-at {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding: 0 0.5rem 0 0.65rem;
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--accent);
  background: var(--accent-soft);
  border-right: 1px solid var(--card-border);
  user-select: none;
}

.field .input-with-at input {
  flex: 1;
  min-width: 0;
  margin: 0;
  padding: 0.55rem 0.7rem;
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--text-h);
  font: inherit;
  font-weight: 400;
}

.field .input-with-at input:focus {
  outline: none;
  box-shadow: none;
}

.field .input-with-at input::placeholder {
  color: var(--muted);
  opacity: 0.75;
}

.form-err {
  margin: 0;
  font-size: 0.85rem;
  color: var(--danger);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.65rem;
}
</style>
