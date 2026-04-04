// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { OpenApiGeneratorV3 } from '@asteasolutions/zod-to-openapi';
import { env } from '@config/env';
import { registry } from '@config/openapi';

const generator = new OpenApiGeneratorV3(registry.definitions);

export const swaggerSpec = generator.generateDocument({
    openapi: '3.0.3',
    info: {
        title: 'CoverIt API',
        version: '0.1.0',
        description: 'CoverIt REST API — authentication and platform services',
    },
    servers: [
        {
            url: `http://localhost:${env.PORT}${env.API_PREFIX}`,
            description: 'Local development',
        },
    ],
});

