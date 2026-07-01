<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight, Check, Clock3, MessageCircle } from 'lucide-vue-next'
import AppActionButton from '../components/AppActionButton.vue'
import { fetchJson } from '../api/client.js'

const route = useRoute()
const linksLoading = ref(true)
/** @type {import('vue').Ref<{ telegram_bot_page_url?: string | null, support_telegram_url?: string | null } | null>} */
const siteLinks = ref(null)

const isCanceled = computed(() => {
  const q = route.query
  return q.success === 'false' || q.canceled === '1'
})

const botUrl = computed(() => {
  const raw = siteLinks.value?.telegram_bot_page_url
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
})

const botLabel = computed(() => {
  const url = botUrl.value
  if (!url) return 'Telegram-бот'
  const m = url.match(/t\.me\/([^/?#]+)/i)
  return m?.[1] ? `@${m[1]}` : 'Telegram-бот'
})

const supportTelegramUrl = computed(() => {
  const raw = siteLinks.value?.support_telegram_url
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
})

const supportTelegramLabel = computed(() => {
  const url = supportTelegramUrl.value
  if (!url) return null
  const m = url.match(/t\.me\/([^/?#]+)/i)
  return m?.[1] ? `@${m[1]}` : 'поддержку'
})

onMounted(async () => {
  try {
    siteLinks.value = await fetchJson('/api/public/site-links')
  } catch {
    siteLinks.value = null
  } finally {
    linksLoading.value = false
  }
})
</script>

<template>
  <main class="return-page">
    <div class="return-page__inner">
      <div class="return-card">
        <div
          class="return-card__icon"
          :class="{
            'return-card__icon--ok': !isCanceled,
            'return-card__icon--fail': isCanceled,
          }"
        >
          <Check
            v-if="!isCanceled"
            :size="36"
            :stroke-width="2.5"
            aria-hidden="true"
          />
          <span v-else class="return-card__x" aria-hidden="true">×</span>
        </div>

        <h1 v-if="isCanceled" class="return-card__title">Оплата не завершена</h1>
        <h1 v-else class="return-card__title">Спасибо за оплату!</h1>

        <p v-if="isCanceled" class="return-card__lead">
          Платёж отменён или прерван. Средства не списаны. Вернитесь в бот и попробуйте снова.
        </p>
        <p v-else class="return-card__lead">
          Банк принял платёж. Подписка активируется в течение минуты — вернитесь в
          Telegram-бот, чтобы пользоваться VPN.
        </p>

        <p v-if="!isCanceled" class="return-card__hint">
          <Clock3 :size="16" :stroke-width="2" aria-hidden="true" />
          Если доступ в боте не обновился через 1–2 минуты,
          <template v-if="supportTelegramUrl">
            напишите в
            <a
              class="return-card__hint-link"
              :href="supportTelegramUrl"
              target="_blank"
              rel="noopener noreferrer"
            >{{ supportTelegramLabel }}</a>.
          </template>
          <template v-else>обратитесь в поддержку.</template>
        </p>

        <AppActionButton
          v-if="botUrl"
          variant="primary"
          large
          block
          class="return-cta-btn--trail"
          :href="botUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          Открыть {{ botLabel }}
          <template #icon>
            <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
          </template>
        </AppActionButton>

        <p v-else-if="!linksLoading" class="return-card__warn">
          <MessageCircle :size="18" :stroke-width="2" aria-hidden="true" />
          Ссылка на бот не настроена на сервере. Закройте эту вкладку и откройте бот из
          Telegram вручную.
        </p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.return-page {
  flex: 1;
  min-height: 0;
  background: var(--bg-gradient);
  color: var(--text);
  font: inherit;
}

.return-page__inner {
  width: 100%;
  max-width: min(var(--page-content-max, 36rem), 100%);
  margin: 0 auto;
  padding: var(--page-content-pad-block-start, 2rem) max(1rem, env(safe-area-inset-left))
    var(--page-content-pad-block-end, 2.5rem) max(1rem, env(safe-area-inset-right));
  box-sizing: border-box;
}

.return-card {
  padding: 2rem 1.5rem 1.75rem;
  text-align: center;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  box-shadow: var(--shadow-md);
  animation: return-rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes return-rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.return-card__icon {
  width: 4.5rem;
  height: 4.5rem;
  margin: 0 auto 1.15rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2px solid var(--card-border);
  color: var(--muted);
}

.return-card__icon--ok {
  border-color: transparent;
  color: var(--on-accent);
  background: linear-gradient(135deg, var(--brand-mint) 0%, var(--brand-teal) 100%);
  box-shadow: var(--shadow-sm), 0 8px 24px var(--accent-glow);
}

@media (prefers-color-scheme: light) {
  .return-card__icon--ok {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-muted) 100%);
  }
}

.return-card__icon--fail {
  background: var(--danger-soft);
  border-color: color-mix(in srgb, var(--danger) 35%, transparent);
  color: var(--danger);
}

.return-card__x {
  font-size: 2rem;
  line-height: 1;
  font-weight: 300;
}

.return-card__title {
  margin: 0 0 0.5rem;
  font-size: 1.45rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text-h);
}

.return-card__lead {
  margin: 0 0 1.35rem;
  font-size: 0.92rem;
  line-height: 1.5;
  color: var(--muted);
}

.return-card__hint {
  display: flex;
  align-items: flex-start;
  gap: 0.45rem;
  margin: 0 0 1.25rem;
  padding: 0.75rem 0.9rem;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
  text-align: left;
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  border-radius: 12px;
}

.return-card__hint :deep(svg) {
  flex-shrink: 0;
  margin-top: 0.1rem;
  color: var(--accent);
}

.return-card__hint-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.return-card__warn {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0;
  padding: 0.75rem 0.9rem;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
  text-align: left;
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 25%, transparent);
  border-radius: 12px;
}

.return-cta-btn--trail {
  flex-direction: row-reverse;
}
</style>
