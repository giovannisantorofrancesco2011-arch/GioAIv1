// node --test test/  (le risposte di Vio passano da qui prima di finire nel pannello)
const test = require("node:test");
const assert = require("node:assert");
const { render, inline } = require("../media/markdown.js");

test("niente HTML del modello arriva alla pagina", () => {
  const html = render('<img src=x onerror="alert(1)"> e `<script>` e [x](javascript:alert(1))');
  assert.ok(!html.includes("<img") && !html.includes("<script>"));
  assert.ok(html.includes("&lt;img") && html.includes("<code>&lt;script&gt;</code>"));
  assert.ok(!html.includes('data-href="javascript'));
});

test("blocchi di codice con Copia/Inserisci, e diff colorati", () => {
  const html = render("```python file=app/main.py\ndef f():\n    return 1 < 2\n```");
  assert.match(html, /<span>app\/main.py<\/span>/);
  assert.ok(html.includes("data-copy") && html.includes("data-insert"));
  assert.ok(html.includes("return 1 &lt; 2"));
  const diff = render("```diff\n-a\n+b\n```");
  assert.ok(diff.includes('<span class="del">-a</span>') && diff.includes('<span class="add">+b</span>'));
  assert.ok(!diff.includes("data-insert"));
});

test("liste annidate, compiti, tabelle, titoli e link", () => {
  const html = render("# Titolo\n- uno\n  - due\n- [x] fatto\n\n| a | b |\n|---|---|\n| 1 | **2** |\n\nvedi https://example.com.");
  assert.ok(html.startsWith("<h3>Titolo</h3><ul><li>uno<ul><li>due</li></ul></li>"));
  assert.ok(html.includes('<li class="task done">fatto</li>'));
  assert.ok(html.includes("<td><strong>2</strong></td>"));
  assert.ok(html.includes('<a href="#" data-href="https://example.com">https://example.com</a>.'));
});

test("inline: codice protetto dalla formattazione", () => {
  assert.strictEqual(inline("`a*b*c` e *io*"), "<code>a*b*c</code> e <em>io</em>");
});
