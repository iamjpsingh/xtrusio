import { useMemo } from "react";
import type { PermissionDef, PermissionScope } from "@xtrusio/api-types";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

type Props = {
  catalog: PermissionDef[];
  scope: PermissionScope;
  value: string[];
  onChange: (next: string[]) => void;
};

export function PermissionPicker({ catalog, scope, value, onChange }: Props) {
  const filtered = useMemo(
    () => catalog.filter((p) => p.scope === scope),
    [catalog, scope],
  );
  const byCategory = useMemo(() => {
    const map = new Map<string, PermissionDef[]>();
    for (const p of filtered) {
      const list = map.get(p.category) ?? [];
      list.push(p);
      map.set(p.category, list);
    }
    return Array.from(map.entries()).map(([category, perms]) => ({
      category,
      perms,
    }));
  }, [filtered]);

  const selected = useMemo(() => new Set(value), [value]);

  function toggle(key: string) {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(Array.from(next));
  }

  function selectAllForCategory(perms: PermissionDef[]) {
    const next = new Set(selected);
    for (const p of perms) next.add(p.key);
    onChange(Array.from(next));
  }

  return (
    <div className="space-y-6">
      {byCategory.map(({ category, perms }) => (
        <section key={category} className="space-y-2">
          <header className="flex items-center justify-between">
            <h3 className="text-sm font-medium tracking-tight">{category}</h3>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => selectAllForCategory(perms)}
              aria-label={`Select all ${category}`}
            >
              Select all
            </Button>
          </header>
          <ul className="space-y-2">
            {perms.map((p) => {
              const id = `perm-${p.key}`;
              return (
                <li key={p.key} className="flex items-start gap-3">
                  <Checkbox
                    id={id}
                    checked={selected.has(p.key)}
                    onCheckedChange={() => toggle(p.key)}
                    aria-label={p.key}
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor={id} className="font-mono text-xs">
                      {p.key}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {p.description}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
