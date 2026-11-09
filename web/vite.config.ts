import { defineConfig, loadEnv, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/**
 * CSP restritiva injetada como <meta> no index.html SOMENTE no build (o dev server do Vite usa script inline
 * para o React Refresh, que uma CSP sem 'unsafe-inline' bloquearia). Fontes do Google permitidas.
 * `apiOrigin` entra em connect-src/img-src quando VITE_API_URL aponta para outra origem.
 * Observação: `frame-ancestors` não funciona via <meta>; configure no cabeçalho do servidor que hospedar o painel.
 */
function cspPlugin(apiOrigin: string): Plugin {
  const csp = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    `img-src 'self' data: blob: ${apiOrigin}`.trim(),
    `connect-src 'self' ${apiOrigin}`.trim(),
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ');
  return {
    name: 'fast-ariam-csp',
    apply: 'build',
    transformIndexHtml() {
      return [{ tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: csp }, injectTo: 'head-prepend' }];
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.VITE_API_URL || 'http://127.0.0.1:8000';
  let apiOrigin = '';
  try {
    apiOrigin = env.VITE_API_URL ? new URL(env.VITE_API_URL).origin : '';
  } catch {
    apiOrigin = '';
  }

  return {
    plugins: [react(), tailwindcss(), cspPlugin(apiOrigin)],
    server: {
      host: '0.0.0.0',
      port: 3000,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
          autoRewrite: true,
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              if (proxyRes.headers.location) {
                proxyRes.headers.location = proxyRes.headers.location.replace(
                  /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?/,
                  ''
                );
              }
            });
          },
        },
        '/static': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
