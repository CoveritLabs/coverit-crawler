// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import express from "express";
import request from "supertest";

jest.mock("@services/auth.service");
jest.mock("@services/oauth.service");
jest.mock("@config/env", () => ({ env: { FRONTEND_URL: "https://app.example.com" } }));
jest.mock("@queues/email.queue", () => ({
  emailQueue: {
    add: jest.fn(),
  },
}));

import * as authService from "@services/auth.service";
import * as oauthService from "@services/oauth.service";
import { buildRedirectUrl } from "@utils/redirect";
import { env } from "@config/env";
import {
  signup,
  login,
  refresh,
  logout,
  forgotPassword,
  resetPassword,
  oauthRedirect,
  oauthCallback,
} from "@api/controllers/auth.controller";
import { AUTH_MESSAGES } from "@constants/messages";

function makeApp() {
  const a = express();
  a.use(express.json());
  a.post("/signup", signup);
  a.post("/login", login);
  a.post("/refresh", refresh);
  a.post("/logout", logout);
  a.post("/forgot", forgotPassword);
  a.post("/reset", resetPassword);
  a.get("/oauth/:provider/redirect", oauthRedirect);
  a.get("/oauth/:provider/callback", oauthCallback);
  return a;
}

describe("auth.controller", () => {
  let app: express.Application;

  beforeEach(() => {
    jest.resetAllMocks();
    app = makeApp();
  });

  test("signup returns 201 on success", async () => {
    (authService.signup as jest.Mock).mockResolvedValue({ message: "ok" });
    const res = await request(app).post("/signup").send({ email: "a@b.com", password: "p", name: "n" });
    expect(res.status).toBe(201);
    expect(res.body).toEqual({ message: "ok" });
  });

  test("login returns 200 on success", async () => {
    (authService.login as jest.Mock).mockResolvedValue({ tokens: {}, user: {} });
    const res = await request(app).post("/login").send({ email: "a@b.com", password: "p" });
    expect(res.status).toBe(200);
  });

  test("refresh returns 200 on success", async () => {
    (authService.refresh as jest.Mock).mockResolvedValue({ tokens: {} });
    const res = await request(app).post("/refresh").send({ refreshToken: "rt" });
    expect(res.status).toBe(200);
  });

  test("logout with refreshToken calls service", async () => {
    (authService.logout as jest.Mock).mockResolvedValue({ message: "logged out" });
    const res = await request(app).post("/logout").send({ refreshToken: "x" });
    expect(res.status).toBe(200);
    expect(authService.logout).toHaveBeenCalledWith("x");
  });

  test("logout without refreshToken returns success message", async () => {
    const res = await request(app).post("/logout").send({});
    expect(res.status).toBe(200);
    expect(res.body.message).toBe(AUTH_MESSAGES.LOGOUT_SUCCESS);
  });

  test("forgotPassword triggers service and returns 200", async () => {
    (authService.forgotPassword as jest.Mock).mockResolvedValue(undefined);
    const res = await request(app).post("/forgot").send({ email: "a@b.com" });
    expect(res.status).toBe(200);
    expect(authService.forgotPassword).toHaveBeenCalledWith({ email: "a@b.com" });
  });

  test("resetPassword returns 200 on success", async () => {
    (authService.resetPassword as jest.Mock).mockResolvedValue({ message: "ok" });
    const res = await request(app).post("/reset").send({ token: "t", newPassword: "np" });
    expect(res.status).toBe(200);
  });

  test("oauthRedirect returns 400 for unsupported provider", async () => {
    const res = await request(app).get("/oauth/unknown/redirect");
    expect(res.status).toBe(400);
    expect(res.body.message).toBe(AUTH_MESSAGES.UNSUPPORTED_OAUTH_PROVIDER);
  });

  test("oauthRedirect redirects to provider authorization url", async () => {
    (oauthService.getAuthorizationUrl as jest.Mock).mockReturnValue("https://auth.example");
    const res = await request(app).get("/oauth/google/redirect");
    expect(res.status).toBe(302);
    expect(res.header.location).toBe("https://auth.example");
  });

  test("oauthCallback redirects to login when code missing", async () => {
    const res = await request(app).get("/oauth/google/callback");
    expect(res.status).toBe(302);
    expect(res.header.location).toBe(
      buildRedirectUrl(env.FRONTEND_URL, "/login", { error: AUTH_MESSAGES.OAUTH_CODE_MISSING }),
    );
  });

  test("oauthCallback redirects back to frontend on success", async () => {
    (oauthService.exchangeCodeForProfile as jest.Mock).mockResolvedValue({ email: "a@b.com", name: "A" });
    (authService.oauthLogin as jest.Mock).mockResolvedValue({
      tokens: { accessToken: "a", refreshToken: "r" },
      user: { id: "u", email: "a@b.com", name: "A" },
    });
    const res = await request(app).get("/oauth/google/callback").query({ code: "c" });
    expect(res.status).toBe(302);
    expect(res.header.location).toContain(`${env.FRONTEND_URL}/oauth/callback?`);
  });

  test("oauthCallback redirects to login with error when exchange fails", async () => {
    (oauthService.exchangeCodeForProfile as jest.Mock).mockRejectedValue(new Error("fail"));
    const res = await request(app).get("/oauth/google/callback").query({ code: "c" });
    expect(res.status).toBe(302);
    expect(res.header.location).toBe(buildRedirectUrl(env.FRONTEND_URL, "/login", { error: "fail" }));
  });

  describe("error handling catch blocks", () => {
    test("signup next(err) on service failure", async () => {
      (authService.signup as jest.Mock).mockRejectedValue(new Error("signup fail"));
      const res = await request(app).post("/signup").send({});
      expect(res.status).toBe(500); 
    });

    test("login next(err)", async () => {
      (authService.login as jest.Mock).mockRejectedValue(new Error("login fail"));
      const res = await request(app).post("/login").send({});
      expect(res.status).toBe(500); 
    });

    test("refresh next(err)", async () => {
      (authService.refresh as jest.Mock).mockRejectedValue(new Error("refresh fail"));
      const res = await request(app).post("/refresh").send({});
      expect(res.status).toBe(500); 
    });

    test("logout next(err)", async () => {
      (authService.logout as jest.Mock).mockRejectedValue(new Error("logout fail"));
      const res = await request(app).post("/logout").send({ refreshToken: "x" });
      expect(res.status).toBe(500); 
    });

    test("forgotPassword next(err)", async () => {
      const mockReq = { body: {} } as any;
      const mockRes = {} as any;
      const nextFn = jest.fn();
      
      const originalForgot = authService.forgotPassword;
      Object.defineProperty(authService, "forgotPassword", { value: () => { throw new Error("sync throw"); } });
      
      await forgotPassword(mockReq, mockRes, nextFn);
      expect(nextFn).toHaveBeenCalledWith(new Error("sync throw"));
      
      Object.defineProperty(authService, "forgotPassword", { value: originalForgot });
    });

    test("resetPassword next(err)", async () => {
      (authService.resetPassword as jest.Mock).mockRejectedValue(new Error("reset fail"));
      const res = await request(app).post("/reset").send({});
      expect(res.status).toBe(500); 
    });
    
    test("oauthRedirect next(err)", async () => {
        const mockReq = { params: { provider: "google" } } as any;
        const mockRes = {} as any;
        const nextFn = jest.fn();
        
        const originalRedirect = oauthService.getAuthorizationUrl;
        Object.defineProperty(oauthService, "getAuthorizationUrl", { value: () => { throw new Error("sync throw auth"); } });
        
        await oauthRedirect(mockReq, mockRes, nextFn);
        expect(nextFn).toHaveBeenCalledWith(new Error("sync throw auth"));
        
        Object.defineProperty(oauthService, "getAuthorizationUrl", { value: originalRedirect });
      });
  });
});
