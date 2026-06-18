if (!window.__manualCrawlInitialized) {
    window.__manualCrawlInitialized = true;

    function getSelector(el) {
        if (!el || el === document.body) return 'body';
        if (el.id) return `#${el.id}`;
        const testId = el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-cy');
        if (testId) return `[data-testid="${testId}"]`;
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`;
        
        let path = [];
        let current = el;
        while (current && current !== document.body) {
            let selector = current.tagName.toLowerCase();
            if (current.id) {
                selector = `#${current.id}`;
                path.unshift(selector);
                break;
            }
            let sibling = current;
            let nth = 1;
            while ((sibling = sibling.previousElementSibling)) {
                if (sibling.tagName === current.tagName) nth++;
            }
            if (nth > 1) selector += `:nth-of-type(${nth})`;
            path.unshift(selector);
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    document.addEventListener('click', e => {
        if (typeof window.__reportStep === 'function') {
            const el = e.target;
            const tag = el.tagName.toLowerCase();
            const label = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('value') || '').trim().slice(0, 80);
            const href = tag === 'a' ? (el.href || el.getAttribute('href') || '') : '';
            window.__reportStep({ action: 'click', element: getSelector(el), tag, label, href });
        }
    }, true);

    document.addEventListener('input', e => {
        const el = e.target;
        if (!['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return;
        if (typeof window.__reportStep === 'function') {
            const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '';
            const inputType = el.type || el.tagName.toLowerCase();
            window.__reportStep({
                action: 'input',
                element: getSelector(el),
                value: el.value,
                label,
                inputType,
            });
        }
    }, true);

    document.addEventListener('keydown', e => {
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
        if (typeof window.__reportStep === 'function') {
            window.__reportStep({ action: 'keypress', key: e.key, element: getSelector(e.target) });
        }
    }, true);
}