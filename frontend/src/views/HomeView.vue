<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="home">
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-bg" aria-hidden="true" />
      <div class="hero-inner">
        <h1 id="hero-title">Подорожник VPN</h1>
        <p class="lead">
          Подписка, ключи и личный кабинет в одном спокойном интерфейсе — без
          лишнего шума, с акцентом на приватность и стабильное соединение.
        </p>
        <div class="cta-row">
          <RouterLink class="cta primary" to="/register">Создать аккаунт</RouterLink>
          <RouterLink class="cta secondary" to="/login">Войти</RouterLink>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 0;
}

/* Высота = остаток под шапкой через flex (main → .home → .hero), без 100dvh, иначе
   снова «прибавляется» шапка и появляется лишний скролл. */
.hero {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  padding: clamp(2rem, 6vw, 3.5rem) 1.25rem;
  overflow: hidden;
  /* Как у body, чтобы «дыр» снизу не было: радикалы в .hero-bg были полупрозрачные. */
  background: var(--bg-gradient);
}

/* Дополнительный слой поверх глобального --bg-gradient: зелень + фиолет */
.hero-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  background:
    radial-gradient(
      ellipse 95% 72% at 15% 12%,
      rgba(139, 92, 246, 0.34),
      transparent 58%
    ),
    radial-gradient(
      ellipse 85% 58% at 92% 18%,
      rgba(88, 214, 141, 0.26),
      transparent 52%
    ),
    radial-gradient(
      ellipse 70% 50% at 55% 85%,
      rgba(124, 58, 237, 0.16),
      transparent 55%
    ),
    radial-gradient(
      ellipse 55% 44% at 72% 48%,
      rgba(45, 179, 157, 0.14),
      transparent 48%
    );
  pointer-events: none;
}

@media (prefers-color-scheme: light) {
  .hero-bg {
    background:
      radial-gradient(
        ellipse 95% 75% at 12% 10%,
        rgba(139, 92, 246, 0.12),
        transparent 58%
      ),
      radial-gradient(
        ellipse 88% 60% at 90% 20%,
        rgba(88, 214, 141, 0.16),
        transparent 52%
      ),
      radial-gradient(
        ellipse 80% 55% at 50% 95%,
        rgba(99, 102, 234, 0.08),
        transparent 50%
      ),
      radial-gradient(
        ellipse 50% 40% at 70% 45%,
        rgba(45, 179, 157, 0.1),
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

.cta:active {
  transform: translateY(1px);
}

.cta:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring), var(--shadow-sm);
}
</style>
