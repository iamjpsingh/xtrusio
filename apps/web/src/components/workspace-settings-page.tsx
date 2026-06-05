// apps/web/src/components/workspace-settings-page.tsx
// Workspace-scope settings page. P6d MVP exposes only `name` as mutable;
// `slug` and `created_at` are shown read-only below. View is gated by
// workspace.settings.read; edit is gated by workspace.settings.manage
// (the form inputs are disabled if the caller only has read access).
//
// On submit the page invalidates qk.workspaceSettings(wid) and shows a
// success toast. Inline form error for 422 / 403 / unknown via the
// shared error-messages mapping.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { errorCode, fetchWorkspaceSettings, updateWorkspaceSettings } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { formatDateTime } from "@/lib/format";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { ErrorState } from "@/components/error-state";
import { FormSkeleton } from "@/components/ui/page-skeleton";

export function WorkspaceSettingsPage({ workspaceId }: { workspaceId: string }) {
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.settings.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  const canManage = hasWorkspacePerm(me, workspaceId, "workspace.settings.manage");
  return <Body workspaceId={workspaceId} canManage={canManage} />;
}

function Body({ workspaceId, canManage }: { workspaceId: string; canManage: boolean }) {
  const qc = useQueryClient();
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: qk.workspaceSettings(workspaceId),
    queryFn: () => fetchWorkspaceSettings(workspaceId),
  });

  const [name, setName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // Mirror the server name into local state once the query resolves. This
  // means an external refetch won't blow away the user's pending edit.
  useEffect(() => {
    if (data) setName(data.name);
  }, [data]);

  const save = useMutation({
    mutationFn: (next: string) => updateWorkspaceSettings(workspaceId, { name: next }),
    onSuccess: async (row) => {
      await qc.invalidateQueries({ queryKey: qk.workspaceSettings(workspaceId) });
      setName(row.name);
      setFormError(null);
      toast.success("Settings saved");
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  if (isPending) {
    return (
      <>
        <PageHeader title="Workspace settings" description="Per-workspace configuration." />
        <FormSkeleton fields={3} />
      </>
    );
  }
  if (isError || !data) {
    return (
      <>
        <PageHeader title="Workspace settings" description="Per-workspace configuration." />
        <ErrorState
          title="We couldn't load this workspace"
          description="The workspace settings failed to load. Check your connection and try again."
          onRetry={() => void refetch()}
        />
      </>
    );
  }

  const trimmed = name.trim();
  const dirty = trimmed !== data.name;
  const canSubmit = canManage && dirty && trimmed.length > 0 && !save.isPending;

  return (
    <>
      <PageHeader
        title="Workspace settings"
        description="Per-workspace configuration. Only the name is editable in this release."
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!canSubmit) return;
          save.mutate(trimmed);
        }}
        className="max-w-xl space-y-6"
      >
        <div className="space-y-1.5">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={name}
            maxLength={200}
            required
            disabled={!canManage || save.isPending}
            onChange={(e) => setName(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Up to 200 characters. Displayed in the workspace switcher.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="slug">Slug</Label>
          <Input id="slug" value={data.slug} readOnly disabled />
          <p className="text-xs text-muted-foreground">
            The slug is part of the URL and can't be changed in this release.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="created-at">Created</Label>
          <Input id="created-at" value={formatDateTime(data.created_at)} readOnly disabled />
        </div>
        {formError ? (
          <p role="alert" className="text-sm text-destructive">
            {formError}
          </p>
        ) : null}
        <Button type="submit" disabled={!canSubmit}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </form>
    </>
  );
}
