// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

import * as _z from 'zod';

function requiredString(message: string) {
    return _z.string({ error: message }).trim().min(1, message);
}

export const z = {
    ..._z,
    requiredString,
};
