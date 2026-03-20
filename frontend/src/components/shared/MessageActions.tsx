import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Copy, Check } from "lucide-react";
import { toast } from "sonner";

interface MessageActionsProps {
  content: string;
}

export const MessageActions = React.memo(function MessageActions({ content }: MessageActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      toast.success("Message copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      toast.error("Failed to copy message");
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity"
      onClick={handleCopy}
      aria-label={copied ? "Copied" : "Copy message"}
    >
      {copied ? (
        <Check className="w-4 h-4 text-green-500" />
      ) : (
        <Copy className="w-4 h-4" />
      )}
    </Button>
  );
});
