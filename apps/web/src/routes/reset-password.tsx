import { createFileRoute } from "@tanstack/react-router";
import { ResetPasswordPage } from "@/components/reset-password-page";

export const Route = createFileRoute("/reset-password")({ component: ResetPasswordPage });
