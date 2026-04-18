<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="home">
    <div class="hero">
      <p class="badge">VPN</p>
      <h1>Клиентское приложение</h1>
      <p class="lead">
        Управление доступом и подписками в едином интерфейсе.
      </p>
      <div class="actions">
        <RouterLink class="cta" to="/admin/login">Вход в админку</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(2rem, 6vw, 4rem) 1.25rem;
  text-align: center;
}

.hero {
  max-width: 36rem;
}

.badge {
  display: inline-block;
  margin: 0 0 1rem;
  padding: 0.35rem 0.9rem;
  border-radius: 999px;
  font-family: var(--heading);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
}

.lead {
  margin: 0 0 2rem;
  font-size: 1.05rem;
  line-height: 1.6;
  color: var(--muted);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: center;
}

.cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.65rem 1.4rem;
  border-radius: 12px;
  font-weight: 600;
  text-decoration: none;
  color: var(--on-accent);
  background: var(--accent);
  box-shadow: var(--shadow-md);
  transition:
    background 0.2s ease,
    transform 0.15s ease,
    box-shadow 0.2s ease;
}

.cta:hover {
  background: var(--accent-hover);
  box-shadow: var(--shadow-lg);
}

.cta:active {
  transform: translateY(1px);
}

.cta:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring), var(--shadow-md);
}
</style>
