// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { env } from '@config/env';
import { BadRequestError } from '@utils/errors';
import { AUTH_MESSAGES } from '@constants/messages';
import type { OAuthProvider, OAuthUserProfile, OAuthProviderConfig } from 'types/auth';

function getProviderConfig(provider: OAuthProvider): OAuthProviderConfig {
    switch (provider) {
        case 'google':
            return {
                clientId: env.GOOGLE_CLIENT_ID,
                clientSecret: env.GOOGLE_CLIENT_SECRET,
                callbackUrl: env.GOOGLE_CALLBACK_URL,
                authorizeUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
                tokenUrl: 'https://oauth2.googleapis.com/token',
                scope: 'openid email profile',
                fetchProfile: fetchGoogleProfile,
            };
        case 'github':
            return {
                clientId: env.GITHUB_CLIENT_ID,
                clientSecret: env.GITHUB_CLIENT_SECRET,
                callbackUrl: env.GITHUB_CALLBACK_URL,
                authorizeUrl: 'https://github.com/login/oauth/authorize',
                tokenUrl: 'https://github.com/login/oauth/access_token',
                scope: 'read:user user:email',
                fetchProfile: fetchGitHubProfile,
            };
    }
}

export function getAuthorizationUrl(provider: OAuthProvider, state: string): string {
    const config = getProviderConfig(provider);

    if (!config.clientId) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_PROVIDER_NOT_CONFIGURED);
    }

    const params = new URLSearchParams({
        client_id: config.clientId,
        redirect_uri: config.callbackUrl,
        response_type: 'code',
        scope: config.scope,
        state,
    });

    if (provider === 'google') {
        params.set('access_type', 'offline');
        params.set('prompt', 'consent');
    }

    return `${config.authorizeUrl}?${params.toString()}`;
}

export async function exchangeCodeForProfile(
    provider: OAuthProvider,
    code: string,
): Promise<OAuthUserProfile> {
    const config = getProviderConfig(provider);

    const tokenBody: Record<string, string> = {
        client_id: config.clientId,
        client_secret: config.clientSecret,
        code,
        redirect_uri: config.callbackUrl,
        grant_type: 'authorization_code',
    };

    const tokenHeaders: Record<string, string> = {
        'Content-Type': 'application/x-www-form-urlencoded',
    };

    if (provider === 'github') {
        tokenHeaders['Accept'] = 'application/json';
    }

    const tokenRes = await fetch(config.tokenUrl, {
        method: 'POST',
        headers: tokenHeaders,
        body: new URLSearchParams(tokenBody).toString(),
    });

    if (!tokenRes.ok) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_TOKEN_EXCHANGE_FAILED);
    }

    const tokenData = (await tokenRes.json()) as Record<string, string>;

    if (tokenData.error) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_TOKEN_EXCHANGE_FAILED);
    }

    const accessToken: string = tokenData.access_token;

    if (!accessToken) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_TOKEN_EXCHANGE_FAILED);
    }

    return config.fetchProfile(accessToken);
}

async function fetchGoogleProfile(accessToken: string): Promise<OAuthUserProfile> {
    const res = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
        headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!res.ok) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_USER_INFO_FAILED);
    }

    const data = (await res.json()) as Record<string, string>;
    if (!data.email) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_EMAIL_MISSING);
    }

    return { email: data.email, name: data.name ?? data.email, providerAccountId: data.id };
}

async function fetchGitHubProfile(accessToken: string): Promise<OAuthUserProfile> {
    const headers = {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/vnd.github+json',
    };

    const userRes = await fetch('https://api.github.com/user', { headers });
    if (!userRes.ok) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_USER_INFO_FAILED);
    }
    const userData = (await userRes.json()) as Record<string, string | null>;

    let email: string | null = userData.email ?? null;

    if (!email) {
        const emailRes = await fetch('https://api.github.com/user/emails', { headers });
        if (emailRes.ok) {
            const emails = (await emailRes.json()) as Array<{ email: string; primary: boolean; verified: boolean }>;
            const primary = emails.find((e) => e.primary && e.verified);
            email = primary?.email ?? emails[0]?.email ?? null;
        }
    }

    if (!email) {
        throw new BadRequestError(AUTH_MESSAGES.OAUTH_EMAIL_MISSING);
    }

    return { email, name: (userData.name ?? userData.login ?? email) as string, providerAccountId: String(userData.id) };
}
