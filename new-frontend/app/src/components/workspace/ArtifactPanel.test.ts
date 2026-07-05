import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { variantForMode } from './ArtifactPanel';
import type { WorkspaceMode } from '../../types';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** The four workspace modes the ArtifactPanel can render. */
const ALL_MODES: WorkspaceMode[] = ['sources', 'prepare', 'visualize', 'publish'];

const modeArb: fc.Arbitrary<WorkspaceMode> = fc.constantFrom<WorkspaceMode>(...ALL_MODES);

/** The single variant each mode is expected to map to (by header title). */
const EXPECTED_TITLE: Record<WorkspaceMode, string> = {
  sources: 'Sources',
  prepare: 'Prepare',
  visualize: 'Visualize',
  publish: 'Publish',
};

// ---------------------------------------------------------------------------
// Property 8: Panel/mode consistency
// Validates: Requirements 4.1
//
// The ArtifactPanel renders exactly ONE variant for the active WorkspaceMode.
// `variantForMode` is the pure selector that drives that rendering, so the
// property reduces to: the mode → variant mapping is (1) total - defined for
// every mode, (2) deterministic - equal input yields equal output, (3) a
// single well-formed variant per mode, and (4) injective - each mode maps to a
// distinct variant. Together these guarantee the panel can only ever show one
// variant and that it matches the active mode.
// ---------------------------------------------------------------------------
describe('Property 8: Panel/mode consistency', () => {
  it('maps every mode to exactly one well-formed variant', () => {
    fc.assert(
      fc.property(modeArb, (mode) => {
        const variant = variantForMode(mode);

        // Total: a variant exists for every mode.
        expect(variant).toBeDefined();
        // Exactly one variant object with a single Component, title and icon.
        expect(typeof variant.Component).toBe('object'); // React.lazy → object
        expect(typeof variant.title).toBe('string');
        expect(variant.title.length).toBeGreaterThan(0);
        expect(variant.icon).toBeDefined();

        // The single variant rendered matches the active mode.
        expect(variant.title).toBe(EXPECTED_TITLE[mode]);
      }),
    );
  });

  it('is deterministic - the same mode always selects the same variant', () => {
    fc.assert(
      fc.property(modeArb, (mode) => {
        const a = variantForMode(mode);
        const b = variantForMode(mode);
        // Reference-stable: not just equal, the very same variant instance.
        expect(a.Component).toBe(b.Component);
        expect(a.title).toBe(b.title);
        expect(a.icon).toBe(b.icon);
      }),
    );
  });

  it('is injective - distinct modes never share a variant', () => {
    fc.assert(
      fc.property(modeArb, modeArb, (m1, m2) => {
        const v1 = variantForMode(m1);
        const v2 = variantForMode(m2);
        if (m1 === m2) {
          expect(v1.Component).toBe(v2.Component);
        } else {
          // Different modes resolve to different components AND titles, so no
          // two modes can ever render the same variant.
          expect(v1.Component).not.toBe(v2.Component);
          expect(v1.title).not.toBe(v2.title);
        }
      }),
    );
  });

  it('covers the entire mode domain with distinct variants (total + injective)', () => {
    const variants = ALL_MODES.map(variantForMode);
    // One variant per mode (total).
    expect(variants).toHaveLength(ALL_MODES.length);
    // All distinct components and titles (injective ⇒ exactly one per mode).
    const components = new Set(variants.map((v) => v.Component));
    const titles = new Set(variants.map((v) => v.title));
    expect(components.size).toBe(ALL_MODES.length);
    expect(titles.size).toBe(ALL_MODES.length);
  });
});
