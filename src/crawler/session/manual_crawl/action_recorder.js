(() => {
  if (globalThis.__coveritFlowRecorderInstalled) return;
  globalThis.__coveritFlowRecorderInstalled = true;

  const TEST_ID_ATTRIBUTES = ["data-testid", "data-test", "data-cy", "data-qa"];
  const SUPPORT_FIELD_RE = /(webauthn|javascript).*support|iuvpaa/i;
  const GENERATED_ID_RE = /^_r_[a-z0-9_]+(?:--[a-z0-9_-]+)?$/i;
  const HASH_ID_RE = /^[a-f0-9]{8,}(?:-[a-f0-9]{4,})*$/i;
  const DYNAMIC_CLASS_PREFIXES = ["css-", "sc-", "prc-"];

  function escapeCss(value) {
    if (globalThis.CSS && typeof globalThis.CSS.escape === "function") {
      return globalThis.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, "\\$&");
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
    if (tail.length >= 5 && /[A-Z]/.test(tail) && (/[a-z]/.test(tail) || /\d/.test(tail))) {
      return true;
    }
    return false;
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
      .filter((className) => className && !/^\d/.test(className) && !isGeneratedClass(className))
      .slice(0, 2);
  }

  function selectorPartFor(element) {
    const tag = element.tagName.toLowerCase();
    const stableId = stableIdSelectorFor(element);
    if (stableId) return `${tag}${stableId}`;

    const classes = stableClassNames(element);
    let part = tag;
    for (const className of classes) {
      part += `.${escapeCss(className)}`;
    }
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
    if (href && !href.startsWith("javascript:")) {
      addCandidate(candidates, `a[href="${escapeAttr(href)}"]`);
    }

    const role = element.getAttribute("role");
    const label = elementLabel(element);
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

  function nearestInteractiveAncestor(element) {
    if (!(element instanceof Element)) return null;

    const selector = [
      "a[href]",
      "button",
      "input:not([type='hidden'])",
      "textarea",
      "select",
      "label",
      "summary",
      "[role='button']",
      "[role='link']",
      "[role='menuitem']",
      "[role='option']",
      "[contenteditable='true']",
      "[tabindex]:not([tabindex='-1'])",
      "[onclick]",
    ].join(",");
    const explicit = element.closest(selector);
    if (explicit) return explicit;

    let current = element;
    while (current && current !== document.body) {
      try {
        if (globalThis.getComputedStyle(current).cursor === "pointer") return current;
      } catch {
        return current;
      }
      current = current.parentElement;
    }

    return element;
  }

  function isVisible(element) {
    if (!(element instanceof Element)) return false;
    if (element.hidden) return false;
    const style = globalThis.getComputedStyle(element);
    if (!style || style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function fieldType(element) {
    const tag = element?.tagName?.toLowerCase();
    return element?.getAttribute?.("type")?.toLowerCase() || tag || "text";
  }

  function isTextEntry(element) {
    if (!(element instanceof Element)) return false;
    const tag = element.tagName?.toLowerCase();
    const type = fieldType(element);
    if (tag === "textarea" || element.isContentEditable) return true;
    if (tag !== "input") return false;
    return ![
      "button",
      "checkbox",
      "color",
      "file",
      "hidden",
      "image",
      "radio",
      "range",
      "reset",
      "submit",
    ].includes(type);
  }

  function isEnterSubmittableTextInput(element) {
    if (!(element instanceof Element)) return false;
    if (element.tagName?.toLowerCase() !== "input") return false;
    return isTextEntry(element);
  }

  function supportFieldIdentity(element) {
    if (!(element instanceof Element)) return "";
    return [
      element.id,
      element.getAttribute("name"),
      element.getAttribute("aria-label"),
      element.getAttribute("title"),
      element.getAttribute("placeholder"),
    ].filter(Boolean).join(" ");
  }

  function isIgnoredInputTarget(element) {
    if (!(element instanceof Element)) return true;
    if (SUPPORT_FIELD_RE.test(supportFieldIdentity(element))) return true;
    if (fieldType(element) === "hidden") return true;
    return !isVisible(element);
  }

  function elementText(element) {
    if (!(element instanceof Element)) return "";
    const tag = element.tagName?.toLowerCase();
    const type = element.getAttribute("type")?.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || type === "password") return "";
    return (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 160);
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
    ).slice(0, 160);
  }

  function elementLabel(element) {
    return (accessibleName(element) || elementText(element) || "").trim();
  }

  function basePayload(action, event) {
    const target = event.target instanceof Element ? event.target : null;
    const interactive =
      action === "click" || action === "keypress"
        ? nearestInteractiveAncestor(target)
        : target;
    const element = interactive || target;
    const rect = element?.getBoundingClientRect?.();
    const targetRect = target?.getBoundingClientRect?.();
    const link = element?.closest?.("a") || target?.closest?.("a");
    const selectorCandidates = [
      ...selectorCandidatesFor(element),
      ...selectorCandidatesFor(target),
    ].filter((selector, index, list) => selector && list.indexOf(selector) === index);
    const selector = selectorCandidates[0] || selectorFor(element);
    const targetSelector = selectorFor(target);
    const tag = element?.tagName?.toLowerCase() || null;
    const targetTag = target?.tagName?.toLowerCase() || null;
    const text = elementText(element);
    const targetText = elementText(target);
    const name = accessibleName(element);
    const targetName = accessibleName(target);
    return {
      action,
      element: selector,
      selector,
      selectorCandidates,
      interactiveSelector: selectorFor(element),
      targetSelector,
      elementId: element?.id || "",
      targetElementId: target?.id || "",
      name: element?.getAttribute?.("name") || "",
      targetNameAttribute: target?.getAttribute?.("name") || "",
      isTrusted: event.isTrusted,
      hidden: element instanceof Element ? !isVisible(element) : false,
      editable: element instanceof Element ? isTextEntry(element) || tag === "select" : false,
      x: Math.round(event.clientX || 0),
      y: Math.round(event.clientY || 0),
      pageX: Math.round(event.pageX || 0),
      pageY: Math.round(event.pageY || 0),
      button: event.button ?? null,
      tag,
      targetTag,
      label: elementLabel(element) || elementLabel(target),
      text,
      accessibleName: name,
      targetText,
      targetAccessibleName: targetName,
      href: link?.href || null,
      elementBox: rect
        ? {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          }
        : null,
      targetElementBox: targetRect
        ? {
            x: Math.round(targetRect.x),
            y: Math.round(targetRect.y),
            width: Math.round(targetRect.width),
            height: Math.round(targetRect.height),
          }
        : null,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    };
  }

  function safeValue(element) {
    if (!(element instanceof Element)) return "";
    if ("value" in element) return String(element.value ?? "").slice(0, 2000);
    if (element.isContentEditable) return String(element.textContent || "").slice(0, 2000);
    return "";
  }

  function report(payload) {
    if (typeof globalThis.__recordFlowEvent === "function") {
      globalThis.__recordFlowEvent(payload).catch(() => {});
    }
    if (typeof globalThis.__reportStep === "function") {
      globalThis.__reportStep(payload);
    }
  }

  document.addEventListener(
    "click",
    (event) => {
      if (event.isTrusted === false) return;
      report(basePayload("click", event));
    },
    true,
  );

  document.addEventListener(
    "input",
    (event) => {
      if (event.isTrusted === false) return;
      const element = event.target instanceof Element ? event.target : null;
      if (!isTextEntry(element) || isIgnoredInputTarget(element)) return;

      const payload = basePayload("input", event);
      const type = fieldType(element);
      payload.value = safeValue(element);
      payload.inputType = type;
      report(payload);
    },
    true,
  );

  document.addEventListener(
    "change",
    (event) => {
      if (event.isTrusted === false) return;
      const element = event.target instanceof Element ? event.target : null;
      const tag = element?.tagName?.toLowerCase();
      if (!["input", "textarea", "select"].includes(tag || "")) return;
      if (isIgnoredInputTarget(element)) return;

      const payload = basePayload("change", event);
      const type = fieldType(element);
      payload.value = safeValue(element);
      payload.inputType = type;
      report(payload);
    },
    true,
  );

  document.addEventListener(
    "keydown",
    (event) => {
      if (event.isTrusted === false) return;
      if (["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(event.key)) return;

      const target = event.target instanceof Element ? event.target : null;
      if (isTextEntry(target) || target?.tagName === "SELECT") {
        if (event.key !== "Enter" || !isEnterSubmittableTextInput(target) || isIgnoredInputTarget(target)) {
          return;
        }
      }

      const payload = basePayload("keypress", event);
      payload.key = event.key;
      if (target instanceof Element) {
        payload.value = safeValue(target);
        payload.inputType = fieldType(target);
      }
      report(payload);
    },
    true,
  );
})();
