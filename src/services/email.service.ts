// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import { env } from "@config/env";
import { logger } from "@services/logger.service";
import { Resend } from "resend";

const resend = new Resend(env.RESEND_API_KEY);

export async function sendResetEmail(email: string, resetUrl: string, name: string): Promise<void> {
  const from = env.RESET_PASSWORD_EMAIL;
  const templateId = env.RESET_PASSWORD_TEMPLATE_ID;

  const { data, error } = await resend.emails.send({
    from,
    to: [email],
    subject: "Reset your Coverit password",
    template: {
      id: templateId,
      variables: {
        NAME: name,
        RESET_URL: resetUrl,
        EXPIRE_TIME: Math.ceil(env.RESET_TOKEN_TTL_SECONDS / 60),
      },
    },
  });

  if (error) {
    logger.error(error, "Error sending email:");
    return;
  }

  logger.info("Reset password email sent successfully!");
  logger.info(
    {
      email,
      messageId: data?.id,
    },
    "Reset password email sent",
  );
}
