// A native modal keeps keyboard focus on the decision and returns it on close.
export function confirmRemoval({ title, body, files = [], works = [], shared = [], actions, doc = document }) {
  const d = doc.createElement("dialog");
  d.className = "dp-removal";
  d.setAttribute("aria-labelledby", "dp-removal-title");
  d.setAttribute("aria-describedby", "dp-removal-body");
  const add = (tag, text, parent = d) => {
    const node = doc.createElement(tag);
    node.textContent = text;
    parent.append(node);
    return node;
  };
  add("h2", title).id = "dp-removal-title";
  add("p", body).id = "dp-removal-body";
  for (const [label, entries] of [files, shared, works]) {
    if (!entries?.length) continue;
    add("h3", label);
    const list = add("ul", "");
    for (const line of entries) add("li", line, list);
  }
  const row = add("form", "");
  row.method = "dialog";
  for (const [label, value] of actions) {
    const b = add("button", label, row);
    b.value = value;
  }
  doc.body.append(d);
  return new Promise(resolve => {
    d.addEventListener("close", () => { resolve(d.returnValue || null); d.remove(); }, { once: true });
    d.showModal();
    row.firstElementChild.focus();
  });
}
