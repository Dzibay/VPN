<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { CheckCircle2, Clock3, ArrowRight } from 'lucide-vue-next'
import { fetchJson } from '../api/client.js'
import AppActionButton from '../components/AppActionButton.vue'
import CabinetBackLink from '../components/CabinetBackLink.vue'

const route = useRoute()
const meLoading = ref(true)
const subscriptionActive = ref(false)
const subscriptionUntil = ref(null)

const statusHint = computed(() => {
  const q = route.query
  if (q.success === 'false' || q.canceled === '1') return 'canceled'
  return 'pending'
})

const isCanceled = computed(() => statusHint.value === 'canceled')

onMounted(async () => {
  try {
    const me = await fetchJson('/api/me')
    subscriptionActive.value = Boolean(me.subscription_active)
    subscriptionUntil.value = me.subscription_until ?? null
  } catch {
    /* страница всё равно полезна без /me */
  } finally {
    meLoading.value = false
  }
})
</script>

<template>
  <main class="return-page">
    <div class="return-bg" aria-hidden="true" />
    <div class="return-wrap">
      <div class="return-card">
        <div class="icon-ring" :class="{ 'icon-ring--ok': subscriptionActive, 'icon-ring--wait': !subscriptionActive && !isCanceled }">
          <CheckCircle2
            v-if="subscriptionActive"
            :size="40"
            :stroke-width="1.75"
            aria-hidden="true"
          />
          <Clock3
            v-else-if="!isCanceled"
            :size="40"
            :stroke-width="1.75"
            aria-hidden="true"
          />
          <span v-else class="icon-x" aria-hidden="true">×</span>
        </div>

        <h1 v-if="isCanceled" class="return-title">Оплата не завершена</h1>
        <h1 v-else-if="subscriptionActive" class="return-title">Подписка продлена</h1>
        <h1 v-else class="return-title">Проверяем оплату</h1>

        <p v-if="isCanceled" class="return-desc">
          Платёж отменён или прерван. Средства не списаны — выберите тариф снова, когда будете готовы.
        </p>
        <p v-else-if="subscriptionActive" class="return-desc">
          Спасибо! Доступ обновлён
          <template v-if="subscriptionUntil"> до {{ subscriptionUntil }}</template>.
          Можно подключать устройства в личном кабинете.
        </p>
        <p v-else class="return-desc">
          Банк подтвердил перевод — мы получим уведомление от ЮKassa в течение минуты.
          Обновите кабинет чуть позже: подписка активируется автоматически.
        </p>

        <div v-if="!meLoading && !isCanceled && !subscriptionActive" class="return-tip card-pad">
          <p class="tip-text">
            Если через 5–10 минут доступ не появился, напишите в поддержку с email аккаунта.
          </p>
        </div>

        <div class="return-actions">
          <AppActionButton
            variant="primary"
            block
            :to="{ name: 'cabinet', query: { tab: 'subscription' } }"
          >
            <template #icon>
              <ArrowRight :size="18" :stroke-width="2" aria-hidden="true" />
            </template>
            В личный кабинет
          </AppActionButton>
          <AppActionButton
            v-if="!isCanceled && !subscriptionActive"
            variant="secondary"
            block
            :to="{ name: 'cabinet-pay' }"
          >
            К тарифам
          </AppActionButton>
        </div>
      </div>

      <CabinetBackLink
        class="return-back"
        :to="{ name: 'cabinet', query: { tab: 'subscription' } }"
      />
    </div>
  </main>
</template>

<style scoped>
.return-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
  overflow: hidden;
  color: var(--text);
  background: var(--bg-gradient);
}

.return-bg {
  position: absolute;
  inset: -20% -30%;
  background:
    radial-gradient(ellipse 55% 45% at 15% 20%, rgba(var(--accent-rgb, 59, 130, 246), 0.18), transparent 60%),
    radial-gradient(ellipse 50% 40% at 85% 75%, rgba(16, 185, 129, 0.12), transparent 55%);
  pointer-events: none;
}

.return-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem max(1rem, env(safe-area-inset-left, 0px)) 2.5rem
    max(1rem, env(safe-area-inset-right, 0px));
  position: relative;
  z-index: 1;
  gap: 1rem;
}

.return-card {
  width: 100%;
  max-width: 22rem;
  padding: 2rem 1.5rem 1.75rem;
  text-align: center;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  box-shadow: var(--shadow-md);
  animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.icon-ring {
  width: 4.5rem;
  height: 4.5rem;
  margin: 0 auto 1.25rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--card-border);
  color: var(--muted);
}

.icon-ring--ok {
  border-color: rgba(16, 185, 129, 0.45);
  background: color-mix(in srgb, rgb(16, 185, 129) 12%, transparent);
  color: rgb(16, 185, 129);
}

.icon-ring--wait {
  border-color: rgba(var(--accent-rgb, 59, 130, 246), 0.35);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
}

.icon-x {
  font-size: 2rem;
  line-height: 1;
  font-weight: 300;
}

.return-title {
  margin: 0 0 0.65rem;
  font-size: 1.35rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--text-h);
}

.return-desc {
  margin: 0 0 1.25rem;
  font-size: 0.92rem;
  line-height: 1.5;
  color: var(--muted);
}

.return-tip {
  margin-bottom: 1.25rem;
  text-align: left;
  background: color-mix(in srgb, var(--accent) 6%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--card-border));
  border-radius: 12px;
}

.tip-text {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
}

.return-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.return-back {
  margin-top: 0.25rem;
}
</style>
