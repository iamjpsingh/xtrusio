import { createFileRoute } from "@tanstack/react-router";
import { OnboardingPage } from "@/components/onboarding-page";

export const Route = createFileRoute("/onboarding")({ component: OnboardingPage });
