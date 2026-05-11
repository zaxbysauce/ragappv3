/**
 * Settings → Models tab.
 *
 * Replaces the legacy "AI" + "Advanced" tabs that contradicted each other
 * (AI claimed read-only via env vars; Advanced edited the same fields).
 *
 * All fields are runtime-editable. Each field shows a source badge derived
 * from ``effective_sources`` so the operator can see whether the displayed
 * value came from a settings_kv override, an env var, or the Pydantic
 * default. Per actual lifespan order in the backend (kv > env > default),
 * saving here will shadow any env var at runtime — that's documented in
 * the help text rather than enforced by disabling inputs.
 */
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  REINDEX_REQUIRED_FIELDS,
  type SettingsErrors,
  type SettingsFormData,
} from "@/stores/useSettingsStore";
import { ReindexFieldWarning } from "./ReindexFieldWarning";

export interface ModelsTabProps {
  formData: SettingsFormData;
  errors: SettingsErrors;
  onChange: <K extends keyof SettingsFormData>(
    field: K,
    value: SettingsFormData[K],
  ) => void;
  effectiveSources: Record<string, "kv" | "env" | "default">;
}

function SourceBadge({
  source,
}: {
  source?: "kv" | "env" | "default";
}) {
  if (!source) return null;
  const label =
    source === "kv"
      ? "Runtime override"
      : source === "env"
      ? "From env"
      : "Default";
  const variant: "secondary" | "outline" =
    source === "kv" ? "secondary" : "outline";
  return (
    <Badge variant={variant} className="text-[10px] uppercase">
      {label}
    </Badge>
  );
}

interface FieldProps {
  field: keyof SettingsFormData;
  label: string;
  placeholder: string;
  description: string;
  type?: string;
  formData: SettingsFormData;
  errors: SettingsErrors;
  onChange: ModelsTabProps["onChange"];
  source?: "kv" | "env" | "default";
}

function StringField({
  field,
  label,
  placeholder,
  description,
  type = "text",
  formData,
  errors,
  onChange,
  source,
}: FieldProps) {
  const value = (formData as unknown as Record<string, string>)[field as string] ?? "";
  const err = (errors as Record<string, string | undefined>)[field as string];
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={String(field)} className="text-sm font-medium">
          {label}
        </Label>
        <SourceBadge source={source} />
      </div>
      <Input
        id={String(field)}
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) =>
          onChange(field, e.target.value as SettingsFormData[typeof field])
        }
        aria-invalid={err ? true : undefined}
        className={err ? "border-destructive" : undefined}
      />
      {err && (
        <p className="text-xs text-destructive" role="alert">
          {err}
        </p>
      )}
      <p className="text-xs text-muted-foreground">{description}</p>
      {REINDEX_REQUIRED_FIELDS.has(field) && <ReindexFieldWarning />}
    </div>
  );
}

export function ModelsTab({
  formData,
  errors,
  onChange,
  effectiveSources,
}: ModelsTabProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Model endpoints</CardTitle>
          <CardDescription>
            All fields are runtime-editable. Saving overrides any env value
            at runtime; env values seed defaults at startup but do not
            enforce precedence.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <StringField
            field="ollama_embedding_url"
            label="Embedding service URL"
            placeholder="http://localhost:11434"
            description="OpenAI-compatible / Ollama / TEI URL for embeddings."
            type="url"
            formData={formData}
            errors={errors}
            onChange={onChange}
            source={effectiveSources.ollama_embedding_url}
          />
          <StringField
            field="ollama_chat_url"
            label="Chat / LLM service URL"
            placeholder="http://localhost:11434"
            description="Chat model endpoint. For Docker, use http://host.docker.internal:11434 to reach a host Ollama."
            type="url"
            formData={formData}
            errors={errors}
            onChange={onChange}
            source={effectiveSources.ollama_chat_url}
          />
          <StringField
            field="reranker_url"
            label="Reranker service URL"
            placeholder="http://localhost:8082"
            description="Reranker endpoint. Leave empty to use local sentence-transformers."
            type="url"
            formData={formData}
            errors={errors}
            onChange={onChange}
            source={effectiveSources.reranker_url}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Model names</CardTitle>
          <CardDescription>
            Names are passed verbatim to the configured endpoints.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <StringField
            field="embedding_model"
            label="Embedding model"
            placeholder="microsoft/harrier-oss-v1-0.6b"
            description="Used for document embeddings."
            formData={formData}
            errors={errors}
            onChange={onChange}
            source={effectiveSources.embedding_model}
          />
          <StringField
            field="chat_model"
            label="Chat model"
            placeholder="llama3"
            description="Used for chat responses."
            formData={formData}
            errors={errors}
            onChange={onChange}
            source={effectiveSources.chat_model}
          />
          <StringField
            field="reranker_model"
            label="Reranker model"
            placeholder="BAAI/bge-reranker-v2-m3"
            description="Cross-encoder model used by the reranker."
            formData={formData}
            errors={errors}
            onChange={onChange}
            source={effectiveSources.reranker_model}
          />
        </CardContent>
      </Card>
    </div>
  );
}
