import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useMonthlySeries } from '../sampleData'

// useMonthlySeries reads organizationId/token/showSampleData from AuthContext.
// Stub the module so the hook can be exercised without a real Clerk-backed
// AuthProvider in the tree. `mockAuth` is mutated per-test to flip
// showSampleData on/off.
const mockAuth = {
  organizationId: 'org-1',
  token: 'tok-1',
  showSampleData: true,
}
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

describe('useMonthlySeries', () => {
  beforeEach(() => {
    mockAuth.showSampleData = true
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('a non-OK response yields source "unavailable" and series null — never the sample baseline', async () => {
    ;(fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers(),
      json: async () => ({ rows: [] }),
    })

    const { result } = renderHook(() => useMonthlySeries('site-a', 2026))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.source).toBe('unavailable')
    expect(result.current.series).toBeNull()
  })

  it('a successful response with zero rows yields "sample" when sample mode is on', async () => {
    mockAuth.showSampleData = true
    ;(fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({ rows: [] }),
    })

    const { result } = renderHook(() => useMonthlySeries('site-a', 2026))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.source).toBe('sample')
    expect(result.current.series).not.toBeNull()
  })

  it('a successful response with zero rows yields "none" when sample mode is off', async () => {
    mockAuth.showSampleData = false
    ;(fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({ rows: [] }),
    })

    const { result } = renderHook(() => useMonthlySeries('site-a', 2026))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.source).toBe('none')
    expect(result.current.series).toBeNull()
  })

  it('a thrown fetch yields "unavailable", not "none"', async () => {
    ;(fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'))

    const { result } = renderHook(() => useMonthlySeries('site-a', 2026))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.source).toBe('unavailable')
    expect(result.current.source).not.toBe('none')
    expect(result.current.series).toBeNull()
  })
})
