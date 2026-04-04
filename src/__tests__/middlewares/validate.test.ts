// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { validateBody } from "@api/middlewares/validate";
import { Request, Response, NextFunction } from "express";
import { z } from "zod";

describe("api/middlewares/validate", () => {
  test("returns 400 when missing custom message", () => {
    const schema = z.object({
      field: z.string(),
    });

    const req = { body: { field: 123 } } as Request;
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    } as unknown as Response;
    const next = jest.fn() as NextFunction;

    const middleware = validateBody(schema);
    middleware(req, res, next);

    expect(res.status).toHaveBeenCalledWith(400);
    expect(res.json).toHaveBeenCalledWith({
      error: "Validation failed",
      message: "Invalid input: expected string, received number", // zod default message
    });
  });

  test("uses fallback message if issue is undefined (edge case)", () => {
    const mockSchema = {
      safeParse: () => ({ success: false, error: { issues: [] } }),
    } as any;

    const req = { body: {} } as Request;
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    } as unknown as Response;
    const next = jest.fn() as NextFunction;

    const middleware = validateBody(mockSchema);
    middleware(req, res, next);

    expect(res.status).toHaveBeenCalledWith(400);
    expect(res.json).toHaveBeenCalledWith({
      error: "Validation failed",
      message: "Invalid request body",
    });
  });
});
