import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { PermissionDef, PermissionScope } from "@xtrusio/api-types";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  catalog: PermissionDef[];
  scope: PermissionScope;
  value: string[];
  onChange: (next: string[]) => void;
};

type Category = { category: string; perms: PermissionDef[] };

/** Stable, deterministic category order — alphabetical by display name. */
function groupByCategory(perms: PermissionDef[]): Category[] {
  const map = new Map<string, PermissionDef[]>();
  for (const p of perms) {
    const list = map.get(p.category) ?? [];
    list.push(p);
    map.set(p.category, list);
  }
  return Array.from(map.entries())
    .map(([category, list]) => ({
      category,
      perms: [...list].sort((a, b) => a.key.localeCompare(b.key)),
    }))
    .sort((a, b) => a.category.localeCompare(b.category));
}

export function PermissionPicker({ catalog, scope, value, onChange }: Props) {
  const [query, setQuery] = useState("");

  const inScope = useMemo(() => catalog.filter((p) => p.scope === scope), [catalog, scope]);
  const selected = useMemo(() => new Set(value), [value]);

  const needle = query.trim().toLowerCase();
  const visible = useMemo(() => {
    if (needle === "") return inScope;
    return inScope.filter(
      (p) => p.key.toLowerCase().includes(needle) || p.description.toLowerCase().includes(needle),
    );
  }, [inScope, needle]);

  const categories = useMemo(() => groupByCategory(visible), [visible]);
  const totalSelected = useMemo(
    () => inScope.filter((p) => selected.has(p.key)).length,
    [inScope, selected],
  );
  const allKeys = useMemo(() => inScope.map((p) => p.key), [inScope]);
  const allSelected = allKeys.length > 0 && totalSelected === allKeys.length;

  function emit(next: Set<string>) {
    onChange(Array.from(next));
  }

  function toggle(key: string) {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    emit(next);
  }

  function toggleCategory(perms: PermissionDef[]) {
    const next = new Set(selected);
    const full = perms.every((p) => next.has(p.key));
    for (const p of perms) {
      if (full) next.delete(p.key);
      else next.add(p.key);
    }
    emit(next);
  }

  function toggleAll() {
    if (allSelected) {
      emit(new Set());
    } else {
      emit(new Set(allKeys));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-foreground">Permissions</span>
          <Badge variant="secondary">{totalSelected} selected</Badge>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={toggleAll}
          disabled={allKeys.length === 0}
        >
          {allSelected ? "Clear all" : "Select all"}
        </Button>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search permissions…"
          className="pl-8"
          aria-label="Search permissions"
        />
      </div>

      {categories.length === 0 ? (
        <p className="rounded-lg border border-dashed py-8 text-center text-sm text-muted-foreground">
          No permissions match “{query.trim()}”.
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {categories.map(({ category, perms }) => {
            const count = perms.filter((p) => selected.has(p.key)).length;
            const state: boolean | "indeterminate" =
              count === 0 ? false : count === perms.length ? true : "indeterminate";
            const headerId = `cat-${category.replace(/\s+/g, "-").toLowerCase()}`;
            return (
              <section key={category} className="flex flex-col overflow-hidden rounded-lg border">
                <header className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id={headerId}
                      checked={state}
                      onCheckedChange={() => toggleCategory(perms)}
                      aria-label={`Select all ${category}`}
                    />
                    <Label htmlFor={headerId} className="text-sm font-semibold tracking-tight">
                      {category}
                    </Label>
                  </div>
                  <Badge variant="outline" className="tabular-nums">
                    {count} / {perms.length}
                  </Badge>
                </header>
                <ul className="divide-y">
                  {perms.map((p) => {
                    const id = `perm-${p.key}`;
                    return (
                      <li key={p.key} className="flex items-start gap-3 px-3 py-2.5">
                        <Checkbox
                          id={id}
                          className="mt-0.5"
                          checked={selected.has(p.key)}
                          onCheckedChange={() => toggle(p.key)}
                          aria-label={p.key}
                        />
                        <div className="min-w-0 space-y-1">
                          <Label
                            htmlFor={id}
                            className="block text-sm leading-snug font-normal text-foreground"
                          >
                            {p.description}
                          </Label>
                          <code className="block truncate font-mono text-xs text-muted-foreground">
                            {p.key}
                          </code>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
