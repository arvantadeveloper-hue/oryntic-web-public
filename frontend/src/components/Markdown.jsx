import React from "react";

// Lightweight markdown renderer (headings, bold, lists, code blocks, inline code, tables-ish, paragraphs)
function inline(text) {
  let t = text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return t;
}

export function Markdown({ content = "" }) {
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
    if (line.trim() === "") { i++; continue; }
    blocks.push(<p key={key++} dangerouslySetInnerHTML={{ __html: inline(line) }} />);
    i++;
  }
  return <div className="md-body">{blocks}</div>;
}
