# Event Ticketing UI Brief

## Product direction

The customer and admin applications should feel like one dependable ticketing
product: calm, clear, and quick to understand. The visual language uses a
light neutral canvas, indigo/blue-violet brand accents, restrained elevation,
and purposeful feedback. Customer pages can use richer event imagery and
generous spacing; admin pages use the same tokens with a denser information
layout.

## Foundations

- Brand: indigo as the primary action color, blue-violet for secondary emphasis.
- Surfaces: warm-white page background, white cards, subtle slate borders.
- Semantic colors: green success, amber warning, red danger, blue information.
- Type: a readable system sans stack with a compact heading scale and relaxed
  body line-height.
- Shape: medium corner radius (never capsule-everything), light shadows only
  where hierarchy benefits from them.
- Motion: short transitions for feedback, dialogs, and state changes only.
  Every transition is disabled/reduced under `prefers-reduced-motion`.

## Layout

- Content max width is 72rem with responsive gutters.
- Customer shell prioritizes discovery, event imagery, and a simple booking
  path. Primary navigation collapses into a keyboard-accessible drawer.
- Admin shell prioritizes scanning: compact sidebar/header, tables, filters,
  and explicit status feedback.
- Focus rings are always visible for keyboard users and never rely on color
  alone to communicate state.

## Accessibility

Semantic HTML is preferred over generic containers. Form controls expose labels
and errors through `aria-describedby`; dialogs trap attention visually and can
be closed with Escape; menus and tabs expose their roles; all interactive
controls support keyboard focus and disabled/loading states. Status messages are
announced with polite live regions where appropriate.

## Component guidance

Use the shared primitives for all controls and feedback. Keep page-level color,
spacing, type, and z-index decisions in tokens rather than one-off values.
Avoid glassmorphism, neon, decorative gradients, emoji icons, and speculative
fake data. Service failures should be visible and actionable (retry, sign in,
or contact support), never disguised as an empty successful result.
