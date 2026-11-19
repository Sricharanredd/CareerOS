import { describe, expect, it } from "vitest";

import { ApiError, csrfHeaders, fieldErrors, readCookie, toQuery } from "@/lib/api";

describe("ApiError.fromResponse", () => {
  it("parses the backend error envelope", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "duplicate_application",
          message: "A similar application already exists.",
          details: { matches: [] },
          request_id: "req-123",
        },
      }),
      { status: 409, headers: { "content-type": "application/json" } },
    );

    const error = await ApiError.fromResponse(response);
    expect(error.status).toBe(409);
    expect(error.code).toBe("duplicate_application");
    expect(error.message).toContain("similar application");
    expect(error.requestId).toBe("req-123");
    expect(error.details).toEqual({ matches: [] });
  });

  it("falls back to a friendly message when the body is not JSON", async () => {
    const response = new Response("upstream exploded", { status: 500 });
    const error = await ApiError.fromResponse(response);
    expect(error.code).toBe("http_500");
    expect(error.message).toBe("Something went wrong on the server.");
  });
});

describe("fieldErrors", () => {
  it("maps validation details to field messages", () => {
    const error = new ApiError(422, "validation_error", "Some fields are invalid.", [
      { field: "title", msg: "String should have at least 1 character" },
    ]);
    expect(fieldErrors(error)).toEqual({
      title: "String should have at least 1 character",
    });
  });

  it("ignores non-validation errors", () => {
    expect(fieldErrors(new ApiError(409, "conflict", "Conflict"))).toEqual({});
  });
});

describe("toQuery", () => {
  it("skips empty values and keeps false flags out", () => {
    expect(toQuery({ a: "x", b: null, c: undefined, d: false, e: true })).toBe("?a=x&e=true");
    expect(toQuery({})).toBe("");
  });
});

describe("cookies", () => {
  it("reads the CSRF cookie and builds the header", () => {
    document.cookie = "careeros_csrf=token-abc; path=/";
    expect(readCookie("careeros_csrf")).toBe("token-abc");
    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "token-abc" });
  });
});
