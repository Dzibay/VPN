<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AdminHeader from './components/AdminHeader.vue'
import AdminTopbar from './components/AdminTopbar.vue'
import { getCurrentProject, hasStaffToken } from './auth/staffSession.js'

const route = useRoute()
const showChrome = computed(
  () => hasStaffToken() && route.name !== 'staff-login',
)

function isDesktopSidebar() {
  return typeof window !== 'undefined' && window.matchMedia('(min-width: 901px)').matches
}

/** На десктопе меню открыто и сдвигает контент; на мобильных — оверлей, по умолчанию скрыто. */
const sidebarOpen = ref(isDesktopSidebar())
const projectRenderKey = ref(getCurrentProject() || 'none')

function onProjectChanged(event) {
  projectRenderKey.value = `${event?.detail || getCurrentProject() || 'none'}:${Date.now()}`
}

function onViewportChange(event) {
  sidebarOpen.value = event.matches
}

onMounted(() => {
  window.addEventListener('staff:project-changed', onProjectChanged)
  window.matchMedia('(min-width: 901px)').addEventListener('change', onViewportChange)
})
onUnmounted(() => {
  window.removeEventListener('staff:project-changed', onProjectChanged)
  window.matchMedia('(min-width: 901px)').removeEventListener('change', onViewportChange)
})
</script>

<template>
  <div class="admin-shell" :class="{ 'admin-shell--chrome': showChrome }">
    <AdminTopbar v-if="showChrome" v-model:open="sidebarOpen" />
    <button
      v-if="showChrome && sidebarOpen"
      type="button"
      class="sidebar-backdrop"
      aria-label="Закрыть меню"
      @click="sidebarOpen = false"
    />
    <div v-if="showChrome" class="admin-workspace">
      <AdminHeader
        :sidebar-open="sidebarOpen"
        @toggle-sidebar="sidebarOpen = !sidebarOpen"
      />
      <main class="admin-main">
        <router-view :key="`${route.fullPath}:${projectRenderKey}`" />
      </main>
    </div>
    <main v-else class="admin-main admin-main--login">
      <router-view :key="route.fullPath" />
    </main>
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
}

.admin-shell--chrome {
  display: flex;
  min-height: 100vh;
}

.admin-workspace {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 100vh;
}

.admin-main {
  flex: 1;
  min-width: 0;
  padding: 24px clamp(18px, 3vw, 42px) 44px;
}

.admin-main--login {
  padding: 0;
}

.sidebar-backdrop {
  display: none;
}

@media (max-width: 900px) {
  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 200;
    padding: 0;
    border: none;
    background: rgba(8, 12, 22, 0.45);
    cursor: pointer;
  }

  .admin-main {
    padding: 16px 14px 32px;
  }
}
</style>
