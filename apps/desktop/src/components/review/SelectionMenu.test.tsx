import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { SelectionMenu } from './SelectionMenu';
import { useWorkspaceStore } from '../../stores/workspaceStore';

vi.mock('../../stores/workspaceStore', async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    useWorkspaceStore: vi.fn(),
  };
});

describe('SelectionMenu positioning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockEntity = {
    drawingId: 'dwg1',
    side: 'ref' as const,
    entityId: 'e1',
    handle: '100',
    parentHandle: null,
    entityType: 'text',
    layer: '0',
    text: '6-9キリ',
    coordinates: [100, 200] as [number, number],
    zone: 'A1',
  };

  it('positions menu below the entity box when targetBounds are provided and room exists', () => {
    (useWorkspaceStore as any).mockImplementation((selector: any) =>
      selector({
        selectedEntities: [mockEntity],
        markings: [],
        pendingPairRef: null,
        pendingPairTool: 'changed',
        recordStamp: vi.fn(),
        selectionCounterpart: null,
      }),
    );

    const targetBounds = { x0: 100, y0: 150, x1: 200, y1: 180 };
    const { container } = render(
      <SelectionMenu
        x={150}
        y={165}
        targetBounds={targetBounds}
        canvasWidth={1000}
        canvasHeight={800}
        theme="hc-dark"
        onClose={vi.fn()}
      />,
    );

    const menuEl = container.firstChild as HTMLElement;
    expect(menuEl).toBeDefined();
    // y1 (180) + GAP (10) = 190px
    expect(menuEl.style.top).toBe('190px');
    // x0 = 100px
    expect(menuEl.style.left).toBe('100px');
  });

  it('flips menu above the entity when close to the bottom of the canvas', () => {
    (useWorkspaceStore as any).mockImplementation((selector: any) =>
      selector({
        selectedEntities: [mockEntity],
        markings: [],
        pendingPairRef: null,
        pendingPairTool: 'changed',
        recordStamp: vi.fn(),
        selectionCounterpart: null,
      }),
    );

    // Entity near bottom of canvasHeight 800: y0 = 700, y1 = 730
    const targetBounds = { x0: 100, y0: 700, x1: 200, y1: 730 };
    const { container } = render(
      <SelectionMenu
        x={150}
        y={715}
        targetBounds={targetBounds}
        canvasWidth={1000}
        canvasHeight={800}
        theme="hc-dark"
        onClose={vi.fn()}
      />,
    );

    const menuEl = container.firstChild as HTMLElement;
    expect(menuEl).toBeDefined();
    // Flipped above: top should be well below 700 (around y0 - 10 - 160 - 26 = 504px)
    const topPx = parseInt(menuEl.style.top, 10);
    expect(topPx).toBeLessThan(700);
    expect(topPx).toBeGreaterThan(450);
  });
});
