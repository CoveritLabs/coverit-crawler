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
        const type = (el.type || "").toLowerCase();
        const value = el.getAttribute && el.getAttribute("value");
        if (tag === "input" && (type === "radio" || type === "checkbox") && el.name && value) {
            candidates.unshift(`input[type="${escapeAttrValue(type)}"][name="${escapeAttrValue(el.name)}"][value="${escapeAttrValue(value)}"]`);
        }
        if (el.name) candidates.push(`${tag}[name="${escapeAttrValue(el.name)}"]`);
        const ariaLabel = el.getAttribute && el.getAttribute("aria-label");
        if (ariaLabel) candidates.push(`${tag}[aria-label="${escapeAttrValue(ariaLabel)}"]`);
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

    const toField = (el, frame) => {
        const tag = el.tagName.toLowerCase();
        const type = (el.type || "").toLowerCase();
        const options = tag === "select"
            ? Array.from(el.options).slice(0, 50).map(o => ({ value: o.value, text: (o.text || "").trim() }))
            : [];
        return {
            tag,
            id: el.id || "",
            name: el.name || "",
            type,
            value: el.value || "",
            placeholder: el.placeholder || "",
            label: labelFor(el.ownerDocument || document, el),
            checked: !!el.checked,
            required: !!el.required,
            disabled: !!el.disabled,
            readonly: !!el.readOnly,
            min: el.getAttribute && el.getAttribute("min"),
            max: el.getAttribute && el.getAttribute("max"),
            maxlength: el.getAttribute && el.getAttribute("maxlength"),
            pattern: el.getAttribute && el.getAttribute("pattern"),
            aria_label: el.getAttribute && (el.getAttribute("aria-label") || ""),
            role: el.getAttribute && (el.getAttribute("role") || ""),
            autocomplete: el.getAttribute && (el.getAttribute("autocomplete") || ""),
            options,
            selector_candidates: selectorCandidates(el),
            frame,
        };
    };

    const toSubmit = (el, frame) => {
        if (!el) return null;
        return {
            tag: el.tagName.toLowerCase(),
            id: el.id || "",
            name: el.name || "",
            type: (el.type || "").toLowerCase(),
            value: el.value || "",
            text: (el.innerText || el.value || "").trim(),
            aria_label: el.getAttribute && (el.getAttribute("aria-label") || ""),
            role: el.getAttribute && (el.getAttribute("role") || ""),
            selector_candidates: selectorCandidates(el),
            frame,
        };
    };

    const isFillableField = (f) => {
        if (!f) return false;
        if (f.disabled || f.readonly) return false;
        if (f.tag === "select" || f.tag === "textarea") return true;
        if (f.tag !== "input") return false;
        const t = (f.type || "").toLowerCase();
        return !["submit", "button", "reset", "hidden", "image", "file"].includes(t);
    };

    const forms = [];
    for (const root of allRoots) {
        const formEls = deepQueryAll(root.doc, "form");
        for (let i = 0; i < formEls.length; i++) {
            const form = formEls[i];
            const fields = Array.from(form.querySelectorAll("input, select, textarea")).filter(isVisible).map((el) => toField(el, root.frame));
            const candidates = Array.from(
                form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type]), [role="button"], [onclick]')
            ).filter(isVisible);
            const submit = toSubmit(candidates[0] || null, root.frame);
            const method = (form.method || "get").toLowerCase();
            const hasFillable = fields.some(isFillableField);

            forms.push({
                form_id: form.id || `form-${forms.length}`,
                method,
                action: form.action || "",
                fields,
                submit,
                has_fillable_fields: hasFillable,
                frame: root.frame,
            });
        }
    }

    return forms.filter(f => !!f.submit);
}