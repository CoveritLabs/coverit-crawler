() => {
    const BBOX_ATTRS = ["data-x", "data-y", "data-width", "data-height"];

    const isVisible = (el) => {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
        if (el.hidden) return false;

        const style = getComputedStyle(el);
        if (!style || style.display === "none" || style.visibility === "hidden") {
            return false;
        }

        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    const allElements = (doc) => {
        try {
            return Array.from(doc.querySelectorAll("*"));
        } catch {
            return [];
        }
    };

    const clearBoundingBoxAttrs = (doc) => {
        for (const el of allElements(doc)) {
            for (const attr of BBOX_ATTRS) {
                el.removeAttribute(attr);
            }
        }
    };

    const annotateBoundingBoxes = (doc) => {
        for (const el of allElements(doc)) {
            if (!isVisible(el)) continue;

            const rect = el.getBoundingClientRect();
            el.setAttribute("data-x", String(rect.x));
            el.setAttribute("data-y", String(rect.y));
            el.setAttribute("data-width", String(rect.width));
            el.setAttribute("data-height", String(rect.height));
        }
    };

    const docs = [document];
    for (const iframe of Array.from(document.querySelectorAll("iframe"))) {
        try {
            if (iframe.contentDocument) docs.push(iframe.contentDocument);
        } catch {
        }
    }

    for (const doc of docs) {
        clearBoundingBoxAttrs(doc);
        annotateBoundingBoxes(doc);
    }

    const doctype = document.doctype
        ? `<!DOCTYPE ${document.doctype.name}>`
        : "";

    return `${doctype}${document.documentElement.outerHTML}`;
};
