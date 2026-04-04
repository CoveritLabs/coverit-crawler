// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

jest.mock("@config/env", () => ({
  env: {
    CORS_ORIGINS: ["http://localhost:5173", "http://example.com"],
    CORS_CREDENTIALS: "true",
    API_PREFIX: "/api/v1",
    RESEND_API_KEY: "test-key"
  }
}));

jest.mock("bullmq", () => {
    return {
        Queue: jest.fn().mockImplementation(() => ({
            on: jest.fn(),
            add: jest.fn(),
        })),
        Worker: jest.fn().mockImplementation(() => ({
            on: jest.fn(),
            close: jest.fn(),
        })),
    };
});

jest.mock("@lib/redis", () => require("./mocks/redis"));
jest.mock("@lib/prisma", () => require("./mocks/prisma"));

jest.mock("@workers/email.worker", () => ({}));

import request from "supertest";
import app from "../app";
import { env } from "@config/env";

describe("app.ts", () => {
  test("GET /health should return status ok", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("ok");
    expect(res.body.timestamp).toBeDefined();
  });

  test("GET /docs.json should return swagger spec", async () => {
    const res = await request(app).get("/docs.json");
    expect(res.status).toBe(200);
    expect(res.body.openapi).toBeDefined();
    expect(res.body.info).toBeDefined();
  });

  describe("CORS configuration", () => {
    test("should allow requests from allowed origins", async () => {
      // Assuming env.FRONTEND_URL or standard localhost is in CORS_ORIGINS
      const validOrigin = env.CORS_ORIGINS[0] === "*" ? "http://example.com" : env.CORS_ORIGINS[0];
      const res = await request(app).options("/health").set("Origin", validOrigin);
      expect(res.status).toBe(200);
      expect(res.header["access-control-allow-origin"]).toBe(validOrigin);
    });

    test("should reject requests from disallowed origins", async () => {
      if (env.CORS_ORIGINS.includes("*")) {
        // Skip if everything is allowed
        return;
      }
      const res = await request(app).options("/health").set("Origin", "http://malicious.com");
      // Cors middleware typically sends a 500 when the origin callback throws an error
      expect(res.status).toBe(500);
    });
    
    test("should allow requests with no origin (e.g., server-to-server)", async () => {
        const res = await request(app).get("/health"); // No Origin header set
        expect(res.status).toBe(200);
    });
  });
});
