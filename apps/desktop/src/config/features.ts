/**
 * Feature flags and mode detection for KMTI 2D Checker.
 *
 * In Prototype Mode (`VITE_PROTOTYPE_MODE=true`):
 * - Login / Authentication screen is bypassed directly into 2D Workspace.
 * - 3D Workspace is hidden.
 * - History tab and audit session logs are hidden.
 * - AI Engine / Copilot LLM queries are hidden, focusing 100% on deterministic & physical CAD comparison.
 */

export const isPrototypeMode = (): boolean => {
  return import.meta.env.VITE_PROTOTYPE_MODE === "true" || import.meta.env.VITE_PROTOTYPE_MODE === true;
};

export const FEATURES = {
  get auth() {
    return !isPrototypeMode();
  },
  get threeDWorkspace() {
    return !isPrototypeMode();
  },
  get history() {
    return !isPrototypeMode();
  },
  get standards() {
    return !isPrototypeMode();
  },
  get aiEngine() {
    return !isPrototypeMode();
  },
  get copilot() {
    return !isPrototypeMode();
  },
  get rooms() {
    return true;
  }
};
