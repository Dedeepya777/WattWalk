/** Report tab: report_md rendered as Markdown (plan 11.3). */
import type { ReactNode } from "react";
import { useAppState } from "../state";

function inline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-b-${index}`}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={`${keyPrefix}-c-${index}`}>{token.slice(1, -1)}</code>);
    }
    last = match.index + token.length;
    index += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function renderMarkdown(markdown: string): ReactNode[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const text = paragraph.join(" ");
    blocks.push(<p key={`p-${blocks.length}`}>{inline(text, `p-${blocks.length}`)}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (listItems.length === 0) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {listItems.map((item, index) => (
          <li key={`li-${index}`}>{inline(item, `li-${blocks.length}-${index}`)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };

  for (const line of lines) {
    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }
    if (line.startsWith("### ")) {
      flushParagraph();
      flushList();
      blocks.push(<h4 key={`h4-${blocks.length}`}>{inline(line.slice(4), `h4-${blocks.length}`)}</h4>);
    } else if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      blocks.push(<h3 key={`h3-${blocks.length}`}>{inline(line.slice(3), `h3-${blocks.length}`)}</h3>);
    } else if (line.startsWith("# ")) {
      flushParagraph();
      flushList();
      blocks.push(<h2 key={`h2-${blocks.length}`}>{inline(line.slice(2), `h2-${blocks.length}`)}</h2>);
    } else if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph();
      listItems.push(line.replace(/^\s*[-*]\s+/, ""));
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}

export function ReportTab() {
  const report = useAppState().audit?.report_md ?? null;
  const status = useAppState().audit?.status.status;

  if (!report) {
    return (
      <p className="empty">
        {status === "running"
          ? "Report appears when the audit completes."
          : "Report appears when the audit completes."}
      </p>
    );
  }

  return (
    <div className="report">
      <button
        className="button small copy-button"
        onClick={() => {
          if (navigator.clipboard) void navigator.clipboard.writeText(report);
        }}
      >
        Copy Markdown
      </button>
      <article className="report-body">{renderMarkdown(report)}</article>
    </div>
  );
}
