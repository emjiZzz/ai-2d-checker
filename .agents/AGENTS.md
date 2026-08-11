# Workspace Behavioral Guidelines & Technical Rules

## FlexLayout React (>= 0.9.0) Splitter Sizing Rule
- `global.splitterSize` and `global.splitterExtra` in FlexLayout JSON models are deprecated and ignored in `flexlayout-react` >= 0.9.0.
- FlexLayout >= 0.9.0 measures splitter dimensions via CSS variables on `.flexlayout__layout`:
  - `--splitter-size`: Visible bar thickness (e.g., `--splitter-size: 1px !important`).
  - `--splitter-active-size`: Invisible drag hit area (e.g., `--splitter-active-size: 9px !important`).
- Never attempt to set `splitterSize` in JSON model `globalOpts` or mutate `parsed.global.splitterSize`. Control splitter thickness exclusively via `--splitter-size` in `index.css`.
