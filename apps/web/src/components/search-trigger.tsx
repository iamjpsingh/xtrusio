import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CommandDialog, CommandEmpty, CommandInput, CommandList } from "@/components/ui/command";

export function SearchTrigger() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="text-muted-foreground gap-2"
        onClick={() => setOpen(true)}
      >
        <Search className="h-4 w-4" />
        <span className="hidden md:inline">Search…</span>
        <kbd className="bg-muted text-muted-foreground hidden rounded px-1.5 py-0.5 text-xs md:inline">
          ⌘K
        </kbd>
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Search…" />
        <CommandList>
          <CommandEmpty>Search isn’t available yet.</CommandEmpty>
        </CommandList>
      </CommandDialog>
    </>
  );
}
