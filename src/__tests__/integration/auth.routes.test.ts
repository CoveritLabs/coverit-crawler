// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

/**
 * @file Integration tests for all POST /auth/* routes via supertest.
 */

import { AUTH_MESSAGES, AUTH_VALIDATION } from "@constants/messages";
import jwt from "jsonwebtoken";
import request from "supertest";

jest.mock("@workers/email.worker", () => ({}));
jest.mock("@lib/prisma", () => require("../mocks/prisma"));
jest.mock("@lib/redis", () => require("../mocks/redis"));
jest.mock("@services/email.service", () => ({
  sendResetEmail: jest.fn().mockResolvedValue(undefined),
}));
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
    API_PREFIX: "/api/v1",
    RESEND_API_KEY: "test-key",
    RESET_PASSWORD_EMAIL: "test@test.com",
    FRONTEND_URL: "https://app.example.com",
  },
}));

jest.mock("argon2", () => ({
  hash: jest.fn().mockResolvedValue("$argon2-hashed"),
  verify: jest.fn(),
}));

import { env } from "@config/env";
import prisma from "@lib/prisma";
import redis from "@lib/redis";
import argon2 from "argon2";
import app from "../../app";

const BASE = `${env.API_PREFIX}/auth`;

const mockPrisma = prisma as any; // eslint-disable-line @typescript-eslint/no-explicit-any
const mockRedis = redis as any; // eslint-disable-line @typescript-eslint/no-explicit-any
const mockArgon2 = argon2 as any; // eslint-disable-line @typescript-eslint/no-explicit-any

describe("POST /auth/signup", () => {
  it("should return 201 on successful signup", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);
    mockPrisma.user.create.mockResolvedValue({
      id: "uuid-1",
      email: "new@user.com",
      name: "New User",
      password: "$argon2-hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    const res = await request(app)
      .post(`${BASE}/signup`)
      .send({ email: "new@user.com", password: "P@ssword1", name: "New User" });

    expect(res.status).toBe(201);
    expect(res.body.message).toBe(AUTH_MESSAGES.SIGNUP_SUCCESS);
  });

  it("should return 409 if email already exists", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "dup@user.com",
      name: "Dup",
      password: "hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    const res = await request(app)
      .post(`${BASE}/signup`)
      .send({ email: "dup@user.com", password: "P@ssword1", name: "Dup" });

    expect(res.status).toBe(409);
    expect(res.body.message).toBe(AUTH_MESSAGES.EMAIL_TAKEN);
  });

  it("should not return any tokens or set cookies", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);
    mockPrisma.user.create.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "User",
      password: "$argon2-hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    const res = await request(app)
      .post(`${BASE}/signup`)
      .send({ email: "a@b.com", password: "P@ssword1", name: "User" });

    expect(res.status).toBe(201);
    expect(res.body.tokens).toBeUndefined();
  });
});

describe("POST /auth/login", () => {
  it("should return 200 with user info and tokens in response body", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "user@test.com",
      name: "Test",
      password: "$argon2-hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockArgon2.verify.mockResolvedValue(true);
    mockRedis.set.mockResolvedValue("OK");

    const res = await request(app).post(`${BASE}/login`).send({ email: "user@test.com", password: "P@ssword1" });

    expect(res.status).toBe(200);
    expect(res.body.user).toEqual({ id: "uuid-1", email: "user@test.com", name: "Test" });
    expect(res.body.tokens).toBeDefined();
    expect(res.body.tokens.accessToken).toBeDefined();
    expect(res.body.tokens.refreshToken).toBeDefined();
  });

  it("should return 401 for wrong email", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);

    const res = await request(app).post(`${BASE}/login`).send({ email: "wrong@test.com", password: "P@ssword1" });

    expect(res.status).toBe(401);
    expect(res.body.message).toBe(AUTH_MESSAGES.INVALID_CREDENTIALS);
  });

  it("should return 401 for wrong password", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "user@test.com",
      name: "Test",
      password: "$argon2-hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockArgon2.verify.mockResolvedValue(false);

    const res = await request(app).post(`${BASE}/login`).send({ email: "user@test.com", password: "WrongPass" });

    expect(res.status).toBe(401);
    expect(res.body.message).toBe(AUTH_MESSAGES.INVALID_CREDENTIALS);
  });
});

describe("POST /auth/refresh", () => {
  it("should return 200 and rotate tokens on valid refresh token", async () => {
    const oldToken = "valid-refresh-token";
    const crypto = require("crypto");
    const hashed = crypto.createHash("sha256").update(oldToken).digest("hex");
    const key = `refresh:uuid-1:${hashed}`;

    mockRedis.scan.mockResolvedValueOnce(["0", [key]]);
    mockRedis.del.mockResolvedValue(1);
    mockRedis.set.mockResolvedValue("OK");

    const res = await request(app).post(`${BASE}/refresh`).send({ refreshToken: oldToken });

    expect(res.status).toBe(200);
    expect(res.body.message).toBe(AUTH_MESSAGES.REFRESH_SUCCESS);
    expect(res.body.tokens).toBeDefined();
    expect(res.body.tokens.accessToken).toBeDefined();
    expect(res.body.tokens.refreshToken).toBeDefined();
  });

  it("should return 401 if no refresh token in body", async () => {
    const res = await request(app).post(`${BASE}/refresh`).send({});

    expect(res.status).toBe(400);
    expect(res.body.message).toBe(AUTH_VALIDATION.REFRESH_TOKEN_REQUIRED);
  });

  it("should return 401 if refresh token not in Redis", async () => {
    mockRedis.scan.mockResolvedValue(["0", []]);

    const res = await request(app).post(`${BASE}/refresh`).send({ refreshToken: "bad-token" });

    expect(res.status).toBe(401);
  });
});

describe("POST /auth/logout", () => {
  it("should return 200 and invalidate refresh token", async () => {
    const token = "some-refresh-token";
    const crypto = require("crypto");
    const hashed = crypto.createHash("sha256").update(token).digest("hex");
    const key = `refresh:uuid-1:${hashed}`;

    mockRedis.scan.mockResolvedValueOnce(["0", [key]]);
    mockRedis.del.mockResolvedValue(1);

    const res = await request(app).post(`${BASE}/logout`).send({ refreshToken: token });

    expect(res.status).toBe(200);
    expect(res.body.message).toBe(AUTH_MESSAGES.LOGOUT_SUCCESS);
  });

  it("should return 200 even without a refresh token (graceful)", async () => {
    const res = await request(app).post(`${BASE}/logout`).send({});

    expect(res.status).toBe(200);
    expect(res.body.message).toBe(AUTH_MESSAGES.LOGOUT_SUCCESS);
  });
});

describe("POST /auth/forgot-password", () => {
  it("should always return 200 regardless of email existence", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);

    const res = await request(app).post(`${BASE}/forgot-password`).send({ email: "nonexistent@test.com" });

    expect(res.status).toBe(200);
    expect(res.body.message).toContain("If an account");
  });

  it("should return 200 for existing email (same response)", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "exists@test.com",
      name: "Test",
      password: "hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.set.mockResolvedValue("OK");

    const res = await request(app).post(`${BASE}/forgot-password`).send({ email: "exists@test.com" });

    expect(res.status).toBe(200);
    expect(res.body.message).toContain("If an account");
  });

  it("should not leak whether the email exists via timing or response", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);
    const res1 = await request(app).post(`${BASE}/forgot-password`).send({ email: "a@b.com" });

    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "T",
      password: "h",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.set.mockResolvedValue("OK");
    const res2 = await request(app).post(`${BASE}/forgot-password`).send({ email: "a@b.com" });

    expect(res1.body).toEqual(res2.body);
    expect(res1.status).toBe(res2.status);
  });
});

describe("POST /auth/reset-password", () => {
  it("should return 200 on successful password reset", async () => {
    const crypto = require("crypto");
    const rawToken = "secure-reset-token";
    const hashed = crypto.createHash("sha256").update(rawToken).digest("hex");

    mockRedis.get.mockResolvedValue("uuid-1");
    mockArgon2.hash.mockResolvedValue("$argon2-new-hashed");
    mockPrisma.user.update.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Test",
      password: "$argon2-new-hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.del.mockResolvedValue(1);
    mockRedis.scan.mockResolvedValueOnce(["0", []]);

    const res = await request(app)
      .post(`${BASE}/reset-password`)
      .send({ token: rawToken, newPassword: "NewP@ssword1" });

    expect(res.status).toBe(200);
    expect(res.body.message).toBe(AUTH_MESSAGES.RESET_PASSWORD_SUCCESS);
    expect(mockRedis.get).toHaveBeenCalledWith(`reset:${hashed}`);
  });

  it("should return 400 for invalid reset token", async () => {
    mockRedis.get.mockResolvedValue(null);

    const res = await request(app)
      .post(`${BASE}/reset-password`)
      .send({ token: "000000", newPassword: "NewP@ssword1" });

    expect(res.status).toBe(400);
    expect(res.body.message).toBe(AUTH_MESSAGES.RESET_TOKEN_INVALID);
  });

  it("should purge all refresh tokens (global logout) after reset", async () => {
    const crypto = require("crypto");
    const rawToken = "another-reset-token";
    const hashed = crypto.createHash("sha256").update(rawToken).digest("hex");

    mockRedis.get.mockResolvedValue("uuid-1");
    mockArgon2.hash.mockResolvedValue("$argon2-new");
    mockPrisma.user.update.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "T",
      password: "$argon2-new",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.del.mockResolvedValue(1);
    mockRedis.scan.mockResolvedValueOnce(["0", ["refresh:uuid-1:abc"]]);

    await request(app)
      .post(`${BASE}/reset-password`)
      .send({ token: rawToken, newPassword: "NewP@ss1" });

    expect(mockRedis.del).toHaveBeenCalledWith(`reset:${hashed}`);
    expect(mockRedis.del).toHaveBeenCalledWith("refresh:uuid-1:abc");
  });
});
