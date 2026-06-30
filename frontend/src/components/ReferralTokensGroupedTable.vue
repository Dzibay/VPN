<script setup>
import { computed, ref, watch } from 'vue'
import AdminHighlightListLink from './AdminHighlightListLink.vue'
import AdminSortTh from './AdminSortTh.vue'
import AdminTableWrap from './AdminTableWrap.vue'
import RowActionsDropdown from './RowActionsDropdown.vue'
import { sitePublicUrl } from '../api/client.js'

const EXPANDED_STORAGE_KEY = 'referral-admin-expanded-groups'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  sortKey: { type: String, default: 'id' },
  sortDir: { type: String, default: 'desc' },
  highlightRowId: { type: Number, default: null },
  deletingId: { type: Number, default: null },
  groupBusy: { type: Boolean, default: false },
})

const emit = defineEmits([
  'sort',
  'copy-url',
  'edit-token',
  'delete-token',
  'create-group',
  'edit-group',
  'delete-group',
  'add-to-group',
  'remove-from-group',
])

const selectedLinkIds = ref(new Set())
const expandedGroupIds = ref(new Set())
const addToGroupOpen = ref(false)

function loadExpandedGroups() {
  try {
    const raw = localStorage.getItem(EXPANDED_STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((x) => Number.isFinite(Number(x))).map((x) => Number(x)))
  } catch {
    return new Set()
  }
}

function persistExpandedGroups() {
  localStorage.setItem(
    EXPANDED_STORAGE_KEY,
    JSON.stringify([...expandedGroupIds.value]),
  )
}

watch(
  () => props.groups.map((g) => g.id).join(','),
  () => {
    const known = new Set(props.groups.map((g) => g.id))
    expandedGroupIds.value = new Set(
      [...expandedGroupIds.value].filter((id) => known.has(id)),
    )
  },
  { immediate: true },
)

if (expandedGroupIds.value.size === 0 && props.groups.length > 0) {
  expandedGroupIds.value = loadExpandedGroups()
}

function fmtDatePart(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('ru-RU', { dateStyle: 'short' })
}

function fmtTimePart(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('ru-RU', { timeStyle: 'medium' })
}

function fmtMoney(v) {
  const n = Number(String(v ?? '').replace(',', '.'))
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function paymentConversionPct(payments, registrations) {
  const pay = Number(payments) || 0
  const reg = Number(registrations) || 0
  if (reg <= 0) return null
  return (pay / reg) * 100
}

function fmtConversionPct(payments, registrations) {
  const pct = paymentConversionPct(payments, registrations)
  if (pct == null || Number.isNaN(pct)) return '—'
  if (pct >= 100) return `${pct.toFixed(1)}%`
  if (pct >= 10) return `${pct.toFixed(1)}%`
  return `${pct.toFixed(2)}%`
}

function fallbackSiteEntry(token) {
  const base = sitePublicUrl().replace(/\/$/, '')
  return `${base}/?ref=${encodeURIComponent(token)}`
}

function siteUrlForRow(r) {
  return r.site_entry_url || fallbackSiteEntry(r.token)
}

function telegramUrlForRow(r) {
  return r.telegram_deep_link || ''
}

function isUserOwnedToken(r) {
  return r.owner_kind === 'user'
}

function aggregateRows(list) {
  let clicks = 0
  let registrations = 0
  let payments = 0
  let revenue = 0
  for (const r of list) {
    clicks += Number(r.clicks_count) || 0
    registrations += Number(r.registrations_count) || 0
    payments += Number(r.payments_count) || 0
    revenue += Number(r.revenue_net) || 0
  }
  return { clicks, registrations, payments, revenue }
}

const groupedLinkIds = computed(() => {
  const ids = new Set()
  for (const g of props.groups) {
    for (const id of g.link_ids ?? []) ids.add(id)
  }
  return ids
})

const groupSections = computed(() =>
  props.groups.map((g) => {
    const members = props.rows.filter((r) => (g.link_ids ?? []).includes(r.id))
    return {
      group: g,
      members,
      totals: aggregateRows(members),
      expanded: expandedGroupIds.value.has(g.id),
    }
  }),
)

const ungroupedRows = computed(() =>
  props.rows.filter((r) => !groupedLinkIds.value.has(r.id)),
)

const selectedCount = computed(() => selectedLinkIds.value.size)

const allVisibleSelected = computed(() => {
  if (props.rows.length === 0) return false
  return props.rows.every((r) => selectedLinkIds.value.has(r.id))
})

function toggleSort(columnKey) {
  emit('sort', columnKey)
}

function toggleGroupExpanded(groupId) {
  const next = new Set(expandedGroupIds.value)
  if (next.has(groupId)) next.delete(groupId)
  else next.add(groupId)
  expandedGroupIds.value = next
  persistExpandedGroups()
}

function expandAllGroups() {
  expandedGroupIds.value = new Set(props.groups.map((g) => g.id))
  persistExpandedGroups()
}

function collapseAllGroups() {
  expandedGroupIds.value = new Set()
  persistExpandedGroups()
}

function toggleSelectLink(id) {
  const next = new Set(selectedLinkIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedLinkIds.value = next
}

function toggleSelectAllVisible() {
  if (allVisibleSelected.value) {
    selectedLinkIds.value = new Set()
    return
  }
  selectedLinkIds.value = new Set(props.rows.map((r) => r.id))
}

function toggleSelectGroupMembers(members) {
  const ids = members.map((r) => r.id)
  const allSelected = ids.length > 0 && ids.every((id) => selectedLinkIds.value.has(id))
  const next = new Set(selectedLinkIds.value)
  if (allSelected) ids.forEach((id) => next.delete(id))
  else ids.forEach((id) => next.add(id))
  selectedLinkIds.value = next
}

function isGroupMembersAllSelected(members) {
  const ids = members.map((r) => r.id)
  return ids.length > 0 && ids.every((id) => selectedLinkIds.value.has(id))
}

function clearSelection() {
  selectedLinkIds.value = new Set()
  addToGroupOpen.value = false
}

function emitAddToGroup(groupId) {
  emit('add-to-group', {
    groupId,
    linkIds: [...selectedLinkIds.value],
  })
  addToGroupOpen.value = false
}

function emitCreateGroupFromSelection() {
  emit('create-group', { linkIds: [...selectedLinkIds.value] })
}

defineExpose({ clearSelection })
</script>

<template>
  <div class="grouped-table-shell">
    <div class="grouped-table-toolbar" role="toolbar" aria-label="Группы токенов">
      <button
        type="button"
        class="btn-secondary btn-toolbar"
        :disabled="groupBusy"
        @click="emit('create-group')"
      >
        Создать группу
      </button>
      <button
        v-if="groups.length > 0"
        type="button"
        class="btn-secondary btn-toolbar"
        @click="expandAllGroups"
      >
        Развернуть все
      </button>
      <button
        v-if="groups.length > 0"
        type="button"
        class="btn-secondary btn-toolbar"
        @click="collapseAllGroups"
      >
        Свернуть все
      </button>

      <div v-if="selectedCount > 0" class="bulk-bar">
        <span class="bulk-bar__label">{{ selectedCount }} выбрано</span>
        <div class="bulk-bar__actions">
          <div v-if="groups.length === 0" class="bulk-dropdown">
            <button
              type="button"
              class="btn-primary btn-toolbar"
              @click="emitCreateGroupFromSelection"
            >
              Создать группу
            </button>
          </div>
          <div v-else class="bulk-dropdown">
            <button
              type="button"
              class="btn-primary btn-toolbar"
              :disabled="groupBusy || groups.length === 0"
              @click="addToGroupOpen = !addToGroupOpen"
            >
              В группу ▾
            </button>
            <div v-if="addToGroupOpen" class="bulk-dropdown__panel" role="menu">
              <button
                v-for="g in groups"
                :key="g.id"
                type="button"
                class="bulk-dropdown__item"
                role="menuitem"
                @click="emitAddToGroup(g.id)"
              >
                <span class="bulk-dropdown__dot" :style="{ background: g.color }" />
                {{ g.name }}
              </button>
              <p v-if="groups.length === 0" class="bulk-dropdown__empty muted">
                Сначала создайте группу
              </p>
            </div>
          </div>
          <button type="button" class="btn-secondary btn-toolbar" @click="clearSelection">
            Снять выбор
          </button>
        </div>
      </div>
    </div>

    <AdminTableWrap aria-label="Таблица реферальных токенов с группами">
      <table class="admin-table grouped-table">
        <thead>
          <tr>
            <th class="col-select" aria-label="Выбор">
              <input
                type="checkbox"
                :checked="allVisibleSelected"
                :disabled="loading || rows.length === 0"
                aria-label="Выбрать все видимые токены"
                @change="toggleSelectAllVisible"
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
              label="Токен"
              column-key="token"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Источник"
              column-key="owner"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Ссылки"
              column-key="links"
              :sortable="false"
              :sort-key="sortKey"
              :sort-dir="sortDir"
            />
            <AdminSortTh
              label="Клики"
              column-key="clicks_count"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Рег."
              column-key="registrations_count"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Оплаты"
              column-key="payments_count"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Конверсия"
              column-key="payment_conversion_pct"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Доход"
              column-key="revenue_net"
              align="right"
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
            <th class="admin-th row-actions-head col-actions" aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="12" class="muted">Загрузка…</td>
          </tr>
          <tr v-else-if="error">
            <td colspan="12" class="error-cell">{{ error }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="12" class="muted">Пока нет записей</td>
          </tr>
          <template v-else>
            <template v-for="section in groupSections" :key="'group-' + section.group.id">
              <tr
                class="ref-group-row"
                :class="{ 'ref-group-row--expanded': section.expanded }"
                :style="{ '--group-color': section.group.color }"
                @click="toggleGroupExpanded(section.group.id)"
              >
                <td class="col-select" @click.stop>
                  <input
                    type="checkbox"
                    :checked="isGroupMembersAllSelected(section.members)"
                    :indeterminate="
                      section.members.some((r) => selectedLinkIds.has(r.id)) &&
                        !isGroupMembersAllSelected(section.members)
                    "
                    :disabled="section.members.length === 0"
                    :aria-label="`Выбрать все токены группы ${section.group.name}`"
                    @change="toggleSelectGroupMembers(section.members)"
                  />
                </td>
                <td colspan="3" class="ref-group-row__main">
                  <button
                    type="button"
                    class="ref-group-row__toggle"
                    :aria-expanded="section.expanded"
                    :aria-label="
                      section.expanded
                        ? `Свернуть группу ${section.group.name}`
                        : `Развернуть группу ${section.group.name}`
                    "
                    @click.stop="toggleGroupExpanded(section.group.id)"
                  >
                    <svg
                      class="ref-group-row__chevron"
                      viewBox="0 0 24 24"
                      width="18"
                      height="18"
                      aria-hidden="true"
                    >
                      <path
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.25"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        d="M9 6l6 6-6 6"
                      />
                    </svg>
                    <span
                      class="ref-group-row__dot"
                      :style="{ background: section.group.color }"
                      aria-hidden="true"
                    />
                    <span class="ref-group-row__name">{{ section.group.name }}</span>
                    <span class="ref-group-row__badge">{{ section.members.length }} токенов</span>
                  </button>
                </td>
                <td class="ref-group-row__muted">—</td>
                <td class="num ref-group-row__metric">{{ section.totals.clicks }}</td>
                <td class="num ref-group-row__metric">{{ section.totals.registrations }}</td>
                <td class="num ref-group-row__metric">{{ section.totals.payments }}</td>
                <td class="num ref-group-row__metric">{{
                  fmtConversionPct(section.totals.payments, section.totals.registrations)
                }}</td>
                <td class="num ref-group-row__metric">{{ fmtMoney(section.totals.revenue) }}</td>
                <td class="ref-group-row__muted">—</td>
                <td class="col-actions" @click.stop>
                  <RowActionsDropdown
                    :menu-id-suffix="'ref-group-' + section.group.id"
                    panel-aria-label="Действия с группой"
                  >
                    <template #default="{ close }">
                      <button
                        type="button"
                        class="dropdown-item"
                        role="menuitem"
                        @click="close(); emit('edit-group', section.group)"
                      >
                        Изменить
                      </button>
                      <button
                        type="button"
                        class="dropdown-item dropdown-item--danger"
                        role="menuitem"
                        @click="close(); emit('delete-group', section.group)"
                      >
                        Удалить группу
                      </button>
                    </template>
                  </RowActionsDropdown>
                </td>
              </tr>
              <tr
                v-for="r in section.expanded ? section.members : []"
                :key="'member-' + r.id"
                :id="'ref-' + r.id"
                class="ref-group-child"
                :class="{ 'admin-row-highlight': highlightRowId === r.id }"
                :style="{ '--group-color': section.group.color }"
              >
                <td class="col-select">
                  <input
                    type="checkbox"
                    :checked="selectedLinkIds.has(r.id)"
                    :aria-label="`Выбрать токен ${r.token}`"
                    @change="toggleSelectLink(r.id)"
                  />
                </td>
                <td class="num">{{ r.id }}</td>
                <td class="mono-cell">{{ r.token }}</td>
                <td class="owner-cell">
                  <span class="owner-cell-inner">
                    <template v-if="isUserOwnedToken(r) && r.owner_user_id != null">
                      <span class="num-inline">{{ r.owner_user_id }}</span>
                      <AdminHighlightListLink list="users" :highlight="r.owner_user_id" />
                    </template>
                    <template v-else-if="!isUserOwnedToken(r)">
                      <span class="pill pill-mono" :title="r.owner_kind">{{ r.owner_kind }}</span>
                    </template>
                    <template v-else>—</template>
                  </span>
                </td>
                <td class="link-actions">
                  <div class="link-copy-btns">
                    <button
                      type="button"
                      class="btn-icon link-copy-btn"
                      title="Копировать ссылку на сайт (?ref)"
                      aria-label="Копировать ссылку на сайт"
                      @click="emit('copy-url', siteUrlForRow(r))"
                    >
                      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                        <path
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"
                        />
                        <path
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          d="M3 12h18M12 3a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="btn-icon link-copy-btn"
                      title="Копировать ссылку на Telegram-бота (?start)"
                      aria-label="Копировать ссылку на Telegram-бота"
                      :disabled="!telegramUrlForRow(r)"
                      @click="emit('copy-url', telegramUrlForRow(r))"
                    >
                      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                        <path
                          fill="currentColor"
                          d="M9.78 16.02 9.5 20.5c.57 0 .82-.24 1.12-.53l2.69-2.58 5.58 4.09c1.02.56 1.75.27 2.01-.94l3.67-17.2h.01c.32-1.5-.54-2.08-1.53-1.72L2.2 9.78c-1.47.58-1.45 1.41-.25 1.78l5.26 1.64L18.9 5.9c.66-.43 1.26-.19.77.24"
                        />
                      </svg>
                    </button>
                  </div>
                </td>
                <td class="num">{{ r.clicks_count }}</td>
                <td class="num">{{ r.registrations_count }}</td>
                <td class="num">{{ r.payments_count }}</td>
                <td class="num">{{ fmtConversionPct(r.payments_count, r.registrations_count) }}</td>
                <td class="num">{{ fmtMoney(r.revenue_net) }}</td>
                <td class="date-cell task-dates-cell">
                  <span class="task-dates-cell__line">{{ fmtDatePart(r.created_at) }}</span>
                  <span class="task-dates-cell__line">{{ fmtTimePart(r.created_at) }}</span>
                </td>
                <td class="col-actions">
                  <RowActionsDropdown
                    :menu-id-suffix="'ref-' + r.id"
                    panel-aria-label="Действия с реферальным токеном"
                  >
                    <template #default="{ close }">
                      <button
                        type="button"
                        class="dropdown-item"
                        role="menuitem"
                        :disabled="deletingId === r.id"
                        @click="close(); emit('edit-token', r)"
                      >
                        Изменить
                      </button>
                      <button
                        type="button"
                        class="dropdown-item"
                        role="menuitem"
                        @click="close(); emit('remove-from-group', { groupId: section.group.id, linkId: r.id })"
                      >
                        Убрать из группы
                      </button>
                      <button
                        type="button"
                        class="dropdown-item dropdown-item--danger"
                        role="menuitem"
                        :disabled="deletingId === r.id"
                        @click="close(); emit('delete-token', r)"
                      >
                        {{ deletingId === r.id ? '…' : 'Удалить' }}
                      </button>
                    </template>
                  </RowActionsDropdown>
                </td>
              </tr>
            </template>

            <tr v-if="ungroupedRows.length > 0 && groups.length > 0" class="ref-ungrouped-head">
              <td colspan="12">Без группы</td>
            </tr>

            <tr
              v-for="r in ungroupedRows"
              :key="'solo-' + r.id"
              :id="'ref-' + r.id"
              :class="{ 'admin-row-highlight': highlightRowId === r.id }"
            >
              <td class="col-select">
                <input
                  type="checkbox"
                  :checked="selectedLinkIds.has(r.id)"
                  :aria-label="`Выбрать токен ${r.token}`"
                  @change="toggleSelectLink(r.id)"
                />
              </td>
              <td class="num">{{ r.id }}</td>
              <td class="mono-cell">{{ r.token }}</td>
              <td class="owner-cell">
                <span class="owner-cell-inner">
                  <template v-if="isUserOwnedToken(r) && r.owner_user_id != null">
                    <span class="num-inline">{{ r.owner_user_id }}</span>
                    <AdminHighlightListLink list="users" :highlight="r.owner_user_id" />
                  </template>
                  <template v-else-if="!isUserOwnedToken(r)">
                    <span class="pill pill-mono" :title="r.owner_kind">{{ r.owner_kind }}</span>
                  </template>
                  <template v-else>—</template>
                </span>
              </td>
              <td class="link-actions">
                <div class="link-copy-btns">
                  <button
                    type="button"
                    class="btn-icon link-copy-btn"
                    title="Копировать ссылку на сайт (?ref)"
                    aria-label="Копировать ссылку на сайт"
                    @click="emit('copy-url', siteUrlForRow(r))"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                      <path
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"
                      />
                      <path
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        d="M3 12h18M12 3a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="btn-icon link-copy-btn"
                    title="Копировать ссылку на Telegram-бота (?start)"
                    aria-label="Копировать ссылку на Telegram-бота"
                    :disabled="!telegramUrlForRow(r)"
                    @click="emit('copy-url', telegramUrlForRow(r))"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                      <path
                        fill="currentColor"
                        d="M9.78 16.02 9.5 20.5c.57 0 .82-.24 1.12-.53l2.69-2.58 5.58 4.09c1.02.56 1.75.27 2.01-.94l3.67-17.2h.01c.32-1.5-.54-2.08-1.53-1.72L2.2 9.78c-1.47.58-1.45 1.41-.25 1.78l5.26 1.64L18.9 5.9c.66-.43 1.26-.19.77.24"
                      />
                    </svg>
                  </button>
                </div>
              </td>
              <td class="num">{{ r.clicks_count }}</td>
              <td class="num">{{ r.registrations_count }}</td>
              <td class="num">{{ r.payments_count }}</td>
              <td class="num">{{ fmtConversionPct(r.payments_count, r.registrations_count) }}</td>
              <td class="num">{{ fmtMoney(r.revenue_net) }}</td>
              <td class="date-cell task-dates-cell">
                <span class="task-dates-cell__line">{{ fmtDatePart(r.created_at) }}</span>
                <span class="task-dates-cell__line">{{ fmtTimePart(r.created_at) }}</span>
              </td>
              <td class="col-actions">
                <RowActionsDropdown
                  :menu-id-suffix="'ref-' + r.id"
                  panel-aria-label="Действия с реферальным токеном"
                >
                  <template #default="{ close }">
                    <button
                      type="button"
                      class="dropdown-item"
                      role="menuitem"
                      :disabled="deletingId === r.id"
                      @click="close(); emit('edit-token', r)"
                    >
                      Изменить
                    </button>
                    <button
                      type="button"
                      class="dropdown-item dropdown-item--danger"
                      role="menuitem"
                      :disabled="deletingId === r.id"
                      @click="close(); emit('delete-token', r)"
                    >
                      {{ deletingId === r.id ? '…' : 'Удалить' }}
                    </button>
                  </template>
                </RowActionsDropdown>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </AdminTableWrap>
  </div>
</template>

<style scoped>
.grouped-table-shell {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}
.grouped-table-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
}
.btn-toolbar {
  font-size: 0.82rem;
  padding: 0.38rem 0.75rem;
}
.bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin-left: auto;
  padding: 0.35rem 0.65rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 12%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--card-border));
  animation: bulk-in 0.22s ease;
}
@keyframes bulk-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.bulk-bar__label {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-h);
  font-variant-numeric: tabular-nums;
}
.bulk-bar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}
.bulk-dropdown {
  position: relative;
}
.bulk-dropdown__panel {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  z-index: 30;
  min-width: 12rem;
  padding: 0.35rem;
  border-radius: 12px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg, 0 12px 40px rgba(0, 0, 0, 0.18));
}
.bulk-dropdown__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.45rem 0.55rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.85rem;
  text-align: left;
  cursor: pointer;
}
.bulk-dropdown__item:hover {
  background: var(--surface);
}
.bulk-dropdown__dot {
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  flex-shrink: 0;
}
.bulk-dropdown__empty {
  margin: 0.35rem 0.5rem;
  font-size: 0.78rem;
}
.col-select {
  width: 2.25rem;
  text-align: center;
  vertical-align: middle;
}
.ref-group-row {
  background: color-mix(in srgb, var(--group-color) 10%, var(--card-bg));
  cursor: pointer;
  transition: background 0.18s ease;
}
.ref-group-row:hover {
  background: color-mix(in srgb, var(--group-color) 16%, var(--card-bg));
}
.ref-group-row__main {
  padding-top: 0.55rem;
  padding-bottom: 0.55rem;
}
.ref-group-row__toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-h);
  font: inherit;
  cursor: pointer;
  text-align: left;
}
.ref-group-row__chevron {
  flex-shrink: 0;
  transition: transform 0.22s ease;
  color: var(--muted);
}
.ref-group-row--expanded .ref-group-row__chevron {
  transform: rotate(90deg);
}
.ref-group-row__dot {
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  flex-shrink: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--group-color) 25%, transparent);
}
.ref-group-row__name {
  font-weight: 700;
  font-size: 0.92rem;
}
.ref-group-row__badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--group-color) 18%, transparent);
  color: var(--text-h);
  font-variant-numeric: tabular-nums;
}
.ref-group-row__metric {
  font-weight: 700;
  color: var(--text-h);
}
.ref-group-row__muted {
  color: var(--muted);
  text-align: center;
}
.owner-cell {
  vertical-align: middle;
  max-width: 10rem;
}
.owner-cell-inner {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}
.num-inline {
  font-variant-numeric: tabular-nums;
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
  white-space: nowrap;
}
.ref-group-child {
  background: color-mix(in srgb, var(--group-color) 4%, transparent);
}
.ref-group-child .mono-cell {
  padding-left: 0.35rem;
  border-left: 3px solid var(--group-color);
}
.ref-ungrouped-head td {
  padding: 0.55rem 0.75rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  background: var(--surface);
  border-top: 1px solid var(--card-border);
}
.error-cell {
  color: var(--danger);
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
.link-actions {
  vertical-align: middle;
  text-align: center;
  white-space: nowrap;
}
.link-copy-btns {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
}
.link-copy-btn {
  margin-left: 0;
  padding: 0.3rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.col-actions {
  vertical-align: middle;
  text-align: center;
}
</style>
