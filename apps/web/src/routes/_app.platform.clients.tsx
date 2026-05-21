import { createFileRoute } from "@tanstack/react-router";
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
import { apiFetch } from "@/lib/api";
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
  component: ClientsRoute,
});

function ClientsRoute() {
  const { data, isLoading } = useQuery({
    queryKey: ["tenants"],
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
