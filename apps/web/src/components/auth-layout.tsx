import type { ReactNode } from "react";
import { motion } from "motion/react";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="dark flex min-h-screen flex-col items-center justify-between bg-background px-6 py-12">
      <div className="flex w-full max-w-[400px] flex-1 flex-col items-center justify-center">
        <motion.div
          className="mb-10 space-y-2 text-center"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <h1 className="text-4xl font-semibold tracking-tight text-foreground">Xtrusio</h1>
          <p className="text-sm text-muted-foreground">Multi-tenant AI workflows</p>
        </motion.div>

        <motion.div
          className="w-full rounded-2xl border border-foreground/10 bg-card p-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut", delay: 0.15 }}
        >
          <div className="mb-6 space-y-1.5 text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h2>
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          </div>
          {children}
          {footer && <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div>}
        </motion.div>
      </div>

      <motion.p
        className="text-xs font-medium text-muted-foreground/70"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.4 }}
      >
        {"Powered by Xtrusio"}
      </motion.p>
    </div>
  );
}
