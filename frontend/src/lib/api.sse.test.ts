import { describe, it, expect } from "vitest";
import { parseSSEStream, type ChatStreamCallbacks } from "./api";

function makeReader(events: object[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder();
  const sseBody = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(sseBody));
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
  return stream.getReader();
}

async function run(events: object[]) {
  const contents: string[] = [];
  const sourcesCalls: unknown[][] = [];
  const memoryCalls: unknown[][] = [];
  const validationCalls: unknown[] = [];
  const errors: string[] = [];
  let completed = false;

  const callbacks: ChatStreamCallbacks = {
    onMessage: (c) => contents.push(c),
    onSources: (s) => sourcesCalls.push(s),
    onMemories: (m) => memoryCalls.push(m),
    onCitationValidation: (v) => validationCalls.push(v),
    onError: (e) => errors.push(e.message),
    onComplete: () => {
      completed = true;
    },
  };

  await parseSSEStream(makeReader(events), callbacks);
  return {
    contents,
    sourcesCalls,
    memoryCalls,
    validationCalls,
    errors,
    completed,
  };
}

describe("parseSSEStream — reasoning suppression", () => {
  it("ignores events typed as 'reasoning'", async () => {
    const out = await run([
      { type: "reasoning", content: "secret thought" },
      { type: "content", content: "visible answer" },
    ]);
    expect(out.contents.join("")).toBe("visible answer");
    expect(out.contents.join("")).not.toContain("secret thought");
  });

  it("ignores 'thinking_content' typed events", async () => {
    const out = await run([
      { type: "thinking_content", content: "hidden" },
      { type: "content", content: "real" },
    ]);
    expect(out.contents.join("")).toBe("real");
  });

  it("does not stream events whose type is reasoning_content even if .content is present", async () => {
    const out = await run([
      { type: "reasoning_content", content: "leak attempt" },
      { type: "content", content: "ok" },
    ]);
    expect(out.contents.join("")).toBe("ok");
  });

  it("ignores 'thinking' events", async () => {
    const out = await run([
      { type: "thinking", content: "internal" },
      { type: "content", content: "answer" },
    ]);
    expect(out.contents.join("")).toBe("answer");
  });
});

describe("parseSSEStream — memories", () => {
  it("parses memories_used into onMemories callback (structured shape)", async () => {
    const out = await run([
      { type: "content", content: "Per [M1], here." },
      {
        type: "done",
        sources: [],
        memories_used: [
          {
            id: "42",
            memory_label: "M1",
            content: "User likes lists.",
            category: "preference",
          },
        ],
        score_type: "distance",
      },
    ]);
    expect(out.memoryCalls.length).toBe(1);
    const mem = out.memoryCalls[0][0] as { memory_label: string; content: string; id: string };
    expect(mem.memory_label).toBe("M1");
    expect(mem.content).toBe("User likes lists.");
    expect(mem.id).toBe("42");
  });

  it("normalizes legacy bare-string memories_used into structured records", async () => {
    const out = await run([
      {
        type: "done",
        sources: [],
        memories_used: ["legacy memory text"],
        score_type: "distance",
      },
    ]);
    const mem = out.memoryCalls[0][0] as { memory_label: string; content: string };
    expect(mem.memory_label).toBe("M1");
    expect(mem.content).toBe("legacy memory text");
  });
});

describe("parseSSEStream — citation_validation", () => {
  it("forwards citation_validation events to onCitationValidation", async () => {
    const out = await run([
      {
        type: "done",
        sources: [],
        memories_used: [],
        score_type: "distance",
        citation_validation: {
          valid: ["S1"],
          invalid: ["S99"],
          uncited_factual_warning: false,
          has_evidence: true,
        },
      },
    ]);
    expect(out.validationCalls.length).toBe(1);
    const cv = out.validationCalls[0] as { valid: string[]; invalid: string[] };
    expect(cv.invalid).toContain("S99");
    expect(cv.valid).toContain("S1");
  });
});
