// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { Request, Response, NextFunction } from 'express';
import { verifyAccessToken } from '@utils/token';
import { UnauthorizedError } from '@utils/errors';

export function requireAuth(req: Request, _res: Response, next: NextFunction): void {
    try {
        const header = req.headers.authorization;
        if (!header || !header.startsWith('Bearer ')) {
            throw new UnauthorizedError('Authentication required');
        }
        const token = header.slice(7);
        req.userId = verifyAccessToken(token);
        next();
    } catch {
        next(new UnauthorizedError('Invalid or expired access token'));
    }
}
