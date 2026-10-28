// Fails when src/shared/api/schema.d.ts is out of date with backend/openapi.json. Fix: npm run api:types
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const committed = 'src/shared/api/schema.d.ts'
const dir = mkdtempSync(join(tmpdir(), 'api-types-'))
const fresh = join(dir, 'schema.d.ts')
try {
  execFileSync('npx', ['openapi-typescript', '../backend/openapi.json', '-o', fresh], { stdio: 'ignore' })
  if (readFileSync(fresh, 'utf8') !== readFileSync(committed, 'utf8')) {
    console.error(`${committed} is out of date with backend/openapi.json. Run: npm run api:types`)
    process.exit(1)
  }
  console.log(`${committed} matches backend/openapi.json`)
} finally {
  rmSync(dir, { recursive: true, force: true })
}
