() => {
    const formEls = new Set(
        Array.from(document.querySelectorAll('form input, form select, form textarea, form button'))
    );

    const labelFor = el => {
        if (el.id) {
            const lbl = document.querySelector(`label[for="${el.id}"]`);
            if (lbl) return lbl.innerText.trim();
        }
        const parent = el.closest('label');
        return parent ? parent.innerText.trim() : '';
    };

    const elements = Array.from(document.querySelectorAll(
        "button, a[href], input, select, textarea, [role='button'], [onclick]"
    ))
    .filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && !el.hidden;
    });

    const uniqueElements = [];
    const seenSignatures = new Set();

    elements.forEach((el, i) => {
        const tag = el.tagName.toLowerCase();
        const text = (tag === 'input' ? '' : (el.innerText || '')).trim();
        const type = (el.type || '').toLowerCase();
        const name = el.name || '';
        const href = el.href || '';
        const firstClass = el.className && typeof el.className === 'string' 
            ? el.className.trim().split(/\s+/)[0] 
            : '';

        const signature = `${tag}|${text}|${type}|${name}|${firstClass}|${href}`;

        if (!seenSignatures.has(signature)) {
            seenSignatures.add(signature);
            
            uniqueElements.push({
                id: el.id || String(i),
                tag: tag,
                text: text,
                value: (tag === 'input' ? (el.value || '') : ''),
                type: type,
                name: name,
                placeholder: el.placeholder || '',
                label: labelFor(el),
                href: href,
                in_form: formEls.has(el),
                options: tag === 'select'
                    ? Array.from(el.options).map(o => ({ value: o.value, text: o.text.trim() }))
                    : [],
                selector: el.id
                    ? `#${el.id}`
                    : tag + (firstClass ? '.' + firstClass : ''),
            });
        }
    });

    return uniqueElements;
}