({ x, y, stateHash }) => {
  function escapeCss(value) {
    if (globalThis.CSS && typeof globalThis.CSS.escape === "function") {
      return globalThis.CSS.escape(value);
    }
    return String(value).replace(/["\\\\]/g, "\\\\$&");
  }

  function addCandidate(candidates, value) {
    const selector = String(value || "").trim();
    if (!selector || candidates.includes(selector)) return;
    candidates.push(selector);
  }

  function testIdSelectorFor(element) {
    for (const attribute of ["data-testid", "data-test", "data-cy"]) {
      const value = element.getAttribute(attribute);
      if (value) return `[${attribute}="${escapeCss(value)}"]`;
    }
    return "";
  }

  function selectorFor(element) {
    if (!(element instanceof Element)) return "body";
    const testId = testIdSelectorFor(element);
    if (testId) return testId;
    if (element.id) return `#${escapeCss(element.id)}`;

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) return `${element.tagName.toLowerCase()}[aria-label="${escapeCss(ariaLabel)}"]`;

    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body && parts.length < 6) {
      let part = current.tagName.toLowerCase();
      if (current.id) {
        part += `#${escapeCss(current.id)}`;
        parts.unshift(part);
        break;
      }

      const classes = [...current.classList].filter((className) => className && !/^\\d/.test(className)).slice(0, 2);
      for (const className of classes) part += `.${escapeCss(className)}`;

      const parent = current.parentElement;
      if (parent) {
        const siblings = [...parent.children].filter((child) => child.tagName === current.tagName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      }

      parts.unshift(part);
      current = current.parentElement;
    }

    return parts.length ? parts.join(" > ") : "body";
  }

  function selectorCandidatesFor(element) {
    const candidates = [];
    if (!(element instanceof Element)) return candidates;

    addCandidate(candidates, testIdSelectorFor(element));
    if (element.id) addCandidate(candidates, `#${escapeCss(element.id)}`);

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) addCandidate(candidates, `${element.tagName.toLowerCase()}[aria-label="${escapeCss(ariaLabel)}"]`);

    const name = element.getAttribute("name");
    if (name) addCandidate(candidates, `${element.tagName.toLowerCase()}[name="${escapeCss(name)}"]`);

    const href = element.tagName.toLowerCase() === "a" ? element.getAttribute("href") : "";
    if (href) addCandidate(candidates, `a[href="${escapeCss(href)}"]`);

    const role = element.getAttribute("role");
    if (role) addCandidate(candidates, `${element.tagName.toLowerCase()}[role="${escapeCss(role)}"]`);

    addCandidate(candidates, selectorFor(element));
    return candidates;
  }

  function safeText(element) {
    if (!(element instanceof Element)) return "";
    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type")?.toLowerCase();
    if (["input", "textarea", "select"].includes(tag) || type === "password") return "";
    return (element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 500);
  }

  function accessibleName(element) {
    if (!(element instanceof Element)) return "";
    return (
      element.getAttribute("aria-label") ||
      element.getAttribute("title") ||
      element.getAttribute("alt") ||
      element.getAttribute("placeholder") ||
      element.getAttribute("name") ||
      ""
    ).slice(0, 500);
  }

  function safeAttributes(element) {
    const result = {};
    if (!(element instanceof Element)) return result;
    for (const attribute of element.attributes) {
      const name = attribute.name.toLowerCase();
      if (
        name === "id" ||
        name === "name" ||
        name === "role" ||
        name === "type" ||
        name === "href" ||
        name === "aria-label" ||
        name === "title" ||
        name === "alt" ||
        name === "placeholder" ||
        name.startsWith("data-")
      ) {
        result[name] = attribute.value.slice(0, 500);
      }
    }
    return result;
  }

  const element = document.elementFromPoint(x, y);
  if (!(element instanceof Element)) return null;

  const rect = element.getBoundingClientRect();
  const selectorCandidates = selectorCandidatesFor(element);
  const selector = selectorCandidates[0] || selectorFor(element);

  return {
    selector,
    selectorCandidates,
    tag: element.tagName.toLowerCase(),
    text: safeText(element),
    accessibleName: accessibleName(element),
    attributes: safeAttributes(element),
    pageUrl: window.location.href,
    stateHash,
    box: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    },
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
    },
  };
}
