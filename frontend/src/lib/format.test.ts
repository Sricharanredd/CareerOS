import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatSalaryRange,
  labelize,
  parseDate,
  pluralize,
  toDateInputValue,
  truncate,
} from "@/lib/format";

describe("parseDate", () => {
  it("treats naive API timestamps as UTC", () => {
    expect(parseDate("2026-01-15T12:00:00").toISOString()).toBe("2026-01-15T12:00:00.000Z");
  });

  it("keeps explicit offsets intact", () => {
    expect(parseDate("2026-01-15T12:00:00+05:30").toISOString()).toBe("2026-01-15T06:30:00.000Z");
  });
});

describe("labelize", () => {
  it("turns enum values into readable labels", () => {
    expect(labelize("full_time")).toBe("Full Time");
    expect(labelize("status_change")).toBe("Status Change");
    expect(labelize(null)).toBe("—");
  });
});

describe("formatSalaryRange", () => {
  it("formats a range with a period", () => {
    const value = formatSalaryRange(120000, 150000, "USD", "year");
    expect(value).toContain("120");
    expect(value).toContain("150");
    expect(value).toContain("/ year");
  });

  it("returns null when no bounds are provided", () => {
    expect(formatSalaryRange(null, null, "USD", "year")).toBeNull();
  });
});

describe("helpers", () => {
  it("formats ISO date input values", () => {
    expect(toDateInputValue("2026-03-04T00:00:00")).toBe("2026-03-04");
    expect(toDateInputValue(null)).toBe("");
  });

  it("pluralizes counts", () => {
    expect(pluralize(1, "application")).toBe("1 application");
    expect(pluralize(3, "application")).toBe("3 applications");
    expect(pluralize(2, "company", "companies")).toBe("2 companies");
  });

  it("truncates with an ellipsis", () => {
    expect(truncate("abcdef", 4)).toBe("abc…");
    expect(truncate("abc", 10)).toBe("abc");
  });

  it("formats dates without throwing on empty values", () => {
    expect(formatDate(null)).toBe("—");
  });
});
