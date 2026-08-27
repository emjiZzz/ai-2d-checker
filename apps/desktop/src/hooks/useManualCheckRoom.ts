import { useRoomStore } from '../stores/roomStore';
import { isPrototypeMode } from '../config/features';

/**
 * True when the active room collects an engineer's own markings and no engine runs.
 *
 * ⚠ **In a prototype build this is unconditionally true**, which is what makes prototype mode a
 * ground-truth collection build rather than a comparison one — see `config/features.ts`. Every
 * consumer inherits that: `TwoDLeftPanel` swaps the comparison panel for `ManualMarkingList`,
 * `CanvasRenderer` suppresses engine markers, `CanvasContextMenu` offers marking actions.
 *
 * ⚠ **The store subscription is unconditional on purpose.** This read the flag first and returned
 * before `useRoomStore(...)`, which is a conditional hook call — inert today only because Vite
 * folds the flag to a build-time constant, so the hook order cannot actually vary between renders.
 * `eslint-plugin-react-hooks` is not installed here, so nothing would have caught it if the flag
 * ever became runtime state. Subscribing first and overriding after costs one store read in a
 * build that ignores the value, and removes the trap.
 */
export function useIsManualCheckRoom(): boolean {
  const isManualCheckRoom = useRoomStore((s) => s.activeRoom?.room_mode === 'manual_check');
  return isPrototypeMode() || isManualCheckRoom;
}
