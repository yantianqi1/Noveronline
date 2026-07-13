# Editorial design system

## Contents

1. Visual direction
2. Color and typography
3. Layout and surfaces
4. Motion and feedback
5. Accessibility
6. Anti-patterns

## Visual direction

Aim for a modern Agent-first editorial workspace: calm, tactile, precise, and suitable for long sessions. The task thread carries the interaction emphasis; manuscript and planning artifacts remain stable, readable, and visually distinct.

Use [../assets/editorial-tokens.css](../assets/editorial-tokens.css) only when the project lacks coherent tokens. Map its semantic variables into the existing theme rather than duplicating color systems.

## Color and typography

- Prefer warm neutral paper and ink over pure white/black.
- Use one restrained accent such as teal, indigo, oxblood, or ochre.
- Reserve green, amber, red, and blue for semantic success, waiting, danger, and information.
- Meet WCAG AA contrast for normal text and interactive controls.
- Use a serif for manuscript prose and a sans-serif for interface controls when language coverage is verified.
- Prefer openly licensed font families such as Noto Serif/Sans CJK or system fonts; confirm the font license before bundling files.
- Target prose at `16–19px`, line height `1.65–1.85`, and measure `65–78ch`.
- Use tabular numerals for word counts, times, and token/usage data.

## Layout and surfaces

- Use a 4px spacing base with common steps `4, 8, 12, 16, 24, 32, 48`.
- Use compact radii (`6–12px`) and modest borders. Reserve large radii for drawers or intentional feature surfaces.
- Prefer one elevation level plus overlays. Avoid a separate shadow on every card.
- Separate navigation, the primary thread, and artifact modes with dividers and tabs before adding containers.
- Keep the editor background and outer application background subtly distinct.
- Keep important actions in stable positions. Streaming content must not push cancel, approve, or accept controls out of reach.
- Use density controls only for lists/timelines, not to shrink manuscript typography.

## Motion and feedback

- Use `120–160ms` for hover/press feedback and `180–220ms` for drawers or mode transitions.
- Animate opacity and transform; avoid expensive layout animation on long prose.
- Respect `prefers-reduced-motion` and keep progress understandable without animation.
- Stream text in buffered chunks rather than character-by-character flicker.
- Preserve scroll position unless the user is already near the end. Provide “jump to latest” for new agent events.
- Show autosave as unobtrusive text/icon state: saving, saved, offline, conflict.
- Use optimistic feedback only for reversible local actions; reconcile with authoritative server state.

## Accessibility

- Provide visible focus treatment and logical tab order.
- Use semantic landmarks for navigation, the main Agent thread, the artifact workspace, and status.
- Announce run state changes through a polite live region; do not announce every token or event.
- Pair color with icon/text for every status.
- Make diff additions/deletions understandable to screen readers.
- Provide keyboard commands for send, cancel, search, command palette, accept, reject, and panel navigation, while avoiding conflicts with editor shortcuts.
- Keep pointer targets at least `40px`; provide labels/tooltips for icon-only controls.

## Anti-patterns

Reject or revise these patterns unless explicitly required by the product language:

- generic KPI cards on a writing screen;
- large gradient hero areas inside the app;
- glass panels over low-contrast backgrounds;
- purple/blue “AI glow” as the only sign of intelligence;
- emoji as permanent navigation icons;
- excessive pill containers and rounded chat bubbles;
- a full-screen chat feed with the manuscript embedded in messages;
- raw JSON tool calls shown by default;
- fake streaming, fake progress percentages, or endlessly rotating loaders;
- hiding errors in toasts with no persistent recovery action;
- hover-only controls needed for critical work;
- tiny grey metadata that fails contrast or readability.
