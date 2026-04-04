// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

// User domain DTOs

import type {
    UserInfo as ContractUserInfo,
} from '@coveritlabs/contracts';

import type { Plain } from './common';

// Shared domain models
export type UserInfo = Plain<ContractUserInfo>;
