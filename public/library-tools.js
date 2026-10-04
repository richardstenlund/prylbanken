"use strict";
(function (root) {
  const placeholder = /\{\{([A-Za-z_][A-Za-z0-9_]{0,39})\}\}/g;
  const tools = {
    variableNames(text) {
      return [...new Set([...text.matchAll(placeholder)].map(match => match[1]))];
    },
    renderTemplate(text, values) {
      const missing = tools.variableNames(text).filter(name => typeof values[name] !== "string" || !values[name].trim());
      if (missing.length) throw new Error(`Fyll i alla mallvariabler: ${missing.join(", ")}.`);
      return text.replace(placeholder, (_, name) => values[name]);
    },
    matches(item, filters, categoryKeys) {
      const tags = String(filters.tags || "").toLocaleLowerCase("sv").split(",").map(tag => tag.trim()).filter(Boolean);
      const itemTags = item.tags.toLocaleLowerCase("sv").split(",").map(tag => tag.trim());
      const query = String(filters.query || "").toLocaleLowerCase("sv").trim().split(/\s+/).filter(Boolean);
      const text = [item.title, item.content, item.notes, item.tags, item.filename || "", item.os || "",
        item.program_version || "", item.ports || "", item.dependencies || "", item.language || ""].join(" ").toLocaleLowerCase("sv");
      const category = filters.category || "all";
      return (category === "all" || (category === "favorites" ? Boolean(item.favorite) :
        category === "filer" ? item.filename !== null || item.category === "filer" : categoryKeys.has(item.category))) &&
        query.every(term => text.includes(term)) && tags.every(tag => itemTags.includes(tag)) &&
        (!filters.attachments || item.filename !== null) &&
        (!filters.project || (item.project_ids || []).includes(Number(filters.project))) &&
        (!filters.os || item.os === filters.os) && (!filters.language || item.language === filters.language) &&
        (!filters.status || item.status === filters.status);
    },
    language(filename) {
      const extension = filename.toLowerCase().split(".").pop();
      return ({sh:"bash", bash:"bash", ps1:"powershell", bat:"bat", cmd:"bat", yaml:"yaml", yml:"yaml",
        json:"json", py:"python", js:"javascript", mjs:"javascript", sql:"sql"})[extension] || "plain";
    },
    isText(filename) {
      return /(?:\.(?:txt|sh|bash|ps1|bat|cmd|ya?ml|json|py|js|mjs|sql|cfg|ini|conf|md|env)$|^Dockerfile$|^\.env$)/i.test(filename);
    }
  };
  if (typeof module !== "undefined" && module.exports) module.exports = tools;
  else root.LibraryTools = tools;
})(globalThis);
