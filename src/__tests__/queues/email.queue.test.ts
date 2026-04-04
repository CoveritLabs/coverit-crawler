// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { emailQueue } from "@queues/email.queue";

jest.mock("bullmq", () => {
  return {
    Queue: jest.fn().mockImplementation((name) => ({ name })),
  };
});
jest.mock("@lib/redis", () => ({}));

describe("queues/email.queue", () => {
  test("exports email queue instance", () => {
    // This just validates the queue definition runs without error 
    // and matches the mocked structure
    expect(emailQueue).toBeDefined();
    expect(emailQueue.name).toBe("email");
  });
});
