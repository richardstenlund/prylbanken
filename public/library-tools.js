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
    },
    reviewDue(item, now = new Date()) {
      const source = item.reviewed_at || item.tested_at || String(item.created || "").slice(0, 10);
      const date = new Date(source + "T00:00:00Z");
      const months = Number(item.review_months || 6);
      if (Number.isNaN(date.getTime()) || !Number.isInteger(months) || months < 1 || months > 120) {
        throw new Error("Ogiltigt granskningsdatum eller intervall.");
      }
      const day = date.getUTCDate();
      date.setUTCDate(1);
      date.setUTCMonth(date.getUTCMonth() + months);
      const end = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
      date.setUTCDate(Math.min(day, end));
      return {date:date.toISOString().slice(0,10), due:now >= date};
    },
    lineDiff(before, after) {
      const a = before.split("\n"), b = after.split("\n");
      if (a.length + b.length > 20000) {
        throw new Error("Versionerna innehåller för många rader för webbvisning. Jämför dem lokalt.");
      }
      let start = 0, end = 0;
      while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
      while (end < a.length - start && end < b.length - start &&
        a[a.length - end - 1] === b[b.length - end - 1]) end += 1;
      const x = a.slice(start, a.length - end), y = b.slice(start, b.length - end);
      if ((x.length + 1) * (y.length + 1) > 1000000) {
        throw new Error("Ändringen är för stor för radjämförelsen. Ladda ned versionerna och jämför dem lokalt.");
      }
      const matrix = Array.from({length:x.length + 1}, () => new Uint32Array(y.length + 1));
      for (let i = x.length - 1; i >= 0; i -= 1) {
        for (let j = y.length - 1; j >= 0; j -= 1) {
          matrix[i][j] = x[i] === y[j] ? matrix[i+1][j+1] + 1 : Math.max(matrix[i+1][j], matrix[i][j+1]);
        }
      }
      const output = a.slice(0,start).map(text => ({kind:"same", text}));
      let i = 0, j = 0;
      while (i < x.length || j < y.length) {
        if (i < x.length && j < y.length && x[i] === y[j]) output.push({kind:"same", text:x[i++]}), j++;
        else if (j < y.length && (i === x.length || matrix[i][j+1] > matrix[i+1][j])) output.push({kind:"add", text:y[j++]});
        else output.push({kind:"remove", text:x[i++]});
      }
      return output.concat(a.slice(a.length-end).map(text => ({kind:"same", text})));
    }
  };
  if (typeof module !== "undefined" && module.exports) module.exports = tools;
  else root.LibraryTools = tools;
})(globalThis);
