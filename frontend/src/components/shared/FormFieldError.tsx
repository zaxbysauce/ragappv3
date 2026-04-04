import { AlertCircle } from "lucide-react";

interface FormFieldErrorProps {
  children?: React.ReactNode;
  id?: string;
}

export function FormFieldError({ children, id }: FormFieldErrorProps) {
  if (!children) return null;
  return (
    <p
      id={id}
      className="text-xs text-destructive mt-1 flex items-center gap-1"
      role="alert"
    >
      <AlertCircle className="h-3 w-3 flex-shrink-0" />
      {children}
    </p>
  );
}
