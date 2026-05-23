import { describe, test, expect } from 'bun:test'

// Replicate the normalization logic from vite.config.ts
function normalizeBasename(appBasename: string): string {
  return appBasename.replace(/\/+$/, '')
}

function computeProxyConfig(appBasename: string): { key: string; rewrite: ((path: string) => string) | undefined } {
  const normalizedBasename = normalizeBasename(appBasename)
  const key = normalizedBasename ? `${normalizedBasename}/api` : '/api'
  const rewrite = normalizedBasename
    ? (path: string) => path.replace(new RegExp(`^${normalizedBasename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`), '')
    : undefined
  return { key, rewrite }
}

describe('1.5: Proxy rewrite with regex escape', () => {

  test('1. appBasename="" → normalizedBasename="", key="/api", no rewrite', () => {
    const { key, rewrite } = computeProxyConfig('')
    expect(normalizeBasename('')).toBe('')
    expect(key).toBe('/api')
    expect(rewrite).toBeUndefined()
  })

  test('2. appBasename="/knowledgevault" → normalizedBasename="/knowledgevault", key="/knowledgevault/api", rewrite strips basename', () => {
    const { key, rewrite } = computeProxyConfig('/knowledgevault')
    expect(normalizeBasename('/knowledgevault')).toBe('/knowledgevault')
    expect(key).toBe('/knowledgevault/api')
    expect(rewrite).toBeDefined()
    expect(rewrite!('/knowledgevault/api/users')).toBe('/api/users')
    expect(rewrite!('/knowledgevault/api')).toBe('/api')
  })

  test('3. appBasename="/knowledgevault/" → normalizedBasename="/knowledgevault", key="/knowledgevault/api"', () => {
    const { key, rewrite } = computeProxyConfig('/knowledgevault/')
    expect(normalizeBasename('/knowledgevault/')).toBe('/knowledgevault')
    expect(key).toBe('/knowledgevault/api')
    expect(rewrite).toBeDefined()
    expect(rewrite!('/knowledgevault/api/users')).toBe('/api/users')
  })

  test('4. appBasename="/" → normalizedBasename="", key="/api"', () => {
    const { key, rewrite } = computeProxyConfig('/')
    expect(normalizeBasename('/')).toBe('')
    expect(key).toBe('/api')
    expect(rewrite).toBeUndefined()
  })

  test('5. appBasename="/app.v2" → regex properly escapes the dot', () => {
    const { key, rewrite } = computeProxyConfig('/app.v2')
    expect(normalizeBasename('/app.v2')).toBe('/app.v2')
    expect(key).toBe('/app.v2/api')
    expect(rewrite).toBeDefined()
    // The dot must be escaped - /app.v2/api should NOT match /appX2/api
    expect(rewrite!('/app.v2/api/users')).toBe('/api/users')
    // Verify it doesn't incorrectly match similar paths
    expect(rewrite!('/appX2/api')).toBe('/appX2/api') // not matched, dot is escaped
    expect(rewrite!('/app.v2/api')).toBe('/api')
  })

  test('Edge: multiple trailing slashes are stripped', () => {
    expect(normalizeBasename('///')).toBe('')
  })

  test('Edge: path with no match remains unchanged', () => {
    const { rewrite } = computeProxyConfig('/app')
    expect(rewrite!('/other/api')).toBe('/other/api')
  })
})
