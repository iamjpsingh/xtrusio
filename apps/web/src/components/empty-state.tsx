import { type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

type Action = {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  reason?: string;
};

type EmptyStateProps = {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: Action;
};

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  const button = action ? (
    <Button onClick={action.onClick} disabled={action.disabled} className="mt-2">
      {action.label}
    </Button>
  ) : null;

  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-8 text-center">
      {Icon && (
        <div className="rounded-full bg-muted p-3">
          <Icon className="h-6 w-6 text-muted-foreground" />
        </div>
      )}
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      {action && action.disabled && action.reason ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="mt-2 inline-block">{button}</span>
            </TooltipTrigger>
            <TooltipContent>{action.reason}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        button
      )}
    </div>
  );
}
