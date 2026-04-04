// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

export class AppError extends Error {
    constructor(
        public readonly statusCode: number,
        message: string,
    ) {
        super(message);
        this.name = 'AppError';
    }
}

export class UnauthorizedError extends AppError {
    constructor(message = 'Unauthorized') {
        super(401, message);
        this.name = 'UnauthorizedError';
    }
}

export class BadRequestError extends AppError {
    constructor(message = 'Bad request') {
        super(400, message);
        this.name = 'BadRequestError';
    }
}

export class ConflictError extends AppError {
    constructor(message = 'Conflict') {
        super(409, message);
        this.name = 'ConflictError';
    }
}
