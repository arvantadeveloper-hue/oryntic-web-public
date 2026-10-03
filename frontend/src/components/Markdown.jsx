import React from "react";

// Lightweight markdown renderer (headings, bold, lists, code blocks, inline code, tables-ish, paragraphs)
const repairHref = (url) => (/^(workspace|chat|calendar|gallery|reminders)\//.test(url) ? "/" + url : url);
const safeHref = (url) => (/^(https?:\/\/[^\s"'<>]+|\/[\w\-\/#?=&.%:]*)$/i.test(url) ? url : null);
const isFile = (url) => /\/api\/files\//.test(url);

function linkTag(label, raw) {
  const url = safeHref(repairHref(raw));
  if (!url) return label;
  const abs = url.startsWith("/") ? `${window.location.origin}${url}` : url;
  const dl = isFile(abs) ? ` download data-file="1" href="${abs}${abs.includes("?") ? "&" : "?"}download=1"` : ` href="${abs}"`;
  return `<a${dl} target="_blank" rel="noreferrer noopener" data-link="1">${label}</a>`;
}

function inline(text) {
  let t = text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^)]*&quot;)?\)/g, (_, label, url) => linkTag(label, url.replace(/&amp;/g, "&")));
  return t;
}

export function Markdown({ content = "" }) {
  const onClick = (e) => { const a = e.target.closest && e.target.closest("a[data-link]"); if (a) e.stopPropagation(); };
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
