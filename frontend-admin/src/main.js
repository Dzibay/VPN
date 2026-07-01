import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router/index.js'
import { rehydrateLegacyBridge } from './auth/staffSession.js'
import { installGlobalFetchInterceptor } from './api/globalFetchInterceptor.js'
import { initTheme } from './theme/theme.js'
import '@fontsource/manrope/400.css'
import '@fontsource/manrope/500.css'
import '@fontsource/manrope/600.css'
import '@fontsource/manrope/700.css'
import '@fontsource/sora/600.css'
import '@fontsource/sora/700.css'
import './styles/base.css'
import './styles/admin-legacy.css'

initTheme()

// 1. После reload восстанавливаем bridge staff-JWT → legacy vpn_access_token,
//    чтобы @legacy-views (fetchJson) сразу увидели валидный токен.
rehydrateLegacyBridge()

// 2. Ставим глобальный fetch-interceptor: добавляет X-Admin-Project ко всем /api/*.
//    Работает и для нашего apiFetch, и для legacy fetchJson без переписывания legacy кода.
installGlobalFetchInterceptor()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
