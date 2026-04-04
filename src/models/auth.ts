// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

// Auth domain DTOs

import { AUTH_VALIDATION } from "@constants/messages";
import type {
  ForgotPasswordRequest as ContractForgotPasswordRequest,
  LoginRequest as ContractLoginRequest,
  LoginResponse as ContractLoginResponse,
  RefreshRequest as ContractRefreshRequest,
  RefreshResponse as ContractRefreshResponse,
  ResetPasswordRequest as ContractResetPasswordRequest,
  SignupRequest as ContractSignupRequest,
  TokenPair as ContractTokenPair,
} from "@coveritlabs/contracts";
import { z } from "@utils/zod";
import type { ZodType } from "zod";
import type { Plain } from "./common";

export type SignupRequest = Plain<ContractSignupRequest>;
export type LoginRequest = Plain<ContractLoginRequest>;
export type LoginResponse = Plain<ContractLoginResponse>;
export type RefreshResponse = Plain<ContractRefreshResponse>;
export type ForgotPasswordRequest = Plain<ContractForgotPasswordRequest>;
export type ResetPasswordRequest = Plain<ContractResetPasswordRequest>;
export type TokenPair = Plain<ContractTokenPair>;
export type RefreshRequest = Plain<ContractRefreshRequest>;

export const SignupRequestSchema = z.object({
  email: z.email(AUTH_VALIDATION.INVALID_EMAIL),
  password: z.requiredString(AUTH_VALIDATION.PASSWORD_REQUIRED).min(8, AUTH_VALIDATION.PASSWORD_MIN_LENGTH),
  name: z.requiredString(AUTH_VALIDATION.NAME_REQUIRED),
}) satisfies ZodType<SignupRequest>;

export const LoginRequestSchema = z.object({
  email: z.email(AUTH_VALIDATION.INVALID_EMAIL),
  password: z.requiredString(AUTH_VALIDATION.PASSWORD_REQUIRED),
}) satisfies ZodType<LoginRequest>;

export const ForgotPasswordRequestSchema = z.object({
  email: z.email(AUTH_VALIDATION.INVALID_EMAIL),
}) satisfies ZodType<ForgotPasswordRequest>;

export const ResetPasswordRequestSchema = z.object({
  token: z.requiredString(AUTH_VALIDATION.RESET_TOKEN_REQUIRED),
  newPassword: z.requiredString(AUTH_VALIDATION.PASSWORD_REQUIRED).min(8, AUTH_VALIDATION.PASSWORD_MIN_LENGTH),
}) satisfies ZodType<ResetPasswordRequest>;

export const RefreshRequestSchema = z.object({
  refreshToken: z.requiredString(AUTH_VALIDATION.REFRESH_TOKEN_REQUIRED),
}) satisfies ZodType<RefreshRequest>;
