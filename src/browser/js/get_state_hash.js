() => {
    const body = document.body.cloneNode(true);
    body.querySelectorAll('script, style, meta, noscript, link, iframe, svg').forEach(el => el.remove());
    let text = (body.innerText || '').toLowerCase().trim().replace(/\s+/g, ' ');
    const interactives = Array.from(body.querySelectorAll('button, a, input'))
        .map(el => `${el.name || ''}|${el.type || ''}|${el.placeholder || ''}`.trim())
        .filter(Boolean)
        .sort()
        .join('|');
    return text + ':::' + interactives;
}