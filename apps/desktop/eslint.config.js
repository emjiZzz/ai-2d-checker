import tseslint from "typescript-eslint";

// Guards against the recurring bug pattern found across three review rounds:
// page/component code reaching directly into useWorkspaceStore.setState()
// instead of going through a named action defined in stores/workspace/slices/*.
// Direct setState calls bypass whatever invariants an action is meant to
// enforce (e.g. loadSessionIntoWorkspace keeping drawing/violation/audit-status
// writes atomic) and make store mutations hard to trace from the store file
// alone. See frontend-remediation-plan.md, Phase 8.
//
// Deliberately scoped to ONLY this rule — not js.configs.recommended or
// tseslint.configs.recommended. Turning on full recommended rule sets on a
// codebase with no prior linting history surfaces thousands of pre-existing,
// unrelated issues (unused vars, `any` usage, etc.) that are a separate,
// much larger effort than this targeted regression guard. If/when you want
// to adopt broader linting, do it as its own deliberate phase with a
// baseline/ignore pass, not bundled in here.
export default tseslint.config({
  files: ["src/**/*.{ts,tsx}"],
  ignores: ["src/stores/workspace/**"],
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: {
      ecmaFeatures: { jsx: true },
    },
  },
  rules: {
    "no-restricted-syntax": [
      "error",
      {
        selector:
          "CallExpression[callee.object.name='useWorkspaceStore'][callee.property.name='setState']",
        message:
          "Do not call useWorkspaceStore.setState() directly outside the store definition. " +
          "Add or use a named action in src/stores/workspace/slices/* instead. " +
          "If this is deliberate demo/seed data (not production data flow), " +
          "disable this rule on the line with a comment explaining why.",
      },
    ],
  },
});
