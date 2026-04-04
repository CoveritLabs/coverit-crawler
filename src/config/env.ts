// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

export const env = {
  NODE_ENV: process.env.NODE_ENV ?? "development",
  PORT: parseInt(process.env.PORT ?? "3000", 10),
  DATABASE_URL: process.env.DATABASE_URL ?? "",
  REDIS_URL: process.env.REDIS_URL ?? "redis://localhost:6379",
  CORS_ORIGINS: (process.env.CORS_ORIGINS ?? "http://localhost:5173").split(","),
  CORS_CREDENTIALS: process.env.CORS_CREDENTIALS ?? "true",
  JWT_SECRET: process.env.JWT_SECRET ?? "",
  JWT_ACCESS_EXPIRY: process.env.JWT_ACCESS_EXPIRY ?? "15m",
  JWT_REFRESH_EXPIRY_SECONDS: parseInt(process.env.JWT_REFRESH_EXPIRY_SECONDS ?? "604800", 10), // 7 days
  RESET_TOKEN_TTL_SECONDS: parseInt(process.env.RESET_TOKEN_TTL_SECONDS ?? "900", 10), // 15 min
  API_PREFIX: process.env.API_PREFIX ?? "/api/v1",

  // OAuth
  FRONTEND_URL: process.env.FRONTEND_URL ?? "http://localhost:5173",
  GOOGLE_CLIENT_ID: process.env.GOOGLE_CLIENT_ID ?? "",
  GOOGLE_CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET ?? "",
  GOOGLE_CALLBACK_URL: process.env.GOOGLE_CALLBACK_URL ?? "http://localhost:3000/api/v1/auth/oauth/google/callback",
  GITHUB_CLIENT_ID: process.env.GITHUB_CLIENT_ID ?? "",
  GITHUB_CLIENT_SECRET: process.env.GITHUB_CLIENT_SECRET ?? "",
  GITHUB_CALLBACK_URL: process.env.GITHUB_CALLBACK_URL ?? "http://localhost:3000/api/v1/auth/oauth/github/callback",

  // Emails
  RESEND_API_KEY: process.env.RESEND_API_KEY ?? "",
  RESET_PASSWORD_EMAIL: process.env.RESET_PASSWORD_EMAIL ?? "Coverit <support@updates.coverit.cyou>",
  RESET_PASSWORD_TEMPLATE_ID: process.env.RESET_PASSWORD_TEMPLATE_ID ?? "",
} as const;

console.info("Loaded environment variables:", {
  NODE_ENV: env.NODE_ENV,
  PORT: env.PORT,
  DATABASE_URL: env.DATABASE_URL ? "****" : "(not set)",
  REDIS_URL: env.REDIS_URL ? "****" : "(not set)",
  CORS_ORIGINS: env.CORS_ORIGINS,
  CORS_CREDENTIALS: env.CORS_CREDENTIALS,
  JWT_SECRET: env.JWT_SECRET ? "****" : "(not set)",
  JWT_ACCESS_EXPIRY: env.JWT_ACCESS_EXPIRY,
  JWT_REFRESH_EXPIRY_SECONDS: env.JWT_REFRESH_EXPIRY_SECONDS,
  RESET_TOKEN_TTL_SECONDS: env.RESET_TOKEN_TTL_SECONDS,
  API_PREFIX: env.API_PREFIX,
  FRONTEND_URL: env.FRONTEND_URL,
  GOOGLE_CLIENT_ID: env.GOOGLE_CLIENT_ID ? "****" : "(not set)",
  GOOGLE_CLIENT_SECRET: env.GOOGLE_CLIENT_SECRET ? "****" : "(not set)",
  GOOGLE_CALLBACK_URL: env.GOOGLE_CALLBACK_URL,
  GITHUB_CLIENT_ID: env.GITHUB_CLIENT_ID ? "****" : "(not set)",
  GITHUB_CLIENT_SECRET: env.GITHUB_CLIENT_SECRET ? "****" : "(not set)",
  GITHUB_CALLBACK_URL: env.GITHUB_CALLBACK_URL,
  RESEND_API_KEY: env.RESEND_API_KEY ? "****" : "(not set)",
  RESET_PASSWORD_EMAIL: env.RESET_PASSWORD_EMAIL,
  RESET_PASSWORD_TEMPLATE_ID: env.RESET_PASSWORD_TEMPLATE_ID ? "****" : "(not set)",
});