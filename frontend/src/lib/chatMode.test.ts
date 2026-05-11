import { describe, it, expect } from "vitest";
import { computeEffectiveChatMode } from "./chatMode";

describe("computeEffectiveChatMode", () => {
  it("returns stored mode when its backend is healthy", () => {
    expect(
      computeEffectiveChatMode({
        stored: "instant",
        defaultMode: "thinking",
        thinkingHealthy: true,
        instantHealthy: true,
      })
    ).toBe("instant");

    expect(
      computeEffectiveChatMode({
        stored: "thinking",
        defaultMode: "instant",
        thinkingHealthy: true,
        instantHealthy: true,
      })
    ).toBe("thinking");
  });

  it("falls back from instant to thinking when instant is unhealthy", () => {
    expect(
      computeEffectiveChatMode({
        stored: "instant",
        defaultMode: "instant",
        thinkingHealthy: true,
        instantHealthy: false,
      })
    ).toBe("thinking");
  });

  it("falls back from thinking to instant when thinking is unhealthy", () => {
    expect(
      computeEffectiveChatMode({
        stored: "thinking",
        defaultMode: "thinking",
        thinkingHealthy: false,
        instantHealthy: true,
      })
    ).toBe("instant");
  });

  it("returns desired mode when both backends are unhealthy (caller handles failure)", () => {
    expect(
      computeEffectiveChatMode({
        stored: "instant",
        defaultMode: "thinking",
        thinkingHealthy: false,
        instantHealthy: false,
      })
    ).toBe("instant");

    expect(
      computeEffectiveChatMode({
        stored: "thinking",
        defaultMode: "instant",
        thinkingHealthy: false,
        instantHealthy: false,
      })
    ).toBe("thinking");
  });

  it("falls back to default mode when no stored preference exists", () => {
    expect(
      computeEffectiveChatMode({
        stored: null,
        defaultMode: "instant",
        thinkingHealthy: true,
        instantHealthy: true,
      })
    ).toBe("instant");

    expect(
      computeEffectiveChatMode({
        stored: undefined,
        defaultMode: "thinking",
        thinkingHealthy: true,
        instantHealthy: true,
      })
    ).toBe("thinking");
  });

  it("falls back to 'thinking' when neither stored nor default is set", () => {
    expect(
      computeEffectiveChatMode({
        stored: null,
        defaultMode: null,
        thinkingHealthy: true,
        instantHealthy: true,
      })
    ).toBe("thinking");
  });

  it("applies health fallback to default mode when stored is unset", () => {
    expect(
      computeEffectiveChatMode({
        stored: null,
        defaultMode: "instant",
        thinkingHealthy: true,
        instantHealthy: false,
      })
    ).toBe("thinking");
  });
});
