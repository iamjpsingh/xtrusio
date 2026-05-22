import { Button } from "@/components/ui/button";

type Props = {
  nextCursor: string | null;
  pending: boolean;
  onClick: () => void;
};

export function LoadMoreButton({ nextCursor, pending, onClick }: Props) {
  if (nextCursor === null) return null;
  return (
    <div className="mt-4 flex justify-center">
      <Button variant="outline" disabled={pending} onClick={onClick}>
        {pending ? "Loading…" : "Load more"}
      </Button>
    </div>
  );
}
