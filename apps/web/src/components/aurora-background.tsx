import { motion } from "motion/react";

/**
 * Full-bleed animated aurora background.
 *
 * Renders five soft, heavily-blurred colour blobs that slowly drift and
 * scale, plus a top vignette and bottom fade so content sits comfortably
 * on top. Colours come from --aurora-1..5 in globals.css (.aurora-bg
 * scope) — no inline hex.
 *
 * Drop this as the FIRST child of an element with the .aurora-bg class.
 * It positions itself absolutely and covers the full container.
 */
export function AuroraBackground() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      <motion.div
        className="absolute -left-[10%] -top-[10%] h-[55vmax] w-[55vmax] rounded-full opacity-60 blur-[100px]"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--aurora-1) / 0.7) 0%, transparent 60%)",
        }}
        animate={{
          x: [0, 60, -40, 0],
          y: [0, 40, -30, 0],
          scale: [1, 1.15, 0.95, 1],
        }}
        transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -right-[10%] -top-[15%] h-[50vmax] w-[50vmax] rounded-full opacity-55 blur-[100px]"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--aurora-3) / 0.7) 0%, transparent 60%)",
        }}
        animate={{
          x: [0, -50, 50, 0],
          y: [0, 50, 20, 0],
          scale: [1, 1.1, 1.05, 1],
        }}
        transition={{ duration: 26, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -bottom-[20%] -left-[15%] h-[55vmax] w-[55vmax] rounded-full opacity-50 blur-[110px]"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--aurora-2) / 0.65) 0%, transparent 60%)",
        }}
        animate={{
          x: [0, 80, -20, 0],
          y: [0, -40, 30, 0],
          scale: [1, 1.05, 1.15, 1],
        }}
        transition={{ duration: 30, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -bottom-[15%] -right-[15%] h-[50vmax] w-[50vmax] rounded-full opacity-50 blur-[100px]"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--aurora-4) / 0.6) 0%, transparent 60%)",
        }}
        animate={{
          x: [0, -60, 30, 0],
          y: [0, -30, 40, 0],
          scale: [1, 1.1, 0.95, 1],
        }}
        transition={{ duration: 28, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute left-[35%] top-[35%] h-[35vmax] w-[35vmax] rounded-full opacity-40 blur-[110px]"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--aurora-5) / 0.55) 0%, transparent 60%)",
        }}
        animate={{
          x: [0, 30, -30, 0],
          y: [0, -20, 20, 0],
          scale: [1, 1.2, 0.9, 1],
        }}
        transition={{ duration: 24, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Subtle dark vignette so the aurora doesn't fight the card */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 50%, transparent 0%, hsl(var(--background) / 0.35) 70%, hsl(var(--background) / 0.6) 100%)",
        }}
      />
    </div>
  );
}
