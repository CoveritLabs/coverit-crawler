// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

// Auth domain — registers schemas and paths with the OpenAPI registry
import { z } from '@utils/zod';
import { registry } from './registry';
import {
    SignupRequestSchema,
    LoginRequestSchema,
    RefreshRequestSchema,
    ForgotPasswordRequestSchema,
    ResetPasswordRequestSchema,
} from '@models/auth';

const MessageResponseSchema = z.object({ message: z.string() });
const ErrorResponseSchema = z.object({ message: z.string() });
const UserInfoSchema = z.object({ id: z.string(), email: z.string(), name: z.string() });
const TokenPairSchema = z.object({ accessToken: z.string(), refreshToken: z.string() });
const LoginResponseSchema = z.object({ user: UserInfoSchema, tokens: TokenPairSchema });
const RefreshResponseSchema = z.object({ message: z.string(), tokens: TokenPairSchema });

registry.register('MessageResponse', MessageResponseSchema);
registry.register('ErrorResponse', ErrorResponseSchema);
registry.register('UserInfo', UserInfoSchema);
registry.register('TokenPair', TokenPairSchema);

registry.register('SignupRequest', SignupRequestSchema);
registry.register('LoginRequest', LoginRequestSchema);
registry.register('RefreshRequest', RefreshRequestSchema);
registry.register('ForgotPasswordRequest', ForgotPasswordRequestSchema);
registry.register('ResetPasswordRequest', ResetPasswordRequestSchema);
registry.register('LoginResponse', LoginResponseSchema);
registry.register('RefreshResponse', RefreshResponseSchema);

registry.registerPath({
    method: 'post',
    path: '/auth/signup',
    tags: ['Auth'],
    summary: 'Create a new account',
    description: 'Register a new user. No tokens are issued — the client must log in separately.',
    request: { body: { content: { 'application/json': { schema: SignupRequestSchema } } } },
    responses: {
        201: { description: 'Account created', content: { 'application/json': { schema: MessageResponseSchema } } },
        409: { description: 'Email already registered', content: { 'application/json': { schema: ErrorResponseSchema } } },
    },
});

registry.registerPath({
    method: 'post',
    path: '/auth/login',
    tags: ['Auth'],
    summary: 'Log in with email and password',
    description: 'Verify credentials and return access + refresh tokens with user info.',
    request: { body: { content: { 'application/json': { schema: LoginRequestSchema } } } },
    responses: {
        200: { description: 'Login successful', content: { 'application/json': { schema: LoginResponseSchema } } },
        401: { description: 'Invalid email or password', content: { 'application/json': { schema: ErrorResponseSchema } } },
    },
});

registry.registerPath({
    method: 'post',
    path: '/auth/refresh',
    tags: ['Auth'],
    summary: 'Rotate tokens',
    description: 'Exchange a valid refresh token for a new access + refresh token pair.',
    request: { body: { content: { 'application/json': { schema: RefreshRequestSchema } } } },
    responses: {
        200: { description: 'Tokens rotated', content: { 'application/json': { schema: RefreshResponseSchema } } },
        401: { description: 'Missing, invalid, or expired refresh token', content: { 'application/json': { schema: ErrorResponseSchema } } },
    },
});

registry.registerPath({
    method: 'post',
    path: '/auth/logout',
    tags: ['Auth'],
    summary: 'Log out',
    description: 'Invalidate the provided refresh token. The client should discard any stored tokens.',
    request: { body: { required: false, content: { 'application/json': { schema: RefreshRequestSchema.partial() } } } },
    responses: {
        200: { description: 'Logged out', content: { 'application/json': { schema: MessageResponseSchema } } },
    },
});

registry.registerPath({
    method: 'post',
    path: '/auth/forgot-password',
    tags: ['Auth'],
    summary: 'Request a password reset',
    description: 'Always returns 200 to prevent email enumeration. If the email exists, a reset link is sent.',
    request: { body: { content: { 'application/json': { schema: ForgotPasswordRequestSchema } } } },
    responses: {
        200: { description: 'Generic success (regardless of whether the email exists)', content: { 'application/json': { schema: MessageResponseSchema } } },
    },
});

registry.registerPath({
    method: 'post',
    path: '/auth/reset-password',
    tags: ['Auth'],
    summary: 'Reset password with a token',
    description: 'Validate the reset token, update the password, and invalidate all existing sessions for the user.',
    request: { body: { content: { 'application/json': { schema: ResetPasswordRequestSchema } } } },
    responses: {
        200: { description: 'Password reset successfully', content: { 'application/json': { schema: MessageResponseSchema } } },
        400: { description: 'Invalid or expired reset code', content: { 'application/json': { schema: ErrorResponseSchema } } },
    },
});
