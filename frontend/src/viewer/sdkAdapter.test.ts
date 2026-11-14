import { describe, expect, it } from "vitest";
import { sdkErrorText } from "./sdkAdapter";

describe("sdkErrorText", () => {
  it("never repeats the application key", () => {
    const text = sdkErrorText(new Error("abc123@https://example.test - upstream refused"), "abc123");
    expect(text).toBe("upstream refused");
    expect(text).not.toContain("abc123");
  });

  it("maps a referrer mismatch to the allowed-domain explanation", () => {
    const text = sdkErrorText(
      new Error("abc123@http://localhost:5173 - referrer mismatch"),
      "abc123",
    );
    expect(text).toMatch(/not allowed for/);
    expect(text).toMatch(/allowed domains|Matterport key settings/);
  });

  it("falls back to the raw message without a key", () => {
    const text = sdkErrorText(new Error("something broke"), "");
    expect(text).toBe("something broke");
  });
});
