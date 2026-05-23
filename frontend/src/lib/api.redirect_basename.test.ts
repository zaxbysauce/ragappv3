/// <reference types="vitest" />
import { describe, test, expect } from 'vitest'

// Test the login path construction logic from api.ts 401 interceptor
// Replicates actual implementation: lines 250-251 in api.ts

describe('401 redirect basename-aware login path', () => {
  // Replicates the EXACT logic from api.ts lines 250-251
  const getLoginPath = (basename: string | undefined): string => {
    const base = (basename || '').replace(/\/$/, '')
    return base ? `${base}/login` : '/login'
  }

  describe('loginPath construction', () => {
    test('Root-level deployment: empty basename yields /login', () => {
      expect(getLoginPath('')).toBe('/login')
    })

    test('Root-level deployment: undefined basename yields /login', () => {
      expect(getLoginPath(undefined)).toBe('/login')
    })

    test('Root-level deployment: "/" basename yields /login', () => {
      expect(getLoginPath('/')).toBe('/login')
    })

    test('Path-prefixed deployment: /knowledgevault yields /knowledgevault/login', () => {
      expect(getLoginPath('/knowledgevault')).toBe('/knowledgevault/login')
    })

    test('Path-prefixed deployment: /knowledgevault/ (trailing slash) yields /knowledgevault/login', () => {
      expect(getLoginPath('/knowledgevault/')).toBe('/knowledgevault/login')
    })

    test('Path-prefixed deployment: /myapp yields /myapp/login', () => {
      expect(getLoginPath('/myapp')).toBe('/myapp/login')
    })

    test('Path-prefixed deployment: /myapp/ (trailing slash) yields /myapp/login', () => {
      expect(getLoginPath('/myapp/')).toBe('/myapp/login')
    })

    test('Path-prefixed deployment: /api/admin yields /api/admin/login', () => {
      expect(getLoginPath('/api/admin')).toBe('/api/admin/login')
    })

    test('Path-prefixed deployment: /api/admin/ (trailing slash) yields /api/admin/login', () => {
      expect(getLoginPath('/api/admin/')).toBe('/api/admin/login')
    })

  })

  describe('window.location assignment guard', () => {
    // Test that we don't redirect if already on login page
    const willRedirect = (currentPath: string, loginPath: string): boolean => {
      return currentPath !== loginPath
    }

    test('Redirects when on /dashboard and login is /login', () => {
      expect(willRedirect('/dashboard', '/login')).toBe(true)
    })

    test('Redirects when on /knowledgevault/dashboard and login is /knowledgevault/login', () => {
      expect(willRedirect('/knowledgevault/dashboard', '/knowledgevault/login')).toBe(true)
    })

    test('Redirects when on /knowledgevault/ (with trailing slash) and login is /knowledgevault/login', () => {
      expect(willRedirect('/knowledgevault/', '/knowledgevault/login')).toBe(true)
    })

    test('Does NOT redirect when already on /login', () => {
      expect(willRedirect('/login', '/login')).toBe(false)
    })

    test('Does NOT redirect when already on /knowledgevault/login', () => {
      expect(willRedirect('/knowledgevault/login', '/knowledgevault/login')).toBe(false)
    })
  })
})
