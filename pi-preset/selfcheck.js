/**
 * π self-check: the last row of the preset's composition.
 *
 * Preset registration mounts its child rows in order and rejects the whole
 * mount when any row fails to import or activate. Placing this module last
 * therefore turns its activation into evidence: if it ran, every row before it
 * mounted. It appends one JSON line to the configured journal so the
 * composition's activation and retirement stay auditable after the fact.
 *
 * Diagnostics must never break the preset, so every filesystem failure is
 * swallowed. Without `journalPath` the module is a no-op beyond its ordering.
 */
import { appendFileSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'

export const name = 'pi-selfcheck'

export function apply(ctx, config) {
  const journal = typeof config?.journalPath === 'string' ? config.journalPath : ''

  const record = (event, extra = {}) => {
    if (journal.length === 0) return
    try {
      mkdirSync(dirname(journal), { recursive: true })
      const line = JSON.stringify({
        at: new Date().toISOString(),
        event,
        preset: 'pi',
        module: name,
        pid: process.pid,
        node: process.versions.node,
        ...extra,
      })
      appendFileSync(journal, line + '\n', 'utf8')
    } catch {
      // A journal is a convenience, never a dependency of the composition.
    }
  }

  // Which pi_* tools this scope can see, when the registry exposes that view.
  let visiblePiTools = null
  try {
    const tools = ctx.get?.('tools')
    if (tools && typeof tools.schemas === 'function') {
      visiblePiTools = tools
        .schemas()
        .map((entry) => entry.name)
        .filter((toolName) => typeof toolName === 'string' && toolName.startsWith('pi_'))
    }
  } catch {
    visiblePiTools = null
  }

  record('activated', { visiblePiTools })

  try {
    ctx.on('dispose', () => record('disposed'))
  } catch {
    // Older Loader revisions may not expose a dispose event; activation still holds.
  }
}
