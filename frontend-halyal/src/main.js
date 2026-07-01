import { createApp } from 'vue'
import './fonts.css'
import './style.css'
import './styles/halyal-theme.css'
import './styles/admin-ui.css'
import './styles/admin-table.css'
import './styles/admin-chart-wrap.css'
import './styles/admin-chart-panel.css'
import './styles/admin-period-presets.css'
import App from './App.vue'
import {
  ensureIpBlockStatus,
  redirectFromBlockedPageIfAllowed,
  redirectToBlockedPage,
} from './auth/ipBlock.js'
import { router } from './router/index.js'
import { captureReferralFromRoute } from './referral/refCapture.js'
import { applyRobotsMeta, routeShouldNoindex } from './seo/documentMeta.js'
import { trackSeoPageFromRoute } from './seo/trackSeoPageView.js'

async function bootstrap() {
  const ipBlocked = await ensureIpBlockStatus()
  if (ipBlocked && window.location.pathname !== '/blocked') {
    redirectToBlockedPage()
    return
  }
  if (!ipBlocked && window.location.pathname === '/blocked') {
    redirectFromBlockedPageIfAllowed()
    return
  }

  createApp(App).use(router).mount('#app')
}

void bootstrap()

router.afterEach((to) => {
  applyRobotsMeta(routeShouldNoindex(to))
  captureReferralFromRoute(to)
  trackSeoPageFromRoute(to)
})
