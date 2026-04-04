// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { Worker } from "bullmq";
import * as emailService from "@services/email.service";

let workerCallback: any;

jest.mock("bullmq", () => {
  return {
    Worker: jest.fn().mockImplementation((name, cb) => {
      workerCallback = cb;
      return {};
    }),
  };
});

jest.mock("@config/env", () => ({
  env: { RESEND_API_KEY: "test-key" }
}));

jest.mock("@services/email.service");
jest.mock("@services/logger.service", () => ({ logger: { info: jest.fn() } }));
jest.mock("@lib/redis", () => ({ workerRedis: {} }));

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import "@workers/email.worker";

describe("workers/email.worker", () => {
  test("workerCallback delegates send-reset-email job", async () => {
    expect(workerCallback).toBeDefined();

    const job = {
      name: "send-reset-email",
      data: { email: "u@u.com", resetUrl: "link", name: "U" },
    };

    await workerCallback(job);
    expect(emailService.sendResetEmail).toHaveBeenCalledWith("u@u.com", "link", "U");
  });

  test("workerCallback ignores other job names", async () => {
    jest.clearAllMocks();
    const job = {
      name: "other-job",
      data: {},
    };

    await workerCallback(job);
    expect(emailService.sendResetEmail).not.toHaveBeenCalled();
  });
});
