(() => {
  const BRAND = "Mosent Group";

  const replaceInText = (text) => {
    if (!text) return text;
    return text
      .replace(/Mosent Group\s*\(Open WebUI\)/g, BRAND)
      .replace(/\bOpen WebUI\b/g, BRAND)
      .replace(/\s+\(Open WebUI\)/g, "");
  };

  const patchTextNodes = (root) => {
    if (!root) return;

    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const v = node.nodeValue || "";
          if (
            v.includes("Open WebUI") ||
            v.includes("(Open WebUI)") ||
            v.includes("Mosent Group (Open WebUI)")
          ) {
            return NodeFilter.FILTER_ACCEPT;
          }
          return NodeFilter.FILTER_REJECT;
        },
      }
    );

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    for (const node of nodes) {
      const next = replaceInText(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    }
  };

  const patchAttributes = () => {
    document.title = replaceInText(document.title || BRAND) || BRAND;

    document
      .querySelectorAll("meta[name='application-name'], meta[name='apple-mobile-web-app-title'], meta[property='og:title']")
      .forEach((el) => {
        el.setAttribute("content", BRAND);
      });

    document.documentElement.setAttribute("data-brand", BRAND);
  };

  const patchAll = () => {
    patchAttributes();
    patchTextNodes(document.body);
  };

  const start = () => {
    patchAll();

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "characterData" && m.target?.nodeValue) {
          const next = replaceInText(m.target.nodeValue);
          if (next !== m.target.nodeValue) m.target.nodeValue = next;
        }

        for (const node of m.addedNodes || []) {
          if (node.nodeType === Node.TEXT_NODE) {
            const next = replaceInText(node.nodeValue || "");
            if (next !== node.nodeValue) node.nodeValue = next;
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            patchTextNodes(node);
          }
        }
      }

      patchAttributes();
    });

    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
    });

    setInterval(patchAll, 1200);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
