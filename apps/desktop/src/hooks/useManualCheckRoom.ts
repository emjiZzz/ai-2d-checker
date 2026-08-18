import { useRoomStore } from '../stores/roomStore';

/**
 * Is the open room a manual engineer check?
 *
 * ## Why this is derived rather than stored
 *
 * The mode is a property of the **room**, chosen once at creation. Mirroring it into a
 * `reviewStore` flag would create a second copy that can disagree with the first — and the
 * disagreement would be silent and expensive in exactly one direction: an AI room that thinks
 * it is a manual check hides the engine's findings, and a manual room that thinks it is an AI
 * room *shows* them, which quietly destroys the independence that makes the markings worth
 * collecting at all.
 *
 * So there is one source of truth and no synchronisation to get wrong. This started life as a
 * `reviewStore` toggle beside the other view toggles; it was removed once the mode became a
 * room property, because the two could not both be authoritative.
 *
 * A room created before `room_mode` existed carries none, and was an AI comparison room. Absent
 * and `"ai_comparison"` mean the same thing, here and on the server.
 */
export function useIsManualCheckRoom(): boolean {
  return useRoomStore((s) => s.activeRoom?.room_mode === 'manual_check');
}
