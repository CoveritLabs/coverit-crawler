// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import express, { Application, Request, Response } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import swaggerUi from 'swagger-ui-express';

import { env } from '@config/env';
import { swaggerSpec } from '@config/swagger';
import authRoutes from '@api/routes/auth.routes';
import { errorHandler } from '@api/middlewares/errorHandler';
import { httpLogger } from '@api/middlewares/logger';
import "@workers/email.worker"

const app: Application = express();

app.use(helmet());

const allowedOrigins = env.CORS_ORIGINS;
const corsOptions = {
    origin: (requestOrigin: string | undefined, callback: (err: Error | null, allow?: boolean) => void) => {
        if (!requestOrigin) return callback(null, true);
        if (allowedOrigins.includes('*') || allowedOrigins.includes(requestOrigin)) return callback(null, true);
        return callback(new Error('Not allowed by CORS'));
    },
    credentials: env.CORS_CREDENTIALS === 'true',
    optionsSuccessStatus: 200,
};
app.use(cors(corsOptions));
app.options('*', cors(corsOptions));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(httpLogger);

app.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.use('/docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));
app.get('/docs.json', (_req: Request, res: Response) => {
    res.json(swaggerSpec);
});

const apiBase = env.API_PREFIX;
app.use(`${apiBase}/auth`, authRoutes);

app.use(errorHandler);

export default app;
