() => {
    const cssEscape = (value) => {
        try {
            return CSS.escape(String(value));
        } catch {
            return String(value).replace(/[^a-zA-Z0-9_\-]/g, (c) => `\\${c}`);
        }
    };

    const escapeAttrValue = (value) => {
        return String(value).replace(/\\/g, "\\\\").replace(/\"/g, "\\\"");
    };

    const isVisible = (el) => {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
        if (el.hidden) return false;
        const style = getComputedStyle(el);
        if (!style || style.display === "none" || style.visibility === "hidden" || style.opacity === "0" || style.pointerEvents === "none") {
            return false;
        }
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const labelFor = (doc, el) => {
        if (el.id) {
            const lbl = doc.querySelector(`label[for="${cssEscape(el.id)}"]`);
            if (lbl) return (lbl.innerText || "").trim();
        }
        const parent = el.closest ? el.closest("label") : null;
        return parent ? (parent.innerText || "").trim() : "";
    };

    const cssPath = (el) => {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return "";
        const parts = [];
        let cur = el;
        while (cur && cur.nodeType === Node.ELEMENT_NODE) {
            const tag = cur.tagName.toLowerCase();
            if (cur.id && cur.id.length > 0 && !/^\d+$/.test(cur.id)) {
                parts.unshift(`${tag}#${cssEscape(cur.id)}`);
                break;
            }
            const parent = cur.parentElement;
            if (!parent) {
                parts.unshift(tag);
                break;
            }
            const siblings = Array.from(parent.children).filter((c) => c.tagName === cur.tagName);
            const index = siblings.indexOf(cur);
            const needsNth = siblings.length > 1;
            parts.unshift(needsNth ? `${tag}:nth-of-type(${index + 1})` : tag);
            cur = parent;
            if (tag === "html" || tag === "body") break;
        }
        return parts.join(" > ");
    };

    const selectorCandidates = (el) => {
        const tag = el.tagName ? el.tagName.toLowerCase() : "";
        const candidates = [];
        if (el.getAttribute) {
            for (const attrName of ["data-testid", "data-test", "data-qa"]) {
                const v = el.getAttribute(attrName);
                if (v) {
                    candidates.push(`[${attrName}="${escapeAttrValue(v)}"]`);
                    break;
                }
            }
        }
        if (el.id && el.id.length > 0 && !/^\d+$/.test(el.id)) candidates.push(`#${cssEscape(el.id)}`);
        if (el.name) candidates.push(`${tag}[name="${escapeAttrValue(el.name)}"]`);
        const ariaLabel = el.getAttribute && el.getAttribute("aria-label");
        if (ariaLabel) candidates.push(`${tag}[aria-label="${escapeAttrValue(ariaLabel)}"]`);

        const visibleText = (tag === "input" ? "" : (el.innerText || "")).trim();
        if (visibleText) {
            const safeText = escapeAttrValue(visibleText);
            if (tag === "button" || tag === "a") {
                candidates.push(`${tag}:has-text("${safeText}")`);
            }
        }
        if (tag === "input") {
            const type = (el.type || "").toLowerCase();
            const value = el.getAttribute && el.getAttribute("value");
            if ((type === "radio" || type === "checkbox") && el.name && value) {
                candidates.unshift(`input[type="${escapeAttrValue(type)}"][name="${escapeAttrValue(el.name)}"][value="${escapeAttrValue(value)}"]`);
            }
        }
        const path = cssPath(el);
        if (path) candidates.push(path);
        return candidates;
    };

    const deepQueryAll = (root, selector) => {
        const out = [];
        const visited = new Set();
        const walk = (node) => {
            if (!node || visited.has(node)) return;
            visited.add(node);
            if (node.querySelectorAll) {
                out.push(...Array.from(node.querySelectorAll(selector)));
                const all = Array.from(node.querySelectorAll("*"));
                for (const el of all) {
                    if (el.shadowRoot) walk(el.shadowRoot);
                }
            }
        };
        walk(root);
        return out;
    };

    const allRoots = [{ doc: document, frame: null }];
    for (const iframe of Array.from(document.querySelectorAll("iframe"))) {
        try {
            const doc = iframe.contentDocument;
            if (!doc) continue;
            let frameUrl = "";
            try {
                frameUrl = iframe.contentWindow && iframe.contentWindow.location ? String(iframe.contentWindow.location.href || "") : "";
            } catch {
                frameUrl = "";
            }
            allRoots.push({
                doc,
                frame: {
                    name: String(iframe.name || ""),
                    id: String(iframe.id || ""),
                    src: String(iframe.getAttribute("src") || ""),
                    url: frameUrl,
                },
            });
        } catch {
        }
    }

    const selector = "button, a[href], input, select, textarea, [role='button'], [onclick], [contenteditable]";
    const elements = [];
    for (const root of allRoots) {
        const found = deepQueryAll(root.doc, selector);
        for (const el of found) {
            elements.push({ el, frame: root.frame });
        }
    }

    const unique = [];
    const seen = new Set();

    for (let i = 0; i < elements.length; i++) {
        const el = elements[i].el;
        const frame = elements[i].frame;
        if (!isVisible(el)) continue;

        const tag = el.tagName.toLowerCase();
        const type = (el.type || "").toLowerCase();

        const href = tag === "a" ? (el.href || "") : "";
        const name = el.name || "";
        const placeholder = el.placeholder || "";
        const role = el.getAttribute && (el.getAttribute("role") || "");
        const ariaLabel = el.getAttribute && (el.getAttribute("aria-label") || "");
        const disabled = !!el.disabled;
        const readonly = !!el.readOnly;
        const required = !!el.required;
        const checked = !!el.checked;
        const contenteditable = !!(el.isContentEditable || el.getAttribute("contenteditable"));

        const text = (tag === "input" ? "" : (el.innerText || "")).trim();
        const value = (tag === "input" ? (el.value || "") : "");
        const options = tag === "select"
            ? Array.from(el.options).slice(0, 50).map(o => ({ value: o.value, text: (o.text || "").trim() }))
            : [];

        const inForm = !!(el.closest && el.closest("form"));
        const path = cssPath(el);
        const candidates = selectorCandidates(el);
        const primarySelector = candidates && candidates.length ? candidates[0] : path;
        const frameSig = frame && (frame.url || frame.src || frame.name || frame.id) ? `${frame.url || frame.src || frame.name || frame.id}` : "";
        const signature = (frameSig ? `${frameSig}::` : "") + (primarySelector || `${tag}|${type}|${name}|${href}|${i}`);

        if (seen.has(signature)) continue;
        seen.add(signature);

        unique.push({
            id: el.id || String(i),
            tag,
            type,
            text,
            value,
            name,
            href,
            placeholder,
            role,
            aria_label: ariaLabel,
            label: labelFor(el.ownerDocument || document, el),
            in_form: inForm,
            disabled,
            readonly,
            required,
            checked,
            contenteditable,
            min: el.getAttribute && el.getAttribute("min"),
            max: el.getAttribute && el.getAttribute("max"),
            maxlength: el.getAttribute && el.getAttribute("maxlength"),
            pattern: el.getAttribute && el.getAttribute("pattern"),
            options,
            css_path: path,
            selector_candidates: selectorCandidates(el),
            frame,
        });
    }

    return unique;
}