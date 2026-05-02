<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import UserRolePill from '../components/UserRolePill.vue'
import { RouterLink, useRoute } from 'vue-router'
import { fetchJson, subscriptionPublicUrl } from '../api/client.js'
import { formatTrafficBytes } from '../utils/formatTraffic.js'

const route = useRoute()

const section = computed(() =>
  route.name === 'admin-servers' ? 'servers' : 'users',
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
/** null — создание пользователя; иначе id для PATCH */
const editingUserId = ref(null)

/** Текущая строка пользователя при открытом редактировании (модалка). */
const editingUserRow = computed(() => {
  const id = editingUserId.value
  if (id == null) return null
  return users.value.find((x) => x.id === id) ?? null
})

/** Есть ли в БД telegram_id или непустой telegram_properties — доступен сброс. */
const editingUserHasTelegramData = computed(() => {
  const u = editingUserRow.value
  if (!u) return false
  if (u.telegram_id != null) return true
  const p = u.telegram_properties
  if (!p || typeof p !== 'object') return false
  return Object.keys(p).length > 0
})

const formTelegramId = ref('')
const formSubUntil = ref('')
/** client | manager | admin — при редактировании пользователя */
const formAccountRole = ref('client')
/** Дата регистрации в форме ДД.ММ.ГГГГ (календарный день UTC); пусто — сбросить в БД */
const formRegisteredAt = ref('')
/** @username при редактировании (только отображение) */
const editingUserTgUsername = ref('')

const usersSyncLoading = ref(false)
const usersSyncError = ref(null)
const usersSyncOk = ref(null)
/** Массовое продление подписок (только активные с конечной датой) */
const extendDays = ref('7')
const extendLoading = ref(false)
const extendError = ref(null)
const extendOk = ref(null)
/** @type {import('vue').Ref<number | null>} */
const deletingUserId = ref(null)
const clearTelegramBusy = ref(false)

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
/** Вход (РФ) в каскаде: дальше трафик на внешний exit (подготовка к Xray) */
const formIsCascadeRuEntry = ref(false)
/** id внешнего сервера; '' = не задано */
const formCascadeNextServerId = ref('')
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
const serverFairEgressId = ref(null)
const serverCleanupId = ref(null)
const provisionActionError = ref(null)
/** Проверка TCP с API к host:port узла */
const serverPingId = ref(null)
const serverReachabilityOk = ref(null)
const serverReachabilityMsg = ref(null)
/** Подпункты ответа GET /servers/:id/ping (TCP, БД, каскад, node_exporter) */
const serverHealthChecks = ref([])
const deletingServerId = ref(null)

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
    editingUserId.value = null
    serverModalTab.value = 'general'
    closeServerMenu()
    loadSyncOk.value = null
    loadSyncError.value = null
    serverReachabilityOk.value = null
    serverReachabilityMsg.value = null
    serverHealthChecks.value = []
    usersSyncOk.value = null
    usersSyncError.value = null
    if (s === 'users') loadUsers()
    else loadServers()
  },
  { immediate: true },
)

function openModal() {
  createError.value = null
  editingServerId.value = null
  editingUserId.value = null
  serverModalTab.value = 'general'
  if (section.value === 'users') {
    formTelegramId.value = ''
    formSubUntil.value = ''
    formAccountRole.value = 'client'
    formRegisteredAt.value = ''
    editingUserTgUsername.value = ''
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
    formIsCascadeRuEntry.value = false
    formCascadeNextServerId.value = ''
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
  formIsCascadeRuEntry.value = Boolean(s.is_cascade_ru_entry)
  formCascadeNextServerId.value =
    s.cascade_next_server_id != null ? String(s.cascade_next_server_id) : ''
  modalOpen.value = true
}

function closeModal() {
  if (
    creating.value ||
    deletingServerId.value != null ||
    clearTelegramBusy.value ||
    deletingUserId.value != null
  ) {
    return
  }
  modalOpen.value = false
  editingServerId.value = null
  editingUserId.value = null
  editingUserTgUsername.value = ''
  serverModalTab.value = 'general'
}

function openEditUser(u) {
  createError.value = null
  editingServerId.value = null
  editingUserId.value = u.id
  formTelegramId.value =
    u.telegram_id != null ? String(u.telegram_id) : ''
  editingUserTgUsername.value =
    u.telegram_properties &&
    typeof u.telegram_properties.username === 'string'
      ? u.telegram_properties.username
      : ''
  const su = u.subscription_until
  formSubUntil.value =
    su != null && String(su).trim()
      ? isoYyyyMmDdToRuDmy(String(su).slice(0, 10))
      : ''
  formAccountRole.value =
    u.account_role === 'manager' || u.account_role === 'admin'
      ? u.account_role
      : 'client'
  formRegisteredAt.value = utcIsoToRuDmy(u.registered_at)
  modalOpen.value = true
}

/** YYYY-MM-DD → ДД.ММ.ГГГГ для показа в форме */
function isoYyyyMmDdToRuDmy(iso) {
  const s = String(iso ?? '').trim().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return ''
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return ''
  return `${String(d).padStart(2, '0')}.${String(m).padStart(2, '0')}.${y}`
}

/** Момент UTC (ISO) → календарный день UTC как ДД.ММ.ГГГГ */
function utcIsoToRuDmy(iso) {
  if (iso == null || iso === '') return ''
  const t = Date.parse(String(iso))
  if (Number.isNaN(t)) return ''
  const d = new Date(t)
  const day = String(d.getUTCDate()).padStart(2, '0')
  const month = String(d.getUTCMonth() + 1).padStart(2, '0')
  const y = d.getUTCFullYear()
  return `${day}.${month}.${y}`
}

/**
 * Пустая строка → null.
 * ДД.ММ.ГГГГ или ГГГГ-ММ-ДД → YYYY-MM-DD для API; неверная дата → null.
 */
function dateFormToIsoOrNull(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return null
  const ru = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(s)
  if (ru) {
    const d = Number(ru[1])
    const m = Number(ru[2])
    const y = Number(ru[3])
    if (m < 1 || m > 12 || d < 1 || d > 31 || y < 1 || y > 9999) return null
    const dt = new Date(Date.UTC(y, m - 1, d))
    if (
      dt.getUTCFullYear() !== y ||
      dt.getUTCMonth() !== m - 1 ||
      dt.getUTCDate() !== d
    ) {
      return null
    }
    return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split('-').map(Number)
    const dt = new Date(Date.UTC(y, m - 1, d))
    if (
      dt.getUTCFullYear() !== y ||
      dt.getUTCMonth() !== m - 1 ||
      dt.getUTCDate() !== d
    ) {
      return null
    }
    return s
  }
  return null
}

/** null — очистить registered_at; иначе ISO UTC полночь выбранного календарного дня */
function registrationDateTimeUtcOrNull(raw) {
  const d = dateFormToIsoOrNull(raw)
  if (d === null) return null
  return `${d}T00:00:00.000Z`
}

/** Числовой Telegram user id (Bot API); пусто → null */
function normalizeTelegramId(raw) {
  const s = String(raw ?? '').trim().replace(/^@/, '')
  if (!s) return null
  if (!/^\d{1,19}$/.test(s)) return null
  return Number(s)
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

async function submitSaveUser() {
  creating.value = true
  createError.value = null
  try {
    const subRaw = String(formSubUntil.value ?? '').trim()
    const subIso = subRaw === '' ? null : dateFormToIsoOrNull(formSubUntil.value)
    if (subRaw !== '' && subIso === null) {
      createError.value = 'Подписка до: укажите дату как ДД.ММ.ГГГГ'
      return
    }
    const regRaw = String(formRegisteredAt.value ?? '').trim()
    const regIso =
      regRaw === '' ? null : dateFormToIsoOrNull(formRegisteredAt.value)
    if (editingUserId.value != null && regRaw !== '' && regIso === null) {
      createError.value =
        'Дата регистрации: укажите дату как ДД.ММ.ГГГГ или очистите поле'
      return
    }

    if (editingUserId.value != null) {
      await fetchJson(`/api/users/${editingUserId.value}`, {
        method: 'PATCH',
        body: JSON.stringify({
          subscription_until: subIso,
          account_role: formAccountRole.value,
          registered_at: registrationDateTimeUtcOrNull(formRegisteredAt.value),
        }),
      })
    } else {
      await fetchJson('/api/users', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: normalizeTelegramId(formTelegramId.value),
          subscription_until: subIso,
        }),
      })
    }
    modalOpen.value = false
    editingUserId.value = null
    await loadUsers()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

async function clearEditingUserTelegram() {
  const id = editingUserId.value
  if (id == null || !editingUserHasTelegramData.value) return
  const row = editingUserRow.value
  const noEmail =
    row &&
    (row.email == null ||
      (typeof row.email === 'string' && row.email.trim() === ''))
  const warn =
    noEmail ?
      '\n\nУ пользователя нет email — после сброса Telegram войти в аккаунт будет нельзя.'
    : ''
  if (
    !window.confirm(
      `Сбросить привязку Telegram (числовой ID и профиль в JSON) у пользователя #${id}?${warn}`,
    )
  ) {
    return
  }
  clearTelegramBusy.value = true
  createError.value = null
  try {
    await fetchJson(`/api/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        telegram_id: null,
        telegram_properties: null,
      }),
    })
    formTelegramId.value = ''
    editingUserTgUsername.value = ''
    await loadUsers()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    clearTelegramBusy.value = false
  }
}

async function syncXrayClientsAllServers() {
  usersSyncLoading.value = true
  usersSyncError.value = null
  usersSyncOk.value = null
  try {
    const res = await fetchJson('/api/servers/sync-xray-clients', {
      method: 'POST',
    })
    usersSyncOk.value = `Задача синхронизации Xray поставлена (job: ${res.job_id}).`
    await loadUsers()
  } catch (e) {
    usersSyncError.value = e.message || String(e)
  } finally {
    usersSyncLoading.value = false
  }
}

async function extendActiveSubscriptionsBulk() {
  const n = Number.parseInt(String(extendDays.value ?? '').trim(), 10)
  if (Number.isNaN(n) || n < 1 || n > 3650) {
    extendError.value = 'Укажите число дней от 1 до 3650'
    extendOk.value = null
    return
  }
  extendLoading.value = true
  extendError.value = null
  extendOk.value = null
  usersSyncOk.value = null
  try {
    const res = await fetchJson('/api/users/extend-active-subscriptions', {
      method: 'POST',
      body: JSON.stringify({ days: n }),
    })
    const c = res.updated_count ?? 0
    extendOk.value =
      c === 0
        ? 'Никто не обновлён (нет пользователей с активной конечной подпиской).'
        : `Подписка продлена на ${n} дн. для ${c} пользователей. Синхронизация Xray поставлена в очередь.`
    await loadUsers()
  } catch (e) {
    extendError.value = e.message || String(e)
  } finally {
    extendLoading.value = false
  }
}

async function deleteUser(u, opts = {}) {
  const { fromModal = false } = opts
  const label =
    u.telegram_id != null
      ? String(u.telegram_id)
      : u.telegram_properties?.username
        ? '@' + u.telegram_properties.username
        : `id ${u.id}`
  if (
    !window.confirm(
      `Удалить пользователя «${label}» из базы?\n\n` +
        'Строки трафика по узлам удалятся вместе с записью. На всех узлах с готовым провижинингом в очередь поставится синхронизация Xray — UUID исчезнет из inbound.',
    )
  ) {
    return
  }
  deletingUserId.value = u.id
  usersSyncError.value = null
  usersSyncOk.value = null
  try {
    await fetchJson(`/api/users/${u.id}`, { method: 'DELETE' })
    usersSyncOk.value =
      'Пользователь удалён. Синхронизация клиентов Xray на узлах поставлена в очередь.'
    await loadUsers()
    if (fromModal) {
      modalOpen.value = false
      editingUserId.value = null
      createError.value = null
    }
  } catch (e) {
    usersSyncError.value = e.message || String(e)
  } finally {
    deletingUserId.value = null
  }
}

function deleteUserFromModal() {
  const id = editingUserId.value
  if (id == null) return
  const u = users.value.find((x) => x.id === id)
  if (!u) return
  void deleteUser(u, { fromModal: true })
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
      patch.is_cascade_ru_entry = formIsCascadeRuEntry.value
      const cnx = String(formCascadeNextServerId.value ?? '').trim()
      patch.cascade_next_server_id = cnx
        ? Number.parseInt(cnx, 10)
        : null
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
      createBody.is_cascade_ru_entry = formIsCascadeRuEntry.value
      const cnx = String(formCascadeNextServerId.value ?? '').trim()
      if (cnx) {
        createBody.cascade_next_server_id = Number.parseInt(cnx, 10)
      } else {
        createBody.cascade_next_server_id = null
      }
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
    serverFairEgressId.value === id ||
    serverCleanupId.value === id ||
    serverPingId.value === id ||
    deletingServerId.value === id
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

async function enqueueProvisionFairEgress(s) {
  provisionActionError.value = null
  serverFairEgressId.value = s.id
  try {
    await fetchJson(`/api/servers/${s.id}/provision/fair-egress`, {
      method: 'POST',
    })
    await loadServers()
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    serverFairEgressId.value = null
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

async function pingServerReachability(s) {
  serverReachabilityOk.value = null
  serverReachabilityMsg.value = null
  serverHealthChecks.value = []
  provisionActionError.value = null
  serverPingId.value = s.id
  try {
    const res = await fetchJson(`/api/servers/${s.id}/ping`)
    const checks = Array.isArray(res.checks) ? res.checks : []
    serverHealthChecks.value = checks
    const overall =
      res.overall_ok === true
        ? true
        : res.overall_ok === false
          ? false
          : Boolean(res.reachable)
    serverReachabilityOk.value = overall
    serverReachabilityMsg.value =
      (res.summary && String(res.summary).trim()) ||
      (res.reachable
        ? `Узел отвечает по TCP ${res.host}:${res.port}` +
            (res.latency_ms != null ? `, ${res.latency_ms} мс` : '') +
            ' (с хоста API, не ICMP).'
        : `Нет ответа по TCP ${res.host}:${res.port}. ${res.detail || ''}`.trim())
  } catch (e) {
    serverReachabilityOk.value = false
    serverReachabilityMsg.value = e.message || String(e)
    serverHealthChecks.value = []
  } finally {
    serverPingId.value = null
  }
}

async function deleteServer(s, opts = {}) {
  const { fromModal = false } = opts
  const label = s.name ? `${s.name} (${s.host})` : s.host
  if (
    !window.confirm(
      `Удалить сервер «${label}» (id ${s.id}) из базы?\n\n` +
        'Строки трафика по этому узлу удалятся. Привязки каскада к этому id сбросятся. ' +
        'На оставшихся готовых узлах в очередь поставится синхронизация Xray.',
    )
  ) {
    return
  }
  deletingServerId.value = s.id
  provisionActionError.value = null
  serverReachabilityOk.value = null
  serverReachabilityMsg.value = null
  serverHealthChecks.value = []
  try {
    await fetchJson(`/api/servers/${s.id}`, { method: 'DELETE' })
    await loadServers()
    if (fromModal) {
      modalOpen.value = false
      editingServerId.value = null
      createError.value = null
    }
  } catch (e) {
    provisionActionError.value = e.message || String(e)
  } finally {
    deletingServerId.value = null
  }
}

function deleteServerFromModal() {
  const id = editingServerId.value
  if (id == null) return
  const s = servers.value.find((x) => x.id === id)
  if (!s) return
  void deleteServer(s, { fromModal: true })
}

const sectionTitle = computed(() =>
  section.value === 'users' ? 'Пользователи' : 'Серверы',
)


const userModalTitle = computed(() =>
  editingUserId.value != null ? 'Редактировать пользователя' : 'Новый пользователь',
)

const serverModalTitle = computed(() =>
  editingServerId.value != null ? 'Редактировать сервер' : 'Новый сервер',
)

const addButtonLabel = computed(() =>
  section.value === 'users' ? 'Новый пользователь' : 'Новый сервер',
)

const statsLine = computed(() => {
  if (loading.value) return 'Загрузка…'
  if (error.value) return 'Ошибка загрузки'
  if (section.value === 'users') {
    const n = usersCount.value
    return n != null ? `${n} пользователей` : '— пользователей'
  }
  const n = serversCount.value
  return n != null ? `${n} серверов` : '— серверов'
})

/** id внешнего, на которые ссылаются входы (РФ) */
const cascadeReferencedExitIds = computed(() => {
  const s = new Set()
  for (const x of servers.value) {
    if (x.cascade_next_server_id != null) s.add(x.cascade_next_server_id)
  }
  return s
})

const serverCascadePairs = computed(() => {
  const out = []
  for (const s of servers.value) {
    if (!s.is_cascade_ru_entry || !s.cascade_next_server_id) continue
    const exitS = servers.value.find((e) => e.id === s.cascade_next_server_id) ?? null
    out.push({ entry: s, exit: exitS })
  }
  return out
})

const ruEntryAwaitingCascade = computed(() =>
  servers.value.filter((s) => s.is_cascade_ru_entry && !s.cascade_next_server_id),
)

const externalServersUnpaired = computed(() =>
  servers.value.filter(
    (s) => !s.is_cascade_ru_entry && !cascadeReferencedExitIds.value.has(s.id),
  ),
)

/** Под селектор: кто может быть внешним exit (не «вход РФ»; не self при правке) */
function cascadeExitCandidates(editingId) {
  return servers.value.filter(
    (s) => !s.is_cascade_ru_entry && s.id !== editingId,
  )
}

watch(formIsCascadeRuEntry, (v) => {
  if (!v) formCascadeNextServerId.value = ''
})
</script>

<template>
  <AdminPageShell>
    <AdminPageHeader
      title="Управление данными"
      back-to="/"
      back-label="← На главную"
      tabs-aria-label="Таблицы"
    >
      <template #tabs>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-users' }"
          :to="{ path: '/admin/users' }"
        >
          Пользователи
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-servers' }"
          :to="{ path: '/admin/servers' }"
        >
          Серверы
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
          :to="{ path: '/admin/users/analytics' }"
        >
          Клиенты
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
          :to="{ path: '/admin/users/registrations-by-date' }"
        >
          Статистика по дням
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-analytics' }"
          :to="{ path: '/admin/analytics' }"
        >
          Нагрузка
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-funnel' }"
          :to="{ path: '/admin/funnel' }"
        >
          Воронка
        </RouterLink>
        <RouterLink
          class="tab"
          :class="{ 'tab-active': route.name === 'admin-referrals' }"
          :to="{ path: '/admin/referrals' }"
        >
          Реферальные токены
        </RouterLink>
      </template>
      <div class="head-row">
        <h2 class="section-heading">{{ sectionTitle }}</h2>
        <div class="head-actions">
          <button
            v-if="section === 'users'"
            type="button"
            class="btn-secondary"
            :disabled="usersSyncLoading || usersLoading"
            @click="syncXrayClientsAllServers"
          >
            {{
              usersSyncLoading
                ? 'Синхронизация Xray…'
                : 'Синхронизировать Xray на узлах'
            }}
          </button>
          <div
            v-if="section === 'users'"
            class="extend-active-wrap"
            title="Учитываются только пользователи с заданной датой подписки ≥ сегодня; бессрочные (без даты) не меняются"
          >
            <label class="extend-active-label">
              <span class="extend-active-label-text">+ дней активным</span>
              <input
                v-model="extendDays"
                class="extend-active-input"
                type="number"
                min="1"
                max="3650"
                step="1"
                :disabled="extendLoading || usersLoading"
              />
            </label>
            <button
              type="button"
              class="btn-secondary"
              :disabled="extendLoading || usersLoading"
              @click="extendActiveSubscriptionsBulk"
            >
              {{ extendLoading ? 'Продление…' : 'Продлить всем активным' }}
            </button>
          </div>
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
    </AdminPageHeader>

    <section class="stats" aria-live="polite">
      <p
        class="stats-value"
        :class="{ error: !loading && error }"
        :title="error || undefined"
      >
        {{ statsLine }}
      </p>
    </section>

    <!-- Пользователи -->
    <template v-if="section === 'users'">
      <p v-if="usersSyncOk" class="provision-banner provision-banner--ok">
        {{ usersSyncOk }}
      </p>
      <p v-if="usersSyncError" class="provision-banner">
        {{ usersSyncError }}
      </p>
      <p v-if="extendOk" class="provision-banner provision-banner--ok">
        {{ extendOk }}
      </p>
      <p v-if="extendError" class="provision-banner">
        {{ extendError }}
      </p>
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
      <AdminTableWrap v-else-if="!usersLoading" aria-label="Таблица пользователей">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Email</th>
              <th>Telegram</th>
              <th>Роль</th>
              <th>Регистрация</th>
              <th>Подписка до</th>
              <th>Подписка</th>
              <th class="num">Трафик</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.email ?? '—' }}</td>
              <td>
                <template v-if="u.telegram_id != null">
                  {{ u.telegram_id
                  }}<span
                    v-if="u.telegram_properties?.username"
                    class="muted"
                  > @{{ u.telegram_properties.username }}</span>
                </template>
                <template v-else-if="u.telegram_properties?.username">
                  <span class="muted"
                    >@{{ u.telegram_properties.username }}</span>
                </template>
                <template v-else>—</template>
              </td>
              <td>
                <UserRolePill :role="u.account_role" />
              </td>
              <td>{{ formatDate(u.registered_at) }}</td>
              <td>{{ formatDate(u.subscription_until) }}</td>
              <td class="link-cell">
                <button
                  type="button"
                  class="btn-secondary btn-tiny"
                  :disabled="!u.token"
                  aria-label="Копировать ссылку подписки в буфер обмена"
                  @click="copyText(subscriptionPublicUrl(u.token))"
                >
                  Копировать
                </button>
              </td>
              <td class="num traffic-link-cell">
                <RouterLink
                  class="user-analytics-link"
                  :to="`/admin/users/${u.id}/analytics`"
                  title="Подробная аналитика по серверам"
                >
                  {{ formatTrafficBytes(u.total_traffic_bytes ?? 0) }}
                </RouterLink>
              </td>
              <td class="row-actions">
                <button
                  type="button"
                  class="btn-secondary btn-tiny"
                  @click="openEditUser(u)"
                >
                  Правка
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </AdminTableWrap>
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
        <div
          v-if="serverReachabilityMsg"
          class="provision-banner"
          :class="{ 'provision-banner--ok': serverReachabilityOk === true }"
        >
          <p class="server-health-summary">
            {{ serverReachabilityMsg }}
          </p>
          <ul
            v-if="serverHealthChecks.length"
            class="server-health-list"
            aria-label="Пункты проверки"
          >
            <li
              v-for="c in serverHealthChecks"
              :key="c.id"
              class="server-health-item"
              :class="{
                'server-health-item--ok': c.ok,
                'server-health-item--fail': !c.ok,
              }"
            >
              <span class="server-health-mark" aria-hidden="true">{{ c.ok ? '✓' : '×' }}</span>
              <span class="server-health-line">
                <strong>{{ c.label }}</strong>
                <span
                  v-if="c.latency_ms != null"
                  class="server-health-lat"
                >· {{ c.latency_ms }} мс</span>
              </span>
              <span class="server-health-detail">{{ c.detail }}</span>
            </li>
          </ul>
        </div>
        <div class="cascade-overview" aria-label="Каскадные пары">
          <h3 class="cascade-overview-title">Каскад (вход РФ → внешний exit)</h3>
          <p class="cascade-muted cascade-provision-hint">
            Установка: сначала полный прогон на <strong>внешнем</strong> exit (Xray с REALITY). Затем на
            <strong>РФ-входе</strong> — «Xray» или полная установка: трафик пользователей уйдёт на exit по
            отдельному UUID. При смене пары в БД exit обновится в очереди sync Xray (если Redis доступен).
          </p>
          <p v-if="!serverCascadePairs.length && !ruEntryAwaitingCascade.length && !externalServersUnpaired.length" class="cascade-muted">
            Каскадов нет. Добавьте внешний сервер, при необходимости — отметьте вход (РФ) и привяжите exit.
          </p>
          <ul v-else class="cascade-pair-list">
            <li
              v-for="row in serverCascadePairs"
              :key="`pair-${row.entry.id}`"
              class="cascade-pair-item cascade-pair-item--ok"
            >
              <span class="cascade-pair-line">
                <strong>Вход (РФ)</strong> id {{ row.entry.id }}
                <span v-if="row.entry.name" class="cascade-muted"> · {{ row.entry.name }}</span>
                <span class="cascade-mono"> · {{ row.entry.host }}</span>
                <span class="cascade-arrow" aria-hidden="true"> → </span>
                <strong>Exit</strong> id {{ row.exit?.id ?? row.entry.cascade_next_server_id }}
                <span v-if="row.exit?.name" class="cascade-muted"> · {{ row.exit.name }}</span>
                <span v-if="row.exit" class="cascade-mono"> · {{ row.exit.host }}</span>
              </span>
            </li>
            <li
              v-for="s in ruEntryAwaitingCascade"
              :key="`ru-wait-${s.id}`"
              class="cascade-pair-item cascade-pair-item--wait"
            >
              <span class="cascade-pair-line">
                <strong>Вход (РФ)</strong> id {{ s.id }}{{ s.name ? ` · ${s.name}` : '' }}
                <span class="cascade-mono"> · {{ s.host }}</span>
                <span class="cascade-pair-hint">— внешний exit ещё не привязан (правка сервера)</span>
              </span>
            </li>
            <li
              v-for="s in externalServersUnpaired"
              :key="`ext-${s.id}`"
              class="cascade-pair-item cascade-pair-item--ext"
            >
              <span class="cascade-pair-line">
                <strong>Только внешний</strong> id {{ s.id }}{{ s.name ? ` · ${s.name}` : '' }}
                <span class="cascade-mono"> · {{ s.host }}</span>
                <span v-if="s.country" class="cascade-muted"> ({{ s.country }})</span>
              </span>
            </li>
          </ul>
        </div>
        <AdminTableWrap aria-label="Таблица серверов">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Страна</th>
              <th>Каскад</th>
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
              <td class="cascade-col">
                <span v-if="!s.is_cascade_ru_entry" class="cascade-pill">внешний</span>
                <template v-else-if="s.cascade_next_server_id">
                  <span class="cascade-pill cascade-pill--ru">РФ</span>
                  <span class="cascade-nowrap" title="cascade_next_server_id"
                    >→ {{ s.cascade_next_server_id }}</span
                  >
                </template>
                <span v-else class="cascade-pill cascade-pill--ru">РФ (без exit)</span>
              </td>
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
        </AdminTableWrap>
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
        <button
          type="button"
          class="dropdown-item"
          role="menuitem"
          :disabled="isServerProvisionBusy(serverMenuTarget)"
          title="С API: TCP к Xray, node_exporter, каскадный exit, сверка с БД (provision, ключи)"
          @click="withOpenServerMenu(pingServerReachability)"
        >
          {{
            serverPingId === serverMenuTarget.id
              ? 'Проверка…'
              : 'Полная проверка узла'
          }}
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
        <button
          type="button"
          class="dropdown-item"
          role="menuitem"
          :disabled="
            !canEnqueueReconcile(serverMenuTarget) ||
            isServerProvisionBusy(serverMenuTarget)
          "
          title="Только CAKE/fq_codel на uplink (без переустановки Xray и метрик); для узла, где софт уже стоит"
          @click="withOpenServerMenu(enqueueProvisionFairEgress)"
        >
          {{
            serverFairEgressId === serverMenuTarget.id
              ? 'Справедливость…'
              : 'Справедливость uplink'
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
        <div class="dropdown-sep" role="separator" />
        <button
          type="button"
          class="dropdown-item dropdown-item--danger"
          role="menuitem"
          :disabled="isServerProvisionBusy(serverMenuTarget)"
          title="Удалить запись сервера из БД"
          @click="withOpenServerMenu(deleteServer)"
        >
          {{
            deletingServerId === serverMenuTarget.id
              ? 'Удаление…'
              : 'Удалить сервер'
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
          section === 'users' ? 'modal-user-title' : 'modal-server-title'
        "
        @click.self="closeModal"
      >
        <div v-if="section === 'users'" class="modal">
          <h2 id="modal-user-title">{{ userModalTitle }}</h2>
          <form class="form" @submit.prevent="submitSaveUser">
            <label v-if="editingUserId == null" class="field">
              <span>Telegram ID (необязательно)</span>
              <input
                v-model="formTelegramId"
                type="text"
                inputmode="numeric"
                autocomplete="off"
                autocapitalize="none"
                spellcheck="false"
                placeholder="например 123456789"
              />
            </label>
            <div v-else class="field field-readonly">
              <span>Telegram</span>
              <p class="readonly-value">
                <template v-if="formTelegramId">{{ formTelegramId }}</template>
                <template v-else>—</template>
                <span v-if="editingUserTgUsername" class="muted">
                  @{{ editingUserTgUsername }}</span>
              </p>
              <button
                v-if="editingUserHasTelegramData"
                type="button"
                class="btn-secondary btn-tiny telegram-unlink-btn"
                :disabled="
                  creating ||
                  deletingUserId != null ||
                  clearTelegramBusy
                "
                @click="clearEditingUserTelegram"
              >
                {{
                  clearTelegramBusy ? 'Сброс…' : 'Сбросить Telegram'
                }}
              </button>
            </div>
            <label class="field" v-if="editingUserId != null">
              <span>Роль доступа</span>
              <select
                v-model="formAccountRole"
                class="field-select"
                aria-label="Роль пользователя"
              >
                <option value="client">Клиент (VPN)</option>
                <option value="manager">Менеджер (реферальные токены)</option>
                <option value="admin">Администратор</option>
              </select>
              <span class="field-hint"
                >Администратору нужен пароль (вход по email). Менеджер — только раздел рефералов.</span>
            </label>
            <label v-if="editingUserId != null" class="field">
              <span>Дата регистрации (UTC)</span>
              <input
                v-model="formRegisteredAt"
                type="text"
                class="field-date-ru"
                inputmode="numeric"
                maxlength="10"
                placeholder="ДД.ММ.ГГГГ"
                autocomplete="off"
                autocapitalize="none"
                spellcheck="false"
              />
              <span class="field-hint"
                >Календарный день в UTC, формат день.месяц.год. Пустое поле —
                сбросить дату (как у старых импортов).</span>
            </label>
            <label class="field">
              <span>Подписка до (необязательно)</span>
              <input
                v-model="formSubUntil"
                type="text"
                class="field-date-ru"
                inputmode="numeric"
                maxlength="10"
                placeholder="ДД.ММ.ГГГГ"
                autocomplete="off"
                autocapitalize="none"
                spellcheck="false"
              />
              <span class="field-hint">Формат: день.месяц.год</span>
            </label>
            <p v-if="createError" class="form-err">{{ createError }}</p>
            <div
              class="modal-actions"
              :class="{ 'modal-actions-split': editingUserId != null }"
            >
              <button
                v-if="editingUserId != null"
                type="button"
                class="btn-danger-modal"
                :disabled="
                  creating ||
                  deletingUserId === editingUserId ||
                  clearTelegramBusy
                "
                @click="deleteUserFromModal"
              >
                {{
                  deletingUserId === editingUserId
                    ? 'Удаление…'
                    : 'Удалить пользователя'
                }}
              </button>
              <div class="modal-actions-right">
                <button
                  type="button"
                  class="btn-secondary"
                  :disabled="
                    creating ||
                    deletingUserId != null ||
                    clearTelegramBusy
                  "
                  @click="closeModal"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  class="btn-primary"
                  :disabled="
                    creating ||
                    deletingUserId != null ||
                    clearTelegramBusy
                  "
                >
                  {{
                    creating
                      ? 'Сохранение…'
                      : editingUserId != null
                        ? 'Сохранить'
                        : 'Создать'
                  }}
                </button>
              </div>
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
              <div class="field field-cascade">
                <label class="field field-check">
                  <input v-model="formIsCascadeRuEntry" type="checkbox" />
                  <span>Вход (РФ) в каскаде — дальше трафик на внешний exit</span>
                </label>
                <p class="field-hint field-hint--cascade">
                  Можно сначала создать только внешний сервер (флажок снят), затем вход и
                  привязать exit. Цепь настраивается в БД, установка Xray на узлах — позже.
                </p>
                <label
                  v-show="formIsCascadeRuEntry"
                  class="field"
                >
                  <span>Внешний exit (id сервера)</span>
                  <select
                    v-model="formCascadeNextServerId"
                    class="cascade-exit-select"
                  >
                    <option value="">— не привязан (только договорились, что это вход РФ) —</option>
                    <option
                      v-for="c in cascadeExitCandidates(editingServerId)"
                      :key="c.id"
                      :value="String(c.id)"
                    >
                      #{{ c.id }}{{ c.name ? ` ${c.name}` : '' }} — {{ c.host }}
                    </option>
                  </select>
                </label>
                <p
                  v-if="
                    formIsCascadeRuEntry &&
                    !cascadeExitCandidates(editingServerId).length
                  "
                  class="field-hint"
                >
                  Нет внешних кандидатов (нужен узел без флажка «вход РФ»). Создайте такой
                  сервер и сохраните снова.
                </p>
              </div>
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
            <div
              class="modal-actions"
              :class="{ 'modal-actions-split': editingServerId != null }"
            >
              <button
                v-if="editingServerId != null"
                type="button"
                class="btn-danger-modal"
                :disabled="creating || deletingServerId === editingServerId"
                @click="deleteServerFromModal"
              >
                {{
                  deletingServerId === editingServerId
                    ? 'Удаление…'
                    : 'Удалить сервер'
                }}
              </button>
              <div class="modal-actions-right">
                <button
                  type="button"
                  class="btn-secondary"
                  :disabled="creating || deletingServerId != null"
                  @click="closeModal"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  class="btn-primary"
                  :disabled="creating || deletingServerId != null"
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
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </AdminPageShell>
</template>

<style scoped>
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

.extend-active-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.extend-active-label {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.85rem;
  color: var(--muted);
}

.extend-active-label-text {
  white-space: nowrap;
}

.extend-active-input {
  width: 4.25rem;
  padding: 0.35rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  color: var(--text-h);
  font-variant-numeric: tabular-nums;
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
  margin-bottom: 1rem;
}
.stats-value {
  margin: 0;
  font-size: 0.92rem;
  color: var(--muted);
}
.stats-value.error {
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

.btn-danger-modal {
  font: inherit;
  font-weight: 700;
  font-size: 0.88rem;
  padding: 0.5rem 0.95rem;
  border-radius: 10px;
  border: 1px solid rgba(220, 38, 38, 0.45);
  color: var(--danger);
  background: var(--danger-soft);
  cursor: pointer;
}
.btn-danger-modal:hover:not(:disabled) {
  border-color: var(--danger);
  filter: brightness(1.02);
}
.btn-danger-modal:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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

.provision-banner .server-health-summary {
  margin: 0 0 0.55rem;
  line-height: 1.45;
}

.server-health-list {
  list-style: none;
  margin: 0;
  padding: 0.35rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.8rem;
  line-height: 1.4;
  border-top: 1px solid var(--card-border, rgba(128, 128, 128, 0.25));
}

.server-health-item {
  display: grid;
  grid-template-columns: 1.1em 1fr;
  gap: 0.35rem 0.5rem;
  align-items: start;
}

.server-health-line {
  grid-column: 2;
  display: block;
  color: var(--text-h);
}

.server-health-lat {
  color: var(--muted);
  font-weight: 400;
  margin-left: 0.2rem;
}

.server-health-detail {
  grid-column: 2;
  display: block;
  color: var(--muted);
  font-size: 0.9em;
}

.server-health-item--ok .server-health-mark {
  color: #1a7f37;
}

.server-health-item--fail .server-health-mark {
  color: var(--danger);
}

.server-health-item--ok .server-health-line strong,
.server-health-item--fail .server-health-line strong {
  font-weight: 600;
}

.field-readonly .telegram-unlink-btn {
  margin-top: 0.45rem;
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

.mono .btn-secondary {
  margin-top: 0.45rem;
  margin-right: 0.35rem;
}
.link-cell {
  font-size: 0.78rem;
}
.link-cell .btn-secondary {
  margin-right: 0.35rem;
}

.table th.num {
  text-align: right;
}
.traffic-link-cell {
  text-align: right;
  vertical-align: middle;
}
.traffic-link-cell .user-analytics-link {
  font-variant-numeric: tabular-nums;
}

.user-analytics-link {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;
}
.user-analytics-link:hover {
  text-decoration: underline;
  color: var(--accent-hover);
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 12, 9, 0.55);
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

.field-date-ru {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
  letter-spacing: 0.02em;
}

.field-select {
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-weight: 400;
  cursor: pointer;
  max-width: 100%;
}

.field-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.field-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--muted);
  line-height: 1.35;
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

.modal-actions-split {
  justify-content: space-between;
  align-items: center;
}

.modal-actions-right {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.cascade-overview {
  margin: 0 0 1rem;
  padding: 0.9rem 1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
}

.cascade-overview-title {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-h);
}

.cascade-provision-hint {
  margin: 0 0 0.6rem;
  font-size: 0.8rem;
  line-height: 1.45;
}

.cascade-muted {
  margin: 0;
  font-size: 0.85rem;
  color: var(--muted);
  line-height: 1.4;
}

.cascade-pair-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.cascade-pair-item {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.4;
  padding: 0.4rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
}

.cascade-pair-item--ok {
  border-left: 3px solid var(--accent);
}

.cascade-pair-item--wait {
  border-left: 3px solid #b8860b;
}

.cascade-pair-item--ext {
  border-left: 3px solid var(--muted);
}

.cascade-pair-line {
  display: block;
}

.cascade-pair-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--muted);
  font-style: italic;
}

.cascade-mono {
  font-family: ui-monospace, monospace;
  font-size: 0.78em;
  font-weight: 400;
  color: var(--text-h);
}

.cascade-arrow {
  color: var(--accent);
  font-weight: 800;
  padding: 0 0.1rem;
}

.cascade-exit-select {
  width: 100%;
  max-width: 100%;
  font: inherit;
  font-size: 0.9rem;
  font-weight: 500;
  padding: 0.5rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  color: var(--text-h);
}

.field-hint--cascade {
  margin-top: 0.1rem;
}

.cascade-col {
  font-size: 0.8rem;
  white-space: normal;
  max-width: 8.5rem;
}

.cascade-nowrap {
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
  white-space: nowrap;
}

.cascade-pill {
  display: inline-block;
  margin-right: 0.25rem;
  padding: 0.1rem 0.35rem;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--muted);
  border: 1px solid var(--card-border);
  background: var(--card-bg);
}

.cascade-pill--ru {
  color: #b86a1a;
  border-color: rgba(184, 106, 26, 0.35);
  background: rgba(184, 106, 26, 0.08);
}
</style>
