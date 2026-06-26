(el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) {
        return null;
    }

    const rect = el.getBoundingClientRect();

    if (!rect || rect.width <= 0 || rect.height <= 0) {
        return null;
    }

    const ownsHit = (hit) => {
        if (!hit) return false;
        if (hit === el || el.contains(hit)) return true;

        const root = hit.getRootNode && hit.getRootNode();
        const host = root && root.host;

        return !!host && (host === el || el.contains(host));
    };

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    const candidates = [
        [0.5, 0.5],
        [0.2, 0.5],
        [0.8, 0.5],
        [0.5, 0.2],
        [0.5, 0.8],
        [0.2, 0.2],
        [0.8, 0.2],
        [0.2, 0.8],
        [0.8, 0.8],
    ];

    for (const [xRatio, yRatio] of candidates) {
        const x = clamp(rect.left + rect.width * xRatio, rect.left + 1, rect.right - 1);
        const y = clamp(rect.top + rect.height * yRatio, rect.top + 1, rect.bottom - 1);
        const hit = document.elementFromPoint(x, y);

        if (ownsHit(hit)) {
            return {
                x: x - rect.left,
                y: y - rect.top,
            };
        }
    }

    return null;
};
