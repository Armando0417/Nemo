This folder contains the original cursor-follow magnifier lens extracted from the manga reader.

Files:
- `CursorMagnifierLens.svelte`: the circular lens UI and styling
- `magnifierMath.ts`: the positioning math used to place the lens and its zoomed background
- `index.ts`: convenience exports

Notes:
- This version preserves the original visual design from the reader.
- Cursor-follow lenses always have edge-case tradeoffs near image boundaries. The math here matches the original behavior rather than solving those UX issues.
- The current reader no longer uses this lens. It was extracted so you can copy or adapt it in another project.
