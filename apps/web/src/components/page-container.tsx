import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

type PageContainerProps = {
  children: ReactNode;
  className?: string;
};

/**
 * The single post-login page-body container. Lives once per shell inside the
 * `<main>` element so every authed page gets the same max-width, horizontal
 * centring, and vertical rhythm without each page reinventing its own wrapper.
 *
 * - `max-w-screen-2xl` (1536px) keeps content from sprawling on ultra-wide
 *   displays while leaving tables plenty of room.
 * - `space-y-6` is the canonical gap between a page's `PageHeader` and its
 *   content, so individual pages render bare fragments and inherit the rhythm.
 *
 * Monochrome, tokens only — no colors here.
 */
export function PageContainer({ children, className }: PageContainerProps) {
  return (
    <div className={cn("mx-auto w-full max-w-screen-2xl space-y-6", className)}>{children}</div>
  );
}
