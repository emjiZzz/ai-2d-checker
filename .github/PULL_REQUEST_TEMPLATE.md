## Description
<!-- Provide a clear description of the change, problem solved, or feature added. -->

## Associated Issue
Closes #<!-- Issue number here -->

## Type of Change
- [ ] Feature (non-breaking change adding functionality)
- [ ] Bug Fix (non-breaking change fixing an issue)
- [ ] Refactor (code cleanup, performance optimizations, no behavioral changes)
- [ ] Documentation (updates to READMEs, setup guides, ADRs)
- [ ] CI/CD or Build Pipeline adjustments

## Checklist
- [ ] Checked that code follows the standard naming conventions
- [ ] Python schemas match TypeScript API contract definitions in `packages/types/`
- [ ] All new logic has associated unit tests (Vitest / pytest)
- [ ] Tested the full stack locally (React app + Tauri shell + sidecar)
- [ ] Removed all transient debug statements (`print()`, `console.log`)
- [ ] Prettier formatting and ESLint checks pass locally
- [ ] Any added dependencies are documented and verified in package/requirements configurations
