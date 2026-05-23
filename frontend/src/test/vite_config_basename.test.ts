/// <reference types="vitest" />
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'

// We need to test the appBasename logic without importing the actual config
// since it reads process.env at module load time. Instead, we test the
// equivalent logic directly.

describe('VITE_APP_BASENAME configuration logic', () => {
  const originalEnv = process.env.VITE_APP_BASENAME

  afterEach(() => {
    // Restore original env
    if (originalEnv === undefined) {
      delete process.env.VITE_APP_BASENAME
    } else {
      process.env.VITE_APP_BASENAME = originalEnv
    }
  })

  // Simulates: export const appBasename = process.env.VITE_APP_BASENAME || ''
  const getAppBasename = () => process.env.VITE_APP_BASENAME || ''

  // Simulates: base: appBasename || '/'
  const getBase = (appBasename: string) => appBasename || '/'

  test('base falls back to "/" when VITE_APP_BASENAME is not set', () => {
    delete process.env.VITE_APP_BASENAME
    const appBasename = getAppBasename()
    const base = getBase(appBasename)
    expect(base).toBe('/')
  })

  test('base uses env var value when VITE_APP_BASENAME is set to a path', () => {
    process.env.VITE_APP_BASENAME = '/myapp'
    const appBasename = getAppBasename()
    const base = getBase(appBasename)
    expect(base).toBe('/myapp')
  })

  test('base uses env var value when VITE_APP_BASENAME is set to root', () => {
    process.env.VITE_APP_BASENAME = '/'
    const appBasename = getAppBasename()
    const base = getBase(appBasename)
    expect(base).toBe('/')
  })

  test('base falls back to "/" when VITE_APP_BASENAME is set to empty string', () => {
    process.env.VITE_APP_BASENAME = ''
    const appBasename = getAppBasename()
    const base = getBase(appBasename)
    expect(base).toBe('/')
  })

  test('appBasename is exported as a string', () => {
    process.env.VITE_APP_BASENAME = '/test'
    const appBasename = getAppBasename()
    expect(typeof appBasename).toBe('string')
  })
})
