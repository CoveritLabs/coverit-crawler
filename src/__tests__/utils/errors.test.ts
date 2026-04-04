// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { AppError, UnauthorizedError, BadRequestError, ConflictError } from "@utils/errors";

describe("utils/errors", () => {
  test("AppError", () => {
    const err = new AppError(418, "I am a teapot");
    expect(err.statusCode).toBe(418);
    expect(err.message).toBe("I am a teapot");
    expect(err.name).toBe("AppError");
  });

  test("UnauthorizedError", () => {
    const err = new UnauthorizedError();
    expect(err.statusCode).toBe(401);
    expect(err.message).toBe("Unauthorized");
    expect(err.name).toBe("UnauthorizedError");

    const customErr = new UnauthorizedError("Custom message");
    expect(customErr.message).toBe("Custom message");
  });

  test("BadRequestError", () => {
    const err = new BadRequestError();
    expect(err.statusCode).toBe(400);
    expect(err.message).toBe("Bad request");
    expect(err.name).toBe("BadRequestError");

    const customErr = new BadRequestError("Custom msg");
    expect(customErr.message).toBe("Custom msg");
  });

  test("ConflictError", () => {
    const err = new ConflictError();
    expect(err.statusCode).toBe(409);
    expect(err.message).toBe("Conflict");
    expect(err.name).toBe("ConflictError");

    const customErr = new ConflictError("Custom conflict");
    expect(customErr.message).toBe("Custom conflict");
  });
});
