// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { Router } from 'express';
import * as authController from '@api/controllers/auth.controller';
import { validateBody } from '@api/middlewares/validate';
import {
    SignupRequestSchema,
    LoginRequestSchema,
    RefreshRequestSchema,
    ForgotPasswordRequestSchema,
    ResetPasswordRequestSchema,
} from '@models/auth';

const router = Router();

router.post('/signup', validateBody(SignupRequestSchema), authController.signup);
router.post('/login', validateBody(LoginRequestSchema), authController.login);
router.post('/refresh', validateBody(RefreshRequestSchema), authController.refresh);
router.post('/logout', authController.logout);
router.post('/forgot-password', validateBody(ForgotPasswordRequestSchema), authController.forgotPassword);
router.post('/reset-password', validateBody(ResetPasswordRequestSchema), authController.resetPassword);

// OAuth
router.get('/oauth/:provider', authController.oauthRedirect);
router.get('/oauth/:provider/callback', authController.oauthCallback);

export default router;
