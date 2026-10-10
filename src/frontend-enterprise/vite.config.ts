import path from 'path';
import tailwindcss from '@tailwindcss/vite';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import svgr from 'vite-plugin-svgr';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const omitTikTok = mode === 'production' && env.VITE_TIKTOK_BUSINESS_UNIT_ENABLED !== 'true';
  return {
    plugins: [react(), tailwindcss(), svgr()],
    resolve: {
      alias: [
        ...(omitTikTok
          ? [{
              find: /^\.\/pages\/TikTokBusinessUnitPage$/,
              replacement: path.resolve(__dirname, './src/pages/DisabledModulePage.tsx'),
            }]
          : []),
        { find: '@', replacement: path.resolve(__dirname, './src') },
      ],
      dedupe: [
        '@testing-library/react',
        '@testing-library/user-event',
        'cytoscape',
        'react',
        'react-dom',
        'react-router-dom',
        'sonner',
        'vitest',
      ],
    },
    base: '/',
    test: {
      include: [
        '../tests/frontend/**/*.test.ts',
        '../tests/frontend/**/*.test.tsx',
      ],
      setupFiles: ['./src/test/setup.ts'],
      environmentOptions: {
        jsdom: {
          url: 'http://localhost/',
        },
      },
    },
    server: {
      fs: {
        allow: [
          path.resolve(__dirname),
          path.resolve(__dirname, '../tests/frontend'),
        ],
      },
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
