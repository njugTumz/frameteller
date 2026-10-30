import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'
import { emojiFlags } from './flags'

beforeEach(() => emojiFlags(true)) // flags draw as flags unless a test says otherwise
afterEach(() => cleanup())
