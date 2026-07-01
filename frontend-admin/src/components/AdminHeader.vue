<script setup>
import { LogOut, Moon, PanelLeftOpen, Sun } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import ProjectSelector from './ProjectSelector.vue'
import { clearStaffSession, getStaffProfile } from '../auth/staffSession.js'
import { resolvedTheme, setThemeMode, themeMode } from '../theme/theme.js'

defineProps({
  sidebarOpen: { type: Boolean, default: true },
})

const emit = defineEmits(['toggle-sidebar'])

const router = useRouter()
const profile = computed(() => getStaffProfile())
const roleLabel = computed(() => {
  const role = profile.value?.role || null
  if (role === 'super_admin') return 'Super admin'
  if (role === 'admin') return 'Admin'
  if (role === 'manager') return 'Manager'
  return 'Staff'
})

const themeTitle = computed(() => {
  const label = themeMode.value === 'system'
    ? 'системная'
    : themeMode.value === 'dark'
      ? 'тёмная'
      : 'светлая'
  return `Тема: ${label}. Нажмите для переключения`
})

function logout() {
  clearStaffSession()
  router.replace({ name: 'staff-login' })
}

function cycleTheme() {
  const next = themeMode.value === 'system'
    ? 'dark'
    : themeMode.value === 'dark'
      ? 'light'
      : 'system'
  setThemeMode(next)
}
</script>

<template>
  <header class="admin-header">
    <div class="admin-header__tools">
      <button
        v-if="!sidebarOpen"
        class="header-chip header-chip--icon"
        type="button"
        title="Показать меню"
        aria-label="Показать меню"
        @click="emit('toggle-sidebar')"
      >
        <PanelLeftOpen :size="16" />
      </button>

      <ProjectSelector />

      <div class="admin-header__end">
        <button
          class="header-chip header-chip--icon"
          type="button"
          :title="themeTitle"
          aria-label="Переключить тему"
          @click="cycleTheme"
        >
          <Sun v-if="resolvedTheme === 'light'" :size="16" />
          <Moon v-else :size="16" />
        </button>

        <div
          v-if="profile"
          class="profile-chip"
          :title="`${profile.email} · ${roleLabel}`"
        >
          <span class="profile-chip__email">{{ profile.email }}</span>
          <span class="profile-chip__role">{{ roleLabel }}</span>
          <button
            class="header-chip header-chip--icon profile-chip__logout"
            type="button"
            title="Выйти"
            aria-label="Выйти"
            @click="logout"
          >
            <LogOut :size="15" />
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.admin-header {
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 8px clamp(14px, 2.5vw, 32px);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--sidebar-bg) 88%, transparent);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
}

.admin-header__tools {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
}

.admin-header__end {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  margin-left: auto;
  min-width: 0;
}

.header-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-sm);
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.header-chip--icon {
  width: 36px;
  padding: 0;
}

.header-chip:hover {
  border-color: var(--accent-border);
  color: var(--accent-strong);
}

.profile-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: min(280px, 36vw);
  height: 36px;
  padding: 0 4px 0 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-sm);
}

.profile-chip__email {
  overflow: hidden;
  min-width: 0;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-chip__role {
  flex: 0 0 auto;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.profile-chip__logout {
  border: none;
  background: transparent;
  box-shadow: none;
  border-radius: 8px;
}

.profile-chip__logout:hover {
  color: var(--danger);
  border: none;
  background: var(--danger-soft);
}

@media (max-width: 720px) {
  .profile-chip__role {
    display: none;
  }

  .profile-chip {
    max-width: min(200px, 42vw);
  }
}

@media (max-width: 480px) {
  .admin-header {
    padding: 8px 12px;
  }

  .admin-header__tools {
    gap: 6px;
  }

  .admin-header__end {
    gap: 6px;
  }
}
</style>
