import { createFileRoute } from "@tanstack/react-router";
import { AcceptInvitePage } from "@/components/accept-invite-page";

export const Route = createFileRoute("/accept-invite")({ component: AcceptInvitePage });
