/**
 * π control surface: two model-facing tools scoped to the π preset.
 *
 * `pi_control` — deterministic maths. Every number it returns is computed here
 * from the caller's arguments; nothing is estimated or invented. It covers the
 * π-signal r(n) = frac(n·π) with exact BigInt arithmetic, one closed-loop step,
 * a four-policy simulation on the first-order model
 *   e(t+1) = a·e(t) − b·u(t) + w(t),  u(t) = k(t)·e(t) + ε·σ(t)
 * and an analytic gain scan for |a − b·k| ≤ ρ.
 *
 * `pi_guard`  — measured stability accounting. It reads the *calling session's
 * own durable log* (`tool/call` and `tool/result` events) and reports tool-call
 * load, identical-call repeats, consecutive failures, and simple oscillation,
 * then returns a verdict. No process-wide hook is installed, so no other preset
 * is affected, and the model cannot widen its own budget because budgets come
 * from this plugin's static config.
 *
 * Sources of every reported metric are labelled `measured:*` or
 * `self-reported`, so the model never has to guess what is real.
 */

export const name = 'pi-control'

export const inject = ['tools']

/** Hard-coded π digits (100 decimal places) used for exact sign decisions. */
const PI_DIGITS = '31415926535897932384626433832795028841971693993751058209749445923078164062862089986280348253421170679'
const PI_SCALE = 10n ** 100n
const PI_INT = BigInt(PI_DIGITS)
const PI_HALF = PI_SCALE / 2n

const DEFAULTS = {
  maxToolCallsPerTurn: 60,
  maxToolCallsTotal: 400,
  maxIdenticalRepeats: 3,
  maxConsecutiveFailures: 3,
  warnRatio: 0.7,
  scanWindow: 5000,
}

/**
 * Sign of the π sequence at an integer index: +1 when frac(n·π) < 1/2, else −1.
 * @param {number} n non-negative integer.
 * @returns {1 | -1} the deterministic sign.
 */
function piSign(n) {
  const residue = (BigInt(n) * PI_INT) % PI_SCALE
  return residue < PI_HALF ? 1 : -1
}

/**
 * Decimal expansion of frac(n·π) at the precision this module carries.
 * @param {number} n non-negative integer.
 * @param {number} digits digits to print.
 * @returns {string} `0.xxxxxxxx…`
 */
function piFrac(n, digits) {
  const residue = (BigInt(n) * PI_INT) % PI_SCALE
  return '0.' + residue.toString().padStart(100, '0').slice(0, digits)
}

/** Deterministic 32-bit PRNG (mulberry32); identical in the Python reference. */
function mulberry32(seed) {
  let a = seed >>> 0
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value))

/** Round for output without lying about precision. */
const round = (value, digits = 6) => {
  if (!Number.isFinite(value)) return value
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

/** JSON with sorted keys, so identical calls compare equal regardless of order. */
function stableStringify(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']'
  const keys = Object.keys(value).sort()
  return '{' + keys.map((key) => JSON.stringify(key) + ':' + stableStringify(value[key])).join(',') + '}'
}

/**
 * One disturbance draw. Returned value is added to the next error term.
 * @param {string} kind none | uniform | sine | impulse
 * @param {number} magnitude peak amplitude
 * @param {number} t current step index (1-based)
 * @param {number} period sine period in steps
 * @param {number} at impulse step
 * @param {() => number} rng PRNG for uniform draws
 */
function disturbance(kind, magnitude, t, period, at, rng) {
  switch (kind) {
    case 'uniform':
      return magnitude * (2 * rng() - 1)
    case 'sine':
      return magnitude * Math.sin((2 * Math.PI * t) / period)
    case 'impulse':
      return t === at ? magnitude : 0
    case 'none':
      return 0
    default:
      throw new Error(`unknown disturbance kind: ${kind}`)
  }
}

/**
 * Simulate the first-order loop under one exploration policy.
 * All four arms share the same disturbance draw for a given seed, so the
 * comparison is paired rather than independent.
 */
function simulate(options) {
  const {
    policy,
    horizon,
    a,
    b,
    k0,
    mu,
    kmin,
    kmax,
    umax,
    eps,
    e0,
    seed,
    rhoMax,
    settleTol,
    disturbanceKind,
    disturbanceMagnitude,
    disturbancePeriod,
    disturbanceAt,
  } = options

  const rng = mulberry32(seed)
  let k = clamp(k0, kmin, kmax)
  let e = e0

  const errors = []
  const gains = []
  const controls = []
  let saturation = 0
  let rhoMin = Infinity
  let rhoMaxSeen = -Infinity
  let stableSteps = 0
  let explorationSteps = 0
  let finite = true

  for (let t = 1; t <= horizon; t += 1) {
    let sigma = 0
    let explore = 0
    if (policy === 'adaptive_pi') {
      sigma = piSign(t)
      explore = eps * sigma
      explorationSteps += 1
    } else if (policy === 'adaptive_random') {
      sigma = rng() < 0.5 ? 1 : -1
      explore = eps * sigma
      explorationSteps += 1
    }

    const w = disturbance(disturbanceKind, disturbanceMagnitude, t, disturbancePeriod, disturbanceAt, rng)
    const rawU = k * e + explore
    const u = clamp(rawU, -umax, umax)
    if (Math.abs(rawU - u) > 1e-12) saturation += 1

    const next = a * e - b * u + w
    if (!Number.isFinite(next)) finite = false

    const rho = Math.abs(a - b * k)
    if (rho < rhoMin) rhoMin = rho
    if (rho > rhoMaxSeen) rhoMaxSeen = rho
    if (rho <= rhoMax) stableSteps += 1

    errors.push(next)
    gains.push(k)
    controls.push(u)

    if (policy !== 'fixed') {
      k = clamp(k + mu * e * next, kmin, kmax)
    }
    e = next
    if (!finite) break
  }

  const abs = errors.map(Math.abs)
  const sumSquares = errors.reduce((acc, value) => acc + value * value, 0)
  const rmse = Math.sqrt(sumSquares / Math.max(1, errors.length))
  const mae = abs.reduce((acc, value) => acc + value, 0) / Math.max(1, abs.length)
  let settleStep = null
  for (let i = 0; i < abs.length; i += 1) {
    if (abs.slice(i).every((value) => value <= settleTol)) {
      settleStep = i + 1
      break
    }
  }

  const stride = Math.max(1, Math.floor(horizon / 20))
  const series = errors
    .map((value, index) => ({ t: index + 1, e: round(value, 6), k: round(gains[index], 6), u: round(controls[index], 6) }))
    .filter((point) => point.t % stride === 0 || point.t === errors.length)

  return {
    policy,
    steps: errors.length,
    finite,
    metrics: {
      rmse: round(rmse),
      mae: round(mae),
      maxAbsError: round(Math.max(...abs)),
      finalAbsError: round(abs[abs.length - 1] ?? NaN),
      settleStep,
      controlEffort: round(controls.reduce((acc, value) => acc + Math.abs(value), 0)),
      saturationCount: saturation,
      explorationSteps,
      rhoMin: round(rhoMin),
      rhoMax: round(rhoMaxSeen),
      stableFraction: round(stableSteps / Math.max(1, errors.length)),
      finalGain: round(gains[gains.length - 1] ?? NaN),
    },
    series,
  }
}

/** A text content block. */
const text = (value) => [{ type: 'text', text: value }]

const json = (value) => text(JSON.stringify(value, null, 2))

/** Parameter schema shared by both actions of `pi_control`. */
const CONTROL_PARAMETERS = {
  type: 'object',
  additionalProperties: false,
  required: ['action'],
  properties: {
    action: {
      type: 'string',
      enum: ['signal', 'step', 'simulate', 'gain_scan'],
      description:
        'signal: emit the deterministic π sequence. step: advance one closed-loop step. simulate: run one policy arm on the first-order model. gain_scan: analytic feasible gain interval for |a - b k| <= rho.',
    },
    n: { type: 'integer', description: 'signal: first index n (default 0, max 1000000).' },
    count: { type: 'integer', description: 'signal: how many indices to emit (default 16, max 256).' },
    e: { type: 'number', description: 'step: current normalised error e(t).' },
    a: { type: 'number', description: 'state coefficient a (default 0.9).' },
    b: { type: 'number', description: 'control coefficient b (default 1.0, must be non-zero for gain_scan).' },
    k: { type: 'number', description: 'current gain k (step, default 0.6).' },
    eps: { type: 'number', description: 'exploration magnitude epsilon (default 0.02).' },
    sigma: { type: 'integer', enum: [1, -1], description: 'step: exploration sign.' },
    w: { type: 'number', description: 'step: disturbance w(t).' },
    policy: {
      type: 'string',
      enum: ['fixed', 'adaptive', 'adaptive_random', 'adaptive_pi'],
      description: 'simulate: fixed gain, adaptive without exploration, adaptive with random exploration, adaptive with π-signal exploration.',
    },
    horizon: { type: 'integer', description: 'simulate: steps (default 200, max 5000).' },
    k0: { type: 'number', description: 'simulate: initial gain (default 0.6).' },
    mu: { type: 'number', description: 'simulate: gain step size (default 0.02).' },
    kmin: { type: 'number', description: 'simulate: lower gain projection bound (default 0).' },
    kmax: { type: 'number', description: 'simulate: upper gain projection bound (default 2).' },
    umax: { type: 'number', description: 'simulate: control saturation bound (default 10).' },
    e0: { type: 'number', description: 'simulate: initial error (default 1).' },
    seed: { type: 'integer', description: 'simulate: PRNG seed for paired comparisons (default 12345).' },
    rhoMax: { type: 'number', description: 'simulate: stability threshold rho (default 0.98).' },
    settleTol: { type: 'number', description: 'simulate: settling tolerance (default 0.02).' },
    disturbance: {
      type: 'string',
      enum: ['none', 'uniform', 'sine', 'impulse'],
      description: 'simulate: disturbance shape (default none).',
    },
    disturbanceMagnitude: { type: 'number', description: 'simulate: disturbance peak (default 0.1).' },
    disturbancePeriod: { type: 'number', description: 'simulate: sine period in steps (default 25).' },
    disturbanceAt: { type: 'integer', description: 'simulate: impulse step (default 20).' },
    rhoTarget: { type: 'number', description: 'gain_scan: target stability margin (default 0.9).' },
  },
}

/** Register π's two tools on the preset-scoped tool registry. */
export function apply(ctx, config) {
  const settings = { ...DEFAULTS, ...(config ?? {}) }
  for (const key of Object.keys(DEFAULTS)) {
    const value = settings[key]
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      throw new Error(`pi-control: config.${key} must be a positive finite number, got ${String(value)}`)
    }
  }

  ctx.tools.register({
    name: 'pi_control',
    description:
      'Deterministic control mathematics for π. action=signal emits sigma(n) from r(n)=frac(n*pi) using exact integer arithmetic (a deterministic sequence, not randomness). action=step advances e(t+1)=a*e-b*(k*e+eps*sigma)+w once. action=simulate runs one policy arm on that first-order model and returns measured metrics (rmse, settle step, control effort, saturation, |a-b*k| range) for the given parameters. action=gain_scan returns the analytic gain interval where |a-b*k|<=rho. Use it for real numbers instead of asserting stability or superiority in prose.',
    parameters: CONTROL_PARAMETERS,
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => json(value),
    },
    isConcurrencySafe: () => true,
    presentCall: (args) => ({
      card: 'generic',
      title: `π control · ${String(args?.action ?? '')}`,
      kind: 'other',
      rawInput: args,
    }),
    execute(args) {
      const action = args?.action
      if (action === 'signal') {
        const start = Number.isInteger(args.n) ? args.n : 0
        const count = clamp(Number.isInteger(args.count) ? args.count : 16, 1, 256)
        if (start < 0 || start > 1000000) throw new Error('pi_control(signal): n must be 0..1000000')
        const points = []
        let plus = 0
        let minus = 0
        let run = 0
        let previous = 0
        let maxRun = 0
        for (let index = 0; index < count; index += 1) {
          const n = start + index
          const sigma = piSign(n)
          if (sigma === 1) plus += 1
          else minus += 1
          if (sigma === previous) run += 1
          else {
            previous = sigma
            run = 1
          }
          if (run > maxRun) maxRun = run
          points.push({ n, r: piFrac(n, 20), sigma })
        }
        return {
          action,
          formula: 'r(n) = frac(n*pi); sigma(n) = +1 if r(n) < 1/2 else -1',
          arithmetic: 'exact integer arithmetic with 100 decimal digits of pi; exact for n <= 1e40',
          nature: 'deterministic sequence — not a random number generator, and not claimed to beat random exploration',
          points,
          balance: { plus, minus, maxSignRun: maxRun },
        }
      }

      if (action === 'step') {
        const e = Number(args.e)
        const a = args.a === undefined ? 0.9 : Number(args.a)
        const b = args.b === undefined ? 1 : Number(args.b)
        const k = args.k === undefined ? 0.6 : Number(args.k)
        const eps = args.eps === undefined ? 0.02 : Number(args.eps)
        const sigma = args.sigma === 1 ? 1 : -1
        const w = args.w === undefined ? 0 : Number(args.w)
        if (![e, a, b, k, eps, w].every(Number.isFinite)) throw new Error('pi_control(step): e, a, b, k, eps, w must be finite numbers')
        const u = k * e + eps * sigma
        const next = a * e - b * u + w
        const rho = Math.abs(a - b * k)
        return {
          action,
          inputs: { e, a, b, k, eps, sigma, w },
          outputs: { u, eNext: round(next) },
          closedLoop: { rho: round(rho), stable: rho < 1 },
          caveat: 'stability of this first-order model says nothing about agent workflows that lack a measurable state',
        }
      }

      if (action === 'simulate') {
        const policy = String(args.policy ?? 'fixed')
        const allowed = ['fixed', 'adaptive', 'adaptive_random', 'adaptive_pi']
        if (!allowed.includes(policy)) throw new Error(`pi_control(simulate): policy must be one of ${allowed.join(', ')}`)
        const options = {
          policy,
          horizon: clamp(Number.isInteger(args.horizon) ? args.horizon : 200, 1, 5000),
          a: args.a === undefined ? 0.9 : Number(args.a),
          b: args.b === undefined ? 1 : Number(args.b),
          k0: args.k0 === undefined ? 0.6 : Number(args.k0),
          mu: args.mu === undefined ? 0.02 : Number(args.mu),
          kmin: args.kmin === undefined ? 0 : Number(args.kmin),
          kmax: args.kmax === undefined ? 2 : Number(args.kmax),
          umax: args.umax === undefined ? 10 : Number(args.umax),
          eps: args.eps === undefined ? 0.02 : Number(args.eps),
          e0: args.e0 === undefined ? 1 : Number(args.e0),
          seed: Number.isInteger(args.seed) ? args.seed : 12345,
          rhoMax: args.rhoMax === undefined ? 0.98 : Number(args.rhoMax),
          settleTol: args.settleTol === undefined ? 0.02 : Number(args.settleTol),
          disturbanceKind: String(args.disturbance ?? 'none'),
          disturbanceMagnitude: args.disturbanceMagnitude === undefined ? 0.1 : Number(args.disturbanceMagnitude),
          disturbancePeriod: args.disturbancePeriod === undefined ? 25 : Number(args.disturbancePeriod),
          disturbanceAt: Number.isInteger(args.disturbanceAt) ? args.disturbanceAt : 20,
        }
        for (const [key, value] of Object.entries(options)) {
          if (typeof value === 'number' && !Number.isFinite(value)) throw new Error(`pi_control(simulate): ${key} must be finite`)
        }
        if (options.kmin > options.kmax) throw new Error('pi_control(simulate): kmin must not exceed kmax')
        return {
          action,
          model: 'e(t+1) = a*e(t) - b*u(t) + w(t); u(t) = clip(k(t)*e(t) + eps*sigma(t), -umax, umax); k(t+1) = clip(k + mu*e(t)*e(t+1), kmin, kmax)',
          options: { ...options, gainRule: policy === 'fixed' ? 'k constant' : 'MIT-style gradient step, projected' },
          ...simulate(options),
          caveat:
            'one run, one seed. Treat metrics as a measurement of this model only; do not claim general superiority without repeated paired runs and a statistical test.',
        }
      }

      if (action === 'gain_scan') {
        const a = args.a === undefined ? 0.9 : Number(args.a)
        const b = args.b === undefined ? 1 : Number(args.b)
        const rhoTarget = args.rhoTarget === undefined ? 0.9 : Number(args.rhoTarget)
        const kmin = args.kmin === undefined ? 0 : Number(args.kmin)
        const kmax = args.kmax === undefined ? 2 : Number(args.kmax)
        if (![a, b, rhoTarget, kmin, kmax].every(Number.isFinite)) throw new Error('pi_control(gain_scan): coefficients must be finite')
        if (b === 0) throw new Error('pi_control(gain_scan): b must be non-zero')
        if (rhoTarget <= 0) throw new Error('pi_control(gain_scan): rhoTarget must be positive')
        const low = (a - rhoTarget) / b
        const high = (a + rhoTarget) / b
        const lo = Math.max(kmin, Math.min(low, high))
        const hi = Math.min(kmax, Math.max(low, high))
        const feasible = lo <= hi
        const samples = []
        const steps = 9
        for (let index = 0; index < steps; index += 1) {
          const k = kmin + ((kmax - kmin) * index) / (steps - 1)
          samples.push({ k: round(k), rho: round(Math.abs(a - b * k)) })
        }
        return {
          action,
          condition: '|a - b*k| <= rho',
          feasibleInterval: feasible ? { kMin: round(lo), kMax: round(hi) } : null,
          samples,
        }
      }

      throw new Error(`pi_control: unknown action ${String(action)}`)
    },
  })

  ctx.tools.register({
    name: 'pi_guard',
    description:
      'Measured stability accounting for π. Reads this session\'s own durable tool events and reports tool-call load, identical-call repeats, consecutive failures, and name oscillation, then returns verdict ok | warn | stop with the rule that fired. Budgets come from the preset configuration and cannot be changed by the agent. Call it before long work, after a failure, and before claiming success. action=record may append a self-reported outcome when the session log is unavailable.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['action'],
      properties: {
        action: {
          type: 'string',
          enum: ['status', 'record'],
          description: 'status: measure and judge. record: append one self-reported outcome.',
        },
        outcome: {
          type: 'string',
          enum: ['success', 'failure'],
          description: 'record: what just happened.',
        },
        tool: { type: 'string', description: 'record: which tool (or step) the outcome belongs to.' },
        note: { type: 'string', description: 'record: short free-text note.' },
      },
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => json(value),
    },
    isConcurrencySafe: () => true,
    presentCall: (args) => ({
      card: 'generic',
      title: `π guard · ${String(args?.action ?? '')}`,
      kind: 'other',
      rawInput: args,
    }),
    execute(args, exec) {
      const session = exec?.agent?.session
      const reported = []

      if (args?.action === 'record') {
        const outcome = args.outcome === 'failure' ? 'failure' : 'success'
        reported.push({ outcome, tool: String(args.tool ?? 'unspecified'), note: String(args.note ?? ''), at: Date.now() })
        return {
          action: 'record',
          provenance: 'self-reported',
          recorded: reported[0],
          note: 'Self-reported outcomes are not evidence; prefer the measured status action.',
        }
      }

      const measurement = measureSession(session)
      const state = measurement.state
      const totals = {
        toolCalls: state.toolCalls,
        toolsUsed: Object.keys(state.perTool).length,
        currentTurnCalls: state.currentTurnCalls,
        currentTurn: state.currentTurn,
        consecutiveFailures: state.consecutiveFailures,
        maxIdenticalRepeats: state.maxIdenticalRepeat,
        repeatedSignature: state.repeatedSignature,
        nameOscillations: state.oscillations,
      }

      const violations = []
      if (state.consecutiveFailures >= settings.maxConsecutiveFailures) {
        violations.push({
          rule: 'consecutive-failures',
          detail: `${state.consecutiveFailures} consecutive failing tool results (limit ${settings.maxConsecutiveFailures})`,
        })
      }
      if (state.maxIdenticalRepeat >= settings.maxIdenticalRepeats) {
        violations.push({
          rule: 'identical-repeat',
          detail: `${state.maxIdenticalRepeat} identical ${state.repeatedSignature} calls (limit ${settings.maxIdenticalRepeats})`,
        })
      }
      if (state.currentTurnCalls >= settings.maxToolCallsPerTurn) {
        violations.push({
          rule: 'turn-budget',
          detail: `${state.currentTurnCalls} tool calls this turn (limit ${settings.maxToolCallsPerTurn})`,
        })
      }
      if (state.toolCalls >= settings.maxToolCallsTotal) {
        violations.push({
          rule: 'session-budget',
          detail: `${state.toolCalls} tool calls this session (limit ${settings.maxToolCallsTotal})`,
        })
      }

      const ratios = [
        state.consecutiveFailures / settings.maxConsecutiveFailures,
        state.maxIdenticalRepeat / settings.maxIdenticalRepeats,
        state.currentTurnCalls / settings.maxToolCallsPerTurn,
        state.toolCalls / settings.maxToolCallsTotal,
      ]
      const worst = Math.max(...ratios)
      const verdict = violations.length > 0 ? 'stop' : worst >= settings.warnRatio ? 'warn' : 'ok'

      let tokenMeasurement
      const meter = ctx.get?.('tokenMeter')
      if (meter && session) {
        try {
          tokenMeasurement = truncate(JSON.stringify(meter.measure(session)), 600)
        } catch (error) {
          tokenMeasurement = `unavailable: ${error instanceof Error ? error.message : String(error)}`
        }
      }

      return {
        action: 'status',
        verdict,
        evidence: {
          provenance: measurement.provenance,
          source: measurement.source,
          scannedEvents: measurement.scanned,
          windowTruncated: measurement.truncated,
        },
        totals,
        budgets: {
          maxToolCallsPerTurn: settings.maxToolCallsPerTurn,
          maxToolCallsTotal: settings.maxToolCallsTotal,
          maxIdenticalRepeats: settings.maxIdenticalRepeats,
          maxConsecutiveFailures: settings.maxConsecutiveFailures,
          warnRatio: settings.warnRatio,
          changeNote: 'budgets are preset configuration; the agent cannot widen them',
        },
        utilization: round(worst, 3),
        violations,
        lastError: state.lastError,
        perTool: state.perTool,
        tokenMeasurement,
        instruction:
          verdict === 'stop'
            ? 'Stop now: summarise what is verified, state what is blocked, and ask the user to take over. Do not retry the same action.'
            : verdict === 'warn'
              ? 'Approaching a limit: narrow the remaining plan to the single most informative next step.'
              : 'Within limits: continue, but keep each action tied to the reference goal.',
      }
    },
  })
}

/** Cut a string for display without throwing on undefined. */
function truncate(value, limit) {
  if (typeof value !== 'string') return String(value)
  return value.length > limit ? value.slice(0, limit) + '…' : value
}

/** Extract readable text from a tool-result message payload. */
function resultText(message) {
  if (!message || !Array.isArray(message.content)) return ''
  const parts = []
  for (const block of message.content) {
    if (block && block.type === 'text' && typeof block.text === 'string') parts.push(block.text)
  }
  return truncate(parts.join(' '), 240)
}

/**
 * Measure the calling session's durable tool history.
 *
 * Uses the synchronous session snapshot, which exists on every live Session.
 * When it is unavailable the guard degrades to an empty measurement and says so,
 * rather than inventing numbers.
 */
function measureSession(session) {
  const empty = {
    toolCalls: 0,
    currentTurn: null,
    currentTurnCalls: 0,
    consecutiveFailures: 0,
    maxIdenticalRepeat: 0,
    repeatedSignature: '',
    oscillations: 0,
    perTool: {},
    lastError: null,
  }
  if (!session || typeof session.snapshotEvents !== 'function') {
    return { state: empty, provenance: 'unavailable', source: 'no session snapshot API', scanned: 0, truncated: false }
  }

  let events
  try {
    const end = typeof session.seq === 'number' ? session.seq : undefined
    const start = end === undefined ? 0 : Math.max(0, end - DEFAULTS.scanWindow)
    events = session.snapshotEvents(start, end)
  } catch {
    return { state: empty, provenance: 'unavailable', source: 'session snapshot threw', scanned: 0, truncated: false }
  }

  const calls = []
  const results = []
  for (const event of events) {
    if (!event || typeof event.type !== 'string') continue
    if (event.type === 'tool/call') calls.push(event)
    else if (event.type === 'tool/result') results.push(event)
  }

  const perTool = {}
  const signatures = new Map()
  let maxIdenticalRepeat = 0
  let repeatedSignature = ''
  let currentTurn = null
  for (const event of calls) {
    const data = event.data ?? {}
    const tool = String(data.name ?? 'unknown')
    perTool[tool] = (perTool[tool] ?? 0) + 1
    if (typeof data.turn === 'number' && (currentTurn === null || data.turn > currentTurn)) currentTurn = data.turn
    const signature = tool + ' ' + truncate(stableStringify(data.arguments ?? null), 160)
    const count = (signatures.get(signature) ?? 0) + 1
    signatures.set(signature, count)
    if (count > maxIdenticalRepeat) {
      maxIdenticalRepeat = count
      repeatedSignature = signature
    }
  }

  const currentTurnCalls = currentTurn === null
    ? calls.length
    : calls.filter((event) => event.data?.turn === currentTurn).length

  let consecutiveFailures = 0
  let lastError = null
  for (let index = results.length - 1; index >= 0; index -= 1) {
    const data = results[index].data ?? {}
    const isError = data?.message?.isError === true
    if (!isError) break
    consecutiveFailures += 1
    if (lastError === null) lastError = resultText(data.message) || (data.error?.code ?? null)
  }

  const names = calls.map((event) => String(event.data?.name ?? ''))
  let oscillations = 0
  for (let index = 1; index < names.length; index += 1) {
    if (names[index] !== names[index - 1]) oscillations += 1
  }

  return {
    state: {
      toolCalls: calls.length,
      currentTurn,
      currentTurnCalls,
      consecutiveFailures,
      maxIdenticalRepeat,
      repeatedSignature,
      oscillations,
      perTool,
      lastError,
    },
    provenance: 'measured:session-log',
    source: 'session.snapshotEvents() tool/call + tool/result',
    scanned: events.length,
    truncated: events.length >= DEFAULTS.scanWindow,
  }
}
