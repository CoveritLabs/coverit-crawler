// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

/**
 * HTTP response message strings for the Auth domain.
 */
export const AUTH_MESSAGES = {
  // signup
  SIGNUP_SUCCESS: "Account created successfully",
  EMAIL_TAKEN: "Email already registered",

  // login
  INVALID_CREDENTIALS: "Invalid email or password",

  // refresh
  REFRESH_SUCCESS: "Tokens refreshed successfully",
  REFRESH_TOKEN_INVALID: "Invalid or expired refresh token",

  // logout
  LOGOUT_SUCCESS: "Logged out successfully",

  // forgot-password
  FORGOT_PASSWORD_SENT: "If an account with that email exists, a reset link was sent",

  // reset-password
  RESET_PASSWORD_SUCCESS: "Password reset successfully",
  RESET_TOKEN_INVALID: "Invalid or expired reset token",

  // oauth
  UNSUPPORTED_OAUTH_PROVIDER: "Unsupported OAuth provider",
  OAUTH_PROVIDER_NOT_CONFIGURED: "OAuth provider is not configured",
  OAUTH_CODE_MISSING: "Authorization code missing from callback",
  OAUTH_TOKEN_EXCHANGE_FAILED: "Failed to exchange authorization code for tokens",
  OAUTH_USER_INFO_FAILED: "Failed to retrieve user info from provider",
  OAUTH_EMAIL_MISSING: "OAuth provider did not return an email address",
  OAUTH_CANCELLED: "OAuth flow was cancelled by the user",
} as const;

/**
 * Zod schema validation error messages for the Auth domain.
 */
export const AUTH_VALIDATION = {
  INVALID_EMAIL: "Invalid email address",
  PASSWORD_MIN_LENGTH: "Password must be at least 8 characters",
  PASSWORD_REQUIRED: "Password is required",
  NAME_REQUIRED: "Name is required",
  REFRESH_TOKEN_REQUIRED: "Refresh token is required",
  RESET_TOKEN_REQUIRED: "Reset token is required",
} as const;
