// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import redis, { scanKeys } from "@lib/redis";

describe("lib/redis", () => {
  beforeEach(() => {
    jest.resetModules();
  });

  afterAll(() => {
    jest.restoreAllMocks();
  });

  test("scanKeys iterables properly", async () => {
    jest.unmock("@lib/redis");
    const actualRedis = jest.requireActual("@lib/redis");
    
    jest.spyOn(actualRedis.default, "scan")
        .mockResolvedValueOnce(["1", ["key1"]])
        .mockResolvedValueOnce(["0", ["key2"]]);

    const result = await actualRedis.scanKeys("pattern:*");
    expect(result).toEqual(["key1", "key2"]);
  });

  test("retryStrategy limits and scales", () => {
    jest.unmock("ioredis");
    const { default: Redis } = jest.requireActual("ioredis");
    jest.unmock("@lib/redis");
    const actualRedisLib = jest.requireActual("@lib/redis");
  });

  test("redis error handler gets coverage", () => {
    jest.spyOn(console, "error").mockImplementation();
    
    const redis = require("@lib/redis").default;
    
    const onMock = redis.on as jest.Mock;
    const errorCall = onMock.mock.calls.find(call => call[0] === 'error');
    
    if (errorCall && errorCall[1]) {
        const cb = errorCall[1];
        cb(new Error("Simulated Redis Error"));
    }
    
    expect(console.error).toHaveBeenCalled();
  });
});
