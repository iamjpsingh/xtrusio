import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchPlatformSettings, putPlatformSettings } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/page-header";

export function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: qk.platformSettings(),
    queryFn: fetchPlatformSettings,
  });
  const m = useMutation({
    mutationFn: (v: boolean) => putPlatformSettings(v),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.platformSettings() }),
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform settings"
        description="Platform-wide toggles managed by super admins."
      />
      <section className="rounded-md border p-6">
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
            checked={data?.signups_enabled ?? false}
            onCheckedChange={(v) => m.mutate(v)}
            disabled={m.isPending}
          />
        </div>
      </section>
    </div>
  );
}
