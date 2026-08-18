import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    // 5175, and the number is not free to change. Le Comptoir Immo already runs dev
    // servers on 5173, 5174 and 5180; two apps racing for a port is how a screen quietly
    // serves another product's data to somebody who trusts the address bar.
    port: 5175,
    strictPort: true,
    proxy: { '/api': { target: 'http://localhost:8001', changeOrigin: true } },
  },
})
