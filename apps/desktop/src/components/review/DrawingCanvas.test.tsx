import { render, screen } from '@testing-library/react';
import { expect, test, vi, describe, beforeEach } from 'vitest';
import { DrawingCanvas } from './DrawingCanvas';

// 1. Mock Zustand stores since we only want to test the component
const mockReviewState = {
  viewport: { x: 0, y: 0, scale: 1 },
  showMarkerLabels: true,
  toggleMarkerLabels: vi.fn(),
};

vi.mock('../../stores/reviewStore', () => {
  const mockFn: any = vi.fn(() => mockReviewState);
  mockFn.getState = () => mockReviewState;
  mockFn.subscribe = vi.fn(() => () => {});
  return {
    useReviewStore: mockFn,
  };
});

const mockWorkspaceState = {
  oldDrawing: null,
  newDrawing: null,
  // Annotation-pin state. This stub returns the whole object for every
  // selector, so array-typed fields must exist or the annotation effects in
  // useCanvasInteraction blow up on undefined.
  annotations: [],
  selectedAnnotationId: null,
  isPlacingAnnotation: false,
  pendingAnnotationText: "",
};

vi.mock('../../stores/workspaceStore', () => {
  const mockFn: any = vi.fn(() => mockWorkspaceState);
  mockFn.getState = () => mockWorkspaceState;
  mockFn.subscribe = vi.fn(() => () => {});
  return {
    useWorkspaceStore: mockFn,
  };
});

vi.mock('../../stores/themeStore', () => ({
  useThemeStore: vi.fn(() => ({
    theme: 'hc-dark',
  })),
}));

// 2. Mock CanvasRenderer since testing actual WebGL/Canvas2D via jsdom is notoriously flaky
vi.mock('./CanvasRenderer', () => {
  const mockRender = (props: any) => {
    // If props.layers triggers an error simulation:
    if (props.layers && props.layers['error_layer']) {
      throw new Error('Simulated CanvasRenderer Crash');
    }
    // JSX runtime is automatic, so no React import needed here
    return <div data-testid="mock-canvas-renderer" />;
  };

  return {
    CanvasRenderer: Object.assign(mockRender, {
      $$typeof: Symbol.for('react.forward_ref'),
      render: mockRender,
    }),
  };
});

describe('DrawingCanvas Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders successfully with empty layers', () => {
    render(
      <DrawingCanvas
        layers={{}}
        width={800}
        height={600}
        drawing={{ id: 'test-drawing', file_name: 'test.pdf' }}
      />
    );
    expect(screen.getByTestId('mock-canvas-renderer')).toBeInTheDocument();
  });

  test('gracefully filters out malformed Zod layer data', () => {
    const malformedLayers = {
      good_layer: [
        { id: '1', type: 'line', geometry: {}, style: {} },
      ],
      bad_layer: [
        { id: '2', type: 'line' }, // Missing geometry and style, will fail Zod
      ],
    };

    render(
      <DrawingCanvas
        layers={malformedLayers as any}
        width={800}
        height={600}
        drawing={{ id: 'test-drawing', file_name: 'test.pdf' }}
      />
    );

    // Should still render without completely crashing the component
    expect(screen.getByTestId('mock-canvas-renderer')).toBeInTheDocument();
  });

  test('ErrorBoundary catches CanvasRenderer crashes and shows fallback UI', () => {
    // Suppress React's default console.error dumping during expected throws
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <DrawingCanvas
        layers={{ error_layer: [] }}
        width={800}
        height={600}
        drawing={{ id: 'crash-drawing', file_name: 'crash.pdf' }}
      />
    );

    expect(screen.getByText('Rendering Engine Crashed')).toBeInTheDocument();
    expect(screen.getByText('Simulated CanvasRenderer Crash')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reset Renderer/i })).toBeInTheDocument();

    consoleSpy.mockRestore();
  });
});
