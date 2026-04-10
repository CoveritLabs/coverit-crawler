() => {
    const labelFor = el => {
        if (el.id) {
            const lbl = document.querySelector(`label[for="${el.id}"]`);
            if (lbl) return lbl.innerText.trim();
        }
        const parent = el.closest('label');
        return parent ? parent.innerText.trim() : '';
    };

    const toField = el => ({
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        name: el.name || '',
        type: (el.type || '').toLowerCase(),
        placeholder: el.placeholder || '',
        label: labelFor(el),
        checked: !!el.checked,
        options: el.tagName.toLowerCase() === 'select'
            ? Array.from(el.options).map(o => ({ value: o.value, text: o.text.trim() }))
            : [],
    });

    const toSubmit = el => el ? {
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        name: el.name || '',
        type: (el.type || '').toLowerCase(),
        value: el.value || '',
        text: (el.innerText || el.value || '').trim(),
    } : null;

    const isFillableField = f => {
        if (!f) return false;
        if (f.tag === 'select' || f.tag === 'textarea') return true;
        if (f.tag !== 'input') return false;
        const t = (f.type || '').toLowerCase();
        return !['submit', 'button', 'reset', 'hidden', 'image'].includes(t);
    };

    return Array.from(document.querySelectorAll('form'))
        .map((form, i) => {
            const fields = Array.from(
                form.querySelectorAll('input, select, textarea')
            ).map(toField);
            const submit = toSubmit(
                form.querySelector(
                    'button[type="submit"], input[type="submit"], button:not([type])'
                )
            );
            const method = (form.method || 'get').toLowerCase();
            const hasFillable = fields.some(isFillableField);

            return {
                form_id: form.id || `form-${i}`,
                method,
                action: form.action || '',
                fields,
                submit,
                has_fillable_fields: hasFillable,
            };
        })
        .filter(f => f.submit && (f.has_fillable_fields || f.method !== 'get'));
}