import { render, screen } from '@testing-library/react';
import { expect, test, describe } from 'vitest';
import { StaleExtractionBadge } from './StaleExtractionBadge';
import type { DrawingItem } from '../../stores/workspace/types';

/**
 * The property worth pinning is the SILENCE, not the warning.
 *
 * 36 of 55 stored drawings were stale when this was written, so a badge that renders anything
 * in the healthy case would be lit on two-thirds of the estate — and an always-on warning is
 * one people stop seeing. The healthy state has to be invisible for the unhealthy state to
 * mean anything, and "renders nothing" is exactly the assertion nobody makes by hand.
 */

function drawing(over: Partial<DrawingItem> = {}): DrawingItem {
  return {
    id: 'd1',
    file_name: 'M7452A0N01_reference.dxf',
    file_path: '/storage/uploads/d1.dxf',
    format: 'dxf',
    entity_counts: {},
    metadata: {},
    created_at: '2026-08-20T00:00:00Z',
    ...over,
  };
}

describe('StaleExtractionBadge', () => {
  test('renders nothing when the drawing is current', () => {
    const { container } = render(
      <StaleExtractionBadge
        drawing={drawing({
          extraction_is_stale: false,
          extraction_schema_version: 7,
          current_extraction_schema_version: 7,
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  test('renders nothing when the backend never sent the flag', () => {
    // A backend predating these fields sends no judgement at all. Absent is not the same claim
    // as stale, and manufacturing a warning out of missing data is how a badge loses its
    // credibility — the first false alarm is the one that teaches people to ignore it.
    const { container } = render(<StaleExtractionBadge drawing={drawing()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test('renders nothing without a drawing', () => {
    const { container } = render(<StaleExtractionBadge drawing={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  test('warns, and names both versions, when the drawing is stale', () => {
    render(
      <StaleExtractionBadge
        drawing={drawing({
          extraction_is_stale: true,
          extraction_schema_version: 2,
          current_extraction_schema_version: 7,
        })}
      />,
    );
    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.getByText(/v2 of v7/)).toBeTruthy();
    // The copy has to say what is wrong with the picture, not merely that a number is old.
    expect(screen.getByText(/may draw incorrectly/i)).toBeTruthy();
  });

  test('labels which side is stale when both are shown', () => {
    render(
      <StaleExtractionBadge
        drawing={drawing({
          extraction_is_stale: true,
          extraction_schema_version: 5,
          current_extraction_schema_version: 7,
        })}
        label="Reference"
      />,
    );
    expect(screen.getByText(/Reference: outdated extraction/i)).toBeTruthy();
  });

  test('still warns when the stored version is unknown', () => {
    // A never-stamped row deserializes to 0. It is stale, but "v0" would read as a real
    // version the schema once had, so it is shown as unknown instead.
    render(
      <StaleExtractionBadge
        drawing={drawing({
          extraction_is_stale: true,
          extraction_schema_version: 0,
          current_extraction_schema_version: 7,
        })}
      />,
    );
    expect(screen.getByText(/v\? of v7/)).toBeTruthy();
  });
});
