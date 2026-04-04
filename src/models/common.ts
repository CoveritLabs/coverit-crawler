// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

// Shared DTO utilities and types used across all domains

import type { Message } from '@bufbuild/protobuf';
import type {
    UserInfo as ContractUserInfo,
    MessageResponse as ContractMessageResponse,
} from '@coveritlabs/contracts';

/**
 * Recursively strips the protobuf `$typeName` marker from Message types.
 * Converts protobuf Message objects to plain JS objects.
 */
export type Plain<T> = T extends Message<string>
    ? { [K in keyof Omit<T, '$typeName'>]: Plain<Omit<T, '$typeName'>[K]> }
    : T extends Array<infer U>
      ? Array<Plain<U>>
      : T extends ReadonlyArray<infer U>
        ? ReadonlyArray<Plain<U>>
        : T;

// Shared domain models
export type UserInfo = Plain<ContractUserInfo>;
export type MessageResponse = Plain<ContractMessageResponse>;
