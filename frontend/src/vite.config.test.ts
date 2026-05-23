import { describe, it, expect } from 'vitest'
import { appBasename } from '../vite.config'

describe('vite.config.ts', () => {
  it('exports appBasename as a string', () => {
    expect(typeof appBasename).toBe('string')
  })

  it('appBasename defaults to empty string when VITE_APP_BASENAME is not set', () => {
    // appBasename is captured at module load time.
    // This test verifies the default when the env var was unset at test startup.
    expect(appBasename).toBe('')
  })
})
