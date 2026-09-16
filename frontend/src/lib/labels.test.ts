import { describe, expect, it } from "vitest";

import { translateValue } from "./labels";

describe("translateValue", () => {
  it("translates statuses and priorities stored in English", () => {
    expect(translateValue("RESOLVED")).toBe("Resolvido");
    expect(translateValue("CRITICAL")).toBe("Crítica");
  });

  it("translates each part of an AI analysis summary", () => {
    expect(translateValue("Fiscal / NF-e · HIGH · 70%")).toBe("Fiscal / NF-e · Alta · 70%");
  });

  it("keeps names and empty values as they are", () => {
    expect(translateValue("Maria Oliveira")).toBe("Maria Oliveira");
    expect(translateValue(null)).toBeNull();
  });
});
