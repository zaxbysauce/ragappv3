import { cn } from "@/lib/utils";

interface SectionHeadingProps {
  children: React.ReactNode;
  size?: "xs" | "sm";
  className?: string;
}

const sizeClasses = {
  xs: "text-xs",
  sm: "text-sm",
} as const;

export function SectionHeading({
  children,
  size = "xs",
  className,
}: SectionHeadingProps) {
  return (
    <p
      className={cn(
        "font-semibold uppercase tracking-wide text-muted-foreground",
        sizeClasses[size],
        className
      )}
    >
      {children}
    </p>
  );
}
