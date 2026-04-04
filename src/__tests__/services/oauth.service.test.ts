// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { BadRequestError } from '@utils/errors';
import { AUTH_MESSAGES } from '@constants/messages';

jest.mock('@config/env', () => ({
    env: {
        NODE_ENV: 'test',
        GOOGLE_CLIENT_ID: 'google-id',
        GOOGLE_CLIENT_SECRET: 'google-secret',
        GOOGLE_CALLBACK_URL: 'https://app.example.com/oauth/google/callback',
        GITHUB_CLIENT_ID: 'github-id',
        GITHUB_CLIENT_SECRET: 'github-secret',
        GITHUB_CALLBACK_URL: 'https://app.example.com/oauth/github/callback',
    },
}));

import { getAuthorizationUrl, exchangeCodeForProfile } from '@services/oauth.service';

describe('oauth.service', () => {
    let fetchSpy: jest.SpyInstance;

    afterEach(() => {
        if (fetchSpy) fetchSpy.mockRestore();
    });

    test('getAuthorizationUrl builds google URL and includes access_type', () => {
        const url = getAuthorizationUrl('google', 'state123');
        expect(url).toContain('accounts.google.com');
        expect(url).toContain('client_id=google-id');
        expect(url).toContain('access_type=offline');
        expect(url).toContain('prompt=consent');
        expect(url).toContain('state=state123');
    });

    test('getAuthorizationUrl throws when provider not configured', () => {
        jest.resetModules();
        jest.doMock('@config/env', () => ({ env: { GOOGLE_CLIENT_ID: '', GOOGLE_CLIENT_SECRET: '' } }));
        const svc = require('@services/oauth.service');
        expect(() => svc.getAuthorizationUrl('google', 's')).toThrow(AUTH_MESSAGES.OAUTH_PROVIDER_NOT_CONFIGURED);
        jest.resetModules();
    });

    test('exchangeCodeForProfile throws when token endpoint returns non-ok', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch').mockImplementation(async () => ({ ok: false }));
        await expect(exchangeCodeForProfile('google', 'code')).rejects.toThrow(BadRequestError);
    });

    test('exchangeCodeForProfile throws when token response contains error', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch').mockImplementationOnce(async () => ({
            ok: true,
            json: async () => ({ error: 'bad' }),
        }));

        await expect(exchangeCodeForProfile('google', 'code')).rejects.toThrow(BadRequestError);
    });

    test('exchangeCodeForProfile returns google profile on success', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ access_token: 'tok' }) }))
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ email: 'a@example.com', name: 'Alice', id: 'google-123' }) }));

        const profile = await exchangeCodeForProfile('google', 'code');
        expect(profile.email).toBe('a@example.com');
        expect(profile.name).toBe('Alice');
        expect(profile.providerAccountId).toBe('google-123');
    });

    test('exchangeCodeForProfile returns github profile using emails endpoint when necessary', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ access_token: 'gh-token' }) }))
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ email: null, login: 'octocat', name: null, id: 12345 }) }))
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ([{ email: 'gh@example.com', primary: true, verified: true }]) }));

        const profile = await exchangeCodeForProfile('github', 'code');
        expect(profile.email).toBe('gh@example.com');
        expect(profile.name).toBe('octocat');
        expect(profile.providerAccountId).toBe('12345');
    });

    test('exchangeCodeForProfile throws when google userinfo endpoint fails', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ token_type: 'bearer' }) }));

        await expect(exchangeCodeForProfile('google', 'code')).rejects.toThrow(BadRequestError);
    });

    test('exchangeCodeForProfile throws when google userinfo endpoint fails2', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ access_token: 'tok' }) }))
            .mockImplementationOnce(async () => ({ ok: false }));

        await expect(exchangeCodeForProfile('google', 'code')).rejects.toThrow(BadRequestError);
    });

    test('exchangeCodeForProfile throws when google userinfo missing email', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ access_token: 'tok' }) }))
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ name: 'NoEmail' }) }));

        await expect(exchangeCodeForProfile('google', 'code')).rejects.toThrow(BadRequestError);
    });

    test('exchangeCodeForProfile throws when github user endpoint fails', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ access_token: 'gh-token' }) }))
            .mockImplementationOnce(async () => ({ ok: false }));

        await expect(exchangeCodeForProfile('github', 'code')).rejects.toThrow(BadRequestError);
    });

    test('exchangeCodeForProfile throws when github emails endpoint not ok and no email found', async () => {
        fetchSpy = jest.spyOn(global as any, 'fetch')
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ access_token: 'gh-token' }) }))
            .mockImplementationOnce(async () => ({ ok: true, json: async () => ({ email: null, login: 'octocat', name: null }) }))
            .mockImplementationOnce(async () => ({ ok: false }));

        await expect(exchangeCodeForProfile('github', 'code')).rejects.toThrow(BadRequestError);
    });
});
