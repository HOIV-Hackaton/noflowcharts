type MarkdownBlock =
  | { content: string; level: number; type: "heading" }
  | { items: string[]; type: "list" }
  | { content: string; type: "paragraph" }
  | { content: string; type: "code" };

export function MarkdownContent({
  children,
  omitFirstHeading,
}: {
  children: string;
  omitFirstHeading?: string;
}) {
  const blocks = parseMarkdown(children).filter((block, index) => {
    if (!omitFirstHeading || index !== 0 || block.type !== "heading") {
      return true;
    }

    return block.content.trim().toLowerCase() !== omitFirstHeading.trim().toLowerCase();
  });

  return (
    <div className="markdown-content">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const HeadingTag = `h${Math.min(block.level, 4)}` as "h1" | "h2" | "h3" | "h4";
          return <HeadingTag key={`${block.type}-${index}`}>{block.content}</HeadingTag>;
        }

        if (block.type === "list") {
          return (
            <ul key={`${block.type}-${index}`}>
              {block.items.map((item) => (
                <li key={item}>{formatInlineMarkdown(item)}</li>
              ))}
            </ul>
          );
        }

        if (block.type === "code") {
          return <pre key={`${block.type}-${index}`}>{block.content}</pre>;
        }

        return <p key={`${block.type}-${index}`}>{formatInlineMarkdown(block.content)}</p>;
      })}
    </div>
  );
}

function parseMarkdown(value: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = normalizeInlineHeadings(value).split(/\r?\n/);
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let codeLines: string[] = [];
  let inCode = false;

  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }

    blocks.push({ content: paragraph.join(" ").trim(), type: "paragraph" });
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) {
      return;
    }

    blocks.push({ items: listItems, type: "list" });
    listItems = [];
  };

  const flushCode = () => {
    blocks.push({ content: codeLines.join("\n"), type: "code" });
    codeLines = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (line.startsWith("```")) {
      if (inCode) {
        flushCode();
      } else {
        flushParagraph();
        flushList();
      }
      inCode = !inCode;
      continue;
    }

    if (inCode) {
      codeLines.push(rawLine);
      continue;
    }

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ content: heading[2].trim(), level: heading[1].length, type: "heading" });
      continue;
    }

    const listItem = line.match(/^[-*]\s+(.+)$/);
    if (listItem) {
      flushParagraph();
      listItems.push(listItem[1].trim());
      continue;
    }

    paragraph.push(line);
  }

  if (inCode) {
    flushCode();
  }
  flushParagraph();
  flushList();

  return blocks;
}

function normalizeInlineHeadings(value: string) {
  return value.replace(/\s+(#{1,4}\s+)/g, "\n$1").trim();
}

function formatInlineMarkdown(value: string) {
  const parts = value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);

  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
    }

    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }

    return part;
  });
}
