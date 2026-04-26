// Minimal markdown -> HTML renderer for V30 report.md.
//
// Phase A scope discipline: handles the exact subset that report.md
// emits (headings #/##/###/####, paragraphs, github-pipe tables, bullet
// lists, inline [N] citation tokens). No external dependency.
//
// Citation tokens [N] are converted to <a class="citation"
// data-num="N" href="#citation-N">[N]</a> so M-3 can wire click-to-inspect.

(function (global) {
  "use strict";

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderInline(text) {
    let out = escapeHtml(text);
    // Citation tokens: [N] where N is one or more digits.
    // Multiple consecutive tokens like [19][20] are both replaced.
    out = out.replace(/\[(\d+)\]/g, function (_match, num) {
      return (
        '<a class="citation" data-num="' +
        num +
        '" href="#citation-' +
        num +
        '" role="button" tabindex="0">[' +
        num +
        "]</a>"
      );
    });
    return out;
  }

  function renderTableRow(line, isHeader) {
    const cells = line
      .replace(/^\s*\|/, "")
      .replace(/\|\s*$/, "")
      .split("|")
      .map((c) => c.trim());
    const tag = isHeader ? "th" : "td";
    const inner = cells.map((c) => `<${tag}>${renderInline(c)}</${tag}>`).join("");
    return `<tr>${inner}</tr>`;
  }

  function isTableSeparator(line) {
    // | --- | --- | format
    return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
  }

  function render(markdown) {
    const lines = markdown.replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let i = 0;
    let paragraph = [];

    function flushParagraph() {
      if (paragraph.length === 0) return;
      out.push("<p>" + renderInline(paragraph.join(" ")) + "</p>");
      paragraph = [];
    }

    while (i < lines.length) {
      const line = lines[i];

      // Blank line ends a paragraph.
      if (/^\s*$/.test(line)) {
        flushParagraph();
        i += 1;
        continue;
      }

      // Headings.
      const heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) {
        flushParagraph();
        const level = heading[1].length;
        out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        i += 1;
        continue;
      }

      // Bullet list.
      if (/^\s*-\s+/.test(line)) {
        flushParagraph();
        const items = [];
        while (i < lines.length && /^\s*-\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*-\s+/, ""));
          i += 1;
        }
        out.push(
          "<ul>" +
            items.map((it) => "<li>" + renderInline(it) + "</li>").join("") +
            "</ul>"
        );
        continue;
      }

      // Github-style table: header | sep | row...
      if (
        line.includes("|") &&
        i + 1 < lines.length &&
        isTableSeparator(lines[i + 1])
      ) {
        flushParagraph();
        const header = lines[i];
        i += 2; // skip header + separator
        const rows = [];
        while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
          rows.push(lines[i]);
          i += 1;
        }
        out.push(
          "<table>" +
            "<thead>" +
            renderTableRow(header, true) +
            "</thead>" +
            "<tbody>" +
            rows.map((r) => renderTableRow(r, false)).join("") +
            "</tbody>" +
            "</table>"
        );
        continue;
      }

      paragraph.push(line);
      i += 1;
    }
    flushParagraph();
    return out.join("\n");
  }

  global.PolarisMarkdown = { render: render, renderInline: renderInline };
})(window);
