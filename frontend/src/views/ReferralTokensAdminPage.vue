<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AdminHighlightListLink from '../components/AdminHighlightListLink.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import AppModal from '../components/AppModal.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import RowActionsDropdown from '../components/RowActionsDropdown.vue'
import StatWidget from '../components/StatWidget.vue'
import { fetchJson, sitePublicUrl } from '../api/client.js'
import { useTableSort } from '../utils/adminTableSort.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'

const route = useRoute()
const rows = ref([])
const loading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<{ total: number; with_telegram_id: number; without_telegram_id: number } | null>} */
const directTraffic = ref(null)
const directTrafficLoading = ref(false)
const directTrafficError = ref(null)

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

async function loadDirectTraffic() {
  directTrafficLoading.value = true
  directTrafficError.value = null
  try {
    directTraffic.value = await fetchJson('/api/referral-links/direct-traffic-stats')
  } catch (e) {
    directTrafficError.value = e.message || String(e)
    directTraffic.value = null
  } finally {
    directTrafficLoading.value = false
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
  await Promise.all([load(), loadDirectTraffic()])
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

function fmtDate(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'medium' })
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
    await load()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    creating.value = false
  }
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

const referralSortAccessors = {
  id: (r) => r.id,
  token: (r) => String(r.token ?? '').toLowerCase(),
  owner_kind: (r) => String(r.owner_kind ?? '').toLowerCase(),
  owner_user_id: (r) => (r.owner_user_id != null ? r.owner_user_id : -1),
  site: (r) => siteUrlForRow(r).toLowerCase(),
  telegram: (r) => (telegramUrlForRow(r) || '').toLowerCase(),
  clicks_count: (r) => Number(r.clicks_count) || 0,
  registrations_count: (r) => Number(r.registrations_count) || 0,
  payments_count: (r) => Number(r.payments_count) || 0,
  created_at: (r) => Date.parse(r.created_at) || 0,
}

const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(
  rows,
  referralSortAccessors,
)

const copyHint = ref(null)
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
          <AppRefreshButton :busy="loading || directTrafficLoading" @click="reloadAll" />
          <button type="button" class="btn-primary" @click="openModal">
            Новый токен
          </button>
        </div>
      </div>
    </template>

    <section class="stats widgets-row" aria-live="polite">
      <div class="widgets-grid">
        <StatWidget title="Прямой трафик" aria-label="Прямой трафик без реферальной ссылки">
          <p class="stat-widget-value">
            {{
              directTrafficLoading
                ? '…'
                : directTrafficError
                  ? '—'
                  : (directTraffic?.total ?? 0)
            }}
          </p>
          <p v-if="!directTrafficLoading && !directTrafficError" class="stat-widget-meta">
            Пользователи без реферальной ссылки
          </p>
          <dl
            v-if="!directTrafficLoading && !directTrafficError"
            class="stat-widget-split"
          >
            <div>
              <dt>Telegram</dt>
              <dd>{{ directTraffic?.with_telegram_id ?? 0 }}</dd>
            </div>
            <div>
              <dt>Сайт</dt>
              <dd>{{ directTraffic?.without_telegram_id ?? 0 }}</dd>
            </div>
          </dl>
          <p v-else-if="directTrafficError" class="stat-widget-err">{{ directTrafficError }}</p>
        </StatWidget>
        <StatWidget title="Токены" aria-label="Число реферальных токенов">
          <p class="stat-widget-value">
            {{ loading ? '…' : error ? '—' : rows.length }}
          </p>
          <p v-if="!loading && !error" class="stat-widget-meta">Записей в таблице</p>
        </StatWidget>
      </div>
      <p v-if="copyHint" class="copy-hint">{{ copyHint }}</p>
    </section>

    <AdminTableWrap aria-label="Таблица реферальных токенов">
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
              label="Токен"
              column-key="token"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Источник"
              column-key="owner_kind"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="User id"
              column-key="owner_user_id"
              align="right"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Сайт"
              column-key="site"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Telegram"
              column-key="telegram"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
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
              label="Создан"
              column-key="created_at"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              @sort="toggleSort"
            />
            <AdminSortTh
              label="Действия"
              column-key="actions"
              :sortable="false"
              :sort-key="sortKey"
              :sort-dir="sortDir"
            />
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="11" class="muted">Загрузка…</td>
          </tr>
          <tr v-else-if="error">
            <td colspan="11" class="error-cell">{{ error }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="11" class="muted">Пока нет записей</td>
          </tr>
          <tr
            v-for="r in sortedRows"
            :key="r.id"
            :id="'ref-' + r.id"
            :class="{ 'admin-row-highlight': highlightRowId === r.id }"
          >
            <td class="num">{{ r.id }}</td>
            <td class="mono-cell">{{ r.token }}</td>
            <td>
              <span class="pill pill-mono" :title="r.owner_kind">{{ r.owner_kind }}</span>
            </td>
            <td class="owner-user-id-cell">
              <span class="owner-user-id-inner">
                <template v-if="r.owner_user_id != null">
                  <span>{{ r.owner_user_id }}</span>
                  <AdminHighlightListLink list="users" :highlight="r.owner_user_id" />
                </template>
                <template v-else>—</template>
              </span>
            </td>
            <td class="link-actions">
              <button
                type="button"
                class="btn-secondary btn-tiny"
                title="Копировать ссылку на сайт (?ref)"
                @click="copyUrl(siteUrlForRow(r))"
              >
                Копировать
              </button>
            </td>
            <td class="link-actions">
              <button
                v-if="telegramUrlForRow(r)"
                type="button"
                class="btn-secondary btn-tiny"
                title="Копировать ссылку на Telegram-бота (?start)"
                @click="copyUrl(telegramUrlForRow(r))"
              >
                Копировать
              </button>
              <span v-else class="muted">—</span>
            </td>
            <td class="num">{{ r.clicks_count }}</td>
            <td class="num">{{ r.registrations_count }}</td>
            <td class="num">{{ r.payments_count }}</td>
            <td class="date-cell">{{ fmtDate(r.created_at) }}</td>
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
                    @click="close(); openEditModal(r)"
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    class="dropdown-item dropdown-item--danger"
                    role="menuitem"
                    :disabled="deletingId === r.id"
                    @click="close(); removeReferral(r)"
                  >
                    {{ deletingId === r.id ? '…' : 'Удалить' }}
                  </button>
                </template>
              </RowActionsDropdown>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>

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
.widgets-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
@media (max-width: 640px) {
  .widgets-grid {
    grid-template-columns: 1fr;
  }
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
.link-actions {
  vertical-align: middle;
  text-align: center;
  white-space: nowrap;
}
.col-actions {
  vertical-align: middle;
  text-align: center;
}
.btn-tiny {
  font-size: 0.75rem;
  padding: 0.25rem 0.45rem;
}
/* Нейтральный pill: фон/границу базовый .pill (admin-ui.css) не задаёт. */
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
</style>
