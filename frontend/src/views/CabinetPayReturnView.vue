<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  ArrowRight,
  Calendar,
  Check,
  Clock3,
  Gift,
  Headphones,
  Monitor,
  RefreshCw,
  Shield,
  Wifi,
} from 'lucide-vue-next'
import AppActionButton from '../components/AppActionButton.vue'
import { fetchJson } from '../api/client.js'
import { formatTrafficWithLimit } from '../utils/formatTraffic.js'

const route = useRoute()
const meLoading = ref(true)
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const me = ref(null)

const statusHint = computed(() => {
  const q = route.query
  if (q.success === 'false' || q.canceled === '1') return 'canceled'
  return 'pending'
})

const isCanceled = computed(() => statusHint.value === 'canceled')
const subscriptionActive = computed(() => Boolean(me.value?.subscription_active))

const subscriptionUntilLabel = computed(() => {
  const d = me.value?.subscription_until
  if (!d) return '—'
  try {
    return new Date(String(d)).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
  } catch {
    return String(d)
  }
})

const devicesLabel = computed(() => {
  const n = Number(me.value?.subscription_connections_count) || 0
  const limit = me.value?.subscription_connections_limit
  if (limit == null || limit === '') return `${n}`
  return `${n} из ${limit}`
})

const trafficLabel = computed(() =>
  formatTrafficWithLimit(
    me.value?.traffic_total_bytes ?? 0,
    me.value?.traffic_limit_bytes,
  ),
)

const supportTelegramUrl = computed(() => {
  const raw = me.value?.support_telegram_url
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
})

const supportTelegramLabel = computed(() => {
  const url = supportTelegramUrl.value
  if (!url) return null
  const m = url.match(/t\.me\/([^/?#]+)/i)
  return m?.[1] ? `@${m[1]}` : 'Telegram'
})

onMounted(async () => {
  try {
    me.value = await fetchJson('/api/me')
  } catch {
    me.value = null
  } finally {
    meLoading.value = false
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
            'return-card__icon--ok': subscriptionActive && !isCanceled,
            'return-card__icon--wait': !subscriptionActive && !isCanceled,
            'return-card__icon--fail': isCanceled,
          }"
        >
          <Check
            v-if="subscriptionActive && !isCanceled"
            :size="36"
            :stroke-width="2.5"
            aria-hidden="true"
          />
          <Clock3
            v-else-if="!isCanceled"
            :size="36"
            :stroke-width="2"
            aria-hidden="true"
          />
          <span v-else class="return-card__x" aria-hidden="true">×</span>
        </div>

        <h1 v-if="isCanceled" class="return-card__title">Оплата не завершена</h1>
        <h1 v-else-if="subscriptionActive" class="return-card__title">
          Подписка активирована!
        </h1>
        <h1 v-else class="return-card__title">Проверяем оплату</h1>

        <p v-if="isCanceled" class="return-card__lead">
          Платёж отменён или прерван. Средства не списаны.
        </p>
        <p v-else-if="subscriptionActive" class="return-card__lead">
          Спасибо! Оплата прошла успешно. Доступ к VPN-сервису открыт.
        </p>
        <p v-else class="return-card__lead">
          Банк подтвердил перевод — подписка активируется в течение минуты после
          уведомления ЮKassa.
        </p>

        <ul
          v-if="!isCanceled && subscriptionActive && !meLoading"
          class="return-details"
        >
          <li>
            <span class="return-details__ico" aria-hidden="true">
              <Calendar :size="20" :stroke-width="2" />
            </span>
            <span class="return-details__label">Доступ продлён до</span>
            <span class="return-details__value">{{ subscriptionUntilLabel }}</span>
          </li>
          <li>
            <span class="return-details__ico" aria-hidden="true">
              <Monitor :size="20" :stroke-width="2" />
            </span>
            <span class="return-details__label">Подключено устройств</span>
            <span class="return-details__value">{{ devicesLabel }}</span>
          </li>
          <li>
            <span class="return-details__ico" aria-hidden="true">
              <Wifi :size="20" :stroke-width="2" />
            </span>
            <span class="return-details__label">Потреблённый трафик</span>
            <span class="return-details__value">{{ trafficLabel }}</span>
          </li>
        </ul>

        <p
          v-else-if="!isCanceled && !subscriptionActive && !meLoading"
          class="return-card__hint"
        >
          Обновите страницу через 1–2 минуты. Если доступ не появился —
          <template v-if="supportTelegramUrl">
            напишите в поддержку
            <a
              class="return-card__hint-link"
              :href="supportTelegramUrl"
              target="_blank"
              rel="noopener noreferrer"
            >{{ supportTelegramLabel ? ` ${supportTelegramLabel}` : '' }}</a>
          </template>
          <template v-else>напишите в поддержку</template>
        </p>

        <AppActionButton
          variant="primary"
          large
          block
          class="return-cta-btn--trail"
          :to="{ name: 'cabinet', query: { tab: 'subscription' } }"
        >
          Перейти в личный кабинет
          <template #icon>
            <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
          </template>
        </AppActionButton>

        <AppActionButton
          v-if="!isCanceled && !subscriptionActive"
          variant="secondary"
          block
          class="return-cta-alt"
          :to="{ name: 'cabinet-pay' }"
        >
          К тарифам
        </AppActionButton>
      </div>

      <section v-if="subscriptionActive && !isCanceled" class="return-thanks">
        <p class="return-thanks__title">
          <Gift :size="18" :stroke-width="2" aria-hidden="true" />
          Спасибо, что выбираете нас!
        </p>
        <div class="return-benefits">
          <div>
            <Shield :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>Стабильное соединение</strong>
            <span>Надёжные серверы и шифрование</span>
          </div>
          <div>
            <Headphones :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>Поддержка 24/7</strong>
            <span>Поможем с настройкой</span>
          </div>
          <div>
            <RefreshCw :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>Регулярные обновления</strong>
            <span>Актуальные конфигурации</span>
          </div>
        </div>
      </section>

      <footer class="return-brand" aria-hidden="true">
        <Shield :size="22" :stroke-width="2" />
        <span>Подорожник VPN</span>
      </footer>
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
  background: linear-gradient(
    135deg,
    var(--brand-mint) 0%,
    var(--brand-teal) 100%
  );
  box-shadow: var(--shadow-sm), 0 8px 24px var(--accent-glow);
}

@media (prefers-color-scheme: light) {
  .return-card__icon--ok {
    background: linear-gradient(
      135deg,
      var(--accent) 0%,
      var(--accent-muted) 100%
    );
  }
}

.return-card__icon--wait {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
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

.return-details {
  margin: 0 0 1.35rem;
  padding: 0;
  list-style: none;
  text-align: left;
  border-top: 1px solid var(--card-border);
}

.return-details li {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--card-border);
}

.return-details__ico {
  display: flex;
  color: var(--accent);
}

.return-details__label {
  font-size: 0.88rem;
  color: var(--muted);
}

.return-details__value {
  grid-column: 3;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--accent-muted);
  text-align: right;
}

.return-card__hint {
  margin: 0 0 1.25rem;
  padding: 0.75rem 0.9rem;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  border-radius: 12px;
  text-align: left;
}

.return-card__hint-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.return-card__hint-link:hover {
  color: var(--accent-hover);
}

.return-cta-btn--trail {
  flex-direction: row-reverse;
}

.return-cta-alt {
  margin-top: 0.65rem;
}

.return-thanks {
  margin-top: 1.5rem;
  padding: 1.25rem 1rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  box-shadow: var(--shadow-sm);
}

.return-thanks__title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  margin: 0 0 1rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--accent-muted);
}

.return-benefits {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  text-align: center;
}

@media (min-width: 520px) {
  .return-benefits {
    grid-template-columns: repeat(3, 1fr);
  }
}

.return-benefits div {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
}

.return-benefits :deep(svg) {
  color: var(--accent);
}

.return-benefits strong {
  font-size: 0.82rem;
}

.return-benefits span {
  font-size: 0.72rem;
  color: var(--muted);
  line-height: 1.35;
}

.return-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  margin-top: 2rem;
  color: var(--muted);
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.06em;
}
</style>
