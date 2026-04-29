<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import RowActionsDropdown from '../components/RowActionsDropdown.vue'
import { fetchJson, sitePublicUrl } from '../api/client.js'

const rows = ref([])
const loading = ref(false)
const error = ref(null)

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

const statsLine = computed(() => {
  if (loading.value) return 'Загрузка…'
  if (error.value) return 'Ошибка загрузки'
  return `${rows.value.length} записей`
})

const modalTitle = computed(() =>
  editingId.value != null ? 'Редактировать токен' : 'Новый реферальный токен',
)

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
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'medium',
    })
  } catch {
    return iso
  }
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

function fallbackTelegramDeep(token) {
  const bot = (import.meta.env.VITE_TELEGRAM_BOT_USERNAME || '')
    .trim()
    .replace(/^@/, '')
  if (!bot) return ''
  return `https://t.me/${bot}?start=${encodeURIComponent(token)}`
}

function siteUrlForRow(r) {
  return r.site_entry_url || fallbackSiteEntry(r.token)
}

function telegramUrlForRow(r) {
  return r.telegram_deep_link || fallbackTelegramDeep(r.token)
}

const copyHint = ref(null)
/** id строки во время DELETE */
const deletingId = ref(null)
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
    await load()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/admin">← Управление данными</RouterLink>
      <h1 class="page-title">Реферальные токены</h1>
      <nav class="admin-tabs" aria-label="Разделы админки">
        <RouterLink class="tab" :to="{ path: '/admin' }">Пользователи</RouterLink>
        <RouterLink class="tab" :to="{ path: '/admin', query: { tab: 'servers' } }">
          Серверы
        </RouterLink>
        <RouterLink class="tab tab-active" :to="{ path: '/admin/referrals' }">
          Реферальные токены
        </RouterLink>
      </nav>
      <div class="head-row">
        <h2 class="section-heading">Конверсия по токенам</h2>
        <div class="head-actions">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading"
            @click="load"
          >
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
          <button type="button" class="btn-primary" @click="openModal">
            Новый токен
          </button>
        </div>
      </div>
    </header>

    <section class="stats" aria-live="polite">
      <p class="stats-value">{{ statsLine }}</p>
      <p v-if="copyHint" class="copy-hint">{{ copyHint }}</p>
    </section>

    <AdminTableWrap aria-label="Таблица реферальных токенов">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Токен</th>
            <th>Источник</th>
            <th>User id</th>
            <th>Сайт</th>
            <th>Telegram</th>
            <th class="num">Клики</th>
            <th class="num">Рег.</th>
            <th class="num">Оплаты</th>
            <th>Создан</th>
            <th class="col-actions">Действия</th>
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
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.id }}</td>
            <td class="mono-cell">{{ r.token }}</td>
            <td>
              <span class="pill pill-mono" :title="r.owner_kind">{{ r.owner_kind }}</span>
            </td>
            <td>{{ r.owner_user_id ?? '—' }}</td>
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

    <Teleport to="body">
      <div
        v-if="modalOpen"
        class="modal-backdrop"
        role="presentation"
        @click.self="closeModal"
      >
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="ref-modal-title">
          <h2 id="ref-modal-title" class="modal-title">{{ modalTitle }}</h2>
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
}
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
.sub {
  margin: 0;
  font-size: 0.85rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 52rem;
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
.stats-value {
  margin: 0;
  font-size: 0.95rem;
  color: var(--text-h);
}
.copy-hint {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--accent);
  font-weight: 600;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.data-table th,
.data-table td {
  padding: 0.55rem 0.65rem;
  text-align: left;
  border-bottom: 1px solid var(--card-border);
}
.data-table th {
  font-weight: 700;
  color: var(--muted);
  background: var(--surface);
}
.data-table tbody tr:last-child td {
  border-bottom: none;
}
.muted {
  color: var(--muted);
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
.pill {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--surface);
  border: 1px solid var(--card-border);
  color: var(--muted);
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
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 12, 9, 0.55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1rem, 4vh, 2.5rem) 1rem;
  z-index: 50;
}
.modal {
  width: 100%;
  max-width: 420px;
  padding: 1.35rem 1.45rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg);
}
.modal-title {
  margin: 0 0 1rem;
  font-size: 1.1rem;
  color: var(--text-h);
}
.modal-form .field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}
.modal-form .field > span {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}
.input-like {
  font: inherit;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
}
.field-hint {
  margin: -0.35rem 0 0.65rem;
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.4;
}
.form-err {
  margin: 0 0 0.65rem;
  font-size: 0.85rem;
  color: var(--danger);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
  margin-top: 0.5rem;
}
</style>
