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
