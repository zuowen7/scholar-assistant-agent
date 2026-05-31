import { createApp } from 'vue'

// Suppress Monaco Editor internal cancellation errors (async.js lifecycle race)
window.addEventListener('unhandledrejection', (event) => {
  if (event.reason?.name === 'Canceled' || event.reason?.message === 'Canceled') {
    event.preventDefault()
  }
})

import './styles/tokens.css'
import './styles/transitions.css'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import App from './App.vue'
import { i18n } from './i18n'
import { useLocale } from './composables/useLocale'

const app = createApp(App)
app.use(i18n)
// useLocale() triggers module-level init before mount — sets i18n.locale from stored preference
useLocale()
app.mount('#app')
