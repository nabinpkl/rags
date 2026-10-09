"use client";

import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { arxivAbsUrl } from "@/lib/arxiv-links";

interface MessageMarkdownProps {
  text: string;
  verifiedPaperIds: ReadonlySet<string>;
}

const ARXIV_ID_PATTERN = /\b(\d{4}\.\d{4,5})(v\d+)?\b/g;
const CITATION_SCHEME = "citation:";

/** Rewrites a VERIFIED arXiv id into a markdown link the `a` override below
 * turns into a citation chip. An unverified id is left as plain text —
 * ReactMarkdown never HTML-parses it, so it renders inert by construction,
 * exactly like every other word in the answer (DECISIONS.md 2026-07-08). */
function linkifyVerifiedCitations(text: string, verifiedPaperIds: ReadonlySet<string>): string {
  return text.replace(ARXIV_ID_PATTERN, (match, id: string) =>
    verifiedPaperIds.has(id) ? `[${match}](${CITATION_SCHEME}${id})` : match,
  );
}

const CitationOrInertLink: Components["a"] = ({ href, children }) => {
  if (href?.startsWith(CITATION_SCHEME)) {
    const paperId = href.slice(CITATION_SCHEME.length);
    return (
      <a
        href={arxivAbsUrl(paperId)}
        target="_blank"
        rel="noopener noreferrer"
        className="border-machine-accent/40 bg-machine-accent/10 text-machine-accent hover:bg-machine-accent/20 inline-block rounded border px-1 font-mono text-[11px] leading-normal"
      >
        {children}
      </a>
    );
  }
  // Any other link the answer text happens to contain (e.g. a URL quoted
  // from untrusted, fenced corpus content, §5/§6) renders as plain text —
  // no outbound link askRAG didn't construct itself.
  return <span>{children}</span>;
};

/** Block styles for the tags an answer uses. Preflight strips paragraph
 * margins and list bullets, so without these a multi-paragraph answer ran
 * together as one block and a list lost its markers. Styling only: each
 * override renders the same allow-listed tag react-markdown would. */
const BLOCKS: Components = {
  a: CitationOrInertLink,
  p: ({ children }) => <p className="[&:not(:first-child)]:mt-3">{children}</p>,
  ul: ({ children }) => <ul className="mt-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="marker:text-machine-muted pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children }) => (
    <code className="bg-machine-2 rounded px-1 py-px font-mono text-[12.5px]">{children}</code>
  ),
  h1: ({ children }) => <p className="mt-4 font-semibold first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="mt-4 font-semibold first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="mt-3 font-semibold first:mt-0">{children}</p>,
};

function citationUrlTransform(url: string): string {
  // react-markdown's defaultUrlTransform allow-lists http(s)/irc(s)/mailto/
  // xmpp and drops everything else (including our synthetic scheme) — this
  // is the one, explicit exception, everything else still goes through the
  // library's own safe-URL check.
  return url.startsWith(CITATION_SCHEME) ? url : defaultUrlTransform(url);
}

/** react-markdown + remark-gfm, NO rehype-raw, `skipHtml: true`, NO
 * `dangerouslySetInnerHTML` — hostile HTML in answer text (e.g. a
 * prompt-injection attempt echoed back from fenced, untrusted corpus
 * content, §6) is never parsed as markup, only ever as inert text. This
 * holds by construction: there is no code path in this component capable of
 * turning a string into a DOM element other than react-markdown's own
 * allow-listed tag renderers below. */
export function MessageMarkdown({ text, verifiedPaperIds }: MessageMarkdownProps) {
  return (
    <div className="text-machine-text text-[14px] leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={citationUrlTransform}
        components={BLOCKS}
      >
        {linkifyVerifiedCitations(text, verifiedPaperIds)}
      </ReactMarkdown>
      {/* §6c: every answer carries this label, unconditionally. */}
      <div className="text-machine-muted mt-3 font-mono text-[9.5px] tracking-wide uppercase">
        AI-generated
      </div>
    </div>
  );
}
