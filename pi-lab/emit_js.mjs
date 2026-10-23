/**
 * Emit real trajectories from the module the preset actually mounts, so the
 * Python reference can be compared against it rather than against a copy.
 *
 * Writes JSON to stdout: { cases: [ { name, args, result } ] }
 */
import { apply } from '../pi-preset/control.js'

const tools = new Map()
apply(
  {
    tools: { register: (definition) => { tools.set(definition.name, definition); return () => {} } },
    get: () => undefined,
  },
  {},
)

const control = tools.get('pi_control')

const common = {
  a: 0.9,
  b: 1,
  k0: 0.6,
  mu: 0.02,
  eps: 0.05,
  seed: 4242,
  horizon: 120,
  settleTol: 0.02,
  disturbance: 'uniform',
  disturbanceMagnitude: 0.1,
}

const cases = []
for (const policy of ['fixed', 'adaptive', 'adaptive_random', 'adaptive_pi']) {
  cases.push({
    name: `simulate:${policy}`,
    args: { action: 'simulate', policy, ...common },
  })
}
cases.push({ name: 'step:stable', args: { action: 'step', e: 1, a: 0.9, b: 1, k: 0.6, eps: 0.02, sigma: 1, w: 0.05 } })
cases.push({ name: 'signal:0-40', args: { action: 'signal', n: 0, count: 40 } })
cases.push({ name: 'gain', args: { action: 'gain_scan', a: 0.9, b: 1, rhoTarget: 0.9, kmin: 0, kmax: 2 } })

const out = cases.map((entry) => {
  const value = control.execute(entry.args, {})
  return { name: entry.name, args: entry.args, result: value }
})

process.stdout.write(JSON.stringify({ cases: out }, null, 2))
