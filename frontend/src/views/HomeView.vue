<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { getAccessToken } from '../auth/session.js'

const router = useRouter()
const hasToken = ref(false)

function refreshAuth() {
  hasToken.value = Boolean(getAccessToken())
}

const isLoggedIn = computed(() => hasToken.value)

onMounted(refreshAuth)
router.afterEach(refreshAuth)

// Данные для преимуществ
const benefits = [
  {
    title: 'Умный Split Tunneling',
    text: 'Трафик разделяется на уровне системы. ИИ и зарубежные сайты идут через VPN, а российские сервисы — напрямую.',
    icon: 'M13 10V3L4 14h7v7l9-11h-7z'
  },
  {
    title: 'Банки всегда онлайн',
    text: 'Сбербанк, Т-Банк и Госуслуги видят ваш реальный IP. Больше никаких блокировок счетов или медленной работы.',
    icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04M12 10a2 2 0 110-4 2 2 0 010 4z'
  },
  {
    title: 'Доступ к Gemini и ИИ',
    text: 'Стабильная работа с Google Gemini, ChatGPT и Claude без необходимости постоянно включать и выключать доступ.',
    icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z'
  }
]

// Данные для маршрутизации
const services = {
  vpn: ['YouTube', 'Instagram', 'Google Gemini', 'Netflix', 'ChatGPT', 'Claude AI'],
  direct: ['Сбербанк', 'Т-Банк', 'Госуслуги', 'Кинопоиск', 'Яндекс Еда', 'Wildberries']
}

// Данные для тарифов
const plans = [
  { 
    id: 1, 
    name: 'Месяц', 
    monthlyPrice: '100 ₽', 
    totalPrice: '100 ₽', 
    period: 'за 30 дней', 
    note: 'Базовый тариф', 
    popular: false 
  },
  { 
    id: 3, 
    name: '6 месяцев', 
    monthlyPrice: '85 ₽', 
    totalPrice: '510 ₽', 
    period: 'за 180 дней', 
    note: 'Экономия 15%', 
    popular: true 
  },
  { 
    id: 4, 
    name: 'Год', 
    monthlyPrice: '80 ₽', 
    totalPrice: '960 ₽', 
    period: 'за 365 дней', 
    note: 'Максимальная выгода', 
    popular: false 
  },
]

// Данные и логика FAQ
const faqs = [
  { q: 'Нужно ли выключать ВПН для оплаты картой?', a: 'Нет. Подорожник настроен так, что банковские приложения (Сбер, Т-Банк и др.) и Госуслуги работают через ваше прямое соединение, минуя VPN-сервер.' },
  { q: 'Будет ли работать Gemini и ChatGPT?', a: 'Да, все популярные ИИ-сервисы, включая Google Gemini, включены в список умной маршрутизации и открываются без проблем.' },
  { q: 'На каких устройствах работает?', a: 'Мы поддерживаем Android, iOS, Windows и macOS. Вы можете использовать удобные клиенты вроде V2Ray или Happ с современным протоколом VLESS.' },
  { q: 'Сколько устройств можно подключить?', a: 'По одной подписке вы можете подключить до 5 устройств одновременно без потери скорости.' }
]

const activeFaq = ref(null)
const toggleFaq = (index) => {
  activeFaq.value = activeFaq.value === index ? null : index
}
</script>

<template>
  <div class="home">
    <!-- HERO SECTION -->
    <section id="hero" class="hero" aria-labelledby="hero-title">
      <div class="hero-bg" aria-hidden="true" />
      
      <div class="hero-container">
        <!-- Левая колонка -->
        <div class="hero-content">
          <div class="badge">
            <span class="badge-pulse"></span>
            Работает стабильно в 2026 году
          </div>
          
          <h1 id="hero-title">
            VPN, который <br>
            <span class="text-accent">не нужно выключать</span>
          </h1>
          
          <p class="hero-description">
            Настройте один раз и забудьте. <strong>Gemini, YouTube и Instagram</strong> работают через защищенный туннель, а <strong>Сбербанк и Госуслуги</strong> открываются напрямую без блокировок.
          </p>
          
          <div class="cta-row">
            <template v-if="isLoggedIn">
              <RouterLink class="cta primary large" to="/cabinet">Перейти в кабинет</RouterLink>
            </template>
            <template v-else>
              <RouterLink class="cta primary large" to="/register">Попробовать бесплатно</RouterLink>
              <RouterLink class="cta secondary large" to="/login">Войти</RouterLink>
            </template>
          </div>
          
          <div class="hero-trust">
            <div class="trust-item">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              <span>Современный протокол VLESS</span>
            </div>
            <div class="trust-item">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              <span>Умный Split Tunneling</span>
            </div>
          </div>
        </div>

        <!-- Правая колонка -->
        <div class="hero-visual" aria-hidden="true">
          <div class="route-illustration">
            <div class="node device-node">
              <div class="node-icon">📱</div>
              <span>Ваше устройство</span>
            </div>
            <div class="path vpn-path">
              <div class="path-line"></div>
              <div class="node service-node vpn-node">
                <span class="node-label text-accent">Через VPN</span>
                <div class="apps-mini">
                  <span>Gemini</span> • <span>YouTube</span> • <span>Instagram</span>
                </div>
              </div>
            </div>
            <div class="path direct-path">
              <div class="path-line"></div>
              <div class="node service-node direct-node">
                <span class="node-label text-green">Напрямую</span>
                <div class="apps-mini">
                  <span>Сбербанк</span> • <span>Госуслуги</span> • <span>Т-Банк</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- HOW IT WORKS -->
    <section id="how" class="section section--split">
      <div class="section-inner">
        <h2 class="section-title">Как работает Подорожник</h2>
        <p class="section-lead">Мы разделили ваш интернет на две скоростные полосы</p>
        
        <div class="split-visual">
          <div class="split-column">
            <div class="column-header tunnel">Через VPN</div>
            <ul class="service-list">
              <li v-for="s in services.vpn" :key="s" class="service-item vpn">{{ s }}</li>
            </ul>
          </div>
          <div class="split-divider">
            <div class="divider-icon">↔</div>
          </div>
          <div class="split-column">
            <div class="column-header direct">Напрямую (РФ)</div>
            <ul class="service-list">
              <li v-for="s in services.direct" :key="s" class="service-item direct">{{ s }}</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- BENEFITS -->
    <section id="benefits" class="section section--strip">
      <div class="section-inner">
        <h2 class="section-title visually-hidden">Наши преимущества</h2>
        <div class="feature-grid">
          <div v-for="(b, i) in benefits" :key="i" class="feature-card">
            <div class="feature-icon">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
                <path :d="b.icon" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>
            <h3 class="feature-title">{{ b.title }}</h3>
            <p class="feature-text">{{ b.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- PRICING -->
    <section id="pricing" class="section pricing" aria-labelledby="pricing-trial-title">
      <div class="section-inner">
        <div class="pricing-trial">
          <h2 id="pricing-trial-title" class="pricing-trial__title">
            Попробуйте бесплатно 14 дней
          </h2>
          <p class="pricing-trial__lead">
            Без привязки карты. Все функции доступны сразу.
          </p>
          <div class="pricing-trial__actions">
            <template v-if="isLoggedIn">
              <RouterLink
                class="cta primary large pricing-trial__cta"
                to="/cabinet"
              >
                Перейти в кабинет
              </RouterLink>
            </template>
            <template v-else>
              <RouterLink
                class="cta primary large pricing-trial__cta"
                to="/register"
              >
                Начать бесплатно
              </RouterLink>
            </template>
          </div>
        </div>

        <h3 class="pricing-plans-heading">Тарифы после пробного периода</h3>
        <div class="pricing-grid" role="list">
          <article
            v-for="plan in plans"
            :key="plan.id"
            class="pricing-card"
            :class="{ 'pricing-card--popular': plan.popular }"
            role="listitem"
          >
            <span v-if="plan.popular" class="pricing-card__badge">Хит</span>
            <h4 class="pricing-card__name">{{ plan.name }}</h4>
            <p class="pricing-card__price">{{ plan.totalPrice }}</p>
            <p class="pricing-card__period">{{ plan.period }}</p>
            <p class="pricing-card__monthly">{{ plan.monthlyPrice }} в месяц</p>
            <p class="pricing-card__note">{{ plan.note }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- FAQ ACCORDION -->
    <section id="faq" class="section section--strip">
      <div class="section-inner">
        <h2 class="section-title">Частые вопросы</h2>
        <div class="faq-accordion">
          <div 
            v-for="(faq, i) in faqs" 
            :key="i" 
            class="faq-item" 
            :class="{ 'is-open': activeFaq === i }"
          >
            <button class="faq-question" @click="toggleFaq(i)" :aria-expanded="activeFaq === i">
              {{ faq.q }}
              <span class="faq-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </span>
            </button>
            <div class="faq-answer-wrapper">
              <div class="faq-answer">{{ faq.a }}</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- FINAL CTA -->
    <section class="section section--final">
      <div class="section-inner section-inner--cta">
        <h2 class="cta-panel-title">Готовы забыть о кнопке «Выкл»?</h2>
        <p class="cta-panel-lead">Присоединяйтесь к пользователям, которые выбрали комфортный интернет без компромиссов.</p>
        <RouterLink class="cta primary large" to="/register">Попробовать Подорожник</RouterLink>
      </div>
    </section>

    <!-- FOOTER -->
    <footer class="footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span class="footer-logo">Подорожник VPN</span>
          <p class="footer-desc">Умный VPN, который не нужно выключать.</p>
        </div>
        <div class="footer-links">
          <a href="#how">Как настроить</a>
          <a href="#benefits">Преимущества</a>
          <a href="#pricing">Тарифы</a>
          <a href="#faq">Вопросы и ответы</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© 2026 Подорожник VPN. Все права защищены.</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* --- БАЗОВЫЕ СТИЛИ --- */
.home {
  flex: 1;
  color: var(--text);
  display: flex;
  flex-direction: column;
}

.home :is(section[id]) {
  scroll-margin-top: 1.25rem;
}

.visually-hidden {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0;
}

.section {
  padding: clamp(3rem, 6vw, 5rem) 1.25rem;
}

.section-inner {
  max-width: 72rem;
  margin: 0 auto;
  text-align: center;
}

.section-title {
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  margin-bottom: 1rem;
  font-weight: 800;
  color: var(--text-h);
}

.section-lead {
  font-size: 1.1rem;
  color: var(--muted);
  margin-bottom: 3rem;
  max-width: 40rem;
  margin-inline: auto;
}

/* Глобальные классы для текста */
.text-accent {
  color: var(--accent);
  background: linear-gradient(120deg, var(--accent), #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.text-green { color: #10b981; }

/* --- СТИЛИ КНОПОК CTA (ОБЩИЕ) --- */
.cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.95rem;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}

.cta.large {
  padding: 1rem 2rem;
  font-size: 1.1rem;
  border-radius: 14px;
}

.cta.primary {
  color: #fff; /* Или var(--on-accent) если у вас задано */
  background: var(--accent, #6366f1);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 40%, transparent);
  border: none;
}

.cta.primary:hover {
  background: color-mix(in srgb, var(--accent) 85%, #000);
  transform: translateY(-2px);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--accent) 50%, transparent);
}

.cta.secondary {
  color: var(--text-h);
  background: var(--surface-glass, rgba(255, 255, 255, 0.05));
  border: 1px solid var(--card-border, #e5e7eb);
}

.cta.secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

/* --- HERO СЕКЦИЯ --- */
.hero {
  position: relative;
  /* Убрали жесткий min-height, используем адаптивный padding */
  padding: clamp(4rem, 10vh, 7rem) 1.25rem;
  display: flex;
  align-items: center;
  background: var(--bg-gradient);
  overflow: hidden;
}

.hero-container {
  position: relative;
  max-width: 72rem;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr;
  gap: 3rem;
  align-items: center;
  z-index: 2;
  width: 100%;
}

@media (min-width: 1024px) {
  .hero-container { grid-template-columns: 1.1fr 0.9fr; gap: 2rem; }
}

.hero-content { text-align: left; }

@media (max-width: 1023px) {
  .hero-content {
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 1rem;
  background: color-mix(in srgb, var(--accent) 15%, transparent);
  color: var(--accent);
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 700;
  margin-bottom: 1.5rem;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
}

.badge-pulse {
  width: 8px; height: 8px; background-color: #10b981; border-radius: 50%;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
  animation: pulse-green 2s infinite;
}

@keyframes pulse-green {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.hero h1 {
  font-size: clamp(2.2rem, 4.5vw, 4rem);
  line-height: 1.1;
  margin-bottom: 1.2rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--text-h);
}

.hero-description {
  max-width: 36rem;
  margin: 0 0 2rem;
  font-size: 1.1rem;
  line-height: 1.6;
  color: var(--muted);
}

@media (max-width: 1023px) { .hero-description { margin: 0 auto 2rem; } }

.hero-description strong { color: var(--text-h); font-weight: 600; }

.cta-row { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; }
@media (max-width: 1023px) { .cta-row { justify-content: center; } }

.hero-trust { display: flex; flex-wrap: wrap; gap: 1.5rem; font-size: 0.9rem; color: var(--muted); font-weight: 500; }
@media (max-width: 1023px) { .hero-trust { justify-content: center; } }
.trust-item { display: flex; align-items: center; gap: 0.5rem; }
.trust-item svg { color: var(--accent); }

/* Анимация маршрутизации (Hero Visual) */
.hero-visual { position: relative; display: flex; justify-content: center; align-items: center; }
.route-illustration { position: relative; width: 100%; max-width: 360px; display: flex; flex-direction: column; gap: 1.5rem; }
.node { background: var(--surface-glass); border: 1px solid var(--card-border); padding: 1rem 1.25rem; border-radius: 16px; box-shadow: var(--shadow-md); text-align: center; position: relative; z-index: 2; backdrop-filter: blur(12px); }
.device-node { align-self: center; border-color: color-mix(in srgb, var(--text) 20%, transparent); font-weight: 700; display: flex; align-items: center; gap: 0.75rem; font-size: 1.05rem; }
.path { position: relative; display: flex; justify-content: flex-end; }
.path-line { position: absolute; top: -1.5rem; left: 50%; width: 2px; height: calc(100% + 1.5rem); background: var(--card-border); z-index: 1; }
.path-line::after { content: ''; position: absolute; top: 0; left: -2px; width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 10px currentColor; animation: data-flow 2s infinite linear; }
@keyframes data-flow { 0% { top: 0; opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 100% { top: 100%; opacity: 0; } }
.vpn-path { margin-right: -5%; }
.vpn-path .path-line { left: 5%; color: var(--accent); background: linear-gradient(to bottom, transparent, var(--accent) 50%, transparent); }
.direct-path { margin-left: -5%; justify-content: flex-start; }
.direct-path .path-line { left: 95%; color: #10b981; background: linear-gradient(to bottom, transparent, #10b981 50%, transparent); }
.service-node { width: 90%; text-align: left; }
.vpn-node { border-left: 4px solid var(--accent); }
.direct-node { border-left: 4px solid #10b981; }
.node-label { display: block; font-weight: 800; font-size: 0.95rem; margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.05em; }
.apps-mini { font-size: 0.8rem; color: var(--muted); font-weight: 500; }
.apps-mini span { color: var(--text-h); }

/* --- SPLIT VISUAL --- */
.split-visual { display: flex; gap: 1rem; margin-top: 2rem; align-items: stretch; }
@media (max-width: 768px) { .split-visual { flex-direction: column; } }
.split-column { flex: 1; background: var(--surface-glass); border: 1px solid var(--card-border); border-radius: var(--radius-lg); padding: 1.5rem; }
.column-header { font-weight: 800; margin-bottom: 1.5rem; padding-bottom: 0.5rem; border-bottom: 2px solid; }
.column-header.tunnel { color: var(--accent); border-color: var(--accent); }
.column-header.direct { color: #58d68d; border-color: #58d68d; }
.service-list { list-style: none; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
@media (max-width: 480px) { .service-list { grid-template-columns: 1fr; } }
.service-item { padding: 0.5rem; background: var(--card-bg); border-radius: 8px; font-size: 0.9rem; font-weight: 600; border: 1px solid var(--card-border); }
.split-divider { display: flex; align-items: center; justify-content: center; }
.divider-icon { font-size: 1.5rem; color: var(--muted); }

/* --- ПРЕИМУЩЕСТВА --- */
.section--strip { background: var(--card-bg); border-block: 1px solid var(--card-border); }
.feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; }
.feature-card { padding: 1.5rem; border-radius: var(--radius-lg); background: var(--surface-glass); border: 1px solid var(--card-border); box-shadow: var(--shadow-sm); text-align: left; }
.feature-icon { display: inline-flex; align-items: center; justify-content: center; width: 3rem; height: 3rem; margin-bottom: 1rem; border-radius: var(--radius); color: var(--accent); background: color-mix(in srgb, var(--accent) 15%, transparent); }
.feature-title { font-size: 1.1rem; margin: 0 0 0.5rem; font-weight: 700; color: var(--text-h); }
.feature-text { margin: 0; font-size: 0.95rem; line-height: 1.5; color: var(--muted); }

/* --- ТАРИФЫ (PRICING) --- */
.pricing .section-inner {
  max-width: 72rem;
}

.pricing-trial {
  text-align: center;
  padding: clamp(2rem, 5vw, 3rem) clamp(1.25rem, 4vw, 2.5rem);
  border-radius: var(--radius-lg);
  border: 1px solid var(--accent-border);
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--accent) 88%, var(--surface) 12%) 0%,
    color-mix(in srgb, var(--accent-muted) 75%, var(--surface) 25%) 100%
  );
  box-shadow:
    0 4px 24px color-mix(in srgb, var(--accent) 22%, transparent),
    var(--shadow-md);
  margin-bottom: clamp(2.5rem, 5vw, 3.5rem);
  color: var(--on-accent);
}

.pricing-trial__title {
  font-size: clamp(1.5rem, 3.5vw, 2.25rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 0.75rem;
  color: inherit;
}

.pricing-trial__lead {
  margin: 0 auto 1.5rem;
  max-width: 28rem;
  font-size: 1.05rem;
  line-height: 1.55;
  color: color-mix(in srgb, var(--on-accent) 82%, transparent);
}

.pricing-trial__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  justify-content: center;
}

.pricing-trial .cta.primary {
  background: var(--on-accent);
  color: var(--accent);
  box-shadow: 0 4px 20px color-mix(in srgb, #000 28%, transparent);
}

.pricing-trial .cta.primary:hover {
  background: color-mix(in srgb, var(--on-accent) 90%, var(--accent) 10%);
  color: color-mix(in srgb, var(--accent) 85%, var(--on-accent) 15%);
}

.pricing-plans-heading {
  font-size: clamp(1.35rem, 3vw, 1.85rem);
  font-weight: 800;
  color: var(--text-h);
  margin: 0 0 1.75rem;
  letter-spacing: -0.02em;
}

.pricing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.5rem;
  text-align: left;
}

.pricing-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  border-radius: var(--radius-lg);
  background: var(--surface-glass);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.pricing-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
  border-color: color-mix(in srgb, var(--accent-border) 55%, var(--card-border));
}

.pricing-card--popular {
  border-color: var(--accent);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent),
    var(--shadow-md);
}

.pricing-card__badge {
  align-self: flex-start;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.35rem 0.65rem;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--accent) 22%, transparent);
  color: var(--accent);
  border: 1px solid var(--accent-border);
  margin-bottom: 0.85rem;
}

.pricing-card__name {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-h);
}

.pricing-card__price {
  margin: 0 0 0.35rem;
  font-size: clamp(1.5rem, 3vw, 1.85rem);
  font-weight: 800;
  color: var(--accent);
  letter-spacing: -0.02em;
}

.pricing-card__period {
  margin: 0 0 0.75rem;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--muted);
}

.pricing-card__monthly {
  margin: 0 0 0.75rem;
  font-size: 0.9rem;
  color: var(--text-h);
  font-weight: 600;
}

.pricing-card__note {
  margin: 0;
  margin-top: auto;
  padding-top: 0.85rem;
  border-top: 1px solid var(--card-border);
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--muted);
}

/* --- FAQ АККОРДЕОН --- */
.faq-accordion { max-width: 48rem; margin: 0 auto; text-align: left; }
.faq-item { border-bottom: 1px solid var(--card-border); }
.faq-item:last-child { border-bottom: none; }

.faq-question {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 0;
  background: none;
  border: none;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-h);
  cursor: pointer;
  text-align: left;
}

.faq-icon {
  color: var(--muted);
  transition: transform 0.3s ease;
  display: flex;
  align-items: center;
}

.faq-item.is-open .faq-icon { transform: rotate(180deg); color: var(--accent); }

.faq-answer-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.3s ease-out;
}

.faq-item.is-open .faq-answer-wrapper { grid-template-rows: 1fr; }

.faq-answer { overflow: hidden; color: var(--muted); font-size: 0.95rem; line-height: 1.6; }
.faq-item.is-open .faq-answer { padding-bottom: 1.25rem; }

/* --- FINAL CTA --- */
.section--final { padding-bottom: 6rem; }
.section-inner--cta {
  background: var(--surface-glass);
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--accent) 5%, transparent), transparent);
  padding: 3rem 2rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--accent-border, var(--card-border));
  box-shadow: var(--shadow-lg);
}

.cta-panel-title { font-size: clamp(1.5rem, 3vw, 2rem); margin-bottom: 1rem; color: var(--text-h); }
.cta-panel-lead { margin-bottom: 2rem; font-size: 1.1rem; color: var(--muted); max-width: 32rem; margin-inline: auto; }

/* --- FOOTER --- */
.footer {
  background: var(--card-bg);
  border-top: 1px solid var(--card-border);
  padding: 3rem 1.25rem 1.5rem;
}

.footer-inner {
  max-width: 72rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2rem;
  align-items: center;
  text-align: center;
}

@media (min-width: 768px) {
  .footer-inner { flex-direction: row; justify-content: space-between; text-align: left; }
}

.footer-brand { max-width: 20rem; }
.footer-logo { font-size: 1.25rem; font-weight: 800; color: var(--text-h); display: block; margin-bottom: 0.5rem; }
.footer-desc { color: var(--muted); font-size: 0.9rem; margin: 0; }

.footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  justify-content: center;
}

.footer-links a {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.95rem;
  font-weight: 500;
  transition: color 0.2s;
}

.footer-links a:hover { color: var(--accent); }

.footer-bottom {
  max-width: 72rem;
  margin: 2rem auto 0;
  padding-top: 1.5rem;
  border-top: 1px solid var(--card-border);
  text-align: center;
  font-size: 0.85rem;
  color: var(--muted);
}
</style>