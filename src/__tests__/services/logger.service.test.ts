// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

describe("services/logger.service", () => {
  const originalEnv = process.env.NODE_ENV;

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });

  test("uses info level when in production", async () => {
    process.env.NODE_ENV = "production";
    const { logger } = await import("@services/logger.service");
    expect(logger.level).toBe("info");
  });

  test("uses debug level when not in production", async () => {
    process.env.NODE_ENV = "development";
    const { logger } = await import("@services/logger.service");
    expect(logger.level).toBe("debug");
  });
});
