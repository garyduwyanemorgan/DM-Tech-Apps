import { describe, it, expect } from 'vitest'
import {
  rollup,
  lightForReading,
  statusFromReadings,
  statusUnavailable,
  LIGHT_STYLE,
  type SiteStatus,
  type TrafficLight,
} from '../status'

/** Minimal SiteStatus builder for rollup() tests. */
function site(light: TrafficLight, compliancePct: number | null = null): SiteStatus {
  return {
    site: `site-${Math.random()}`,
    light,
    latest: null,
    compliancePct,
    failingParams: [],
    alertLevel: null,
  }
}

describe('rollup()', () => {
  it('excludes unavailable sites from the avgCompliancePct denominator (5 sites, 2 unavailable, 80/90/100 -> 90)', () => {
    const statuses: SiteStatus[] = [
      site('green', 80),
      site('green', 90),
      site('green', 100),
      site('unavailable', null),
      site('unavailable', null),
    ]
    const kpis = rollup(statuses)
    expect(kpis.avgCompliancePct).toBe(90)
    expect(kpis.avgCompliancePct).not.toBe(54)
  })

  it('compliancePctBasis counts only sites that contributed a number, not total - unavailable', () => {
    // 5 sites: 2 unavailable, 1 blue (reachable, no reading), 2 with numbers.
    const statuses: SiteStatus[] = [
      site('unavailable', null),
      site('unavailable', null),
      site('blue', null),
      site('green', 80),
      site('green', 90),
    ]
    const kpis = rollup(statuses)
    expect(kpis.compliancePctBasis).toBe(2)
    // total - unavailable would be 3; that must NOT be what's reported.
    expect(kpis.compliancePctBasis).not.toBe(statuses.length - kpis.unavailable)
  })

  it('avgCompliancePct is null, never 0, when nothing is known', () => {
    const statuses: SiteStatus[] = [
      site('blue', null),
      site('unavailable', null),
    ]
    const kpis = rollup(statuses)
    expect(kpis.avgCompliancePct).toBeNull()
    expect(kpis.avgCompliancePct).not.toBe(0)
  })

  it('needsAttention counts only yellow + red; unavailable does not inflate or deflate it', () => {
    const statuses: SiteStatus[] = [
      site('yellow', 70),
      site('red', 40),
      site('unavailable', null),
      site('unavailable', null),
      site('green', 100),
      site('blue', null),
    ]
    const kpis = rollup(statuses)
    expect(kpis.needsAttention).toBe(2)
  })
})

describe('statusUnavailable() vs statusFromReadings(site, null)', () => {
  it('statusUnavailable produces the unavailable light', () => {
    const s = statusUnavailable('site-a', 'req-123')
    expect(s.light).toBe('unavailable')
    expect(s.requestId).toBe('req-123')
  })

  it('statusFromReadings(site, null) still yields blue for genuine no-readings-yet, never unavailable', () => {
    const s = statusFromReadings('site-a', null)
    expect(s.light).toBe('blue')
    expect(s.light).not.toBe('unavailable')
  })
})

describe('lightForReading ordering', () => {
  it('a reading that is red today (NON_COMPLIANT) never becomes grey', () => {
    const light = lightForReading({ compliance: 'NON_COMPLIANT', alert_level: 1 })
    expect(light).toBe('red')
  })

  it('a reading that is red today (failing params) never becomes grey', () => {
    const light = lightForReading({ compliance: 'INCOMPLETE', failing_params: ['ph'] })
    expect(light).toBe('red')
  })

  it('a reading that is red today (alert level >= 3) never becomes grey', () => {
    const light = lightForReading({ compliance: 'NOT_ASSESSED', alert_level: 3 })
    expect(light).toBe('red')
  })

  it('an unjudgeable verdict with no breach signal is grey, not green', () => {
    const light = lightForReading({ compliance: 'INCOMPLETE', alert_level: 1 })
    expect(light).toBe('grey')
  })

  it('no reading at all is blue', () => {
    expect(lightForReading(null)).toBe('blue')
    expect(lightForReading(undefined)).toBe('blue')
  })
})

describe('LIGHT_STYLE', () => {
  it('has an entry for every TrafficLight value', () => {
    const lights: TrafficLight[] = ['green', 'yellow', 'red', 'blue', 'grey', 'unavailable']
    for (const light of lights) {
      expect(LIGHT_STYLE[light]).toBeDefined()
      expect(LIGHT_STYLE[light].label).toEqual(expect.any(String))
    }
    expect(Object.keys(LIGHT_STYLE).sort()).toEqual([...lights].sort())
  })
})
