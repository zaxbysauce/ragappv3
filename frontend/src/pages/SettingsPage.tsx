import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2 } from "lucide-react";
import { getSettings, updateSettings, testConnections } from "@/lib/api";
import type { ConnectionTestResult } from "@/lib/api";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { ConnectionStatusBadges } from "@/components/shared/ConnectionStatusBadges";
import type { HealthStatus } from "@/types/health";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { APIKeySettings } from "@/components/settings/APIKeySettings";
import { ConnectionSettings } from "@/components/settings/ConnectionSettings";
import { DocumentProcessingSettings } from "@/components/settings/DocumentProcessingSettings";
import { ModelConnectionSettings } from "@/components/settings/ModelConnectionSettings";
import { RAGSettings } from "@/components/settings/RAGSettings";
import { RetrievalSettings } from "@/components/settings/RetrievalSettings";
import type { SettingsFormData } from "@/stores/useSettingsStore";

// Internal component that renders the settings form
function SettingsPageContent() {
  const {
    settings,
    formData,
    loading,
    saving,
    error,
    errors,
    setSettings,
    initializeForm,
    setLoading,
    setSaving,
    setError,
    updateFormField,
    validateForm,
    hasChanges,
  } = useSettingsStore();

  const [apiKey, setApiKey] = useState(() => {
    try {
      return localStorage.getItem("kv_api_key") || "";
    } catch {
      return "";
    }
  });
  const [apiKeySaved, setApiKeySaved] = useState(false);

  const handleApiKeySave = () => {
    try {
      localStorage.setItem("kv_api_key", apiKey);
      setApiKeySaved(true);
      toast.success("API key saved");
      setTimeout(() => setApiKeySaved(false), 2000);
    } catch (err) {
      toast.error("Failed to save API key");
    }
  };

  useEffect(() => {
    let mounted = true;
    getSettings()
      .then((data) => {
        if (mounted) {
          setSettings(data);
          initializeForm(data);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load settings");
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [setSettings, initializeForm, setError, setLoading]);

  // Fields that should be parsed as numbers
  const numericFields: Set<keyof SettingsFormData> = new Set([
    'chunk_size_chars',
    'chunk_overlap_chars',
    'retrieval_top_k',
    'auto_scan_interval_minutes',
    'max_distance_threshold',
    'retrieval_window',
    'embedding_batch_size',
    'hybrid_alpha',
    'initial_retrieval_top_k',
    'reranker_top_n',
  ]);

const handleInputChange = (field: keyof SettingsFormData, value: string | boolean | number) => {
  if (typeof value === "boolean") {
    updateFormField(field, value);
  } else if (typeof value === "string") {
    if (value === "") {
      // Empty string: for numeric fields, set to 0; for string fields, keep as empty string
      if (numericFields.has(field)) {
        updateFormField(field, 0);
      } else {
        updateFormField(field as any, value);
      }
    } else if (numericFields.has(field)) {
      const numValue = parseFloat(value);
      if (!isNaN(numValue)) {
        updateFormField(field, numValue);
      }
    } else {
      // String field - keep as string
      updateFormField(field, value);
    }
  } else {
    // number
    updateFormField(field, value);
  }
};

  const handleSave = async () => {
    if (!validateForm()) {
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const updated = await updateSettings({
        chunk_size_chars: formData.chunk_size_chars,
        chunk_overlap_chars: formData.chunk_overlap_chars,
        retrieval_top_k: formData.retrieval_top_k,
        max_distance_threshold: formData.max_distance_threshold,
        auto_scan_enabled: formData.auto_scan_enabled,
        auto_scan_interval_minutes: formData.auto_scan_interval_minutes,
        retrieval_window: formData.retrieval_window,
        vector_metric: formData.vector_metric,
        embedding_doc_prefix: formData.embedding_doc_prefix,
        embedding_query_prefix: formData.embedding_query_prefix,
        embedding_batch_size: formData.embedding_batch_size,
        // New retrieval settings
        reranking_enabled: formData.reranking_enabled,
        reranker_url: formData.reranker_url,
        reranker_model: formData.reranker_model,
        initial_retrieval_top_k: formData.initial_retrieval_top_k,
        reranker_top_n: formData.reranker_top_n,
        hybrid_search_enabled: formData.hybrid_search_enabled,
        hybrid_alpha: formData.hybrid_alpha,
        // Model connection settings
        ollama_embedding_url: formData.ollama_embedding_url,
        ollama_chat_url: formData.ollama_chat_url,
        embedding_model: formData.embedding_model,
        chat_model: formData.chat_model,
      });
      setSettings(updated);
      toast.success("Settings saved successfully");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
      toast.error(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {loading && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-[180px]" />
              <Skeleton className="h-4 w-[250px]" />
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Skeleton className="h-4 w-[100px]" />
                <Skeleton className="h-10 w-full" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-4 w-[120px]" />
                <Skeleton className="h-10 w-full" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-[150px]" />
              <Skeleton className="h-4 w-[200px]" />
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Skeleton className="h-4 w-[80px]" />
                <Skeleton className="h-10 w-full" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-4 w-[100px]" />
                <Skeleton className="h-10 w-full" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-4 w-[140px]" />
                <div className="flex items-center gap-4">
                  <Skeleton className="h-10 w-24" />
                  <Skeleton className="h-2 flex-1" />
                </div>
              </div>
              <div className="flex items-center gap-2 pt-4">
                <Skeleton className="h-4 w-4" />
                <Skeleton className="h-4 w-[120px]" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {error && (
        <Card>
          <CardContent className="py-8">
            <p className="text-destructive text-center">Error: {error}</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && (
        <Tabs defaultValue="ai" className="w-full">
          <TabsList className="grid w-full max-w-md grid-cols-3">
            <TabsTrigger value="ai">AI</TabsTrigger>
            <TabsTrigger value="advanced">Advanced</TabsTrigger>
            <TabsTrigger value="api-key">API Key</TabsTrigger>
          </TabsList>

          <TabsContent value="ai">
            <Card>
              <CardHeader>
                <CardTitle>AI Configuration</CardTitle>
                <CardDescription>Configure AI model and behavior (read-only, set via environment variables)</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Chat Model</label>
                  <Input
                    value={settings?.chat_model || "Not configured"}
                    readOnly
                    className="bg-muted"
                  />
                  <p className="text-xs text-muted-foreground">
                    LLM model used for chat responses (set via CHAT_MODEL env var)
                  </p>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Embedding Model</label>
                  <Input
                    value={settings?.embedding_model || "Not configured"}
                    readOnly
                    className="bg-muted"
                  />
                  <p className="text-xs text-muted-foreground">
                    Model used for document embeddings (set via EMBEDDING_MODEL env var)
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

<TabsContent value="advanced" className="space-y-4">
				{/* Model Connection Settings */}
      <ModelConnectionSettings
        formData={formData}
        errors={errors}
        onChange={handleInputChange}
      />

      {/* Document Processing Settings */}
      <DocumentProcessingSettings
              formData={formData}
              errors={errors}
              onChange={handleInputChange}
            />

            {/* RAG Settings */}
            <RAGSettings
              formData={formData}
              errors={errors}
              onChange={handleInputChange}
            />

            {/* Retrieval Settings */}
            <RetrievalSettings
              formData={formData}
              errors={errors}
              onChange={handleInputChange}
            />

            {/* Save Button and Status */}
            <div className="flex items-center gap-4 pt-4 border-t">
              <Button
                onClick={handleSave}
                disabled={saving || !hasChanges()}
              >
                {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Save Changes
              </Button>

              {hasChanges() && (
                <span className="text-sm text-muted-foreground">You have unsaved changes</span>
              )}
            </div>
          </TabsContent>

          <TabsContent value="api-key">
            <APIKeySettings
              apiKey={apiKey}
              onApiKeyChange={setApiKey}
              onSave={handleApiKeySave}
              isSaved={apiKeySaved}
            />
          </TabsContent>
        </Tabs>
      )}
    </>
  );
}

// Wrapper that provides health status and connection test
function SettingsPageWithStatus({ health }: { health: HealthStatus }) {
  const formatLastChecked = (date: Date | null) => {
    if (!date) return "Not checked";
    return `Last checked: ${date.toLocaleTimeString()}`;
  };

  const [connectionResult, setConnectionResult] = useState<ConnectionTestResult | null>(null);
  const [isTestingConnections, setIsTestingConnections] = useState(false);

  const handleConnectionTest = async () => {
    setIsTestingConnections(true);
    try {
      const result = await testConnections();
      setConnectionResult(result);
      toast.success("Connection test completed");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection test failed";
      toast.error(message);
      setConnectionResult(null);
    } finally {
      setIsTestingConnections(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground mt-1">Configure your application preferences</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <ConnectionStatusBadges health={health} />
          <span className="text-xs text-muted-foreground">{formatLastChecked(health.lastChecked)}</span>
          <ConnectionSettings
            onTestConnections={handleConnectionTest}
            isTesting={isTestingConnections}
            connectionStatus={connectionResult}
          />
        </div>
      </div>
      <SettingsPageContent />
    </div>
  );
}

// Main SettingsPage that checks health
export default function SettingsPage() {
  const health = useHealthCheck();
  return <SettingsPageWithStatus health={health} />;
}
