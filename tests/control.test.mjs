/**
 * Unit tests for the π control plugin, run directly against the module the
 * preset mounts. No Harness process is involved: the test supplies a fake tool
 * registry and a fake session log, so every assertion is about real computed
 * values, not about what a model said.
 *
 * Run: node --test tests/control.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { apply } from '../pi-preset/control.js'

/** Capture the two tool definitions apply() registers. */
function load(config) {
  const tools = new Map()
  const ctx = {
    tools: { register: (definition) => { tools.set(definition.name, definition); return () => tools.delete(definition.name) } },
    get: () => undefined,
  }
  apply(ctx, config)
  return tools
}

/** Build a session stand-in whose snapshotEvents returns the given events. */
function sessionOf(events) {
  return {
    seq: events.length,
    snapshotEvents: (from = 0, to = events.length) => events.slice(from, to),
  }
}

const run = (tools, name, args, exec = {}) => tools.get(name).execute(args, exec)

test('apply registers exactly pi_control and pi_guard', () => {
  const tools = load()
  assert.deepEqual([...tools.keys()].sort(), ['pi_control', 'pi_guard'])
})

test('apply rejects an invalid budget instead of silently defaulting', () => {
  assert.throws(() => load({ maxToolCallsPerTurn: 0 }), /maxToolCallsPerTurn/)
  assert.throws(() => load({ warnRatio: Number.NaN }), /warnRatio/)
})

test('signal reproduces the first known signs of frac(n*pi)', () => {
  const tools = load()
  const out = run(tools, 'pi_control', { action: 'signal', n: 0, count: 8 })
  // frac(n*pi) for n = 0..7: .000, .142, .283, .425, .566, .708, .850, .991
  assert.deepEqual(out.points.map((p) => p.sigma), [1, 1, 1, 1, -1, -1, -1, -1])
  assert.equal(out.points[1].r, '0.14159265358979323846')
  assert.equal(out.balance.plus + out.balance.minus, 8)
})

test('signal refuses out-of-range indices', () => {
  const tools = load()
  assert.throws(() => run(tools, 'pi_control', { action: 'signal', n: -1 }), /0\.\.1000000/)
  assert.throws(() => run(tools, 'pi_control', { action: 'signal', n: 2000000 }), /0\.\.1000000/)
})

test('one step matches the closed-loop equation', () => {
  const tools = load()
  const out = run(tools, 'pi_control', { action: 'step', e: 1, a: 0.9, b: 1, k: 0.6, eps: 0, sigma: 1, w: 0 })
  assert.equal(out.outputs.u, 0.6)
  assert.equal(out.outputs.eNext, 0.3)
  assert.equal(out.closedLoop.rho, 0.3)
  assert.equal(out.closedLoop.stable, true)
})

test('a gain that breaks the stability condition is reported as unstable', () => {
  const tools = load()
  const out = run(tools, 'pi_control', { action: 'step', e: 1, a: 1.4, b: 1, k: 0.1, eps: 0, sigma: 1, w: 0 })
  assert.equal(out.closedLoop.rho, 1.3)
  assert.equal(out.closedLoop.stable, false)
})

test('fixed-gain simulation follows a geometric decay', () => {
  const tools = load()
  const out = run(tools, 'pi_control', {
    action: 'simulate', policy: 'fixed', horizon: 4, a: 0.9, b: 1, k0: 0.6, e0: 1, disturbance: 'none', eps: 0,
  })
  assert.deepEqual(out.series.map((p) => p.e), [0.3, 0.09, 0.027, 0.0081])
  assert.equal(out.metrics.finalAbsError, 0.0081)
  assert.equal(out.metrics.rhoMax, 0.3)
  // |e| = .3, .09, .027, .0081 against tol .02 settles at step 4
  assert.equal(out.metrics.settleStep, 4)
})

test('simulation is deterministic for a given seed and the four policies differ', () => {
  const tools = load()
  const base = { action: 'simulate', horizon: 60, a: 0.9, b: 1, k0: 0.6, mu: 0.02, eps: 0.05, seed: 7, disturbance: 'uniform', disturbanceMagnitude: 0.05 }
  const a1 = run(tools, 'pi_control', { ...base, policy: 'adaptive_pi' })
  const a2 = run(tools, 'pi_control', { ...base, policy: 'adaptive_pi' })
  assert.deepEqual(a1.metrics, a2.metrics)
  const arms = ['fixed', 'adaptive', 'adaptive_random', 'adaptive_pi'].map((policy) => run(tools, 'pi_control', { ...base, policy }))
  for (const arm of arms) {
    assert.equal(arm.steps, 60)
    assert.equal(arm.finite, true)
    assert.ok(Number.isFinite(arm.metrics.rmse))
  }
  const signatures = new Set(arms.map((arm) => JSON.stringify(arm.series)))
  assert.equal(signatures.size > 1, true, 'policies must not collapse to one identical trajectory')
})

test('gain_scan returns the analytic interval', () => {
  const tools = load()
  const out = run(tools, 'pi_control', { action: 'gain_scan', a: 0.9, b: 1, rhoTarget: 0.9, kmin: 0, kmax: 2 })
  assert.deepEqual(out.feasibleInterval, { kMin: 0, kMax: 1.8 })
  const empty = run(tools, 'pi_control', { action: 'gain_scan', a: 3, b: 1, rhoTarget: 0.5, kmin: 0, kmax: 1 })
  assert.equal(empty.feasibleInterval, null)
})

test('guard measures an empty log as ok', () => {
  const tools = load()
  const out = run(tools, 'pi_guard', { action: 'status' }, { agent: { session: sessionOf([]) } })
  assert.equal(out.verdict, 'ok')
  assert.equal(out.totals.toolCalls, 0)
  assert.equal(out.evidence.provenance, 'measured:session-log')
})

test('guard stops on a repeated identical call', () => {
  const tools = load()
  const events = [
    { type: 'turn/start', data: { turn: 1 } },
    ...Array.from({ length: 4 }, () => ({ type: 'tool/call', data: { turn: 1, step: 1, callId: 'c', name: 'read', arguments: { path: 'a.txt' } } })),
  ]
  const out = run(tools, 'pi_guard', { action: 'status' }, { agent: { session: sessionOf(events) } })
  assert.equal(out.verdict, 'stop')
  assert.ok(out.violations.some((v) => v.rule === 'identical-repeat'))
  assert.equal(out.totals.maxIdenticalRepeats, 4)
})

test('guard stops after three consecutive failing results and reports the last error', () => {
  const tools = load()
  const events = []
  for (let index = 0; index < 3; index += 1) {
    events.push({ type: 'tool/call', data: { turn: 1, step: index, callId: `c${index}`, name: 'pwsh', arguments: { command: `echo ${index}` } } })
    events.push({ type: 'tool/result', data: { turn: 1, step: index, message: { callId: `c${index}`, isError: true, content: [{ type: 'text', text: `boom ${index}` }] } } })
  }
  const out = run(tools, 'pi_guard', { action: 'status' }, { agent: { session: sessionOf(events) } })
  assert.equal(out.verdict, 'stop')
  assert.ok(out.violations.some((v) => v.rule === 'consecutive-failures'))
  assert.equal(out.totals.consecutiveFailures, 3)
  assert.equal(out.lastError, 'boom 2')
})

test('guard warns before it stops', () => {
  const tools = load()
  const events = Array.from({ length: 45 }, (_, index) => ({
    type: 'tool/call',
    data: { turn: 1, step: index, callId: `c${index}`, name: index % 2 ? 'read' : 'grep', arguments: { i: index } },
  }))
  const out = run(tools, 'pi_guard', { action: 'status' }, { agent: { session: sessionOf(events) } })
  assert.equal(out.verdict, 'warn')
  assert.equal(out.totals.currentTurnCalls, 45)
})

test('guard degrades honestly without a session log', () => {
  const tools = load()
  const out = run(tools, 'pi_guard', { action: 'status' }, {})
  assert.equal(out.evidence.provenance, 'unavailable')
  assert.equal(out.verdict, 'ok')
})

test('record acknowledges that self-reported outcomes are not evidence', () => {
  const tools = load()
  const out = run(tools, 'pi_guard', { action: 'record', outcome: 'failure', tool: 'pwsh' })
  assert.equal(out.provenance, 'self-reported')
  assert.equal(out.recorded.outcome, 'failure')
})
