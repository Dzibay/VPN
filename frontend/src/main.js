import { createApp } from 'vue'
import './fonts.css'
import './style.css'
import './styles/admin-table.css'
import './styles/admin-chart-wrap.css'
import App from './App.vue'
import { router } from './router/index.js'
import { captureReferralFromRoute } from './referral/refCapture.js'

createApp(App).use(router).mount('#app')

router.afterEach((to) => {
  captureReferralFromRoute(to)
})
