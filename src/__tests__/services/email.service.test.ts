// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

const mockSend = jest.fn();
jest.mock("resend", () => ({
  Resend: jest.fn().mockImplementation(() => ({
    emails: { send: mockSend },
  })),
}));

jest.mock("@config/env", () => ({
  env: {
    RESEND_API_KEY: "test-key",
    RESET_PASSWORD_EMAIL: "support@x.com",
    RESET_PASSWORD_TEMPLATE_ID: "template-1"
  }
}));

import { sendResetEmail } from "@services/email.service";
import { logger } from "@services/logger.service";

jest.spyOn(logger, "info").mockImplementation();
jest.spyOn(logger, "error").mockImplementation();

describe("services/email.service", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("logs error if Resend fails", async () => {
    mockSend.mockResolvedValueOnce({ error: { message: "API failure" } });
    await sendResetEmail("test@x.com", "http://reset", "Tester");
    expect(logger.error).toHaveBeenCalled();
  });

  test("logs success if Resend succeeds", async () => {
    mockSend.mockResolvedValueOnce({ data: { id: "msg-123" }, error: null });
    await sendResetEmail("test@x.com", "http://reset", "Tester");
    expect(logger.info).toHaveBeenCalledTimes(2); // info and structural info
  });
});
