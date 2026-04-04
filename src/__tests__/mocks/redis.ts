// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

const redis = {
    set: jest.fn().mockResolvedValue('OK'),
    get: jest.fn().mockResolvedValue(null),
    del: jest.fn().mockResolvedValue(1),
    scan: jest.fn().mockResolvedValue(['0', []]),
    ping: jest.fn().mockResolvedValue('PONG'),
    on: jest.fn(),
    disconnect: jest.fn(),
};

export async function scanKeys(pattern: string): Promise<string[]> {
    const keys: string[] = [];
    let cursor = '0';
    do {
        const [nextCursor, batch] = await redis.scan(cursor, 'MATCH', pattern, 'COUNT', 100);
        cursor = nextCursor;
        keys.push(...batch);
    } while (cursor !== '0');
    return keys;
}

export const refreshKey = (userId: string, token: string): string =>
    `refresh:${userId}:${token}`;

export const refreshPattern = (userId: string): string =>
    `refresh:${userId}:*`;

export const resetKey = (hashedToken: string): string =>
    `reset:${hashedToken}`;

export default redis;
