import { cn } from "@/lib/utils";

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      role="status"
      aria-label="Loading..."
      aria-hidden="false"
      {...props}
    />
  );
}

export { Skeleton };
