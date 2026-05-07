<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { startStaffSwaggerWithToken } from '../auth/swaggerStaffCookie.js'
import { getAccessToken, getSessionRole } from '../auth/session.js'
import { canAccessReferralsAdmin } from '../auth/permissions.js'
import { getAdminNavTabsForRole } from '../admin/adminNavConfig.js'

const route = useRoute()

const tabs = computed(() => getAdminNavTabsForRole(getSessionRole()))
const activeName = computed(() => route.name)
const showSwaggerBtn = computed(() => canAccessReferralsAdmin(getSessionRole()))

function openSwagger() {
  const role = getSessionRole()
  if (role !== 'admin' && role !== 'manager') return
  startStaffSwaggerWithToken(getAccessToken())
}
</script>

<template>
  <RouterLink
    v-for="t in tabs"
    :key="t.routeName"
    class="tab"
    :class="{ 'tab-active': activeName === t.routeName }"
    :to="t.path"
  >
    {{ t.label }}
  </RouterLink>
  <button
    v-if="showSwaggerBtn"
    type="button"
    class="tab swagger-menu-btn"
    @click="openSwagger"
  >
    Swagger
  </button>
</template>

<style scoped>
.swagger-menu-btn {
  cursor: pointer;
  font: inherit;
}
</style>
