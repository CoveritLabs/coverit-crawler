// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import Redis from "ioredis";
import { env } from "@config/env";

/** Redis client configured with retry strategy. */
const redis = new Redis(env.REDIS_URL, {
  maxRetriesPerRequest: 3,
  retryStrategy(times: number): number | null {
    if (times > 5) return null;
    return Math.min(times * 200, 2000);
  },
});

const workerRedis = new Redis(env.REDIS_URL, {
  maxRetriesPerRequest: null,
});

redis.on("error", (err) => {
  console.error("Redis connection error:", err.message);
});

export const refreshKey = (userId: string, token: string): string => `refresh:${userId}:${token}`;

export const refreshPattern = (userId: string): string => `refresh:${userId}:*`;

export const resetKey = (hashedToken: string): string => `reset:${hashedToken}`;

/** SCAN-based key search using cursor iteration. */
export async function scanKeys(pattern: string): Promise<string[]> {
  const keys: string[] = [];
  let cursor = "0";
  do {
    const [nextCursor, batch] = await redis.scan(cursor, "MATCH", pattern, "COUNT", 100);
    cursor = nextCursor;
    keys.push(...batch);
  } while (cursor !== "0");
  return keys;
}

export default redis;
export { workerRedis };
