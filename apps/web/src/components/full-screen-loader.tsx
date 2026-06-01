import { motion } from "motion/react";

/**
 * Branded full-screen loading state for the auth gate. Centered wordmark over
 * a subtle pulsing track — monochrome, tokens only — so the pre-auth moment
 * reads as an intentional product splash, not a bare "Loading…" string.
 */
export function FullScreenLoader() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="grid min-h-screen place-items-center bg-background px-6"
    >
      <motion.div
        className="flex flex-col items-center gap-5"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
      >
        <span className="text-2xl font-semibold tracking-tight text-foreground">Xtrusio</span>
        <div className="h-1 w-32 overflow-hidden rounded-full bg-muted">
          <motion.div
            className="h-full w-1/2 rounded-full bg-muted-foreground/50"
            animate={{ x: ["-100%", "200%"] }}
            transition={{ duration: 1.1, ease: "easeInOut", repeat: Infinity }}
          />
        </div>
      </motion.div>
    </div>
  );
}
