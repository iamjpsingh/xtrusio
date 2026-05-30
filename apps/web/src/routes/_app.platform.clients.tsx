import { createFileRoute, redirect } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch, fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasPlatformPerm } from "@/lib/me-adapter";
import { CreateClientDialog } from "@/components/create-client-dialog";

type Tenant = {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  updated_at: string;
  created_by: string;
};

export const Route = createFileRoute("/_app/platform/clients")({
  beforeLoad: async () => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasPlatformPerm(me, "platform.clients.read")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: ClientsRoute,
});

function ClientsRoute() {
  const { data, isLoading } = useQuery({
    queryKey: qk.tenants(),
    queryFn: () => apiFetch<Tenant[]>("/api/tenants"),
  });

  const action = <CreateClientDialog trigger={<Button>Create client</Button>} />;

  if (isLoading) {
    return (
      <>
        <PageHeader
          title="Client tenants"
          description="Companies onboarded to the platform."
          action={action}
        />
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </>
    );
  }

  if (!data || data.length === 0) {
    return (
      <>
        <PageHeader
          title="Client tenants"
          description="Companies onboarded to the platform."
          action={action}
        />
        <EmptyState
          icon={Building2}
          title="No client tenants yet"
          description="Create your first one with the button above."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Client tenants"
        description="Companies onboarded to the platform."
        action={action}
      />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Slug</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((t) => (
            <TableRow key={t.id}>
              <TableCell className="font-medium">{t.name}</TableCell>
              <TableCell className="text-muted-foreground font-mono">{t.slug}</TableCell>
              <TableCell className="text-muted-foreground tabular-nums">
                {new Date(t.created_at).toLocaleDateString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}
