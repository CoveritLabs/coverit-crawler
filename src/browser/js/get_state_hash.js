() => {
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

    const allDocs = [document];
    for (const iframe of Array.from(document.querySelectorAll("iframe"))) {
        try {
            const doc = iframe.contentDocument;
            if (doc) allDocs.push(doc);
        } catch {
        }
    }

    const textParts = [];
    for (const doc of allDocs) {
        try {
            const t = (doc.body && doc.body.innerText) ? doc.body.innerText : "";
            if (t) textParts.push(t);
        } catch {
        }
    }
    const pageText = textParts.join("\n").toLowerCase().trim().replace(/\s+/g, " ");

    const interactiveSelector = "button, a[href], input, select, textarea, [role='button'], [onclick], [contenteditable]";
    const sigs = [];
    for (const doc of allDocs) {
        const els = deepQueryAll(doc, interactiveSelector).filter(isVisible);
        for (const el of els) {
            const tag = el.tagName.toLowerCase();
            const type = (el.type || "").toLowerCase();
            const name = el.name || "";
            const id = el.id || "";
            const placeholder = el.placeholder || "";
            const role = el.getAttribute && (el.getAttribute("role") || "");
            const ariaLabel = el.getAttribute && (el.getAttribute("aria-label") || "");
            const ariaInvalid = el.getAttribute && (el.getAttribute("aria-invalid") || "");
            const ariaExpanded = el.getAttribute && (el.getAttribute("aria-expanded") || "");
            const disabled = !!el.disabled;
            const readonly = !!el.readOnly;
            const required = !!el.required;
            const checked = (type === "checkbox" || type === "radio") ? !!el.checked : false;
            const href = tag === "a" ? (el.getAttribute("href") || "") : "";

            let selected = "";
            if (tag === "select") {
                try {
                    const opt = el.selectedOptions && el.selectedOptions.length ? el.selectedOptions[0] : null;
                    if (opt) selected = `${opt.value || ""}|${(opt.text || "").trim()}`;
                } catch {
                }
            }

            const text = (tag === "input" ? "" : (el.innerText || "")).trim().slice(0, 80);
            sigs.push([
                tag,
                type,
                name,
                id,
                placeholder,
                role,
                ariaLabel,
                ariaInvalid,
                ariaExpanded,
                required ? "req" : "",
                disabled ? "dis" : "",
                readonly ? "ro" : "",
                checked ? "chk" : "",
                selected,
                href,
                text,
            ].join("|"));
        }
    }

    const errorSelector = "[role='alert'], [aria-live], .error, .errors, .validation-error";
    const errorTexts = [];
    for (const doc of allDocs) {
        const errEls = deepQueryAll(doc, errorSelector).filter(isVisible);
        for (const el of errEls) {
            const t = (el.innerText || "").trim();
            if (t) errorTexts.push(t.slice(0, 200));
        }
    }

    sigs.sort();
    errorTexts.sort();

    return [
        pageText,
        ":::",
        sigs.join("\n"),
        ":::",
        errorTexts.join("\n"),
    ].join("");
}