import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export default {
  resolve: {
    alias: {
      '@embinder/react': resolve(here, '../../../minderSDK/packages/react/src/index.ts'),
      '@embinder/ghost-cursor': resolve(here, '../../../minderSDK/packages/react/src/ghost-cursor.ts'),
    },
    dedupe: ['react', 'react-dom'],
  },
};
