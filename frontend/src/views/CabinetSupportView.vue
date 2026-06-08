<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppActionButton from '../components/AppActionButton.vue'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import SitePageLayout from '../components/SitePageLayout.vue'
import { fetchJson } from '../api/client.js'
import { refreshClientSupportUnread } from '../composables/useClientSupportUnread.js'
import { formatMskApiDateTime } from '../utils/mskDate.js'
import { Loader2, Send } from 'lucide-vue-next'

const POLL_MS = 15000

const router = useRouter()

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number, author_kind: string, body: string, created_at: string }>>} */
const messages = ref([])
const sendText = ref('')
const sendBusy = ref(false)
const sendError = ref(null)

const messagesEndRef = ref(null)
/** @type {ReturnType<typeof setInterval> | null} */
let pollTimer = null

const hasMessages = computed(() => messages.value.length > 0)

function formatMessageTime(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'short' })
}

function isStaffMessage(msg) {
  return msg?.author_kind === 'staff'
}

async function scrollToBottom() {
  await nextTick()
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

async function markSupportSeen() {
  try {
    await fetchJson('/api/me/support-messages/mark-seen', {
      method: 'POST',
      body: '{}',
    })
    await refreshClientSupportUnread()
  } catch {
    /* ignore */
  }
}

async function loadMessages(options = {}) {
  const { silent = false, markSeen = false } = options
  if (!silent) {
    loading.value = true
    error.value = null
  }
  try {
    const params = new URLSearchParams({ limit: '200', offset: '0' })
    const data = await fetchJson(`/api/me/support-messages?${params.toString()}`)
    const prevLastId = messages.value.at(-1)?.id ?? null
    messages.value = Array.isArray(data?.items) ? data.items : []
    const newLastId = messages.value.at(-1)?.id ?? null
    if (newLastId !== prevLastId || !silent) {
      await scrollToBottom()
    }
    if (markSeen) {
      await markSupportSeen()
    }
  } catch (e) {
    if (e.status === 401) {
      router.replace({ name: 'login', query: { redirect: '/cabinet/support' } })
      return
    }
    if (!silent) {
      error.value = e.message || String(e)
      messages.value = []
    }
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

async function submitMessage() {
  const text = sendText.value.trim()
  if (!text || sendBusy.value) return
  sendBusy.value = true
  sendError.value = null
  try {
    const created = await fetchJson('/api/me/support-messages', {
      method: 'POST',
      body: JSON.stringify({ body: text }),
    })
    if (created && typeof created === 'object') {
      messages.value = [...messages.value, created]
    }
    sendText.value = ''
    await scrollToBottom()
  } catch (e) {
    sendError.value = e.message || String(e)
  } finally {
    sendBusy.value = false
  }
}

function onComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void submitMessage()
  }
}

onMounted(() => {
  void loadMessages({ markSeen: true })
  pollTimer = setInterval(() => {
    void loadMessages({ silent: true })
  }, POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

watch(
  () => messages.value.length,
  () => {
    void scrollToBottom()
  },
)
</script>

<template>
  <SitePageLayout class="support-page">
    <template #header>
      <header class="head">
        <h1>Поддержка</h1>
        <p class="sub">Напишите нам — ответим в этом чате</p>
      </header>
    </template>

    <CabinetBackLink to="/cabinet" label="Личный кабинет" />

    <div class="support-shell">
      <div v-if="loading" class="card card-pad muted">Загрузка…</div>
      <div v-else-if="error" class="card card-pad err">{{ error }}</div>
      <template v-else>
        <div class="card support-chat" aria-label="Чат с поддержкой">
          <div class="support-chat__messages" role="log" aria-live="polite">
            <p v-if="!hasMessages" class="support-chat__empty hint">
              Сообщений пока нет. Опишите проблему — команда поддержки ответит здесь.
            </p>
            <article
              v-for="msg in messages"
              :key="msg.id"
              class="support-msg"
              :class="{
                'support-msg--user': !isStaffMessage(msg),
                'support-msg--staff': isStaffMessage(msg),
              }"
            >
              <div class="support-msg__meta">
                <span class="support-msg__author">{{
                  isStaffMessage(msg) ? 'Поддержка' : 'Вы'
                }}</span>
                <time
                  class="support-msg__time"
                  :datetime="msg.created_at"
                >{{ formatMessageTime(msg.created_at) }}</time>
              </div>
              <p class="support-msg__body">{{ msg.body }}</p>
            </article>
            <div ref="messagesEndRef" class="support-chat__anchor" aria-hidden="true" />
          </div>

          <form class="support-composer" @submit.prevent="submitMessage">
            <label class="support-composer__field">
              <span class="visually-hidden">Сообщение</span>
              <textarea
                v-model="sendText"
                class="support-composer__input"
                rows="3"
                maxlength="4000"
                placeholder="Опишите проблему…"
                :disabled="sendBusy"
                @keydown="onComposerKeydown"
              />
            </label>
            <p v-if="sendError" class="support-composer__err err" role="alert">
              {{ sendError }}
            </p>
            <AppActionButton
              variant="accent"
              block
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
              {{ sendBusy ? 'Отправка…' : 'Отправить' }}
            </AppActionButton>
          </form>
        </div>
      </template>
    </div>
  </SitePageLayout>
</template>

<style scoped>
.support-page :deep(.site-page-layout__body) {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

h1 {
  font-size: 1.6rem;
  margin: 0 0 0.4rem;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.support-shell {
  min-width: 0;
}

.card {
  min-width: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.35rem 1.4rem;
}

.muted {
  color: var(--muted);
}

.err {
  color: var(--danger);
}

.hint {
  margin: 0;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.45;
}

.support-chat {
  display: flex;
  flex-direction: column;
  min-height: min(70dvh, 36rem);
  overflow: hidden;
}

.support-chat__messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem 1rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.support-chat__empty {
  margin: auto 0;
  text-align: center;
  padding: 1.5rem 0.5rem;
}

.support-chat__anchor {
  height: 1px;
  flex-shrink: 0;
}

.support-msg {
  max-width: 92%;
  padding: 0.65rem 0.8rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
}

.support-msg--user {
  align-self: flex-end;
  background: color-mix(in srgb, var(--accent-soft) 55%, var(--card-bg));
  border-color: color-mix(in srgb, var(--accent-border) 70%, var(--card-border));
}

.support-msg--staff {
  align-self: flex-start;
  background: color-mix(in srgb, var(--surface) 65%, var(--card-bg));
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
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
}

.support-msg--user .support-msg__author {
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
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.support-composer__input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.support-composer__input:disabled {
  opacity: 0.65;
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

@media (max-width: 420px) {
  .support-chat {
    min-height: min(72dvh, 32rem);
  }

  .support-chat__messages {
    padding: 0.85rem 0.85rem 0.35rem;
  }

  .support-composer {
    padding: 0.75rem 0.85rem 0.85rem;
  }
}
</style>
