import type { AuditEventOut } from "@xtrusio/api-types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Props = {
  events: AuditEventOut[];
  onSelect: (e: AuditEventOut) => void;
};

function formatTime(iso: string): string {
  // Use the user's locale; keep it short. Stable across SSR/CSR is irrelevant
  // here because this is a CSR-only app.
  return new Date(iso).toLocaleString();
}

function truncate(value: string, head = 8): string {
  return value.length <= head + 1 ? value : `${value.slice(0, head)}…`;
}

export function AuditTable({ events, onSelect }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-44">Time</TableHead>
          <TableHead className="w-60">Actor</TableHead>
          <TableHead>Action</TableHead>
          <TableHead className="w-56">Target</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((e) => (
          <TableRow
            key={e.id}
            className="cursor-pointer"
            onClick={() => onSelect(e)}
          >
            <TableCell className="text-xs text-muted-foreground">
              <time
                dateTime={e.created_at}
                title={new Date(e.created_at).toISOString()}
              >
                {formatTime(e.created_at)}
              </time>
            </TableCell>
            <TableCell className="text-sm">{e.actor_email ?? "—"}</TableCell>
            <TableCell className="font-mono text-xs">{e.action}</TableCell>
            <TableCell className="font-mono text-xs">
              <span title={e.target_id}>
                {e.target_type}:{truncate(e.target_id)}
              </span>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
