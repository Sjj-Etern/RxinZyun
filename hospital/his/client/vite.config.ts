import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const keyPath = path.resolve(__dirname, 'key.pem');
const certPath = path.resolve(__dirname, 'cert.pem');
const devHttps = fs.existsSync(keyPath) && fs.existsSync(certPath)
  ? {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    }
  : undefined;
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '');

  return {
    envDir: path.resolve(__dirname, '..'),
    plugins: [react()],
    optimizeDeps: {
      force: env.HIS_VITE_FORCE === 'true',
    },
    server: {
      host: env.HIS_FRONTEND_HOST,
      port: Number(env.HIS_FRONTEND_PORT),
      strictPort: env.HIS_FRONTEND_STRICT_PORT === 'true',
      ...(devHttps ? { https: devHttps } : {}),
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET,
          changeOrigin: true,
        },
      },
    },
  };
});
