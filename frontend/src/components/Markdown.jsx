import React from "react";

// Lightweight markdown renderer (headings, bold, lists, code blocks, inline code, tables-ish, paragraphs)
const safeHref = (url) => (/^(https?:\/\/[^\s"'<>]+|\/[\w\-\/#?=&.%:]*)$/i.test(url) ? url : "#");
const isInternal = (url) => url.startsWith("/");

function inline(text) {
  let t = text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, url) => (isInternal(url) ? `<a href="${safeHref(url)}" data-internal="1">${label}</a>` : `<a href="${safeHref(url)}" target="_blank" rel="noreferrer noopener">${label}</a>`));
  return t;
}

export function Markdown({ content = "" }) {
  const onClick = (e) => {
    const a = e.target.closest && e.target.closest("a[data-internal]");
    if (a) { e.preventDefault(); window.history.pushState({}, "", a.getAttribute("href")); window.dispatchEvent(new PopStateEvent("popstate")); }
  };
  const lines = content.split("\n");
  const blocks = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) { code.push(lines[i]); i++; }
      i++;
      blocks.push(<pre key={key++}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      const txt = line.replace(/^#+\s/, "");
      const H = `h${level}`;
      blocks.push(React.createElement(H, { key: key++, dangerouslySetInnerHTML: { __html: inline(txt) } }));
      i++; continue;
    }
    if (/^\s*[-*]\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) {
        items.push(<li key={key++} dangerouslySetInnerHTML={{ __html: inline(lines[i].replace(/^\s*[-*]\s/, "")) }} />);
        i++;
      }
      blocks.push(<ul key={key++}>{items}</ul>);
      continue;
    }
    if (/^\s*\d+\.\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s/.test(lines[i])) {
        items.push(<li key={key++} dangerouslySetInnerHTML={{ __html: inline(lines[i].replace(/^\s*\d+\.\s/, "")) }} />);
        i++;
      }
      blocks.push(<ol key={key++}>{items}</ol>);
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        if (!/^\s*\|[\s:|-]+\|\s*$/.test(lines[i])) rows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
        i++;
      }
      if (rows.length) {
        const [head, ...body] = rows;
        blocks.push(
          <div key={key++} className="overflow-x-auto"><table>
            <thead><tr>{head.map((c, k) => <th key={k} dangerouslySetInnerHTML={{ __html: inline(c) }} />)}</tr></thead>
            <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, k) => <td key={k} dangerouslySetInnerHTML={{ __html: inline(c) }} />)}</tr>)}</tbody>
          </table></div>
        );
      }
      continue;
    }
    if (line.trim() === "") { i++; continue; }
    blocks.push(<p key={key++} dangerouslySetInnerHTML={{ __html: inline(line) }} />);
    i++;
  }
  return <div className="md-body" onClick={onClick}>{blocks}</div>;
}
