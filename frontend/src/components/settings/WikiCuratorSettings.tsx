/**
 * Settings → Wiki & Curator tab.
 *
 * Wires every wiki + curator field defined in the backend config to the
 * settings store. Curator inputs are visually grouped and explain that
 * "claims become active only when source quotes are verified", so the
 * operator never thinks the curator can write authoritative claims
 * without provenance.
 *
 * The "Test connection" button is wired to POST /settings/curator/test.
 * The local-model UX hint is rendered inline so operators know the
 * ALLOW_LOCAL_CURATOR=1 opt-in exists.
 */
import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Loader2, ShieldCheck, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { NumberInput } from "./NumberInput";
import { testCuratorConnection } from "@/lib/api";

/**
 * Tiny "always reflect the latest value" ref helper. Used by handleTest
 * so the post-await guard can compare the URL/model the test was
 * launched with against whatever the operator has now typed.
 */
function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
import type { CuratorTestResult } from "@/lib/api";
import type { SettingsErrors, SettingsFormData } from "@/stores/useSettingsStore";

export interface WikiCuratorSettingsProps {
  formData: SettingsFormData;
  errors: SettingsErrors;
  onChange: <K extends keyof SettingsFormData>(
    field: K,
    value: SettingsFormData[K],
  ) => void;
}

export function WikiCuratorSettings({
  formData,
  errors,
  onChange,
}: WikiCuratorSettingsProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<CuratorTestResult | null>(null);

  // Clear any stale test result when the operator toggles curator off,
  // changes the URL, or changes the model — the previous OK / error no
  // longer reflects the current configuration and would mislead.
  useEffect(() => {
    setTestResult(null);
  }, [
    formData.wiki_llm_curator_enabled,
    formData.wiki_llm_curator_url,
    formData.wiki_llm_curator_model,
  ]);

  const handleTest = async () => {
    // Capture the URL/model snapshot we are testing. If the operator
    // edits the URL/model while the request is in flight, the
    // useEffect below will null out testResult; we additionally
    // guard the post-await write so a late response can't repaint
    // a stale OK label against the now-changed config.
    const requestedUrl = formData.wiki_llm_curator_url;
    const requestedModel = formData.wiki_llm_curator_model;
    setTesting(true);
    setTestResult(null);
    try {
      const out = await testCuratorConnection(requestedUrl, requestedModel);
      // Latest formData read AFTER await — guard against in-flight edits.
      const latest = useFormDataSnapshot.current;
      if (
        latest.url === requestedUrl &&
        latest.model === requestedModel
      ) {
        setTestResult(out);
      }
    } catch (e) {
      const latest = useFormDataSnapshot.current;
      if (
        latest.url === requestedUrl &&
        latest.model === requestedModel
      ) {
        setTestResult({
          ok: false,
          model: requestedModel,
          latency_ms: null,
          error: e instanceof Error ? e.message : "Test failed",
        });
      }
    } finally {
      setTesting(false);
    }
  };

  // Live snapshot of the URL/model used by the test handler's
  // post-await guard. We need a ref so the closure inside handleTest
  // sees the latest values without re-binding the callback.
  const useFormDataSnapshot = useLatestRef({
    url: formData.wiki_llm_curator_url,
    model: formData.wiki_llm_curator_model,
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Wiki / Knowledge Compiler</CardTitle>
          <CardDescription>
            Toggle when the wiki compiler runs and which sources it processes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_enabled}
              onCheckedChange={(v) => onChange("wiki_enabled", Boolean(v))}
            />
            Wiki enabled
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_compile_on_ingest}
              onCheckedChange={(v) =>
                onChange("wiki_compile_on_ingest", Boolean(v))
              }
            />
            Compile on document ingest
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_compile_on_query}
              onCheckedChange={(v) =>
                onChange("wiki_compile_on_query", Boolean(v))
              }
            />
            Compile on chat query
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_compile_after_indexing}
              onCheckedChange={(v) =>
                onChange("wiki_compile_after_indexing", Boolean(v))
              }
            />
            Compile after document indexing finishes
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_lint_enabled}
              onCheckedChange={(v) => onChange("wiki_lint_enabled", Boolean(v))}
            />
            Wiki lint enabled
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4" />
            LLM Wiki Curator (optional)
          </CardTitle>
          <CardDescription>
            The curator proposes wiki updates from a small local model.
            Claims become active only when source quotes are verified —
            unsupported output never becomes an active claim.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_llm_curator_enabled}
              onCheckedChange={(v) =>
                onChange("wiki_llm_curator_enabled", Boolean(v))
              }
            />
            Enable LLM curator
          </label>

          <div className="space-y-1">
            <label
              htmlFor="curator-url"
              className="text-sm font-medium block"
            >
              Endpoint URL
            </label>
            <Input
              id="curator-url"
              type="url"
              placeholder="https://localhost:11434"
              value={formData.wiki_llm_curator_url}
              onChange={(e) =>
                onChange("wiki_llm_curator_url", e.target.value)
              }
              disabled={!formData.wiki_llm_curator_enabled}
              data-invalid={errors.wiki_llm_curator_url ? "true" : undefined}
              aria-invalid={errors.wiki_llm_curator_url ? true : undefined}
            />
            {errors.wiki_llm_curator_url && (
              <p className="text-xs text-destructive">
                {errors.wiki_llm_curator_url}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              OpenAI-compatible /v1/chat/completions base URL. Local
              endpoints (loopback / RFC1918) require{" "}
              <code className="rounded bg-muted px-1">ALLOW_LOCAL_CURATOR=1</code>.
            </p>
          </div>

          <div className="space-y-1">
            <label
              htmlFor="curator-model"
              className="text-sm font-medium block"
            >
              Model name
            </label>
            <Input
              id="curator-model"
              type="text"
              placeholder="qwen2.5:1.5b"
              value={formData.wiki_llm_curator_model}
              onChange={(e) =>
                onChange("wiki_llm_curator_model", e.target.value)
              }
              disabled={!formData.wiki_llm_curator_enabled}
              data-invalid={errors.wiki_llm_curator_model ? "true" : undefined}
              aria-invalid={errors.wiki_llm_curator_model ? true : undefined}
            />
            {errors.wiki_llm_curator_model && (
              <p className="text-xs text-destructive">
                {errors.wiki_llm_curator_model}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label
                htmlFor="curator-temp"
                className="text-sm font-medium block"
              >
                Temperature (0.0–1.0)
              </label>
              <NumberInput
                id="curator-temp"
                value={formData.wiki_llm_curator_temperature}
                onCommit={(v) =>
                  onChange("wiki_llm_curator_temperature", v ?? 0)
                }
                error={errors.wiki_llm_curator_temperature}
                disabled={!formData.wiki_llm_curator_enabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor="curator-max-input"
                className="text-sm font-medium block"
              >
                Max input chars (1000–24000)
              </label>
              <NumberInput
                id="curator-max-input"
                parseAs="int"
                value={formData.wiki_llm_curator_max_input_chars}
                onCommit={(v) =>
                  onChange("wiki_llm_curator_max_input_chars", v ?? 6000)
                }
                error={errors.wiki_llm_curator_max_input_chars}
                disabled={!formData.wiki_llm_curator_enabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor="curator-max-output"
                className="text-sm font-medium block"
              >
                Max output tokens
              </label>
              <NumberInput
                id="curator-max-output"
                parseAs="int"
                value={formData.wiki_llm_curator_max_output_tokens}
                onCommit={(v) =>
                  onChange("wiki_llm_curator_max_output_tokens", v ?? 2048)
                }
                error={errors.wiki_llm_curator_max_output_tokens}
                disabled={!formData.wiki_llm_curator_enabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor="curator-timeout"
                className="text-sm font-medium block"
              >
                Timeout seconds (10–600)
              </label>
              <NumberInput
                id="curator-timeout"
                value={formData.wiki_llm_curator_timeout_sec}
                onCommit={(v) =>
                  onChange("wiki_llm_curator_timeout_sec", v ?? 120)
                }
                error={errors.wiki_llm_curator_timeout_sec}
                disabled={!formData.wiki_llm_curator_enabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor="curator-concurrency"
                className="text-sm font-medium block"
              >
                Concurrency (1–4)
              </label>
              <NumberInput
                id="curator-concurrency"
                parseAs="int"
                value={formData.wiki_llm_curator_concurrency}
                onCommit={(v) =>
                  onChange("wiki_llm_curator_concurrency", v ?? 1)
                }
                error={errors.wiki_llm_curator_concurrency}
                disabled={!formData.wiki_llm_curator_enabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor="curator-mode"
                className="text-sm font-medium block"
              >
                Mode
              </label>
              <select
                id="curator-mode"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={formData.wiki_llm_curator_mode}
                onChange={(e) =>
                  onChange("wiki_llm_curator_mode", e.target.value)
                }
                disabled={!formData.wiki_llm_curator_enabled}
              >
                <option value="draft">draft (always needs review)</option>
                <option value="active_if_verified">
                  active if verified
                </option>
              </select>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_llm_curator_require_quote_match}
              onCheckedChange={(v) =>
                onChange(
                  "wiki_llm_curator_require_quote_match",
                  Boolean(v),
                )
              }
              disabled={!formData.wiki_llm_curator_enabled}
            />
            Require source-quote match
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_llm_curator_require_chunk_id}
              onCheckedChange={(v) =>
                onChange("wiki_llm_curator_require_chunk_id", Boolean(v))
              }
              disabled={!formData.wiki_llm_curator_enabled}
            />
            Require chunk ID
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_llm_curator_run_on_ingest}
              onCheckedChange={(v) =>
                onChange("wiki_llm_curator_run_on_ingest", Boolean(v))
              }
              disabled={!formData.wiki_llm_curator_enabled}
            />
            Run on ingest
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_llm_curator_run_on_query}
              onCheckedChange={(v) =>
                onChange("wiki_llm_curator_run_on_query", Boolean(v))
              }
              disabled={!formData.wiki_llm_curator_enabled}
            />
            Run on query (default off)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={formData.wiki_llm_curator_run_on_manual}
              onCheckedChange={(v) =>
                onChange("wiki_llm_curator_run_on_manual", Boolean(v))
              }
              disabled={!formData.wiki_llm_curator_enabled}
            />
            Run on manual / recompile
          </label>

          <div className="flex items-center gap-3 pt-2 border-t">
            <Button
              size="sm"
              variant="outline"
              onClick={handleTest}
              disabled={
                testing ||
                !formData.wiki_llm_curator_url.trim() ||
                !formData.wiki_llm_curator_model.trim()
              }
            >
              {testing && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              Test curator connection
            </Button>
            {testResult && (
              <div
                className={
                  testResult.ok
                    ? "flex items-center gap-1 text-xs text-emerald-600"
                    : "flex items-center gap-1 text-xs text-destructive"
                }
                role="status"
              >
                {testResult.ok ? (
                  <>
                    <CheckCircle2 className="w-3 h-3" />
                    OK · {testResult.latency_ms}ms
                  </>
                ) : (
                  <>
                    <XCircle className="w-3 h-3" />
                    {testResult.error ?? "Failed"}
                  </>
                )}
              </div>
            )}
          </div>
          <p className="flex items-start gap-1 text-xs text-muted-foreground">
            <AlertTriangle className="w-3 h-3 mt-0.5" />
            The curator proposes wiki updates. Claims become active only
            when source quotes are verified.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
