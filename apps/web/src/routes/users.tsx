import { createFileRoute } from "@tanstack/react-router";
import { Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/users")({
  component: UsersRoute,
});

function UsersRoute() {
  return (
    <>
      <PageHeader
        title="Platform users"
        description="Users with access to manage the platform itself."
      />
      <EmptyState
        icon={Users}
        title="No platform users yet"
        description="The first owner is bootstrapped via the `make create-platform-owner` CLI script. Subsequent platform users are invited from this page."
        action={{
          label: "Invite a user",
          onClick: () => {},
          disabled: true,
          reason: "Available in Plan 1E (user management)",
        }}
      />
    </>
  );
}
