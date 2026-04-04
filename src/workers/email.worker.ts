// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { workerRedis } from '@lib/redis'; 
import { sendResetEmail } from "@services/email.service";
import { logger } from "@services/logger.service";
import { Worker } from "bullmq";

new Worker(
  "email",
  async (job) => {
    if (job.name === "send-reset-email") {
      const { email, resetUrl, name } = job.data;
      await sendResetEmail(email, resetUrl, name);
    }
  },
  { connection: workerRedis },
);

logger.info("[Worker] Email worker started and listening for jobs...");
