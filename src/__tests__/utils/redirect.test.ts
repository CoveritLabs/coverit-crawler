// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { buildRedirectUrl } from "@utils/redirect";

describe("utils/redirect", () => {
  test("returns pathname if no baseUrl", () => {
    expect(buildRedirectUrl("", "/path")).toBe("/path");
  });

  test("returns empty string if no baseUrl and no pathname", () => {
    expect(buildRedirectUrl("")).toBe("");
  });

  test("handles baseUrl with trailing slashes and pathname with leading slashes", () => {
    expect(buildRedirectUrl("http://example.com///", "///path///")).toBe("http://example.com/path///");
  });

  test("handles URLSearchParams correctly", () => {
    const params = new URLSearchParams({ a: "1", b: "2" });
    expect(buildRedirectUrl("http://example.com", "/path", params)).toBe("http://example.com/path?a=1&b=2");
  });

  test("handles Record payload correctly", () => {
    expect(buildRedirectUrl("http://example.com", "/path", { foo: "bar", baz: "qux" })).toBe(
      "http://example.com/path?foo=bar&baz=qux",
    );
  });

  test("appends search only if it exists", () => {
    expect(buildRedirectUrl("http://x.com", "/y", {})).toBe("http://x.com/y");
    expect(buildRedirectUrl("http://x.com", "/y", new URLSearchParams())).toBe("http://x.com/y");
  });
});
