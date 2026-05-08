/**
 * Full-bleed aurora background for auth pages.
 *
 * Two layers:
 *   .aurora-curtain — flowing colour ribbons (Aceternity-style technique:
 *     two stacked repeating-linear-gradients, blurred, masked, animated
 *     via background-position over a 60s loop).
 *   .aurora-vignette — radial dark vignette so the card stays readable.
 *
 * Both styles live in globals.css scoped to `.aurora-bg`. Drop this as the
 * first child of an element with the `aurora-bg` class.
 */
export function AuroraBackground() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      <div className="aurora-curtain" />
      <div className="aurora-vignette" />
    </div>
  );
}
