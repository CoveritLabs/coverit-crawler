// Copyright (c) 2026 CoverIt Labs. All Rights Reserved.
// Proprietary and confidential. Unauthorized use is strictly prohibited.
// See LICENSE file in the project root for full license information.

export function buildRedirectUrl(
    baseUrl: string,
    pathname = '',
    params?: URLSearchParams | Record<string, string>
): string {
    if (!baseUrl) return pathname || '';

    const normalizedBase = baseUrl.replace(/\/+$/g, '');
    const normalizedPath = pathname ? '/' + pathname.replace(/^\/+/, '') : '';

    const url = `${normalizedBase}${normalizedPath}`;

    if (!params) return url;

    const search = params instanceof URLSearchParams
        ? params.toString()
        : new URLSearchParams(params).toString();

    return search ? `${url}?${search}` : url;
}

export default buildRedirectUrl;
