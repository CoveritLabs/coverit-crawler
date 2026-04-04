// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { Queue } from "bullmq";
import redis from "@lib/redis";

export const emailQueue = new Queue("email", {
  connection: redis,
});