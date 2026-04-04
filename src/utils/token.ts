// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import crypto from 'crypto';
import jwt from 'jsonwebtoken';

import { env } from '@config/env';
import { UnauthorizedError } from '@utils/errors';

export function generateAccessToken(userId: string): string {
    return jwt.sign({ sub: userId }, env.JWT_SECRET, {
        expiresIn: env.JWT_ACCESS_EXPIRY as jwt.SignOptions['expiresIn'],
    });
}

export function generateRefreshToken(): string {
    return crypto.randomBytes(48).toString('base64url');
}

export function hashToken(token: string): string {
    return crypto.createHash('sha256').update(token).digest('hex');
}

/** Verify an access token and return the userId. Throws on invalid/expired tokens. */
export function verifyAccessToken(token: string): string {
    const payload = jwt.verify(token, env.JWT_SECRET) as jwt.JwtPayload;
    if (!payload.sub) {
        throw new UnauthorizedError('Malformed token');
    }
    return payload.sub;
}
