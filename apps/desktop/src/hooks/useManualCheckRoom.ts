import { useRoomStore } from '../stores/roomStore';
import { isPrototypeMode } from '../config/features';

export function useIsManualCheckRoom(): boolean {
  if (isPrototypeMode()) {
    return true;
  }
  return useRoomStore((s) => s.activeRoom?.room_mode === 'manual_check');
}
