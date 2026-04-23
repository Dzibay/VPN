<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="home">
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-bg" aria-hidden="true" />
      <div class="hero-inner">
        <p class="badge">Доступ без лишнего шума</p>
        <h1 id="hero-title">VPN, подписка и личный кабинет</h1>
        <p class="lead">
          Оформите доступ, следите за сроком подписки и получайте рабочие ключи в
          одном спокойном интерфейсе — без перегруза деталями.
        </p>
        <div class="cta-row">
          <RouterLink class="cta primary" to="/register">Создать аккаунт</RouterLink>
          <RouterLink class="cta secondary" to="/login">Войти</RouterLink>
          <RouterLink class="cta ghost" to="/cabinet">Личный кабинет</RouterLink>
        </div>
      </div>
    </section>

    <section class="features" aria-labelledby="feat-title">
      <h2 id="feat-title" class="feat-heading">Почему это удобно</h2>
      <ul class="feat-grid">
        <li class="feat-card">
          <span class="feat-icon" aria-hidden="true">🔐</span>
          <h3>Аккаунт под ваш email</h3>
          <p>
            Регистрация и вход по почте и паролю. Данные подписки хранятся в вашем
            кабинете.
          </p>
        </li>
        <li class="feat-card">
          <span class="feat-icon" aria-hidden="true">📅</span>
          <h3>Срок подписки наглядно</h3>
          <p>
            Видно, активен ли доступ и до какой даты действует тариф — без
            угадываний.
          </p>
        </li>
        <li class="feat-card">
          <span class="feat-icon" aria-hidden="true">🔗</span>
          <h3>Ссылка подписки</h3>
          <p>
            Готовый URL для клиентов: импорт в один тап в поддерживаемых
            приложениях.
          </p>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.home {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.hero {
  position: relative;
  padding: clamp(2.5rem, 8vw, 5rem) 1.25rem clamp(3rem, 10vw, 5.5rem);
  overflow: hidden;
}

.hero-bg {
  position: absolute;
  inset: -40% -20% auto -20%;
  height: 120%;
  background:
    radial-gradient(
      ellipse 80% 60% at 20% 20%,
      rgba(139, 92, 246, 0.35),
      transparent 55%
    ),
    radial-gradient(
      ellipse 70% 50% at 85% 30%,
      rgba(124, 58, 237, 0.22),
      transparent 50%
    ),
    radial-gradient(
      circle at 50% 100%,
      rgba(139, 92, 246, 0.12),
      transparent 45%
    );
  pointer-events: none;
}

@media (prefers-color-scheme: dark) {
  .hero-bg {
    background:
      radial-gradient(
        ellipse 80% 60% at 25% 15%,
        rgba(167, 139, 250, 0.28),
        transparent 55%
      ),
      radial-gradient(
        ellipse 70% 50% at 90% 25%,
        rgba(139, 92, 246, 0.18),
        transparent 50%
      ),
      radial-gradient(
        circle at 50% 100%,
        rgba(167, 139, 250, 0.08),
        transparent 45%
      );
  }
}

.hero-inner {
  position: relative;
  max-width: 40rem;
  margin: 0 auto;
  text-align: center;
}

.badge {
  display: inline-block;
  margin: 0 0 1rem;
  padding: 0.35rem 0.95rem;
  border-radius: 999px;
  font-family: var(--heading);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
}

.hero h1 {
  font-size: clamp(1.85rem, 5vw, 2.65rem);
  margin-bottom: 1rem;
  line-height: 1.12;
}

.lead {
  margin: 0 auto 2rem;
  max-width: 34rem;
  font-size: 1.08rem;
  line-height: 1.65;
  color: var(--muted);
}

.cta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: center;
}

.cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.65rem 1.35rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.95rem;
  text-decoration: none;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease,
    transform 0.15s ease,
    box-shadow 0.2s ease;
}

.cta.primary {
  color: var(--on-accent);
  background: var(--accent);
  box-shadow: var(--shadow-md);
}

.cta.primary:hover {
  background: var(--accent-hover);
  box-shadow: var(--shadow-lg);
}

.cta.secondary {
  color: var(--text-h);
  background: var(--surface-glass);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
}

.cta.secondary:hover {
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.cta.ghost {
  color: var(--muted);
  background: transparent;
  border: 1px dashed var(--card-border);
}

.cta.ghost:hover {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.cta:active {
  transform: translateY(1px);
}

.cta:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring), var(--shadow-sm);
}

.features {
  padding: clamp(2.5rem, 6vw, 4rem) 1.25rem 3.5rem;
  border-top: 1px solid var(--nav-border);
  background: rgba(255, 255, 255, 0.35);
}

@media (prefers-color-scheme: dark) {
  .features {
    background: rgba(15, 12, 20, 0.5);
  }
}

.feat-heading {
  text-align: center;
  font-size: 1.35rem;
  margin: 0 0 1.75rem;
  color: var(--text-h);
}

.feat-grid {
  list-style: none;
  margin: 0 auto;
  padding: 0;
  max-width: 960px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
}

.feat-card {
  margin: 0;
  padding: 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.feat-card:hover {
  border-color: var(--accent-border);
  box-shadow: var(--shadow-md);
}

.feat-icon {
  font-size: 1.5rem;
  line-height: 1;
  display: block;
  margin-bottom: 0.65rem;
}

.feat-card h3 {
  font-size: 1.05rem;
  margin: 0 0 0.5rem;
  color: var(--text-h);
}

.feat-card p {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.55;
  color: var(--muted);
}
</style>
