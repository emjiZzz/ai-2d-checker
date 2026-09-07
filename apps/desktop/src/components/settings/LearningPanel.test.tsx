import { render, screen } from '@testing-library/react';
import { expect, test, vi, describe, beforeEach } from 'vitest';
import { LearningPanel, MIN_MEANINGFUL_LIFT } from './LearningPanel';

// An accuracy figure over an unbalanced corpus reads far stronger than it is, and this one is
// unbalanced: at 71 class-0 against 41 class-1, always answering "not a real change" scores
// 63.4%. A reported 73.3% is therefore about ten points of skill, not seventy-three — and a
// reader who does not know the split cannot tell those apart.
//
// The backend already enforces exactly this rule for retrieval, where every rate is printed
// beside `chance_recall_at_k` and a verdict is withheld unless the lift clears 0.15. The learning
// side reported a bare accuracy for months. These tests pin the fix on the surface a human
// actually reads.
//
// Why it matters here specifically: `inference._decide` flips a deterministic
// CHANGED/ADDED/REMOVED to MATCHED below LOW_THRESH, in drawing_views / notes_section /
// isometric_view only. A head that is barely beating the majority class in a 63%-negative corpus
// is suppressing findings, not filtering noise — the false-negative direction, in the system
// whose headline gap is that false negatives have never been measured.

vi.mock('../../services/auditsApi', () => ({
  getLearnedModelStatus: vi.fn(),
  retrainLearnedModel: vi.fn(),
}));

import { getLearnedModelStatus } from '../../services/auditsApi';

const baseStatus = {
  trained_at: '2026-08-17T07:22:50Z',
  n_total: 228,
  n_verdict: 112,
  n_category: 7,
  n_exact_overrides: 0,
  min_train: 40,
  verdict_ready: true,
  category_ready: false,
  metrics: {} as Record<string, unknown>,
};

const renderWith = async (metrics: Record<string, unknown>) => {
  (getLearnedModelStatus as any).mockResolvedValue({ ...baseStatus, metrics });
  render(<LearningPanel />);
  await screen.findByText(/Last trained/);
};

describe('LearningPanel accuracy reporting', () => {
  beforeEach(() => vi.clearAllMocks());

  test('the accuracy is never shown without its majority-class baseline', async () => {
    await renderWith({
      verdict_cv_accuracy: 0.7328,
      verdict_majority_baseline: 0.6339,
    });

    const line = screen.getByText(/CV accuracy/);
    expect(line.textContent).toContain('73.3%');
    expect(line.textContent).toContain('63.4%');
    // The lift is what a reader should take away, so it is rendered rather than left as
    // arithmetic between two percentages.
    expect(line.textContent).toContain('+9.9%');
  });

  test('a weak head says so, in the direction that matters', async () => {
    await renderWith({
      verdict_cv_accuracy: 0.7328,
      verdict_majority_baseline: 0.6339,
    });

    // 0.0989 lift, below MIN_MEANINGFUL_LIFT.
    expect(screen.getByText(/only 9\.9% better than always predicting/)).toBeTruthy();
    expect(screen.getByText(/suppresses findings rather than filtering noise/)).toBeTruthy();
  });

  test('a head that clearly beats the baseline draws no warning', async () => {
    await renderWith({
      verdict_cv_accuracy: 0.92,
      verdict_majority_baseline: 0.6339,
    });

    expect(screen.queryByText(/better than always predicting/)).toBeNull();
  });

  test('a bundle trained before the baseline existed shows the accuracy alone', async () => {
    // Graceful degradation, not a wrong comparison: `verdict_majority_baseline` landed
    // 2026-08-17, and every bundle trained before it has an accuracy and no floor. Inventing a
    // baseline for those would be worse than omitting it.
    await renderWith({ verdict_cv_accuracy: 0.7328 });

    const line = screen.getByText(/CV accuracy/);
    expect(line.textContent).toContain('73.3%');
    expect(line.textContent).not.toContain('baseline');
    expect(screen.queryByText(/better than always predicting/)).toBeNull();
  });

  test('a bundle with no metrics at all renders without an accuracy claim', async () => {
    await renderWith({});
    expect(screen.queryByText(/CV accuracy/)).toBeNull();
  });

  test('the lift threshold matches the backend convention', () => {
    // Hand-mirrored across the language boundary, like the comparison taxonomy: no runtime type
    // sharing exists between the two. `tests/test_learning_lift_threshold_consistency.py` parses
    // both files and fails if either side moves alone.
    expect(MIN_MEANINGFUL_LIFT).toBe(0.15);
  });
});
