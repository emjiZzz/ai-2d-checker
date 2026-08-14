import { describe, it, expect } from 'vitest';
import { describeDrawingPairMismatch, isDrawingPairMismatch } from '../drawingIdentity';

/**
 * The TypeScript half of the pair guard. Mirrors `tests/test_drawing_identity.py` — the two
 * implementations must agree, because the backend decides what tokens exist and this decides
 * what they mean.
 */
describe('isDrawingPairMismatch', () => {
  it('accepts two revisions of the same drawing', () => {
    expect(isDrawingPairMismatch(['M7452A0N01'], ['M7452A0N01'])).toBe(false);
  });

  it('rejects two unrelated drawings', () => {
    // The reported case: Room 228 held M745228N01 against M745219N01.
    expect(isDrawingPairMismatch(['M745228N01'], ['M745219N01'])).toBe(true);
  });

  it('accepts a real pair even when one side carries extra shape-matching noise', () => {
    // M745227N01's reference genuinely carries a stray `C2801P`. The guard asks whether the
    // sheets share a number, never which token is the real one.
    expect(isDrawingPairMismatch(['C2801P', 'M745227N01'], ['M745227N01'])).toBe(false);
  });

  it.each([
    ['no tokens on the new side', [] as string[], ['M745203N01']],
    ['no tokens on the existing side', ['M745203N01'], [] as string[]],
    ['no tokens on either side', [] as string[], [] as string[]],
    ['field absent entirely (older drawing)', undefined, ['M745203N01']],
    ['field null', null, ['M745203N01']],
  ])('never reports a mismatch when evidence is absent: %s', (_label, a, b) => {
    // The load-bearing safety property: rejecting deletes a drawing the user just uploaded,
    // so "cannot judge" must always pass.
    expect(isDrawingPairMismatch(a as any, b as any)).toBe(false);
  });

  it('normalises case, so one number in two spellings is not two drawings', () => {
    expect(isDrawingPairMismatch(['m745203n01'], ['M745203N01'])).toBe(false);
  });
});

describe('describeDrawingPairMismatch', () => {
  it('names both drawing numbers and the file already in the room', () => {
    // "These are different drawings" is not actionable — the user needs to know which two,
    // and which slot holds the file they did not mean to upload.
    const msg = describeDrawingPairMismatch(['M745219N01'], ['M745228N01'], 'REFERENCE.DXF');

    expect(msg).toContain('M745219N01');
    expect(msg).toContain('M745228N01');
    expect(msg).toContain('REFERENCE.DXF');
  });
});
