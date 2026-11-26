import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(() => {
  const envDir = '../..'
  const productionEnv = loadEnv('production', envDir, '')
  const frontendHost = new URL(productionEnv.FRONTEND_URL).hostname
  return {
    envDir,
    plugins: [react()],
    define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(productionEnv.BACKEND_URL),
    },
    server: {
      allowedHosts: [frontendHost],
    },
  }
})
