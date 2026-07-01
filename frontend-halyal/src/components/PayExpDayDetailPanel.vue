<script setup>
import { computed, ref, watch } from 'vue'
import AdminHighlightListLink from './AdminHighlightListLink.vue'
import { chartSeriesRgb, rgba } from '../utils/adminChartTheme.js'
import { formatMskCalendarDayLong, formatMskDateTimeShort } from '../utils/mskDate.js'

/**
 * @typedef {{
 *   key: string
 *   title: string
 *   hint: string
 *   count: number
 *   paid_users_count?: number
 *   did_not_renew_count?: number
 *   users?: Array<{
 *     user_id: number
 *     email?: string | null
 *     telegram_id?: number | null
 *     telegram_username?: string | null
 *     subscription_until?: string | null
 *     has_payments_ever?: boolean
 *     did_not_renew?: boolean
 *   }>
 *   payments?: Array<{
 *     payment_id: number
 *     user_id: number
 *     email?: string | null
 *     telegram_id?: number | null
 *     telegram_username?: string | null
 *     amount_rub: number | string
 *     provider: string
 *     is_first_payment?: boolean
 *     payment_at: string
 *   }>
 * }} PayExpGroup
 */

const props = defineProps({
  statsDate: { type: String, required: true },
  /** @type {import('vue').PropType<PayExpGroup[]>} */
  groups: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
})

const emit = defineEmits(['close'])

const GROUP_COLORS = /** @type {const} */ ({
  payments_first: chartSeriesRgb.payment,
  payments_repeat: chartSeriesRgb.persistent,
  expiry_no_traffic: chartSeriesRgb.expiryGray,
  expiry_has_traffic: chartSeriesRgb.traffic,
  expiry_active_on_day: chartSeriesRgb.active,
  expiry_active_today: chartSeriesRgb.activePay,
})

const EXPIRY_GROUP_KEYS = new Set([
  'expiry_no_traffic',
  'expiry_has_traffic',
  'expiry_active_on_day',
  'expiry_active_today',
])

const openGroups = ref(/** @type {Set<string>} */ (new Set()))

const dayTitle = computed(() =>
  formatMskCalendarDayLong(String(props.statsDate).slice(0, 10)),
)

function groupColor(key) {
  const rgb = GROUP_COLORS[key] ?? chartSeriesRgb.active
  return rgba(rgb, 0.92)
}

function groupBg(key) {
  const rgb = GROUP_COLORS[key] ?? chartSeriesRgb.active
  return rgba(rgb, 0.12)
}

function isExpiryGroup(key) {
  return EXPIRY_GROUP_KEYS.has(key)
}

/** @param {PayExpGroup} group */
function expiryDidNotRenewUsers(group) {
  return (group.users ?? []).filter((u) => u.did_not_renew)
}

/** @param {PayExpGroup} group */
function expiryWithoutPaymentUsers(group) {
  return (group.users ?? []).filter((u) => !u.has_payments_ever)
}

/** @param {PayExpGroup} group */
function expiryRenewedOnDayUsers(group) {
  return (group.users ?? []).filter((u) => u.has_payments_ever && !u.did_not_renew)
}

function userDisplayName(item) {
  const uname = item.telegram_username
  if (uname != null && String(uname).trim()) {
    const s = String(uname).trim()
    return s.startsWith('@') ? s : `@${s}`
  }
  if (item.telegram_id != null && String(item.telegram_id).trim()) {
    return String(item.telegram_id)
  }
  if (item.email != null && String(item.email).trim()) {
    return String(item.email).trim()
  }
  return `#${item.user_id}`
}

function userSecondary(item) {
  const parts = []
  const primary = userDisplayName(item)
  if (item.telegram_id != null) parts.push(`tg ${item.telegram_id}`)
  if (item.email && primary !== String(item.email).trim()) {
    parts.push(String(item.email).trim())
  }
  parts.push(`id ${item.user_id}`)
  return parts.join(' · ')
}

function formatAmount(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} ₽`
}

function formatSubUntil(iso) {
  if (!iso) return null
  return formatMskCalendarDayLong(String(iso).slice(0, 10))
}

function toggleGroup(key) {
  const next = new Set(openGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openGroups.value = next
}

watch(
  () => props.groups,
  (groups) => {
    const withChurn = groups.find((g) => (Number(g.did_not_renew_count) || 0) > 0)
    const first = withChurn ?? groups.find((g) => (Number(g.count) || 0) > 0)
    openGroups.value = first ? new Set([first.key]) : new Set()
  },
  { immediate: true },
)
</script>

<template>
  <section
    class="pay-exp-day-panel glass"
    aria-labelledby="pay-exp-day-panel-title"
  >
    <header class="pay-exp-day-panel__head">
      <div class="pay-exp-day-panel__head-main">
        <p class="pay-exp-day-panel__eyebrow">Детали по дню</p>
        <h3 id="pay-exp-day-panel-title" class="pay-exp-day-panel__title">
          {{ dayTitle }}
          <span class="pay-exp-day-panel__msk">МСК</span>
        </h3>
      </div>
      <button
        type="button"
        class="pay-exp-day-panel__close"
        title="Закрыть детали"
        @click="emit('close')"
      >
        Закрыть
      </button>
    </header>

    <p v-if="loading" class="pay-exp-day-panel__status muted">Загрузка списков…</p>
    <p v-else-if="error" class="pay-exp-day-panel__status pay-exp-day-panel__status--err">
      {{ error }}
    </p>
    <p v-else-if="groups.length === 0" class="pay-exp-day-panel__status muted">
      За этот день нет оплат и окончаний подписки.
    </p>

    <div v-else class="pay-exp-day-panel__groups">
      <details
        v-for="group in groups"
        :key="group.key"
        class="pay-exp-day-group"
        :style="{
          '--group-color': groupColor(group.key),
          '--group-bg': groupBg(group.key),
        }"
        :open="openGroups.has(group.key)"
      >
        <summary class="pay-exp-day-group__summary" @click.prevent="toggleGroup(group.key)">
          <span class="pay-exp-day-group__dot" aria-hidden="true" />
          <span class="pay-exp-day-group__titles">
            <span class="pay-exp-day-group__title">{{ group.title }}</span>
            <span class="pay-exp-day-group__hint">{{ group.hint }}</span>
            <span
              v-if="isExpiryGroup(group.key) && (group.did_not_renew_count || group.paid_users_count)"
              class="pay-exp-day-group__renewal"
            >
              <span
                v-if="group.did_not_renew_count"
                class="pay-exp-day-group__renewal-chip pay-exp-day-group__renewal-chip--warn"
              >
                не продлили: {{ group.did_not_renew_count }}
              </span>
              <span
                v-if="group.paid_users_count && group.paid_users_count !== group.did_not_renew_count"
                class="pay-exp-day-group__renewal-chip"
              >
                с оплатой: {{ group.paid_users_count }}
              </span>
              <span
                v-if="expiryWithoutPaymentUsers(group).length"
                class="pay-exp-day-group__renewal-chip pay-exp-day-group__renewal-chip--muted"
              >
                без оплат: {{ expiryWithoutPaymentUsers(group).length }}
              </span>
            </span>
          </span>
          <span class="pay-exp-day-group__count">{{ group.count }}</span>
        </summary>

        <ul v-if="group.payments?.length" class="pay-exp-day-list">
          <li
            v-for="pay in group.payments"
            :key="pay.payment_id"
            class="pay-exp-day-row"
          >
            <span class="pay-exp-day-row__main">
              <span class="pay-exp-day-row__name">{{ userDisplayName(pay) }}</span>
              <span class="pay-exp-day-row__sub muted">{{ userSecondary(pay) }}</span>
            </span>
            <span class="pay-exp-day-row__badges">
              <span class="pay-exp-day-badge pay-exp-day-badge--amount">{{
                formatAmount(pay.amount_rub)
              }}</span>
              <span class="pay-exp-day-badge">{{ pay.provider }}</span>
              <span class="pay-exp-day-badge muted">{{
                formatMskDateTimeShort(pay.payment_at)
              }}</span>
            </span>
            <AdminHighlightListLink
              list="users"
              :highlight="pay.user_id"
              panel
              :title="`Аналитика: ${userDisplayName(pay)}`"
            />
          </li>
        </ul>

        <ul v-else-if="group.users?.length" class="pay-exp-day-list">
          <template v-if="isExpiryGroup(group.key) && expiryDidNotRenewUsers(group).length">
            <li class="pay-exp-day-subhead pay-exp-day-subhead--warn">
              Оплачивали, не продлили подписку
              <span class="pay-exp-day-subhead__n">{{
                expiryDidNotRenewUsers(group).length
              }}</span>
            </li>
            <li
              v-for="user in expiryDidNotRenewUsers(group)"
              :key="`dnr-${user.user_id}`"
              class="pay-exp-day-row pay-exp-day-row--warn"
            >
              <span class="pay-exp-day-row__main">
                <span class="pay-exp-day-row__name">{{ userDisplayName(user) }}</span>
                <span class="pay-exp-day-row__sub muted">{{ userSecondary(user) }}</span>
              </span>
              <span class="pay-exp-day-row__badges">
                <span class="pay-exp-day-badge pay-exp-day-badge--churn">
                  Не продлил
                </span>
                <span
                  v-if="user.subscription_until"
                  class="pay-exp-day-badge pay-exp-day-badge--expiry"
                >
                  истекает {{ formatSubUntil(user.subscription_until) }}
                </span>
              </span>
              <AdminHighlightListLink
                list="users"
                :highlight="user.user_id"
                panel
                :title="`Аналитика: ${userDisplayName(user)}`"
              />
            </li>
          </template>

          <template v-if="isExpiryGroup(group.key) && expiryWithoutPaymentUsers(group).length">
            <li class="pay-exp-day-subhead">
              Без оплат
              <span class="pay-exp-day-subhead__n">{{
                expiryWithoutPaymentUsers(group).length
              }}</span>
            </li>
            <li
              v-for="user in expiryWithoutPaymentUsers(group)"
              :key="`free-${user.user_id}`"
              class="pay-exp-day-row"
            >
              <span class="pay-exp-day-row__main">
                <span class="pay-exp-day-row__name">{{ userDisplayName(user) }}</span>
                <span class="pay-exp-day-row__sub muted">{{ userSecondary(user) }}</span>
              </span>
              <span class="pay-exp-day-row__badges">
                <span class="pay-exp-day-badge muted">Пробный / без оплат</span>
                <span
                  v-if="user.subscription_until"
                  class="pay-exp-day-badge"
                >
                  до {{ formatSubUntil(user.subscription_until) }}
                </span>
              </span>
              <AdminHighlightListLink
                list="users"
                :highlight="user.user_id"
                panel
                :title="`Аналитика: ${userDisplayName(user)}`"
              />
            </li>
          </template>

          <template v-if="isExpiryGroup(group.key) && expiryRenewedOnDayUsers(group).length">
            <li class="pay-exp-day-subhead">
              Оплатили в этот день
              <span class="pay-exp-day-subhead__n">{{
                expiryRenewedOnDayUsers(group).length
              }}</span>
            </li>
            <li
              v-for="user in expiryRenewedOnDayUsers(group)"
              :key="`renew-${user.user_id}`"
              class="pay-exp-day-row"
            >
              <span class="pay-exp-day-row__main">
                <span class="pay-exp-day-row__name">{{ userDisplayName(user) }}</span>
                <span class="pay-exp-day-row__sub muted">{{ userSecondary(user) }}</span>
              </span>
              <span class="pay-exp-day-row__badges">
                <span class="pay-exp-day-badge pay-exp-day-badge--paid">Оплата в этот день</span>
              </span>
              <AdminHighlightListLink
                list="users"
                :highlight="user.user_id"
                panel
                :title="`Аналитика: ${userDisplayName(user)}`"
              />
            </li>
          </template>

          <template v-if="!isExpiryGroup(group.key)">
            <li
              v-for="user in group.users"
              :key="user.user_id"
              class="pay-exp-day-row"
            >
              <span class="pay-exp-day-row__main">
                <span class="pay-exp-day-row__name">{{ userDisplayName(user) }}</span>
                <span class="pay-exp-day-row__sub muted">{{ userSecondary(user) }}</span>
              </span>
              <span class="pay-exp-day-row__badges">
                <span
                  v-if="user.has_payments_ever"
                  class="pay-exp-day-badge pay-exp-day-badge--paid"
                >
                  Оплачивал
                </span>
                <span
                  v-if="user.subscription_until"
                  class="pay-exp-day-badge"
                >
                  до {{ formatSubUntil(user.subscription_until) }}
                </span>
              </span>
              <AdminHighlightListLink
                list="users"
                :highlight="user.user_id"
                panel
                :title="`Аналитика: ${userDisplayName(user)}`"
              />
            </li>
          </template>
        </ul>
      </details>
    </div>
  </section>
</template>

<style scoped>
.pay-exp-day-panel {
  margin-top: 1rem;
  padding: 1rem 1.15rem 1.1rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
  animation: pay-exp-panel-in 0.28s ease-out;
}

@keyframes pay-exp-panel-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.pay-exp-day-panel__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  margin-bottom: 0.85rem;
}

.pay-exp-day-panel__eyebrow {
  margin: 0 0 0.2rem;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.pay-exp-day-panel__title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}

.pay-exp-day-panel__msk {
  margin-left: 0.35rem;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--muted);
  vertical-align: middle;
}

.pay-exp-day-panel__close {
  margin: 0;
  padding: 0.4rem 0.75rem;
  border-radius: 9px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--muted);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease,
    background 0.15s ease;
}

.pay-exp-day-panel__close:hover {
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--card-border));
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
}

.pay-exp-day-panel__status {
  margin: 0;
  font-size: 0.9rem;
}

.pay-exp-day-panel__status--err {
  color: var(--danger);
}

.pay-exp-day-panel__groups {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.pay-exp-day-group {
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  overflow: hidden;
}

.pay-exp-day-group__summary {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.65rem 0.75rem;
  cursor: pointer;
  list-style: none;
  background: linear-gradient(
    90deg,
    var(--group-bg),
    transparent 72%
  );
}

.pay-exp-day-group__summary::-webkit-details-marker {
  display: none;
}

.pay-exp-day-group__dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 999px;
  background: var(--group-color);
  flex-shrink: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--group-color) 22%, transparent);
}

.pay-exp-day-group__titles {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
}

.pay-exp-day-group__title {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--text-h);
}

.pay-exp-day-group__hint {
  font-size: 0.76rem;
  line-height: 1.35;
  color: var(--muted);
}

.pay-exp-day-group__renewal {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.2rem;
}

.pay-exp-day-group__renewal-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.42rem;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--group-color) 35%, var(--card-border));
  background: color-mix(in srgb, var(--group-color) 12%, transparent);
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-h);
}

.pay-exp-day-group__renewal-chip--warn {
  border-color: color-mix(in srgb, var(--danger) 45%, var(--card-border));
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  color: var(--danger);
}

.pay-exp-day-group__renewal-chip--muted {
  color: var(--muted);
  font-weight: 600;
}

.pay-exp-day-group__count {
  flex-shrink: 0;
  min-width: 1.75rem;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--group-color) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--group-color) 35%, var(--card-border));
  font-family: var(--mono);
  font-size: 0.82rem;
  font-weight: 700;
  text-align: center;
  color: var(--text-h);
}

.pay-exp-day-list {
  list-style: none;
  margin: 0;
  padding: 0.25rem 0.55rem 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.pay-exp-day-subhead {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.15rem 0.1rem 0;
  padding: 0.35rem 0.45rem 0.15rem;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}

.pay-exp-day-subhead--warn {
  color: var(--danger);
}

.pay-exp-day-subhead__n {
  display: inline-flex;
  min-width: 1.2rem;
  justify-content: center;
  padding: 0.05rem 0.35rem;
  border-radius: 999px;
  background: color-mix(in srgb, currentColor 12%, transparent);
  font-family: var(--mono);
  font-size: 0.68rem;
}

.pay-exp-day-row--warn {
  border-color: color-mix(in srgb, var(--danger) 22%, transparent);
  background: color-mix(in srgb, var(--danger) 6%, var(--group-bg));
}

.pay-exp-day-row--warn:hover {
  border-color: color-mix(in srgb, var(--danger) 35%, var(--card-border));
  background: color-mix(in srgb, var(--danger) 10%, var(--group-bg));
}

.pay-exp-day-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.45rem 0.65rem;
  padding: 0.5rem 0.55rem;
  border-radius: 10px;
  border: 1px solid transparent;
  background: color-mix(in srgb, var(--group-bg) 55%, transparent);
  transition:
    border-color 0.15s ease,
    background 0.15s ease;
}

.pay-exp-day-row:hover {
  border-color: color-mix(in srgb, var(--group-color) 28%, var(--card-border));
  background: color-mix(in srgb, var(--group-bg) 85%, transparent);
}

.pay-exp-day-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.pay-exp-day-row__name {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pay-exp-day-row__sub {
  font-size: 0.72rem;
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pay-exp-day-row__badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.3rem;
}

.pay-exp-day-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.12rem 0.42rem;
  border-radius: 999px;
  border: 1px solid var(--card-border);
  background: var(--card-bg, var(--surface));
  font-size: 0.68rem;
  font-weight: 600;
  white-space: nowrap;
}

.pay-exp-day-badge--amount {
  font-family: var(--mono);
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--group-color) 35%, var(--card-border));
}

.pay-exp-day-badge--paid {
  color: var(--text-h);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--card-border));
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.pay-exp-day-badge--churn {
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 40%, var(--card-border));
  background: color-mix(in srgb, var(--danger) 10%, transparent);
}

.pay-exp-day-badge--expiry {
  font-family: var(--mono);
}

@media (max-width: 720px) {
  .pay-exp-day-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .pay-exp-day-row__badges {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
</style>
