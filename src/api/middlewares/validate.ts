// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { Request, Response, NextFunction } from 'express';
import { StatusCodes } from 'http-status-codes';
import { ZodType } from 'zod';

/**
 * Generic request body validation middleware factory.
 * Parses `req.body` against the provided Zod schema.
 * On success, replaces `req.body` with the parsed (stripped/coerced) data.
 * On failure, responds 400 with the first validation error.
 */
export function validateBody<T>(schema: ZodType<T>) {
    return (req: Request, res: Response, next: NextFunction): void => {
        const result = schema.safeParse(req.body);
        if (!result.success) {
            const firstIssue = result.error.issues[0];
            res.status(StatusCodes.BAD_REQUEST).json({
                error: 'Validation failed',
                message: firstIssue?.message ?? 'Invalid request body',
            });
            return;
        }
        req.body = result.data;
        next();
    };
}
