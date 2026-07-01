<script setup>
import {
  BarChart3,
  ChevronDown,
  CreditCard,
  ExternalLink,
  LayoutDashboard,
  Network,
  PanelLeftClose,
  Search,
  Settings,
  Shield,
  Users,
} from 'lucide-vue-next'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { canAccessRoute } from '../auth/roleAccess.js'
import { getStaffProfile } from '../auth/staffSession.js'

const open = defineModel('open', { type: Boolean, default: true })

const route = useRoute()
const role = computed(() => getStaffProfile()?.role || null)

function can(access) {
  return canAccessRoute(role.value, access)
}

function isActive(item) {
  if (item.exact) return route.path === item.to
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

const sections = computed(() => [
  {
    title: 'Обзор',
    icon: LayoutDashboard,
    items: [
      { to: '/dashboard', label: 'Дашборд', access: 'staff', exact: true },
    ],
  },
  {
    title: 'Пользователи',
    icon: Users,
    items: [
      { to: '/admin/users/analytics', label: 'Пользователи', access: 'staff' },
      { to: '/admin/users/registrations-by-date', label: 'Регистрации и графики', access: 'staff' },
      { to: '/admin/users/subscription-user-agent-stats', label: 'Устройства и UA', access: 'staff' },
      { to: '/admin/traffic', label: 'Трафик пользователей', access: 'admin' },
    ],
  },
  {
    title: 'Операции',
    icon: CreditCard,
    items: [
      { to: '/admin/payments', label: 'Платежи', access: 'staff' },
      { to: '/admin/finance', label: 'Финансы', access: 'staff' },
      { to: '/admin/tasks', label: 'Задачи', access: 'staff' },
      { to: '/admin/support', label: 'Поддержка', access: 'staff' },
    ],
  },
  {
    title: 'Маркетинг',
    icon: BarChart3,
    items: [
      { to: '/admin/referrals', label: 'Реферальные токены', access: 'staff' },
      { to: '/admin/funnel', label: 'Воронка', access: 'staff' },
      { to: '/admin/seo-pages', label: 'SEO-страницы', access: 'staff' },
    ],
  },
  {
    title: 'Инфраструктура',
    icon: Network,
    items: [
      { to: '/infra/servers', label: 'Серверы', access: 'admin' },
      { to: '/infra/servers/reachability', label: 'Доступность', access: 'admin' },
      { to: '/infra/analytics', label: 'Нагрузка узлов', access: 'admin' },
      { to: '/admin/logs', label: 'HTTP-логи', access: 'staff' },
      { to: '/admin/blocked-ips', label: 'Заблокированные IP', access: 'admin' },
    ],
  },
  {
    title: 'Управление',
    icon: Settings,
    items: [
      { to: '/projects', label: 'Проекты', access: 'super_admin_only' },
      { to: '/staff-users', label: 'Персонал', access: 'super_admin_only' },
    ],
  },
])

const visibleSections = computed(() =>
  sections.value
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => can(item.access)),
    }))
    .filter((section) => section.items.length > 0),
)

function onNavClick() {
  if (window.matchMedia('(max-width: 900px)').matches) {
    open.value = false
  }
}
</script>

<template>
  <aside class="admin-sidebar" :class="{ 'admin-sidebar--collapsed': !open }">
    <div class="sidebar-head">
      <router-link class="brand" to="/dashboard">
        <span class="brand-mark"><Shield :size="20" /></span>
        <span class="brand-text">
          <strong>VPN Admin</strong>
          <small>multi-project console</small>
        </span>
      </router-link>
    </div>

    <div class="sidebar-search" aria-hidden="true">
      <Search :size="16" />
      <span>Навигация по разделам</span>
    </div>

    <nav class="sidebar-nav" aria-label="Админ-навигация">
      <section
        v-for="section in visibleSections"
        :key="section.title"
        class="nav-section"
      >
        <h2>
          <component :is="section.icon" :size="15" />
          {{ section.title }}
        </h2>
        <router-link
          v-for="item in section.items"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ 'nav-link--active': isActive(item) }"
          @click="onNavClick"
        >
          <span>{{ item.label }}</span>
          <ChevronDown v-if="isActive(item)" :size="14" />
        </router-link>
      </section>
    </nav>

    <a
      v-if="role === 'super_admin'"
      class="swagger-link"
      href="/swagger"
      target="_blank"
      rel="noopener"
      @click="onNavClick"
    >
      <ExternalLink :size="15" />
      <span>Swagger API</span>
    </a>

    <button
      class="sidebar-collapse"
      type="button"
      title="Свернуть меню"
      @click="open = false"
    >
      <PanelLeftClose :size="16" />
      <span>Свернуть</span>
    </button>
  </aside>
</template>

<style scoped>
.admin-sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 288px;
  width: 288px;
  height: 100vh;
  padding: 20px 16px;
  overflow: hidden;
  border-right: 1px solid var(--border);
  background:
    radial-gradient(circle at 20% 0%, var(--accent-soft), transparent 34%),
    var(--sidebar-bg);
}

.admin-sidebar--collapsed {
  min-width: 0;
  width: 0;
  padding-left: 0;
  padding-right: 0;
  border-right-width: 0;
}

.sidebar-head {
  padding: 0 4px 4px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text);
  text-decoration: none;
}

.brand:hover {
  text-decoration: none;
}

.brand-mark {
  display: grid;
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 14px;
  color: var(--on-accent);
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
}

.brand-text {
  min-width: 0;
}

.brand strong {
  display: block;
  font-family: var(--heading);
  font-size: 16px;
  letter-spacing: -0.02em;
}

.brand small {
  display: block;
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
}

.sidebar-search,
.sidebar-collapse {
  border: 1px solid var(--border);
  background: var(--surface-raised);
}

.sidebar-search {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 38px;
  padding: 0 12px;
  border-radius: 12px;
  color: var(--text-muted);
  font-size: 12px;
}

.sidebar-nav {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding-right: 4px;
}

.nav-section + .nav-section {
  margin-top: 18px;
}

.nav-section h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  padding: 0 8px;
  color: var(--text-soft);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.nav-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 38px;
  padding: 9px 10px 9px 12px;
  border-radius: 12px;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

.nav-link:hover {
  color: var(--text);
  background: var(--nav-link-hover-bg);
  text-decoration: none;
}

.nav-link--active {
  color: var(--accent-strong);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 22%, transparent);
}

.sidebar-collapse {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  width: calc(100% - 8px);
  margin: auto 4px 4px;
  padding: 10px 12px;
  border-radius: 12px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.sidebar-collapse:hover {
  color: var(--text);
}

.swagger-link {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 38px;
  margin: 0 4px;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

.swagger-link:hover {
  color: var(--accent-strong);
  background: var(--nav-link-hover-bg);
  text-decoration: none;
}

@media (max-width: 900px) {
  .admin-sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 250;
    width: min(288px, 88vw);
    min-width: 0;
    box-shadow: var(--shadow-lg);
    transition: transform var(--duration) ease;
  }

  .admin-sidebar--collapsed {
    width: min(288px, 88vw);
    min-width: 0;
    padding: 20px 16px;
    border-right-width: 1px;
    transform: translateX(-100%);
    pointer-events: none;
  }
}
</style>
