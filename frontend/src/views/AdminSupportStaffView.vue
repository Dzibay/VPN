<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminHighlightListLink from '../components/AdminHighlightListLink.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AppActionButton from '../components/AppActionButton.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import StateNote from '../components/StateNote.vue'
import { fetchJson } from '../api/client.js'
import { getSessionRole } from '../auth/session.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'
import { Loader2, Send } from 'lucide-vue-next'

const POLL_MS = 12000

const route = useRoute()
const router = useRouter()

const chatsLoading = ref(false)
const chatsError = ref(null)
/** @type {import('vue').Ref<Array<Record<string, unknown>>>} */
const chats = ref([])
const chatsTotal = ref(0)
const needsReplyCount = ref(0)
const onlyNeedsReply = ref(false)

const selectedUserId = ref(null)
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const selectedChat = ref(null)

const messagesLoading = ref(false)
const messagesError = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, author_kind: string, body: string, created_at: string }>>} */
const messages = ref([])
const sendText = ref('')
const sendBusy = ref(false)
const sendError = ref(null)

const messagesEndRef = ref(null)
/** @type {ReturnType<typeof setInterval> | null} */
let pollTimer = null

const selectedUserIdFromQuery = computed(() => {
  const raw = route.query.user_id
  const n = Number(typeof raw === 'string' ? raw : Array.isArray(raw) ? raw[0] : NaN)
  return Number.isFinite(n) && n > 0 ? n : null
})

const showStaffAuthor = computed(() => getSessionRole() === 'admin')

function formatTime(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'short' })
}

function isStaffMessage(msg) {
  return msg?.author_kind === 'staff'
}

function messageAuthorLabel(msg) {
  if (!isStaffMessage(msg)) return 'Пользователь'
  if (showStaffAuthor.value && msg?.staff_author_label) {
    return String(msg.staff_author_label)
  }
  return 'Поддержка'
}

function chatUserLabel(chat) {
  return String(chat?.user_label ?? `Пользователь #${chat?.user_id ?? '?'}`)
}

async function scrollToBottom() {
  await nextTick()
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

async function loadChats(options = {}) {
  const { silent = false } = options
  if (!silent) {
    chatsLoading.value = true
    chatsError.value = null
  }
  try {
    const params = new URLSearchParams({
      limit: '200',
      offset: '0',
      only_needs_reply: onlyNeedsReply.value ? 'true' : 'false',
    })
    const data = await fetchJson(`/api/staff/support-chats?${params.toString()}`)
    chats.value = Array.isArray(data?.items) ? data.items : []
    chatsTotal.value = Number(data?.total) || 0
    needsReplyCount.value = Number(data?.needs_reply_count) || 0

    const qid = selectedUserIdFromQuery.value
    if (qid != null) {
      const found = chats.value.find((c) => Number(c.user_id) === qid)
      if (found) {
        selectChat(found, { syncRoute: false })
      } else if (!silent) {
        selectedUserId.value = qid
        selectedChat.value = { user_id: qid, user_label: `Пользователь #${qid}` }
        void loadMessages(qid)
      }
    } else if (selectedUserId.value != null) {
      const still = chats.value.find(
        (c) => Number(c.user_id) === Number(selectedUserId.value),
      )
      if (still) selectedChat.value = still
    }
  } catch (e) {
    if (!silent) {
      chatsError.value = e.message || String(e)
      chats.value = []
      chatsTotal.value = 0
      needsReplyCount.value = 0
    }
  } finally {
    if (!silent) {
      chatsLoading.value = false
    }
  }
}

async function loadMessages(userId, options = {}) {
  const { silent = false } = options
  const id = Number(userId)
  if (!Number.isFinite(id) || id < 1) return
  if (!silent) {
    messagesLoading.value = true
    messagesError.value = null
  }
  try {
    const params = new URLSearchParams({ limit: '300', offset: '0' })
    const data = await fetchJson(
      `/api/staff/support-chats/${id}/messages?${params.toString()}`,
    )
    const prevLastId = messages.value.at(-1)?.id ?? null
    messages.value = Array.isArray(data?.items) ? data.items : []
    const newLastId = messages.value.at(-1)?.id ?? null
    if (newLastId !== prevLastId || !silent) {
      await scrollToBottom()
    }
  } catch (e) {
    if (!silent) {
      messagesError.value = e.message || String(e)
      messages.value = []
    }
  } finally {
    if (!silent) {
      messagesLoading.value = false
    }
  }
}

function selectChat(chat, options = {}) {
  const { syncRoute = true } = options
  const id = Number(chat?.user_id)
  if (!Number.isFinite(id) || id < 1) return
  selectedUserId.value = id
  selectedChat.value = chat
  sendError.value = null
  if (syncRoute) {
    void router.replace({
      name: 'admin-support-staff',
      query: { user_id: String(id) },
    })
  }
  void loadMessages(id)
}

function clearSelection() {
  selectedUserId.value = null
  selectedChat.value = null
  messages.value = []
  messagesError.value = null
  sendError.value = null
  void router.replace({ name: 'admin-support-staff' })
}

async function submitReply() {
  const id = selectedUserId.value
  const text = sendText.value.trim()
  if (id == null || !text || sendBusy.value) return
  sendBusy.value = true
  sendError.value = null
  try {
    const created = await fetchJson(`/api/staff/support-chats/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ body: text }),
    })
    if (created && typeof created === 'object') {
      messages.value = [...messages.value, created]
    }
    sendText.value = ''
    await scrollToBottom()
    await loadChats({ silent: true })
  } catch (e) {
    sendError.value = e.message || String(e)
  } finally {
    sendBusy.value = false
  }
}

function onComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void submitReply()
  }
}

function refreshAll() {
  void loadChats()
  if (selectedUserId.value != null) {
    void loadMessages(selectedUserId.value)
  }
}

watch(onlyNeedsReply, () => {
  void loadChats()
})

watch(
  () => route.query.user_id,
  (q) => {
    const id = Number(typeof q === 'string' ? q : Array.isArray(q) ? q[0] : NaN)
    if (!Number.isFinite(id) || id < 1) {
      if (selectedUserId.value != null) clearSelection()
      return
    }
    if (Number(selectedUserId.value) === id) return
    const found = chats.value.find((c) => Number(c.user_id) === id)
    if (found) selectChat(found, { syncRoute: false })
    else {
      selectedUserId.value = id
      selectedChat.value = { user_id: id, user_label: `Пользователь #${id}` }
      void loadMessages(id)
    }
  },
)

onMounted(() => {
  void loadChats().then(() => {
    const qid = selectedUserIdFromQuery.value
    if (qid != null) {
      const found = chats.value.find((c) => Number(c.user_id) === qid)
      if (found) selectChat(found, { syncRoute: false })
      else {
        selectedUserId.value = qid
        selectedChat.value = { user_id: qid, user_label: `Пользователь #${qid}` }
        void loadMessages(qid)
      }
    }
  })
  pollTimer = setInterval(() => {
    void loadChats({ silent: true })
    if (selectedUserId.value != null) {
      void loadMessages(selectedUserId.value, { silent: true })
    }
  }, POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <AdminStaffShell title="Поддержка" shell-class="admin-support-page">
    <div class="support-toolbar">
      <label class="support-filter">
        <input
          v-model="onlyNeedsReply"
          type="checkbox"
          class="support-filter__input"
        />
        <span>Только ждут ответа</span>
        <span
          v-if="needsReplyCount > 0"
          class="support-filter__badge"
        >{{ needsReplyCount }}</span>
      </label>
      <span class="support-toolbar__meta muted">
        Чатов: {{ chatsTotal }}
      </span>
      <AppRefreshButton :loading="chatsLoading" @click="refreshAll" />
    </div>

    <StateNote v-if="chatsError" variant="error">{{ chatsError }}</StateNote>

    <div class="support-layout">
      <aside class="support-inbox card" aria-label="Список чатов">
        <div v-if="chatsLoading && !chats.length" class="support-inbox__state muted">
          Загрузка…
        </div>
        <p v-else-if="!chats.length" class="support-inbox__state muted">
          {{ onlyNeedsReply ? 'Нет чатов, ожидающих ответа.' : 'Сообщений от пользователей пока нет.' }}
        </p>
        <ul v-else class="support-inbox__list" role="list">
          <li v-for="chat in chats" :key="chat.user_id">
            <button
              type="button"
              class="support-inbox__item"
              :class="{
                'support-inbox__item--active':
                  Number(selectedUserId) === Number(chat.user_id),
                'support-inbox__item--needs-reply': chat.needs_reply,
              }"
              @click="selectChat(chat)"
            >
              <div class="support-inbox__item-head">
                <span class="support-inbox__label">{{ chatUserLabel(chat) }}</span>
                <time
                  class="support-inbox__time"
                  :datetime="String(chat.last_message_at)"
                >{{ formatTime(chat.last_message_at) }}</time>
              </div>
              <p class="support-inbox__preview">{{ chat.last_message_body }}</p>
              <span
                v-if="chat.needs_reply"
                class="support-inbox__badge"
              >Нужен ответ</span>
            </button>
          </li>
        </ul>
      </aside>

      <section class="support-thread card" aria-label="Переписка">
        <template v-if="selectedUserId != null">
          <header class="support-thread__head">
            <div class="support-thread__title-wrap">
              <h2 class="support-thread__title">
                {{ chatUserLabel(selectedChat) }}
              </h2>
              <AdminHighlightListLink
                list="users"
                :highlight="selectedUserId"
                panel
                title="Карточка пользователя"
                aria-label="Перейти к карточке пользователя"
              />
            </div>
            <button
              type="button"
              class="support-thread__close"
              @click="clearSelection"
            >
              Закрыть
            </button>
          </header>

          <div v-if="messagesLoading && !messages.length" class="support-thread__state muted">
            Загрузка сообщений…
          </div>
          <StateNote v-else-if="messagesError" variant="error">
            {{ messagesError }}
          </StateNote>
          <div v-else class="support-thread__messages" role="log" aria-live="polite">
            <article
              v-for="msg in messages"
              :key="msg.id"
              class="support-msg"
              :class="{
                'support-msg--staff': isStaffMessage(msg),
                'support-msg--user': !isStaffMessage(msg),
              }"
            >
              <div class="support-msg__meta">
                <span class="support-msg__author">{{
                  messageAuthorLabel(msg)
                }}</span>
                <time
                  class="support-msg__time"
                  :datetime="msg.created_at"
                >{{ formatTime(msg.created_at) }}</time>
              </div>
              <p class="support-msg__body">{{ msg.body }}</p>
            </article>
            <div ref="messagesEndRef" class="support-thread__anchor" aria-hidden="true" />
          </div>

          <form class="support-composer" @submit.prevent="submitReply">
            <label class="support-composer__field">
              <span class="visually-hidden">Ответ</span>
              <textarea
                v-model="sendText"
                class="support-composer__input"
                rows="3"
                maxlength="4000"
                placeholder="Ответ пользователю…"
                :disabled="sendBusy"
                @keydown="onComposerKeydown"
              />
            </label>
            <p v-if="sendError" class="support-composer__err err" role="alert">
              {{ sendError }}
            </p>
            <AppActionButton
              variant="accent"
              type="submit"
              :disabled="sendBusy || !sendText.trim()"
            >
              <template #icon>
                <Loader2
                  v-if="sendBusy"
                  class="support-composer__icon--spin"
                  :size="18"
                  :stroke-width="2"
                  aria-hidden="true"
                />
                <Send
                  v-else
                  :size="18"
                  :stroke-width="2"
                  aria-hidden="true"
                />
              </template>
              {{ sendBusy ? 'Отправка…' : 'Отправить ответ' }}
            </AppActionButton>
          </form>
        </template>
        <p v-else class="support-thread__empty muted">
          Выберите чат слева, чтобы просмотреть переписку и ответить.
        </p>
      </section>
    </div>
  </AdminStaffShell>
</template>

<style scoped>
.admin-support-page :deep(.admin-page-shell) {
  max-width: 72rem;
}

.support-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.support-filter {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-h);
  cursor: pointer;
  user-select: none;
}

.support-filter__input {
  width: 1rem;
  height: 1rem;
  accent-color: var(--accent);
}

.support-filter__badge {
  min-width: 1.35rem;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1.3;
  text-align: center;
  color: var(--on-accent);
  background: var(--danger);
}

.support-toolbar__meta {
  margin-right: auto;
  font-size: 0.88rem;
}

.muted {
  color: var(--muted);
}

.err {
  color: var(--danger);
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
  min-width: 0;
}

.support-layout {
  display: grid;
  grid-template-columns: minmax(15rem, 22rem) minmax(0, 1fr);
  gap: 0.85rem;
  min-height: min(72dvh, 40rem);
}

.support-inbox {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.support-inbox__state {
  margin: 0;
  padding: 1.25rem 1rem;
  font-size: 0.9rem;
  line-height: 1.45;
}

.support-inbox__list {
  margin: 0;
  padding: 0.35rem;
  list-style: none;
  overflow-y: auto;
  flex: 1;
}

.support-inbox__item {
  appearance: none;
  width: 100%;
  margin: 0 0 0.35rem;
  padding: 0.75rem 0.8rem;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.support-inbox__item:hover {
  background: color-mix(in srgb, var(--accent-soft) 35%, transparent);
}

.support-inbox__item--active {
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
  border-color: var(--accent-border);
}

.support-inbox__item--needs-reply {
  border-color: color-mix(in srgb, var(--danger) 35%, var(--card-border));
  background: color-mix(in srgb, var(--danger-soft) 45%, transparent);
}

.support-inbox__item--needs-reply.support-inbox__item--active {
  border-color: color-mix(in srgb, var(--danger) 55%, var(--accent-border));
}

.support-inbox__item-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.support-inbox__label {
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--text-h);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.support-inbox__time {
  flex-shrink: 0;
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.support-inbox__preview {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.support-inbox__badge {
  display: inline-block;
  margin-top: 0.35rem;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 35%, transparent);
}

.support-thread {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.support-thread__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--nav-border);
}

.support-thread__title-wrap {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem 0.5rem;
  min-width: 0;
}

.support-thread__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-h);
}

.support-thread__close {
  appearance: none;
  margin: 0;
  padding: 0.35rem 0.55rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--surface);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
}

.support-thread__close:hover {
  color: var(--text-h);
  border-color: var(--accent-border);
}

.support-thread__state,
.support-thread__empty {
  margin: 0;
  padding: 1.5rem 1rem;
  font-size: 0.92rem;
  line-height: 1.45;
}

.support-thread__messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.support-thread__anchor {
  height: 1px;
  flex-shrink: 0;
}

.support-msg {
  max-width: 88%;
  padding: 0.65rem 0.8rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
}

.support-msg--user {
  align-self: flex-start;
  background: color-mix(in srgb, var(--surface) 65%, var(--card-bg));
}

.support-msg--staff {
  align-self: flex-end;
  background: color-mix(in srgb, var(--accent-soft) 55%, var(--card-bg));
  border-color: color-mix(in srgb, var(--accent-border) 70%, var(--card-border));
}

.support-msg__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.55rem;
  margin-bottom: 0.25rem;
}

.support-msg__author {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--muted);
}

.support-msg--staff .support-msg__author {
  color: var(--accent);
}

.support-msg__time {
  font-size: 0.72rem;
  color: color-mix(in srgb, var(--muted) 85%, transparent);
  font-variant-numeric: tabular-nums;
}

.support-msg__body {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.5;
  color: var(--text-h);
  white-space: pre-wrap;
  word-break: break-word;
}

.support-composer {
  padding: 0.85rem 1rem 1rem;
  border-top: 1px solid var(--nav-border);
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.support-composer__field {
  display: block;
}

.support-composer__input {
  width: 100%;
  box-sizing: border-box;
  min-height: 4.5rem;
  resize: vertical;
  padding: 0.65rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-size: 0.92rem;
  line-height: 1.45;
}

.support-composer__input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.support-composer__err {
  margin: 0;
  font-size: 0.88rem;
}

.support-composer__icon--spin {
  animation: support-spin 0.85s linear infinite;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes support-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 820px) {
  .support-layout {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .support-inbox {
    max-height: 16rem;
  }

  .support-thread {
    min-height: min(55dvh, 28rem);
  }
}
</style>
