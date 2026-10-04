"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const tools = require("../public/library-tools.js");

test("template names are unique and literal values do not expand recursively", () => {
  const text = '  start --ip "{{ip}}" --port {{port}}\n# {{ip}}\n';
  assert.deepEqual(tools.variableNames(text), ["ip", "port"]);
  assert.equal(tools.renderTemplate(text, {ip:"$&{{port}}", port:"27015"}),
    '  start --ip "$&{{port}}" --port 27015\n# $&{{port}}\n');
  assert.throws(() => tools.renderTemplate(text, {ip:"127.0.0.1"}), /port/);
  assert.throws(() => tools.renderTemplate(text, {ip:" ", port:"27015"}), /ip/);
  assert.equal(tools.renderTemplate("plain\n", {}), "plain\n");
});
test("template values and markup remain literal text", () => {
  assert.equal(tools.renderTemplate("{{name}}", {name:'<script>alert(1)</script>'}), '<script>alert(1)</script>');
  assert.throws(() => tools.renderTemplate("{{constructor}}", {}), /constructor/);
  assert.deepEqual(tools.variableNames("{{bad-name}} {{name with space}} {{ok_1}}"), ["ok_1"]);
});
test("search combines words, exact tags, descendants, attachments and projects", () => {
  const item = {title:"Docker server", content:"  run linux\n", notes:"", tags:"Docker, Linux",
    filename:"server.sh", os:"Ubuntu", language:"bash", status:"tested", project_ids:[3], category:"child"};
  const filters = {query:"linux server", tags:"docker,LINUX", category:"parent", attachments:true,
    project:"3", os:"Ubuntu", language:"bash", status:"tested"};
  assert.equal(tools.matches(item, filters, new Set(["parent", "child"])), true);
  assert.equal(tools.matches(item, filters, new Set(["parent"])), false);
  for (const change of [{tags:"dock"}, {query:"missing"}, {project:"2"}, {os:"Windows"}, {status:"template"}]) {
    assert.equal(tools.matches(item, {...filters, ...change}, new Set(["child"])), false);
  }
  assert.equal(tools.matches({...item, filename:null}, filters, new Set(["child"])), false);
  assert.equal(tools.matches(item, {category:"all"}, new Set()), true);
});
test("text file classification and language detection", () => {
  for (const filename of ["start.sh", "server.cfg", "compose.YAML", "Dockerfile", ".env", "file.txt"]) {
    assert.equal(tools.isText(filename), true);
  }
  assert.equal(tools.isText("backup.zip"), false);
  assert.equal(tools.isText("note.txt.exe"), false);
  assert.equal(tools.language("start.PS1"), "powershell");
  assert.equal(tools.language("server.py"), "python");
  assert.equal(tools.language("notes.txt"), "plain");
});
test("review reminders use calendar months and clamp month end in UTC", () => {
  const row = {created:"2026-01-31 12:00:00", review_months:"1"};
  assert.deepEqual(tools.reviewDue(row, new Date("2026-02-27T23:59:59Z")), {date:"2026-02-28",due:false});
  assert.deepEqual(tools.reviewDue(row, new Date("2026-02-28T00:00:00Z")), {date:"2026-02-28",due:true});
  assert.equal(tools.reviewDue({...row,reviewed_at:"2026-03-01"}).date,"2026-04-01");
  assert.equal(tools.reviewDue({created:"2026-10-04 01:00:00"}).date,"2027-04-04");
  assert.throws(() => tools.reviewDue({...row,review_months:"0"}));
});

test("line diff precisely preserves both versions including blank lines", () => {
  for (const [before,after] of [["a\nb\n","a\nc\n"],["","x"],["x",""],["same\n","same\n"],
    ["a\nb\nc","b\nc\na"], ["<script>\n \n","<img>\n\n"]]) {
    const result = tools.lineDiff(before,after);
    assert.equal(result.filter(row => row.kind !== "add").map(row => row.text).join("\n"),before);
    assert.equal(result.filter(row => row.kind !== "remove").map(row => row.text).join("\n"),after);
  }
  assert.throws(() => tools.lineDiff(Array(1100).fill("a").join("\n"),Array(1100).fill("b").join("\n")));
  assert.throws(() => tools.lineDiff("\n".repeat(10001),"\n".repeat(10001)));
});
