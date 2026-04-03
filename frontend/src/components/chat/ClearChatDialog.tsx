import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ClearChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function ClearChatDialog({
  open,
  onOpenChange,
  onConfirm,
}: ClearChatDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-labelledby="clear-chat-title" aria-describedby="clear-chat-desc">
        <DialogHeader>
          <DialogTitle id="clear-chat-title">Clear Chat</DialogTitle>
          <DialogDescription id="clear-chat-desc">
            Are you sure you want to clear this conversation? This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm}>Clear Chat</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
