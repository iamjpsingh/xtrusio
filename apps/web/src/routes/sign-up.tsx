import { createFileRoute } from "@tanstack/react-router";
import { SignUpPage } from "@/components/sign-up-page";

export const Route = createFileRoute("/sign-up")({ component: SignUpPage });
