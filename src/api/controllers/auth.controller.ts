// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import * as authService from '@services/auth.service';
import * as oauthService from '@services/oauth.service';
import type { OAuthProvider } from 'types/auth';
import { AUTH_MESSAGES } from '@constants/messages';
import { VALID_PROVIDERS } from '@constants/auth';
import { StatusCodes } from 'http-status-codes';
import { env } from '@config/env';
import { buildRedirectUrl } from '@utils/redirect';


export async function signup(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const { email, password, name } = req.body;
        const response = await authService.signup({ email, password, name });
        res.status(StatusCodes.CREATED).json(response);
    } catch (err) {
        next(err);
    }
}

export async function login(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const { email, password } = req.body;
        const response = await authService.login({ email, password });
        res.status(StatusCodes.OK).json(response);
    } catch (err) {
        next(err);
    }
}

export async function refresh(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const { refreshToken } = req.body;
        const response = await authService.refresh(refreshToken);
        res.status(StatusCodes.OK).json(response);
    } catch (err) {
        next(err);
    }
}

export async function logout(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const { refreshToken } = req.body;
        if (refreshToken) {
            const response = await authService.logout(refreshToken);
            res.status(StatusCodes.OK).json(response);
        } else {
            res.status(StatusCodes.OK).json({ message: AUTH_MESSAGES.LOGOUT_SUCCESS });
        }
    } catch (err) {
        next(err);
    }
}

export async function forgotPassword(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const { email } = req.body;
        authService.forgotPassword({ email }).catch((err) => {
            console.error('Error processing forgot-password:', err);
        });
        res.status(StatusCodes.OK).json({ message: AUTH_MESSAGES.FORGOT_PASSWORD_SENT });
    } catch (err) {
        next(err);
    }
}

export async function resetPassword(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const { token, newPassword } = req.body;
        const response = await authService.resetPassword({ token, newPassword });
        res.status(StatusCodes.OK).json(response);
    } catch (err) {
        next(err);
    }
}

export async function oauthRedirect(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const provider = req.params.provider as OAuthProvider;
        if (!VALID_PROVIDERS.has(provider)) {
            res.status(StatusCodes.BAD_REQUEST).json({ message: AUTH_MESSAGES.UNSUPPORTED_OAUTH_PROVIDER });
            return;
        }

        const state = crypto.randomBytes(16).toString('hex');
        const url = oauthService.getAuthorizationUrl(provider, state);
        res.redirect(url);
    } catch (err) {
        next(err);
    }
}

export async function oauthCallback(req: Request, res: Response, next: NextFunction): Promise<void> {
    try {
        const provider = req.params.provider as OAuthProvider;
        if (!VALID_PROVIDERS.has(provider)) {
            res.status(StatusCodes.BAD_REQUEST).json({ message: AUTH_MESSAGES.UNSUPPORTED_OAUTH_PROVIDER });
            return;
        }

        const code = req.query.code as string | undefined;
        const oauthError = req.query.error as string | undefined;

        if (oauthError || !code) {
            const msg = oauthError === 'access_denied'
                ? AUTH_MESSAGES.OAUTH_CANCELLED
                : AUTH_MESSAGES.OAUTH_CODE_MISSING;
            const errorRedirect = buildRedirectUrl(env.FRONTEND_URL, '/login', { error: msg });
            res.redirect(errorRedirect);
            return;
        }

        const profile = await oauthService.exchangeCodeForProfile(provider, code);
        const loginResponse = await authService.oauthLogin(provider, profile);
        const { accessToken, refreshToken } = loginResponse.tokens!;

        const params = new URLSearchParams({
            accessToken,
            refreshToken,
            userId: loginResponse.user!.id,
            email: loginResponse.user!.email,
            name: loginResponse.user!.name,
        });

        const redirectUrl = buildRedirectUrl(env.FRONTEND_URL, '/oauth/callback', params);
        res.redirect(redirectUrl);
    } catch (err) {
        const message = err instanceof Error ? err.message : 'OAuth login failed';
        const errorRedirect = buildRedirectUrl(env.FRONTEND_URL, '/login', { error: message });
        res.redirect(errorRedirect);
    }
}
