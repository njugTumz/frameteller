import { defineConfig, globalIgnores } from 'eslint/config'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores(['dist', 'playwright-report', 'test-results', 'src/shared/api/schema.d.ts']),
  {
    files: ['**/*.{ts,tsx,js,mjs}'],
    extends: [tseslint.configs.strict, tseslint.configs.stylistic, reactHooks.configs.flat['recommended-latest']],
    rules: {
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always'],
    },
  },
  {
    // CLAUDE.md section 6: components render, hooks orchestrate, api.ts talks to the backend.
    files: ['src/**/components/**/*.tsx'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['**/api', '**/api.ts', '**/shared/api/*'], message: 'Components render. Call the backend from a hook.' },
            { group: ['**/session/*', '**/audio/*'], message: 'Components render. Drive the session from a hook.' },
          ],
        },
      ],
    },
  },
])
