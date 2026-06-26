({ x, y, stateHash }) => {
  const TEST_ID_ATTRIBUTES = ["data-testid", "data-test", "data-cy", "data-qa"];
  const GENERATED_ID_RE = /^_r_[a-z0-9_]+(?:--[a-z0-9_-]+)?$/i;
  const HASH_ID_RE = /^[a-f0-9]{8,}(?:-[a-f0-9]{4,})*$/i;
  const DYNAMIC_CLASS_PREFIXES = ["css-", "sc-", "prc-"];

  function escapeCss(value) {
    if (globalThis.CSS && typeof globalThis.CSS.escape === "function") {
      return globalThis.CSS.escape(value);
    }
    return String(value).replace(/["\\\\]/g, "\\\\$&");
  }

  function escapeAttr(value) {
    return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function normalizedToken(value) {
    return String(value || "").replace(/\\/g, "").replace(/[^A-Za-z0-9_-]/g, "");
  }

  function isGeneratedId(value) {
    const token = normalizedToken(value);
    if (!token) return true;
    if (GENERATED_ID_RE.test(token) || HASH_ID_RE.test(token) || /^[0-9]+$/.test(token)) return true;
    if (token.length >= 6 && !token.includes("-") && !token.includes("_")) {
      return /\d/.test(token) && (/[a-z]/.test(token) || /[A-Z]/.test(token));
    }
    return false;
  }

  function isGeneratedClass(value) {
    const className = normalizedToken(value);
    if (!className) return true;
    if (DYNAMIC_CLASS_PREFIXES.some((prefix) => className.startsWith(prefix))) return true;

    const tail = className.split("__").pop().split("-").pop();
    return tail.length >= 5 && /[A-Z]/.test(tail) && (/[a-z]/.test(tail) || /\d/.test(tail));
  }

  function addCandidate(candidates, value) {
    const selector = String(value || "").trim();
    if (!selector || candidates.includes(selector)) return;
    candidates.push(selector);
  }

  function testIdSelectorFor(element) {
    for (const attribute of TEST_ID_ATTRIBUTES) {
      const value = element.getAttribute(attribute);
      if (value) return `[${attribute}="${escapeAttr(value)}"]`;
    }
    return "";
  }

  function attrSelectorFor(element, attribute) {
    const value = element.getAttribute(attribute);
    if (!value) return "";
    return `${element.tagName.toLowerCase()}[${attribute}="${escapeAttr(value)}"]`;
  }

  function stableIdSelectorFor(element) {
    return element.id && !isGeneratedId(element.id) ? `#${escapeCss(element.id)}` : "";
  }

  function stableClassNames(element) {
    return [...element.classList]
      .filter((className) => className && !/^\\d/.test(className) && !isGeneratedClass(className))
      .slice(0, 2);
  }

  function selectorPartFor(element) {
    const tag = element.tagName.toLowerCase();
    const stableId = stableIdSelectorFor(element);
    if (stableId) return `${tag}${stableId}`;

    const classes = stableClassNames(element);
    let part = tag;
    for (const className of classes) part += `.${escapeCss(className)}`;
    return part;
  }

  function pathSelectorFor(element) {
    if (!(element instanceof Element)) return "body";

    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body && parts.length < 4) {
      const part = selectorPartFor(current);
      const hasStableToken = part.includes("#") || part.includes(".");
      parts.unshift(part);
      if (part.includes("#")) break;

      current = current.parentElement;
      if (!hasStableToken && parts.length >= 2) break;
    }

    return parts.length ? parts.join(" > ") : "body";
  }

  function selectorIsStable(selector) {
    if (!selector) return false;
    if (selector.includes(":nth-of-type")) return false;
    if ((selector.match(/>/g) || []).length > 2) return false;
    return true;
  }

  function stableTailSelectors(selector) {
    const parts = String(selector || "").split(">").map((part) => part.trim()).filter(Boolean);
    if (parts.length <= 1) return [];

    const candidates = [];
    for (let tailLength = 1; tailLength <= Math.min(3, parts.length); tailLength += 1) {
      const tail = parts.slice(-tailLength).join(" > ");
      if (selectorIsStable(tail)) addCandidate(candidates, tail);
    }
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

  function selectorCandidatesFor(element) {
    const candidates = [];
    if (!(element instanceof Element)) return candidates;

    const tag = element.tagName.toLowerCase();
    addCandidate(candidates, testIdSelectorFor(element));
    addCandidate(candidates, attrSelectorFor(element, "name"));
    addCandidate(candidates, attrSelectorFor(element, "aria-label"));
    addCandidate(candidates, attrSelectorFor(element, "placeholder"));
    addCandidate(candidates, stableIdSelectorFor(element));

    const href = tag === "a" ? element.getAttribute("href") : "";
    if (href && !href.startsWith("javascript:")) addCandidate(candidates, `a[href="${escapeAttr(href)}"]`);

    const role = element.getAttribute("role");
    const label = accessibleName(element) || safeText(element);
    if (role && label && ["button", "link", "menuitem", "option", "tab"].includes(role)) {
      addCandidate(candidates, `${tag}[role="${escapeAttr(role)}"]:has-text("${escapeAttr(label)}")`);
    }
    if ((tag === "button" || tag === "a") && label) {
      addCandidate(candidates, `${tag}:has-text("${escapeAttr(label)}")`);
    }

    const path = pathSelectorFor(element);
    for (const tail of stableTailSelectors(path)) addCandidate(candidates, tail);
    if (selectorIsStable(path)) addCandidate(candidates, path);
    return candidates;
  }

  function selectorFor(element) {
    if (!(element instanceof Element)) return "body";
    const candidates = selectorCandidatesFor(element);
    return candidates[0] || pathSelectorFor(element) || "body";
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
