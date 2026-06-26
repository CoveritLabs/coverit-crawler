(() => {
  if (globalThis.__coveritFlowRecorderInstalled) return;
  globalThis.__coveritFlowRecorderInstalled = true;

  function escapeCss(value) {
    if (globalThis.CSS && typeof globalThis.CSS.escape === "function") {
      return globalThis.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, "\\$&");
  }

  const TEST_ID_ATTRIBUTES = ["data-testid", "data-test", "data-cy"];

  function testIdSelectorFor(element) {
    for (const attribute of TEST_ID_ATTRIBUTES) {
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

      const classes = [...current.classList]
        .filter((className) => className && !/^\d/.test(className))
        .slice(0, 2);
      for (const className of classes) {
        part += `.${escapeCss(className)}`;
      }

      const parent = current.parentElement;
      if (parent) {
        const siblings = [...parent.children].filter((child) => child.tagName === current.tagName);
        if (siblings.length > 1) {
          part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }

      parts.unshift(part);
      current = current.parentElement;
    }

    return parts.length ? parts.join(" > ") : "body";
  }

  function addCandidate(candidates, value) {
    const selector = String(value || "").trim();
    if (!selector || candidates.includes(selector)) return;
    candidates.push(selector);
  }

  function selectorCandidatesFor(element) {
    const candidates = [];
    if (!(element instanceof Element)) return candidates;

    addCandidate(candidates, testIdSelectorFor(element));
    if (element.id) addCandidate(candidates, `#${escapeCss(element.id)}`);

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) {
      addCandidate(candidates, `${element.tagName.toLowerCase()}[aria-label="${escapeCss(ariaLabel)}"]`);
    }

    const name = element.getAttribute("name");
    if (name) {
      addCandidate(candidates, `${element.tagName.toLowerCase()}[name="${escapeCss(name)}"]`);
    }

    const href = element.tagName.toLowerCase() === "a" ? element.getAttribute("href") : "";
    if (href) {
      addCandidate(candidates, `a[href="${escapeCss(href)}"]`);
    }

    const role = element.getAttribute("role");
    if (role) {
      addCandidate(candidates, `${element.tagName.toLowerCase()}[role="${escapeCss(role)}"]`);
    }

    addCandidate(candidates, selectorFor(element));
    return candidates;
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

  function isTextEntry(element) {
    if (!(element instanceof Element)) return false;
    const tag = element.tagName?.toLowerCase();
    return tag === "input" || tag === "textarea" || element.isContentEditable;
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
      report(basePayload("click", event));
    },
    true,
  );

  document.addEventListener(
    "input",
    (event) => {
      const element = event.target instanceof Element ? event.target : null;
      if (!isTextEntry(element)) return;

      const payload = basePayload("input", event);
      const type = element?.getAttribute?.("type")?.toLowerCase() || element?.tagName?.toLowerCase() || "text";
      payload.value = safeValue(element);
      payload.inputType = type;
      report(payload);
    },
    true,
  );

  document.addEventListener(
    "change",
    (event) => {
      const element = event.target instanceof Element ? event.target : null;
      const tag = element?.tagName?.toLowerCase();
      if (!["input", "textarea", "select"].includes(tag || "")) return;

      const payload = basePayload("change", event);
      const type = element?.getAttribute?.("type")?.toLowerCase() || tag || "text";
      payload.value = safeValue(element);
      payload.inputType = type;
      report(payload);
    },
    true,
  );

  document.addEventListener(
    "keydown",
    (event) => {
      if (isTextEntry(event.target) || event.target?.tagName === "SELECT") return;
      if (["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(event.key)) return;

      const payload = basePayload("keypress", event);
      payload.key = event.key;
      report(payload);
    },
    true,
  );
})();
