import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchPlatformSettings, putPlatformSettings } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/page-header";
import { ErrorState } from "@/components/error-state";
import { FormSkeleton } from "@/components/ui/page-skeleton";

export function SettingsPage() {
  const qc = useQueryClient();
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: qk.platformSettings(),
    queryFn: fetchPlatformSettings,
  });
  const m = useMutation({
    mutationFn: (v: boolean) => putPlatformSettings(v),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.platformSettings() }),
  });

  const header = (
    <PageHeader
      title="Platform settings"
      description="Platform-wide toggles managed by super admins."
    />
  );

  if (isPending) {
    return (
      <>
        {header}
        <FormSkeleton fields={1} />
      </>
    );
  }

  if (isError) {
    return (
      <>
        {header}
        <ErrorState onRetry={() => void refetch()} />
      </>
    );
  }

  return (
    <>
      {header}
      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center justify-between gap-6">
          <div>
            <Label htmlFor="signups" className="text-base font-medium">
              Public client signup
            </Label>
            <p className="text-sm text-muted-foreground">
              Allow anyone to create a new client workspace via the public sign-up page.
            </p>
          </div>
          <Switch
            id="signups"
            checked={data.signups_enabled}
            onCheckedChange={(v) => m.mutate(v)}
            disabled={m.isPending}
          />
        </div>
      </section>
    </>
  );
}
