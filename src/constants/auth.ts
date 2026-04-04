// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

// OAuth provider constants
// Central place for OAuth-related constants used across the API

import type { OAuthProvider } from 'types/auth'

export const VALID_PROVIDERS = new Set<OAuthProvider>(['google', 'github'])
