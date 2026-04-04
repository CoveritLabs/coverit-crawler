// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import 'dotenv/config';
import app from './app';
import prisma from '@lib/prisma';
import redis from '@lib/redis';
import { env } from '@config/env';

async function startServer(): Promise<void> {
    console.info('Connecting to PostgreSQL…');
    try {
        await prisma.$connect();
        console.info('Database connected');
    } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('Database connection error:', message);
        process.exit(1);
    }

    console.info('Connecting to Redis…');
    try {
        await redis.ping();
        console.info('Redis connected');
    } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('Redis connection error:', message);
        process.exit(1);
    }

    app.listen(env.PORT, () => {
        console.info(`Server running on port ${env.PORT} [${env.NODE_ENV}]`);
    });
}

startServer();
