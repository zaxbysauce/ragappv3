import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface APIKeySettingsProps {
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  onSave: () => void;
  isSaved?: boolean;
}

export function APIKeySettings({
  apiKey,
  onApiKeyChange,
  onSave,
  isSaved = false,
}: APIKeySettingsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>API Key</CardTitle>
        <CardDescription>Configure API key for authenticated requests</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">API Key</label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder="Enter your API key (if configured)"
          />
          <p className="text-xs text-muted-foreground">
            Optional. Set this if your server requires authentication. The key is stored in your browser&apos;s localStorage.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Button onClick={onSave}>
            Save API Key
          </Button>
          {isSaved && (
            <span className="text-sm text-success">Saved</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
