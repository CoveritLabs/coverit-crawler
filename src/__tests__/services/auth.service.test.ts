// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

/**
 * @file Unit tests for auth.service and token utilities.
 */

import argon2 from "argon2";
import crypto from "crypto";
import jwt from "jsonwebtoken";

jest.mock("@lib/prisma", () => require("../mocks/prisma"));
jest.mock("@lib/redis", () => require("../mocks/redis"));
jest.mock("@queues/email.queue", () => ({
  emailQueue: {
    add: jest.fn(),
  },
}));
jest.mock("@config/env", () => ({
  env: {
    JWT_SECRET: "test-secret",
    JWT_ACCESS_EXPIRY: "15m",
    JWT_REFRESH_EXPIRY_SECONDS: 604800,
    RESET_TOKEN_TTL_SECONDS: 3600,
    FRONTEND_URL: "https://app.example.com",
  },
}));

import { AUTH_MESSAGES } from "@constants/messages";
import prisma from "@lib/prisma";
import redis from "@lib/redis";
import * as authService from "@services/auth.service";
import { verifyAccessToken } from "@utils/token";
import { emailQueue } from "@queues/email.queue";

const mockPrisma = prisma as any; // eslint-disable-line @typescript-eslint/no-explicit-any
const mockRedis = redis as any; // eslint-disable-line @typescript-eslint/no-explicit-any
const mockEmailQueue = emailQueue as any; // eslint-disable-line @typescript-eslint/no-explicit-any

function hashToken(token: string): string {
  return crypto.createHash("sha256").update(token).digest("hex");
}

describe("authService.signup", () => {
  it("should create a user with hashed password", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);
    mockPrisma.user.create.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Test",
      password: "hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    await authService.signup({ email: "a@b.com", password: "P@ssword1", name: "Test" });

    expect(mockPrisma.user.findUnique).toHaveBeenCalledWith({ where: { email: "a@b.com" } });
    expect(mockPrisma.user.create).toHaveBeenCalledTimes(1);

    const createCall = mockPrisma.user.create.mock.calls[0][0];
    expect(createCall.data.password).not.toBe("P@ssword1");
    expect(createCall.data.password).toMatch(/^\$argon2/);
  });

  it("should throw ConflictError if email already exists", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Existing",
      password: "hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    await expect(authService.signup({ email: "a@b.com", password: "P@ssword1", name: "Test" })).rejects.toThrow(
      AUTH_MESSAGES.EMAIL_TAKEN,
    );
  });
});

describe("authService.login", () => {
  const hashedPw = argon2.hash("P@ssword1");

  it("should return tokens and user info on valid credentials", async () => {
    const pw = await hashedPw;
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Test",
      password: pw,
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.set.mockResolvedValue("OK");

    const result = await authService.login({ email: "a@b.com", password: "P@ssword1" });

    expect(result.user).toEqual({ id: "uuid-1", email: "a@b.com", name: "Test" });
    expect(result.tokens?.accessToken).toBeDefined();
    expect(result.tokens?.refreshToken).toBeDefined();

    const decoded = jwt.verify(result.tokens!.accessToken, "test-secret") as jwt.JwtPayload;
    expect(decoded.sub).toBe("uuid-1");

    expect(mockRedis.set).toHaveBeenCalledWith(expect.stringContaining("refresh:uuid-1:"), "1", "EX", 604800);
  });

  it("should throw UnauthorizedError if user not found", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);

    await expect(authService.login({ email: "no@one.com", password: "P@ssword1" })).rejects.toThrow(
      AUTH_MESSAGES.INVALID_CREDENTIALS,
    );
  });

  it("should throw UnauthorizedError if password is wrong", async () => {
    const pw = await hashedPw;
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Test",
      password: pw,
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    await expect(authService.login({ email: "a@b.com", password: "WrongPassword" })).rejects.toThrow(
      AUTH_MESSAGES.INVALID_CREDENTIALS,
    );
  });
});

describe("authService.refresh", () => {
  it("should rotate tokens and return new pair", async () => {
    const rawToken = "old-refresh-token";
    const hashed = hashToken(rawToken);
    const key = `refresh:uuid-1:${hashed}`;

    mockRedis.scan.mockResolvedValueOnce(["0", [key]]);
    mockRedis.del.mockResolvedValue(1);
    mockRedis.set.mockResolvedValue("OK");

    const result = await authService.refresh(rawToken);

    expect(result.tokens?.accessToken).toBeDefined();
    expect(result.tokens?.refreshToken).toBeDefined();
    expect(mockRedis.del).toHaveBeenCalledWith(key);
    expect(mockRedis.set).toHaveBeenCalledWith(expect.stringContaining("refresh:uuid-1:"), "1", "EX", 604800);
  });

  it("should throw UnauthorizedError if refresh token not found in Redis", async () => {
    mockRedis.scan.mockResolvedValue(["0", []]);

    await expect(authService.refresh("bad-token")).rejects.toThrow(AUTH_MESSAGES.REFRESH_TOKEN_INVALID);
  });
});

describe("authService.logout", () => {
  it("should delete the refresh token from Redis", async () => {
    const rawToken = "some-refresh-token";
    const hashed = hashToken(rawToken);
    const key = `refresh:uuid-1:${hashed}`;

    mockRedis.scan.mockResolvedValueOnce(["0", [key]]);
    mockRedis.del.mockResolvedValue(1);

    await authService.logout(rawToken);

    expect(mockRedis.del).toHaveBeenCalledWith(key);
  });

  it("should be a no-op if token not found in Redis", async () => {
    mockRedis.scan.mockResolvedValue(["0", []]);

    await expect(authService.logout("unknown-token")).resolves.toMatchObject({ message: AUTH_MESSAGES.LOGOUT_SUCCESS });
  });
});

describe("authService.forgotPassword", () => {
  it("should store a hashed reset token in Redis and enqueue email when user has a password", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Test",
      password: "hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.set.mockResolvedValue("OK");

    await authService.forgotPassword({ email: "a@b.com" });

    expect(mockRedis.set).toHaveBeenCalledWith(expect.stringContaining("reset:"), "uuid-1", "EX", 3600);

    expect(mockEmailQueue.add).toHaveBeenCalledWith(
      "send-reset-email",
      expect.objectContaining({
        userId: "uuid-1",
        email: "a@b.com",
        name: "Test",
        resetUrl: expect.stringContaining("https://app.example.com/reset-password?token="),
      }),
    );
  });

  it("should store a hashed reset token in Redis and enqueue email when use has no password", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-1",
      email: "oauth@b.com",
      name: "OAuth User",
      password: null,
      createdAt: new Date(),
      updatedAt: new Date(),
    });

    await authService.forgotPassword({ email: "oauth@b.com" });

    expect(mockRedis.set).toHaveBeenCalledWith(expect.stringContaining("reset:"), "uuid-1", "EX", 3600);
    expect(mockEmailQueue.add).toHaveBeenCalledWith(
      "send-reset-email",
      expect.objectContaining({
        userId: "uuid-1",
        email: "oauth@b.com",
        name: "OAuth User",
        resetUrl: expect.stringContaining("https://app.example.com/reset-password?token="),
      }),
    );
  });

  it("should do nothing (no throw) if user does not exist", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);

    await expect(authService.forgotPassword({ email: "no@one.com" })).resolves.toBeUndefined();
    expect(mockRedis.set).not.toHaveBeenCalled();
  });
});

describe("authService.resetPassword", () => {
  it("should update password, delete reset token from Redis, and purge all refresh tokens", async () => {
    const rawToken = "reset-token-raw";
    const hashed = hashToken(rawToken);

    mockRedis.get.mockResolvedValue("uuid-1");
    mockPrisma.user.update.mockResolvedValue({
      id: "uuid-1",
      email: "a@b.com",
      name: "Test",
      password: "new-hashed",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockRedis.del.mockResolvedValue(1);
    mockRedis.scan.mockResolvedValueOnce(["0", ["refresh:uuid-1:abc", "refresh:uuid-1:def"]]);

    await authService.resetPassword({ token: rawToken, newPassword: "NewP@ss1" });

    expect(mockRedis.get).toHaveBeenCalledWith(`reset:${hashed}`);
    expect(mockPrisma.user.update).toHaveBeenCalledWith({
      where: { id: "uuid-1" },
      data: { password: expect.stringMatching(/^\$argon2/) },
    });
    expect(mockRedis.del).toHaveBeenCalledWith(`reset:${hashed}`);
    expect(mockRedis.del).toHaveBeenCalledWith("refresh:uuid-1:abc", "refresh:uuid-1:def");
  });

  it("should throw BadRequestError if reset token not found in Redis", async () => {
    mockRedis.get.mockResolvedValue(null);

    await expect(authService.resetPassword({ token: "bad-token", newPassword: "NewP@ss1" })).rejects.toThrow(
      AUTH_MESSAGES.RESET_TOKEN_INVALID,
    );
  });
});

describe("verifyAccessToken", () => {
  it("should return userId from valid token", () => {
    const token = jwt.sign({ sub: "uuid-1" }, "test-secret", { expiresIn: "15m" });
    expect(verifyAccessToken(token)).toBe("uuid-1");
  });

  it("should throw UnauthorizedError for expired token", () => {
    const token = jwt.sign({ sub: "uuid-1" }, "test-secret", { expiresIn: "-1s" });
    expect(() => verifyAccessToken(token)).toThrow();
  });

  it("should throw UnauthorizedError for invalid signature", () => {
    const token = jwt.sign({ sub: "uuid-1" }, "wrong-secret");
    expect(() => verifyAccessToken(token)).toThrow();
  });

  it("should throw UnauthorizedError for token without sub", () => {
    const token = jwt.sign({ foo: "bar" }, "test-secret");
    expect(() => verifyAccessToken(token)).toThrow("Malformed token");
  });
});

describe("authService.oauthLogin", () => {
  it("should create a new user and account when none exists and return tokens", async () => {
    mockPrisma.user.findUnique.mockResolvedValue(null);
    mockPrisma.user.create.mockResolvedValue({
      id: "uuid-2",
      email: "oauth@user.com",
      name: "OAuth User",
      createdAt: new Date(),
      updatedAt: new Date(),
    });
    mockPrisma.account.create.mockResolvedValue({
      id: "acc-1",
      userId: "uuid-2",
      provider: "google",
      providerAccountId: "google-id-123",
    });
    mockRedis.set.mockResolvedValue("OK");

    const res = await authService.oauthLogin("google", {
      email: "oauth@user.com",
      name: "OAuth User",
      providerAccountId: "google-id-123",
    });

    expect(mockPrisma.$transaction).toHaveBeenCalled();
    expect(mockPrisma.user.create).toHaveBeenCalled();
    expect(mockPrisma.account.create).toHaveBeenCalled();
    expect(res.user).toEqual({ id: "uuid-2", email: "oauth@user.com", name: "OAuth User" });
    expect(res.tokens?.accessToken).toBeDefined();
    expect(res.tokens?.refreshToken).toBeDefined();
    expect(mockRedis.set).toHaveBeenCalledWith(expect.stringContaining("refresh:uuid-2:"), "1", "EX", 604800);
  });

  it("should link a new account when user exists but has no account for this provider", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-3",
      email: "exist@user.com",
      name: "Existing",
    });
    mockPrisma.account.findFirst.mockResolvedValue(null);
    mockPrisma.account.create.mockResolvedValue({
      id: "acc-2",
      userId: "uuid-3",
      provider: "google",
      providerAccountId: "google-id-456",
    });
    mockRedis.set.mockResolvedValue("OK");

    const res = await authService.oauthLogin("google", {
      email: "exist@user.com",
      name: "Existing",
      providerAccountId: "google-id-456",
    });

    expect(mockPrisma.user.create).not.toHaveBeenCalled();
    expect(mockPrisma.account.findFirst).toHaveBeenCalledWith({
      where: { userId: "uuid-3", provider: "google" },
    });
    expect(mockPrisma.account.create).toHaveBeenCalledWith({
      data: { userId: "uuid-3", provider: "google", providerAccountId: "google-id-456" },
    });
    expect(res.user).toEqual({ id: "uuid-3", email: "exist@user.com", name: "Existing" });
    expect(res.tokens?.accessToken).toBeDefined();
  });

  it("should just log in when user and account already exist", async () => {
    mockPrisma.user.findUnique.mockResolvedValue({
      id: "uuid-3",
      email: "exist@user.com",
      name: "Existing",
    });
    mockPrisma.account.findFirst.mockResolvedValue({
      id: "acc-2",
      userId: "uuid-3",
      provider: "google",
      providerAccountId: "google-id-456",
    });
    mockRedis.set.mockResolvedValue("OK");

    const res = await authService.oauthLogin("google", {
      email: "exist@user.com",
      name: "Existing",
      providerAccountId: "google-id-456",
    });

    expect(mockPrisma.user.create).not.toHaveBeenCalled();
    expect(mockPrisma.account.create).not.toHaveBeenCalled();
    expect(res.user).toEqual({ id: "uuid-3", email: "exist@user.com", name: "Existing" });
    expect(res.tokens?.accessToken).toBeDefined();
    expect(res.tokens?.refreshToken).toBeDefined();
  });
});
