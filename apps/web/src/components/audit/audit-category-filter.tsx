import { useQuery } from "@tanstack/react-query";
import { fetchAuditCatalog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Radix Select reserves "" for the cleared state, so "all" is the sentinel for
// "no category filter" and maps to null at the boundary.
const ALL = "all";

type Props = {
  value: string | null;
  onChange: (category: string | null) => void;
};

export function AuditCategoryFilter({ value, onChange }: Props) {
  // Catalog is non-secret, identical for every caller, and small — cache it
  // forever for this session so the dropdown never refetches.
  const { data } = useQuery({
    queryKey: qk.auditCatalog(),
    queryFn: fetchAuditCatalog,
    staleTime: Infinity,
  });

  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? null : v)}>
      <SelectTrigger className="w-52" aria-label="Filter by category">
        <SelectValue placeholder="All categories" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All categories</SelectItem>
        {(data?.categories ?? []).map((c) => (
          <SelectItem key={c.key} value={c.key}>
            {c.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
