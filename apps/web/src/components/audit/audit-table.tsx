import type { AuditEventOut } from "@xtrusio/api-types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import { roleLabel } from "./audit-format";

type Props = {
  events: AuditEventOut[];
  onSelect: (e: AuditEventOut) => void;
};

function truncate(value: string, head = 8): string {
  return value.length <= head + 1 ? value : `${value.slice(0, head)}…`;
}

export function AuditTable({ events, onSelect }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-44">Time</TableHead>
          <TableHead className="w-56">Actor</TableHead>
          <TableHead>Action</TableHead>
          <TableHead className="w-40">Role</TableHead>
          <TableHead className="w-28">Category</TableHead>
          <TableHead className="w-48">Target</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((e) => {
          const role = roleLabel(e);
          return (
            <TableRow key={e.id} className="cursor-pointer" onClick={() => onSelect(e)}>
              <TableCell className="text-xs text-muted-foreground">
                <time dateTime={e.created_at} title={new Date(e.created_at).toISOString()}>
                  {formatDateTime(e.created_at)}
                </time>
              </TableCell>
              <TableCell className="text-sm">{e.actor_email ?? "—"}</TableCell>
              <TableCell>
                <span className="text-sm font-medium">{e.action_label}</span>
                <span className="block font-mono text-[11px] text-muted-foreground">
                  {e.action}
                </span>
              </TableCell>
              <TableCell className="text-sm">{role ?? "—"}</TableCell>
              <TableCell>
                <Badge variant="secondary" className="capitalize">
                  {e.category}
                </Badge>
              </TableCell>
              <TableCell className="font-mono text-xs">
                <span title={e.target_id}>
                  {e.target_type}:{truncate(e.target_id)}
                </span>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
