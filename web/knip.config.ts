import type { KnipConfig } from 'knip'

const config: KnipConfig = {
  entry: [
    'scripts/**/*.{js,ts,mjs}',
    'bin/**/*.{js,ts,mjs}',
    'tsslint.config.ts',
  ],
  ignore: [
    'public/**',
    'app/components/browser-initializer.tsx',
    'app/components/creator/task-layout.tsx',
    'constants/link.ts',
  ],
  ignoreBinaries: ['only-allow'],
  ignoreDependencies: ['@iconify-json/*', '@storybook/addon-onboarding'],
  /// keep-sorted
  rules: {
    binaries: 'error',
    catalog: 'error',
    dependencies: 'error',
    devDependencies: 'error',
    duplicates: 'error',
    enumMembers: 'error',
    exports: 'warn',
    files: 'error',
    namespaceMembers: 'error',
    nsExports: 'warn',
    nsTypes: 'warn',
    optionalPeerDependencies: 'error',
    types: 'warn',
    unlisted: 'error',
    unresolved: 'error',
  },
}

export default config
