// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

// Manual mock for the `ioredis` package used by the runtime code.
export default class MockRedis {
    constructor(..._args: any[]) {}
    set = jest.fn().mockResolvedValue('OK');
    get = jest.fn().mockResolvedValue(null);
    del = jest.fn().mockResolvedValue(1);
    scan = jest.fn().mockResolvedValue(['0', []]);
    ping = jest.fn().mockResolvedValue('PONG');
    on = jest.fn();
    disconnect = jest.fn();
}
