<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, Lock, ShieldCheck, Zap } from 'lucide-vue-next'
import AppActionButton from '../components/AppActionButton.vue'
import { fetchJson } from '../api/client.js'
import {
  formatPeriod,
  formatRub,
  monthlyPriceRub,
  savingsRub,
  useYookassaPricing,
} from '../composables/useYookassaPricing.js'

/** Кошелёк / карта с щитом: frontend/public/images/pay-wallet.png */
const PAY_WALLET_IMG = '/images/pay-wallet.png'

/**
 * Логотипы платёжных систем (PNG/SVG), положите в frontend/public/images/pay-brands/:
 * visa.png, mastercard.png, mir.png, sbp.png, yookassa.png
 * Либо одна общая полоса: pay-brands-row.png (переключите USE_BRANDS_ROW ниже).
 */
const USE_BRANDS_ROW = false
const PAY_BRANDS_ROW = '/images/pay-brands-row.png'
const PAY_BRAND_FILES = [
  { file: 'visa.png', alt: 'Visa' },
  { file: 'mastercard.png', alt: 'Mastercard' },
  { file: 'mir.png', alt: 'МИР' },
  { file: 'sbp.png', alt: 'СБП' },
  { file: 'yookassa.png', alt: 'ЮKassa' },
]

const payingMonths = ref(null)
const walletImgVisible = ref(true)
const brandsRowVisible = ref(true)
/** @type {import('vue').Ref<Record<string, boolean>>} */
const brandVisible = ref(
  Object.fromEntries(PAY_BRAND_FILES.map((b) => [b.file, true])),
)
const {
  loading,
  error,
  tariffs: tariffList,
  baseMonthlyPrice,
  load: loadTariffs,
} = useYookassaPricing('/api/me/payments/tariffs')

const featureItems = [
  {
    icon: Lock,
    title: 'Без привязки карты',
    desc: 'Платите как удобно: карта или СБП',
  },
  {
    icon: Zap,
    title: 'Моментальная активация',
    desc: 'Доступ к VPN сразу после оплаты',
  },
  {
    icon: ShieldCheck,
    title: 'Безопасно и надёжно',
    desc: 'Ваши данные под защитой',
  },
]

function tariffSavings(tariff) {
  return savingsRub(tariff, baseMonthlyPrice.value)
}

function badgeFor(months) {
  if (months === 3) return { text: '🔥 Популярный', variant: 'popular' }
  if (months === 12) return { text: '💎 Лучшая цена', variant: 'best' }
  return null
}

function onBrandError(file) {
  brandVisible.value[file] = false
}

async function startCheckout(months) {
  if (payingMonths.value != null) return
  payingMonths.value = months
  error.value = null
  try {
    const res = await fetchJson('/api/me/payments/yookassa/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ months }),
    })
    const url = res?.confirmation_url
    if (!url || typeof url !== 'string') {
      throw new Error('Сервер не вернул ссылку на оплату')
    }
    window.location.href = url
  } catch (e) {
    error.value = e.message || String(e)
    payingMonths.value = null
  }
}

onMounted(() => {
  void loadTariffs()
})
</script>

<template>
  <main class="pay-page">
    <div class="pay-page__inner">
      <RouterLink
        class="pay-back"
        :to="{ name: 'cabinet', query: { tab: 'subscription' } }"
      >
        <ArrowLeft :size="16" :stroke-width="2.5" aria-hidden="true" />
        Личный кабинет
      </RouterLink>

      <div v-if="loading" class="pay-state pay-state--loading">
        <div class="pay-spinner" />
        <span>Загрузка тарифов…</span>
      </div>

      <div v-else-if="error" class="pay-state pay-state--error" role="alert">
        {{ error }}
      </div>

      <template v-else>
        <header class="pay-hero">
          <div class="pay-hero__main">
            <h1 class="pay-hero__title">Выберите тариф</h1>
            <div class="pay-secure">
              <span class="pay-secure__icon" aria-hidden="true">
                <Lock :size="20" :stroke-width="2.25" />
              </span>
              <div class="pay-secure__copy">
                <p class="pay-secure__title">Безопасная оплата</p>
                <p class="pay-secure__desc">
                  Оплата через ЮKassa. Карта или СБП. Доступ активируется автоматически.
                </p>
              </div>
            </div>
          </div>
          <div class="pay-hero__art" aria-hidden="true">
            <img
              v-show="walletImgVisible"
              class="pay-hero__wallet"
              :src="PAY_WALLET_IMG"
              alt=""
              @error="walletImgVisible = false"
            >
          </div>
        </header>

        <p v-if="tariffList.length === 0" class="pay-state pay-state--empty">
          Тарифы пока не настроены. Напишите в поддержку.
        </p>

        <div v-else class="pay-tariffs">
          <article
            v-for="tariff in tariffList"
            :key="tariff.months"
            class="pay-tariff"
            :class="{
              'pay-tariff--popular': tariff.months === 3,
              'pay-tariff--best': tariff.months === 12,
            }"
          >
            <span
              v-if="badgeFor(tariff.months)"
              class="pay-tariff__badge"
              :class="`pay-tariff__badge--${badgeFor(tariff.months).variant}`"
            >
              {{ badgeFor(tariff.months).text }}
            </span>

            <h2 class="pay-tariff__term">{{ formatPeriod(tariff.months) }}</h2>
            <p class="pay-tariff__sub">{{ tariff.name }}</p>

            <div class="pay-tariff__price-row">
              <span class="pay-tariff__price">{{ formatRub(tariff.price) }}</span>
              <span v-if="tariff.months > 1" class="pay-tariff__pill">
                ~{{ formatRub(monthlyPriceRub(tariff)) }}/мес
              </span>
            </div>

            <p v-if="tariffSavings(tariff)" class="pay-tariff__save">
              Экономия {{ formatRub(tariffSavings(tariff)) }}
            </p>

            <AppActionButton
              variant="primary"
              large
              block
              class="pay-tariff__checkout"
              :disabled="payingMonths != null"
              @click="startCheckout(tariff.months)"
            >
              {{ payingMonths === tariff.months ? 'Переход…' : 'Оплатить' }}
            </AppActionButton>
          </article>
        </div>

        <section v-if="tariffList.length" class="pay-features">
          <div
            v-for="(item, i) in featureItems"
            :key="i"
            class="pay-features__item"
          >
            <span class="pay-features__ico" aria-hidden="true">
              <component :is="item.icon" :size="22" :stroke-width="2" />
            </span>
            <div class="pay-features__text">
              <p class="pay-features__title">{{ item.title }}</p>
              <p class="pay-features__desc">{{ item.desc }}</p>
            </div>
          </div>
        </section>

        <footer v-if="tariffList.length" class="pay-footer">
          <p class="pay-footer__processor">
            <Lock :size="14" :stroke-width="2" aria-hidden="true" />
            Платежи обрабатываются ЮKassa
          </p>
          <div class="pay-footer__plate">
            <img
              v-if="USE_BRANDS_ROW"
              v-show="brandsRowVisible"
              class="pay-footer__brands-row"
              :src="PAY_BRANDS_ROW"
              alt="Способы оплаты"
              @error="brandsRowVisible = false"
            >
            <div v-else class="pay-footer__brands">
              <img
                v-for="b in PAY_BRAND_FILES"
                v-show="brandVisible[b.file]"
                :key="b.file"
                class="pay-footer__brand-img"
                :src="`/images/pay-brands/${b.file}`"
                :alt="b.alt"
                @error="onBrandError(b.file)"
              >
            </div>
          </div>
        </footer>
      </template>
    </div>
  </main>
</template>

<style scoped>
.pay-page {
  flex: 1;
  min-height: 0;
  background: var(--bg-gradient);
  color: var(--text);
  font: inherit;
}

.pay-page__inner {
  width: 100%;
  max-width: min(var(--page-content-max, 32rem), 100%);
  margin: 0 auto;
  padding: var(--page-content-pad-block-start, 1.75rem) max(1rem, env(safe-area-inset-left, 0px))
    var(--page-content-pad-block-end, 2.5rem) max(1rem, env(safe-area-inset-right, 0px));
  box-sizing: border-box;
}

.pay-back {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 1.5rem;
  color: var(--accent);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}

.pay-back:hover {
  color: var(--accent-hover);
}

.pay-hero {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem;
  margin-bottom: 1.75rem;
  align-items: start;
}

@media (min-width: 480px) {
  .pay-hero {
    grid-template-columns: 1fr auto;
    column-gap: 0.5rem;
  }
}

.pay-hero__title {
  margin: 0 0 1.1rem;
  font-size: clamp(1.75rem, 4.5vw, 2.25rem);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.1;
  color: var(--text-h);
}

.pay-secure {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  max-width: 30rem;
}

.pay-secure__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 0.1rem;
  color: var(--accent);
}

.pay-secure__title {
  margin: 0 0 0.35rem;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-h);
  line-height: 1.25;
}

.pay-secure__desc {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--muted);
}

.pay-hero__art {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  flex-shrink: 0;
  min-height: 6rem;
}

@media (max-width: 479px) {
  .pay-hero__art {
    justify-content: center;
    margin-top: 0.35rem;
  }
}

.pay-hero__wallet {
  width: min(15.5rem, 52vw);
  height: auto;
  max-height: 11.5rem;
  object-fit: contain;
  object-position: top right;
}

.pay-tariffs {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

@media (min-width: 560px) {
  .pay-tariffs {
    grid-template-columns: repeat(2, 1fr);
    gap: 1.1rem;
  }
}

.pay-tariff {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 11.5rem;
  padding: 1.25rem 1.25rem 1.15rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  box-shadow: var(--shadow-md);
}

.pay-tariff--popular {
  border: 2px solid var(--accent-border);
  box-shadow: var(--shadow-md), 0 0 0 1px var(--accent-soft);
}

.pay-tariff--best {
  border: 2px solid color-mix(in srgb, var(--accent-muted) 55%, var(--card-border));
  box-shadow: var(--shadow-md);
}

.pay-tariff__badge {
  position: absolute;
  top: 0.85rem;
  right: 0.85rem;
  padding: 0.28rem 0.6rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

.pay-tariff__badge--popular {
  background: #fff7ed;
  color: #9a3412;
  border: 1px solid #ffedd5;
}

.pay-tariff__badge--best {
  background: var(--accent-soft);
  color: var(--accent-muted);
  border: 1px solid var(--accent-border);
}

.pay-tariff__term {
  margin: 0;
  padding-right: 6.5rem;
  font-size: 1.125rem;
  font-weight: 700;
  line-height: 1.2;
}

.pay-tariff__sub {
  margin: 0.15rem 0 0.85rem;
  font-size: 0.8125rem;
  color: var(--muted);
  line-height: 1.2;
}

.pay-tariff__price-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.65rem;
  margin-bottom: 0.35rem;
}

.pay-tariff__price {
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
}

.pay-tariff__pill {
  display: inline-block;
  padding: 0.22rem 0.55rem;
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent-muted);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.2;
}

.pay-tariff__save {
  margin: 0 0 1rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--accent);
  line-height: 1.3;
}

.pay-tariff:not(:has(.pay-tariff__save)) .pay-tariff__price-row {
  margin-bottom: 1rem;
}

.pay-tariff__checkout {
  margin-top: auto;
}

.pay-features {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.35rem;
  margin-bottom: 1.75rem;
  padding: 1.25rem 1.15rem;
  background: var(--surface-glass);
  border: 1px solid var(--card-border);
  border-radius: 14px;
}

@media (min-width: 520px) {
  .pay-features {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem 0.5rem;
    padding: 1.35rem 1.25rem;
  }
}

.pay-features__item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  min-width: 0;
}

.pay-features__ico {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
}

.pay-features__text {
  min-width: 0;
}

.pay-features__title {
  margin: 0 0 0.2rem;
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--text-h);
  line-height: 1.25;
}

.pay-features__desc {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.4;
  color: var(--muted);
}

.pay-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.pay-footer__processor {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: 0.8125rem;
  color: var(--muted);
}

.pay-footer__processor :deep(svg) {
  color: var(--muted);
  flex-shrink: 0;
}

.pay-footer__plate {
  width: 100%;
  padding: 1rem 1.15rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-sm);
}

.pay-footer__brands {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 1rem 1.5rem;
  min-height: 1.75rem;
}

.pay-footer__brand-img {
  height: 1.5rem;
  width: auto;
  max-width: 5rem;
  object-fit: contain;
  opacity: 0.9;
}

.pay-footer__brands-row {
  display: block;
  width: 100%;
  max-width: 32rem;
  height: auto;
  margin: 0 auto;
  object-fit: contain;
}

.pay-state {
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--muted);
}

.pay-state--error {
  color: var(--danger);
  background: var(--danger-soft);
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 35%, transparent);
}

.pay-state--loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.pay-spinner {
  width: 1.75rem;
  height: 1.75rem;
  border: 2px solid var(--card-border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: pay-spin 0.8s linear infinite;
}

@keyframes pay-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
