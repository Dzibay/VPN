<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AdminChartsGrid from '../components/AdminChartsGrid.vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import ReferralTokenGroupModal from '../components/ReferralTokenGroupModal.vue'
import ReferralTokensGroupedTable from '../components/ReferralTokensGroupedTable.vue'
import AppModal from '../components/AppModal.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import StatWidget from '../components/StatWidget.vue'
import { fetchJson } from '../api/client.js'
import { rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { useTableSort } from '../utils/adminTableSort.js'
import {
  chartLineCountTooltipLabel,
  formatChartCountTick,
} from '../utils/adminChartFormatters.js'
import { formatMskCalendarDayShort } from '../utils/mskDate.js'

const route = useRoute()
const rows = ref([])
/** @type {import('vue').Ref<Array<{ id: number; name: string; color: string; sort_order: number; link_ids: number[] }>>} */
const groups = ref([])
const groupsLoading = ref(false)
const groupsError = ref(null)
const groupModalOpen = ref(false)
const groupModalBusy = ref(false)
const groupModalError = ref(null)
/** @type {import('vue').Ref<{ id: number; name: string; color: string; link_ids: number[] } | null>} */
const editingGroup = ref(null)
/** @type {import('vue').Ref<import('vue').ComponentPublicInstance | null>} */
const groupedTableRef = ref(null)
const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<{ direct: { total: number; with_telegram_id: number; without_telegram_id: number }; channel_links: { total: number; with_telegram_id: number; without_telegram_id: number }; user_referrals: { total: number; with_telegram_id: number; without_telegram_id: number } } | null>} */
const trafficStats = ref(null)
const trafficStatsLoading = ref(false)
const trafficStatsError = ref(null)

const tokenRegDays = ref(30)
/** @type {import('vue').Ref<{ dates: string[]; min_registrations: number; total_registrations_by_day: number[]; tokens: Array<{ referral_link_id: number; token: string; registrations_count: number; registrations_by_day: number[] }> } | null>} */
const tokenRegBundle = ref(null)
const tokenRegLoading = ref(false)
const tokenRegError = ref(null)

/** @type {import('vue').Ref<{ dates: string[]; direct: number[]; direct_bot: number[]; direct_site: number[]; channel_links: number[]; user_referrals: number[]; total_registrations_by_day: number[] } | null>} */
const sourceRegBundle = ref(null)
const sourceRegLoading = ref(false)
const sourceRegError = ref(null)

const tokenRegDayOptions = [
  { value: 7, label: '7 дней' },
  { value: 30, label: '30 дней' },
  { value: 60, label: '60 дней' },
  { value: 90, label: '90 дней' },
]

const TOKEN_LINE_RGB = [
  [56, 189, 248],
  [167, 139, 250],
  [129, 140, 248],
  [45, 212, 191],
  [52, 211, 153],
  [244, 114, 182],
  [245, 158, 11],
  [236, 72, 153],
  [34, 197, 94],
  [251, 146, 60],
  [99, 102, 241],
  [20, 184, 166],
]

const SOURCE_LINE_RGB = {
  direct: [148, 163, 184],
  direct_bot: [56, 189, 248],
  direct_site: [167, 139, 250],
  channel_links: [52, 211, 153],
  user_referrals: [245, 158, 11],
}

const tokenRegLabels = computed(() =>
  (tokenRegBundle.value?.dates ?? []).map((d) => formatMskCalendarDayShort(d)),
)

const tokenRegDatasets = computed(() => {
  const data = tokenRegBundle.value
  if (!data?.dates?.length) return []

  const total = {
    label: 'Суммарно',
    data: data.total_registrations_by_day ?? [],
    rgb: rgbTupleFromVar('--accent', '#58d68d'),
    filled: true,
    borderWidth: 2.75,
  }

  const perToken = (data.tokens ?? []).map((t, idx) => {
    const row = rows.value.find((r) => r.id === t.referral_link_id)
    const isUser = row?.owner_kind === 'user'
    return {
      label: `${t.token} (${t.registrations_count} рег.)`,
      data: t.registrations_by_day ?? [],
      rgb: /** @type {[number, number, number]} */ ([
        ...TOKEN_LINE_RGB[idx % TOKEN_LINE_RGB.length],
      ]),
      filled: false,
      borderWidth: 1.75,
      hidden: isUser,
    }
  })

  return [total, ...perToken]
})

const tokenRegHasData = computed(() => {
  const data = tokenRegBundle.value
  if (!data?.dates?.length) return false
  return (data.tokens ?? []).some((t) =>
    (t.registrations_by_day ?? []).some((v) => Number(v) > 0),
  )
})

const tokenRegChartHint = computed(() => {
  const minReg = tokenRegBundle.value?.min_registrations ?? 10
  const count = tokenRegBundle.value?.tokens?.length ?? 0
  return `Токены с более чем ${minReg} регистрациями (${count} на графике). Суточные регистрации по календарным дням Europe/Moscow.`
})

const tokenRegAriaLabel =
  'По дням МСК: число регистраций по реферальным токенам с более чем 10 регистрациями'

function tokenRegTooltipTitle(i) {
  const d = tokenRegBundle.value?.dates?.[i]
  if (!d) return tokenRegLabels.value[i] ?? ''
  return `${formatMskCalendarDayShort(d)} (МСК)`
}

async function loadTokenRegChart() {
  tokenRegLoading.value = true
  tokenRegError.value = null
  try {
    tokenRegBundle.value = await fetchJson(
      `/api/referral-links/registrations-by-day?days=${encodeURIComponent(tokenRegDays.value)}&min_registrations=10`,
    )
  } catch (e) {
    tokenRegError.value = e.message || String(e)
    tokenRegBundle.value = null
  } finally {
    tokenRegLoading.value = false
  }
}

const sourceRegLabels = computed(() =>
  (sourceRegBundle.value?.dates ?? []).map((d) => formatMskCalendarDayShort(d)),
)

const sourceRegDatasets = computed(() => {
  const data = sourceRegBundle.value
  if (!data?.dates?.length) return []

  const total = {
    label: 'Суммарно',
    data: data.total_registrations_by_day ?? [],
    rgb: rgbTupleFromVar('--accent', '#58d68d'),
    filled: true,
    borderWidth: 2.75,
  }

  const series = [
    { key: 'direct', label: 'Прямой трафик' },
    { key: 'direct_bot', label: 'Прямой трафик бота' },
    { key: 'direct_site', label: 'Прямой трафик сайта' },
    { key: 'channel_links', label: 'По созданным ссылкам' },
    { key: 'user_referrals', label: 'Приглашения пользователей' },
  ]

  const perSource = series.map(({ key, label }) => ({
    label,
    data: data[key] ?? [],
    rgb: /** @type {[number, number, number]} */ ([...SOURCE_LINE_RGB[key]]),
    filled: false,
    borderWidth: 1.75,
  }))

  return [total, ...perSource]
})

const sourceRegHasData = computed(() => {
  const data = sourceRegBundle.value
  if (!data?.dates?.length) return false
  const keys = ['direct', 'direct_bot', 'direct_site', 'channel_links', 'user_referrals']
  return keys.some((key) => (data[key] ?? []).some((v) => Number(v) > 0))
})

const sourceRegChartHint =
  'Суточные регистрации по источникам трафика. Календарные дни Europe/Moscow.'

const sourceRegAriaLabel =
  'По дням МСК: число регистраций по источникам — прямой трафик, созданные ссылки, приглашения'

function sourceRegTooltipTitle(i) {
  const d = sourceRegBundle.value?.dates?.[i]
  if (!d) return sourceRegLabels.value[i] ?? ''
  return `${formatMskCalendarDayShort(d)} (МСК)`
}

async function loadSourceRegChart() {
  sourceRegLoading.value = true
  sourceRegError.value = null
  try {
    sourceRegBundle.value = await fetchJson(
      `/api/referral-links/traffic-registrations-by-day?days=${encodeURIComponent(tokenRegDays.value)}`,
    )
  } catch (e) {
    sourceRegError.value = e.message || String(e)
    sourceRegBundle.value = null
  } finally {
    sourceRegLoading.value = false
  }
}

const modalOpen = ref(false)
const creating = ref(false)
const createError = ref(null)
/** id редактируемой строки; null — режим создания */
const editingId = ref(null)

const formLinkKind = ref('channel')
/** Именованный источник (github, bot1, campaign, …); не использовать «user» здесь */
const formChannelKind = ref('campaign')
const formOwnerUserId = ref('')
const formToken = ref('')

const modalTitle = computed(() =>
  editingId.value != null ? 'Редактировать токен' : 'Новый реферальный токен',
)

async function loadTrafficStats() {
  trafficStatsLoading.value = true
  trafficStatsError.value = null
  try {
    trafficStats.value = await fetchJson('/api/referral-links/traffic-stats')
  } catch (e) {
    trafficStatsError.value = e.message || String(e)
    trafficStats.value = null
  } finally {
    trafficStatsLoading.value = false
  }
}

async function loadGroups() {
  groupsLoading.value = true
  groupsError.value = null
  try {
    groups.value = await fetchJson('/api/referral-link-groups')
  } catch (e) {
    groupsError.value = e.message || String(e)
    groups.value = []
  } finally {
    groupsLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await fetchJson('/api/referral-links')
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function reloadAll() {
  await Promise.all([
    load(),
    loadGroups(),
    loadTrafficStats(),
    loadTokenRegChart(),
    loadSourceRegChart(),
  ])
}

function openModal() {
  createError.value = null
  editingId.value = null
  formLinkKind.value = 'channel'
  formChannelKind.value = 'campaign'
  formOwnerUserId.value = ''
  formToken.value = ''
  modalOpen.value = true
}

function openEditModal(r) {
  createError.value = null
  editingId.value = r.id
  if (r.owner_kind === 'user') {
    formLinkKind.value = 'user'
    formOwnerUserId.value = String(r.owner_user_id ?? '')
    formChannelKind.value = 'campaign'
  } else {
    formLinkKind.value = 'channel'
    formChannelKind.value = r.owner_kind
    formOwnerUserId.value = ''
  }
  formToken.value = r.token
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
  editingId.value = null
}

async function submitModal() {
  createError.value = null
  let ownerKind
  let ownerUserId = null

  if (formLinkKind.value === 'user') {
    ownerKind = 'user'
    const raw = String(formOwnerUserId.value).trim()
    if (!raw) {
      createError.value = 'Укажите id пользователя-владельца'
      return
    }
    const n = Number(raw)
    if (!Number.isFinite(n) || n < 1) {
      createError.value = 'Некорректный id пользователя'
      return
    }
    ownerUserId = Math.floor(n)
  } else {
    ownerKind = String(formChannelKind.value).trim()
    if (!ownerKind) {
      createError.value = 'Укажите название источника (например github, bot1, campaign)'
      return
    }
    if (ownerKind === 'user') {
      createError.value =
        'Слово «user» зарезервировано: выберите режим «Пользователь из БД» и укажите id'
      return
    }
  }

  const tokenTrim = String(formToken.value).trim()
  if (editingId.value != null && !tokenTrim) {
    createError.value = 'Укажите токен'
    return
  }

  creating.value = true
  try {
    if (editingId.value != null) {
      await fetchJson(`/api/referral-links/${editingId.value}`, {
        method: 'PATCH',
        body: JSON.stringify({
          owner_kind: ownerKind,
          owner_user_id: ownerUserId,
          token: tokenTrim,
        }),
      })
    } else {
      await fetchJson('/api/referral-links', {
        method: 'POST',
        body: JSON.stringify({
          owner_kind: ownerKind,
          owner_user_id: ownerUserId,
          token: tokenTrim.length ? tokenTrim : null,
        }),
      })
    }
    modalOpen.value = false
    editingId.value = null
    await reloadAll()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

function openCreateGroupModal() {
  groupModalError.value = null
  editingGroup.value = null
  groupModalOpen.value = true
}

function openEditGroupModal(group) {
  groupModalError.value = null
  editingGroup.value = group
  groupModalOpen.value = true
}

function closeGroupModal() {
  if (groupModalBusy.value) return
  groupModalOpen.value = false
  editingGroup.value = null
}

async function submitGroupModal(payload) {
  groupModalBusy.value = true
  groupModalError.value = null
  try {
    if (editingGroup.value?.id != null) {
      await fetchJson(`/api/referral-link-groups/${editingGroup.value.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: payload.name,
          color: payload.color,
        }),
      })
      await fetchJson(`/api/referral-link-groups/${editingGroup.value.id}/members`, {
        method: 'PUT',
        body: JSON.stringify({ link_ids: payload.link_ids }),
      })
    } else {
      await fetchJson('/api/referral-link-groups', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    }
    groupModalOpen.value = false
    editingGroup.value = null
    groupedTableRef.value?.clearSelection?.()
    await Promise.all([load(), loadGroups()])
  } catch (e) {
    groupModalError.value = e.message || String(e)
  } finally {
    groupModalBusy.value = false
  }
}

async function deleteGroup(group) {
  if (
    !window.confirm(
      `Удалить группу «${group.name}»? Токены останутся в системе, но выйдут из группы.`,
    )
  ) {
    return
  }
  groupModalBusy.value = true
  error.value = null
  try {
    await fetchJson(`/api/referral-link-groups/${group.id}`, { method: 'DELETE' })
    await Promise.all([load(), loadGroups()])
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    groupModalBusy.value = false
  }
}

async function addLinksToGroup({ groupId, linkIds }) {
  if (!linkIds?.length) return
  groupModalBusy.value = true
  error.value = null
  try {
    await fetchJson(`/api/referral-link-groups/${groupId}/members`, {
      method: 'POST',
      body: JSON.stringify({ link_ids: linkIds }),
    })
    groupedTableRef.value?.clearSelection?.()
    await Promise.all([load(), loadGroups()])
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    groupModalBusy.value = false
  }
}

async function removeLinkFromGroup({ groupId, linkId }) {
  groupModalBusy.value = true
  error.value = null
  try {
    await fetchJson(`/api/referral-link-groups/${groupId}/members/${linkId}`, {
      method: 'DELETE',
    })
    await Promise.all([load(), loadGroups()])
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    groupModalBusy.value = false
  }
}

function isUserToken(r) {
  return r.owner_kind === 'user'
}

const userTokenCount = computed(() => rows.value.filter(isUserToken).length)

const rowsForTable = computed(() =>
  showUserTokens.value ? rows.value : rows.value.filter((r) => !isUserToken(r)),
)

const linksForGroupPicker = computed(() => rowsForTable.value)

const referralSortAccessors = {
  id: (r) => r.id,
  token: (r) => String(r.token ?? '').toLowerCase(),
  owner: (r) => {
    if (r.owner_kind === 'user') {
      return r.owner_user_id != null ? r.owner_user_id : -1
    }
    return String(r.owner_kind ?? '').toLowerCase()
  },
  clicks_count: (r) => Number(r.clicks_count) || 0,
  registrations_count: (r) => Number(r.registrations_count) || 0,
  payments_count: (r) => Number(r.payments_count) || 0,
  revenue_net: (r) => Number(r.revenue_net) || 0,
  created_at: (r) => Date.parse(r.created_at) || 0,
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(
  rowsForTable,
  referralSortAccessors,
)

const copyHint = ref(null)
/** Показывать персональные токены (owner_kind = user) в таблице */
const showUserTokens = ref(false)
/** id строки во время DELETE */
const deletingId = ref(null)
/** id строки с временной подсветкой после перехода из других разделов */
const highlightRowId = ref(null)

function referralHighlightFromRoute() {
  const raw = route.query.highlight
  const s = raw == null ? '' : Array.isArray(raw) ? raw[0] : raw
  if (s === '') return null
  const n = Number(s)
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : null
}
async function copyUrl(url) {
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    copyHint.value = 'Скопировано'
    window.setTimeout(() => {
      copyHint.value = null
    }, 2000)
  } catch {
    copyHint.value = null
  }
}

async function removeReferral(r) {
  if (
    !window.confirm(
      `Удалить реферальный токен «${r.token}»? Статистика по нему пропадёт; у пользователей поле привязки к ссылке сбросится.`,
    )
  ) {
    return
  }
  deletingId.value = r.id
  error.value = null
  try {
    await fetchJson(`/api/referral-links/${r.id}`, { method: 'DELETE' })
    await reloadAll()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    deletingId.value = null
  }
}

watch(tokenRegDays, () => {
  void loadTokenRegChart()
  void loadSourceRegChart()
})

watch(
  () =>
    `${loading.value}:${
      route.query.highlight ?? ''
    }:${rows.value.map((r) => r.id).join(',')}`,
  async () => {
    if (loading.value) return
    const hid = referralHighlightFromRoute()
    highlightRowId.value = null
    if (hid == null) return
    if (!rows.value.some((r) => r.id === hid)) return
    await nextTick()
    const el = document.getElementById(`ref-${hid}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    highlightRowId.value = hid
    window.setTimeout(() => {
      if (highlightRowId.value === hid) highlightRowId.value = null
    }, 3400)
  },
  { flush: 'post' },
)

onMounted(() => {
  void reloadAll()
})
</script>

<template>
  <AdminStaffShell title="Реферальные токены">
    <template #headerExtras>
      <div class="head-row">
        <h2 class="section-heading">Конверсия по токенам</h2>
        <div class="head-actions">
          <AppRefreshButton
            :busy="loading || groupsLoading || groupModalBusy || trafficStatsLoading || tokenRegLoading || sourceRegLoading"
            @click="reloadAll"
          />
          <button type="button" class="btn-primary" @click="openModal">
            Новый токен
          </button>
        </div>
      </div>
    </template>

    <section class="stats widgets-row" aria-live="polite">
      <div class="widgets-grid widgets-grid--cols-4">
        <StatWidget title="Прямой трафик" aria-label="Прямой трафик без реферальной ссылки">
          <p class="stat-widget-value">
            {{
              trafficStatsLoading
                ? '…'
                : trafficStatsError
                  ? '—'
                  : (trafficStats?.direct?.total ?? 0)
            }}
          </p>
          <p v-if="!trafficStatsLoading && !trafficStatsError" class="stat-widget-meta">
            Пользователи без реферальной ссылки
          </p>
          <dl
            v-if="!trafficStatsLoading && !trafficStatsError"
            class="stat-widget-split"
          >
            <div>
              <dt>Telegram</dt>
              <dd>{{ trafficStats?.direct?.with_telegram_id ?? 0 }}</dd>
            </div>
            <div>
              <dt>Сайт</dt>
              <dd>{{ trafficStats?.direct?.without_telegram_id ?? 0 }}</dd>
            </div>
          </dl>
          <p v-else-if="trafficStatsError" class="stat-widget-err">{{ trafficStatsError }}</p>
        </StatWidget>
        <StatWidget
          title="По созданным ссылкам"
          aria-label="Пользователи, пришедшие по созданным реферальным ссылкам"
        >
          <p class="stat-widget-value">
            {{
              trafficStatsLoading
                ? '…'
                : trafficStatsError
                  ? '—'
                  : (trafficStats?.channel_links?.total ?? 0)
            }}
          </p>
          <p v-if="!trafficStatsLoading && !trafficStatsError" class="stat-widget-meta">
            Кампании, каналы и внешние токены
          </p>
          <dl
            v-if="!trafficStatsLoading && !trafficStatsError"
            class="stat-widget-split"
          >
            <div>
              <dt>Telegram</dt>
              <dd>{{ trafficStats?.channel_links?.with_telegram_id ?? 0 }}</dd>
            </div>
            <div>
              <dt>Сайт</dt>
              <dd>{{ trafficStats?.channel_links?.without_telegram_id ?? 0 }}</dd>
            </div>
          </dl>
        </StatWidget>
        <StatWidget
          title="Приглашения пользователей"
          aria-label="Пользователи, приглашённые другими пользователями"
        >
          <p class="stat-widget-value">
            {{
              trafficStatsLoading
                ? '…'
                : trafficStatsError
                  ? '—'
                  : (trafficStats?.user_referrals?.total ?? 0)
            }}
          </p>
          <p v-if="!trafficStatsLoading && !trafficStatsError" class="stat-widget-meta">
            По персональным реферальным ссылкам
          </p>
          <dl
            v-if="!trafficStatsLoading && !trafficStatsError"
            class="stat-widget-split"
          >
            <div>
              <dt>Telegram</dt>
              <dd>{{ trafficStats?.user_referrals?.with_telegram_id ?? 0 }}</dd>
            </div>
            <div>
              <dt>Сайт</dt>
              <dd>{{ trafficStats?.user_referrals?.without_telegram_id ?? 0 }}</dd>
            </div>
          </dl>
        </StatWidget>
        <StatWidget title="Токены" aria-label="Число реферальных токенов">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : rowsForTable.length }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">
            {{
              userTokenCount > 0 && !showUserTokens
                ? `В таблице · ${userTokenCount} пользовательских скрыто`
                : 'Записей в таблице'
            }}
          </p>
        </StatWidget>
      </div>
      <p v-if="copyHint" class="copy-hint">{{ copyHint }}</p>
    </section>

    <section class="token-reg-section" aria-label="Графики регистраций">
      <div class="chart-toolbar">
        <label class="days-field">
          <span class="days-label">Период</span>
          <select
            v-model.number="tokenRegDays"
            class="days-select"
            :disabled="tokenRegLoading || sourceRegLoading"
          >
            <option v-for="o in tokenRegDayOptions" :key="o.value" :value="o.value">
              {{ o.label }}
            </option>
          </select>
        </label>
      </div>
      <AdminChartsGrid class="admin-charts-grid--no-top-margin">
        <AdminLineChartPanel
          title="Регистрации по токенам"
          unit-label="рег. / сутки"
          :hint="tokenRegChartHint"
          :aria-label="tokenRegAriaLabel"
          :loading="tokenRegLoading"
          :error="tokenRegError"
          :has-data="tokenRegHasData"
          y-title="Регистрации за сутки"
          y-grace="8%"
          :labels="tokenRegLabels"
          :datasets="tokenRegDatasets"
          :format-y-tick="formatChartCountTick"
          :get-tooltip-title="tokenRegTooltipTitle"
          :get-tooltip-label="chartLineCountTooltipLabel"
        >
          <template #empty>
            <p class="empty-hint">
              Нет регистраций по токенам с более чем 10 регистрациями за выбранный период.
            </p>
          </template>
        </AdminLineChartPanel>
        <AdminLineChartPanel
          title="Регистрации по источникам"
          unit-label="рег. / сутки"
          :hint="sourceRegChartHint"
          :aria-label="sourceRegAriaLabel"
          :loading="sourceRegLoading"
          :error="sourceRegError"
          :has-data="sourceRegHasData"
          y-title="Регистрации за сутки"
          y-grace="8%"
          :labels="sourceRegLabels"
          :datasets="sourceRegDatasets"
          :format-y-tick="formatChartCountTick"
          :get-tooltip-title="sourceRegTooltipTitle"
          :get-tooltip-label="chartLineCountTooltipLabel"
        >
          <template #empty>
            <p class="empty-hint">
              Нет регистраций по источникам трафика за выбранный период.
            </p>
          </template>
        </AdminLineChartPanel>
      </AdminChartsGrid>
    </section>

    <div
      v-if="!loading && !error && userTokenCount > 0"
      class="admin-table-toolbar"
      role="toolbar"
      aria-label="Вид таблицы реферальных токенов"
    >
      <button
        type="button"
        class="btn-icon-toggle"
        :class="{ 'btn-icon-toggle--active': showUserTokens }"
        :aria-pressed="showUserTokens"
        :title="
          showUserTokens
            ? 'Скрыть персональные токены пользователей'
            : 'Показать персональные токены пользователей'
        "
        @click="showUserTokens = !showUserTokens"
      >
        <span class="btn-icon-toggle__icon" aria-hidden="true">
          <svg
            v-if="showUserTokens"
            class="btn-icon-toggle__svg"
            viewBox="0 0 24 24"
            width="18"
            height="18"
          >
            <path
              fill="currentColor"
              d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-5-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"
            />
          </svg>
          <svg
            v-else
            class="btn-icon-toggle__svg"
            viewBox="0 0 24 24"
            width="18"
            height="18"
          >
            <path
              fill="currentColor"
              d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"
            />
          </svg>
        </span>
        <span class="btn-icon-toggle__text">{{
          showUserTokens ? 'Пользовательские видны' : 'Пользовательские скрыты'
        }}</span>
      </button>
      <span class="admin-table-toolbar-meta">{{ userTokenCount }} персональных</span>
    </div>
    <p
      v-if="
        !loading &&
        !error &&
        rows.length > 0 &&
        rowsForTable.length === 0 &&
        !showUserTokens
      "
      class="table-filter-hint muted"
    >
      Все записи — персональные токены пользователей. Включите показ кнопкой с иконкой глаза
      выше.
    </p>

    <ReferralTokensGroupedTable
      ref="groupedTableRef"
      :rows="sortedRows"
      :groups="groups"
      :loading="loading || groupsLoading"
      :error="error || groupsError"
      :sort-key="sortKey"
      :sort-dir="sortDir"
      :highlight-row-id="highlightRowId"
      :deleting-id="deletingId"
      :group-busy="groupModalBusy"
      @sort="toggleSort"
      @copy-url="copyUrl"
      @edit-token="openEditModal"
      @delete-token="removeReferral"
      @create-group="openCreateGroupModal"
      @edit-group="openEditGroupModal"
      @delete-group="deleteGroup"
      @add-to-group="addLinksToGroup"
      @remove-from-group="removeLinkFromGroup"
    />

    <ReferralTokenGroupModal
      :open="groupModalOpen"
      :busy="groupModalBusy"
      :error="groupModalError"
      :editing-group="editingGroup"
      :available-links="linksForGroupPicker"
      @close="closeGroupModal"
      @submit="submitGroupModal"
    />

    <AppModal
      v-if="modalOpen"
      :title="modalTitle"
      :max-width="420"
      :busy="creating"
      @close="closeModal"
    >
      <form class="modal-form" @submit.prevent="submitModal">
        <label class="field">
          <span>Как задать источник</span>
          <select v-model="formLinkKind" class="input-like">
            <option value="channel">Именованный источник (свой ярлык)</option>
            <option value="user">Пользователь из БД (owner_kind = user)</option>
          </select>
        </label>
        <label v-if="formLinkKind === 'channel'" class="field">
          <span>Название источника (owner_kind)</span>
          <input
            v-model="formChannelKind"
            type="text"
            class="input-like mono"
            placeholder="github, bot1, campaign…"
            maxlength="64"
            autocomplete="off"
            spellcheck="false"
          />
        </label>
        <p v-if="formLinkKind === 'channel'" class="field-hint">
          Латиница, цифры, <code class="inline-code">_</code> и <code class="inline-code">-</code>,
          длина до 64. Не используйте ярлык <code class="inline-code">user</code> — для этого второй режим.
        </p>
        <label v-if="formLinkKind === 'user'" class="field">
          <span>ID пользователя</span>
          <input
            v-model="formOwnerUserId"
            type="number"
            min="1"
            step="1"
            class="input-like"
            placeholder="Например 42"
            autocomplete="off"
          />
        </label>
        <label class="field">
          <span>Токен{{ editingId ? '' : ' (необязательно)' }}</span>
          <input
            v-model="formToken"
            type="text"
            class="input-like mono"
            :placeholder="editingId ? 'Обязательно при редактировании' : 'Пусто — сгенерировать автоматически'"
            maxlength="64"
            autocomplete="off"
            spellcheck="false"
          />
        </label>
        <p v-if="editingId" class="field-hint">
          После смены токена ссылки с прежним <code class="inline-code">ref</code> / <code class="inline-code">start</code> больше не относятся к этой записи.
        </p>
        <p v-else class="field-hint">
          Если задаёте токен вручную: только A–Z, a–z, 0–9 и _, длина 4–64 (Telegram
          <code class="inline-code">start</code>).
        </p>
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
          <button type="submit" class="btn-primary" :disabled="creating">
            {{
              creating
                ? editingId
                  ? 'Сохранение…'
                  : 'Создание…'
                : editingId
                  ? 'Сохранить'
                  : 'Создать'
            }}
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
/* Здесь split идёт после meta-текста — нужен верхний отступ (в admin-ui.css он 0). */
.stat-widget-split {
  margin-top: 0.75rem;
}
.stat-widget-err {
  margin: 0.5rem 0 0;
  font-size: 0.82rem;
  color: var(--danger);
}
.copy-hint {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--accent);
  font-weight: 600;
}
.token-reg-section {
  margin-bottom: 1rem;
}
.chart-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem 1rem;
  margin-bottom: 0.35rem;
}
.days-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.days-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}
.days-select {
  min-width: 8.5rem;
  padding: 0.45rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 0.88rem;
}
.table-filter-hint {
  margin: 0 0 0.65rem;
  font-size: 0.85rem;
}
</style>
