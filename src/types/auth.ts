// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

export type OAuthProvider = 'google' | 'github';

export interface OAuthUserProfile {
    email: string;
    name: string;
    providerAccountId: string;
}

export interface OAuthProviderConfig {
    clientId: string;
    clientSecret: string;
    callbackUrl: string;
    authorizeUrl: string;
    tokenUrl: string;
    scope: string;
    fetchProfile: (accessToken: string) => Promise<OAuthUserProfile>;
}
