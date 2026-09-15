import { describe, expect, it } from "vitest";

import {
  formatDeadline,
  formatHours,
  formatNumber,
  formatPercent,
  formatRelative,
} from "./format";

describe("formatHours", () => {
  it("uses minutes, hours and days", () => {
    expect(formatHours(0.5)).toBe("30min");
    expect(formatHours(2.5)).toBe("2h30");
    expect(formatHours(4)).toBe("4h");
    expect(formatHours(30)).toBe("1d 6h");
  });

  it("rounds up instead of dropping the hour", () => {
    // A deadline 3h59m59s away must not read "3h".
    expect(formatHours(3.99997)).toBe("4h");
    expect(formatHours(23.999)).toBe("1d");
  });

  it("shows a dash when there is no value", () => {
    expect(formatHours(null)).toBe("—");
    expect(formatHours(undefined)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats with a comma and a dash for missing values", () => {
    expect(formatPercent(0.8784)).toBe("88%");
    expect(formatPercent(0.8784, 1)).toBe("87,8%");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatNumber", () => {
  it("groups thousands the Brazilian way", () => {
    expect(formatNumber(5000)).toBe("5.000");
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-09-15T12:00:00Z");

  it("describes past and future moments in Portuguese", () => {
    expect(formatRelative("2026-09-15T09:00:00Z", now)).toBe("há 3 horas");
    expect(formatRelative("2026-09-14T12:00:00Z", now)).toBe("ontem");
    expect(formatRelative("2026-09-15T11:59:30Z", now)).toBe("agora");
  });
});

describe("formatDeadline", () => {
  const now = new Date("2026-09-15T12:00:00Z");

  it("counts down and then reports the delay", () => {
    expect(formatDeadline("2026-09-15T14:30:00Z", now)).toBe("2h30 restantes");
    expect(formatDeadline("2026-09-15T11:00:00Z", now)).toBe("atrasado há 1h");
  });
});
