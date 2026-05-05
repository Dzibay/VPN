<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getSessionRole } from '../auth/session.js'
import { getAdminNavTabsForRole } from '../admin/adminNavConfig.js'

const route = useRoute()

const tabs = computed(() => getAdminNavTabsForRole(getSessionRole()))
const activeName = computed(() => route.name)
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
</template>
