import { createApp } from 'vue'
import './style.css'
import './styles/admin-table.css'
import App from './App.vue'
import { router } from './router/index.js'
import { captureReferralFromRoute } from './referral/refCapture.js'

createApp(App).use(router).mount('#app')

router.afterEach((to) => {
  captureReferralFromRoute(to)
})
