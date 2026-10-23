/**
 * Host half of the π preset bundle.
 *
 * The preset itself is declared in `cordis.patch.yml`; this module exists so the
 * package exposes a resolvable root entry, and so an operator has one place to
 * see that the bundle intentionally contributes no process-wide plugin.
 */
export const name = 'pi-preset'

/** Intentionally empty: every π capability is scoped to the preset declaration. */
export function apply() {}
