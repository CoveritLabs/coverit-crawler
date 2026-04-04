// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

/**
 * @file Unit tests for requireAuth and errorHandler middlewares.
 */

import jwt from "jsonwebtoken";
import request from "supertest";

jest.mock("@lib/prisma", () => require("../mocks/prisma"));
jest.mock("@lib/redis", () => require("../mocks/redis"));
jest.mock("@queues/email.queue", () => ({
  emailQueue: {
    add: jest.fn(),
  },
}));
jest.mock("@config/env", () => ({
  env: {
    NODE_ENV: "test",
    PORT: 3000,
    JWT_SECRET: "test-secret",
    JWT_ACCESS_EXPIRY: "15m",
    JWT_REFRESH_EXPIRY_SECONDS: 604800,
    RESET_TOKEN_TTL_SECONDS: 3600,
  },
}));

import app from "../../app";

import { errorHandler } from "@api/middlewares/errorHandler";
import { requireAuth } from "@api/middlewares/requireAuth";
import { logger } from "@services/logger.service";
import express from "express";

/** Creates a minimal Express app with a protected route for testing middleware. */
function createTestApp(): express.Application {
  const testApp = express();
  testApp.use(express.json());

  testApp.get("/protected", requireAuth, (req, res) => {
    res.json({ userId: req.userId });
  });

  testApp.use(errorHandler);
  return testApp;
}

const testApp = createTestApp();

describe("requireAuth middleware", () => {
  it("should attach userId and allow access with valid token", async () => {
    const token = jwt.sign({ sub: "uuid-1" }, "test-secret", { expiresIn: "15m" });

    const res = await request(testApp).get("/protected").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.userId).toBe("uuid-1");
  });

  it("should return 401 when no Authorization header is present", async () => {
    const res = await request(testApp).get("/protected");

    expect(res.status).toBe(401);
    expect(res.body.message).toBe("Invalid or expired access token");
  });

  it("should return 401 when token has invalid signature", async () => {
    const token = jwt.sign({ sub: "uuid-1" }, "wrong-secret");

    const res = await request(testApp).get("/protected").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(401);
  });

  it("should return 401 when token is expired", async () => {
    const token = jwt.sign({ sub: "uuid-1" }, "test-secret", { expiresIn: "-1s" });

    const res = await request(testApp).get("/protected").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(401);
  });

  it("should return 401 when token has no sub claim", async () => {
    const token = jwt.sign({ foo: "bar" }, "test-secret");

    const res = await request(testApp).get("/protected").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(401);
  });

  it("should return 401 for garbage token value", async () => {
    const res = await request(testApp).get("/protected").set("Authorization", "Bearer not.a.jwt");

    expect(res.status).toBe(401);
  });
});

describe("errorHandler middleware", () => {
  let loggerErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    loggerErrorSpy = jest.spyOn(logger, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    loggerErrorSpy.mockRestore();
  });

  it("should return 500 for unknown errors", async () => {
    const errApp = express();
    errApp.use(express.json());
    errApp.get("/boom", () => {
      throw new Error("Something broke");
    });
    errApp.use(errorHandler);

    const res = await request(errApp).get("/boom");

    expect(res.status).toBe(500);
    expect(res.body.message).toBe("Internal server error");
    expect(loggerErrorSpy).toHaveBeenCalledWith(expect.any(Error));
  });
});
