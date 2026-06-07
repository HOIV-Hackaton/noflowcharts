import { useState, type ReactNode } from "react";

import { EmptyPanel, PageHeading, StatusLabel as ServiceStatusLabel } from "@/components/service-desk-ui";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { EventType, RunEvent } from "@/types";

export function PageHeader({
  aside,
  badges,
  title,
}: {
  aside?: ReactNode;
  badges?: ReactNode;
  title: string;
}) {
  return <PageHeading action={aside} badges={badges} title={title} />;
}

export function HeadingWithTags({ badges, children }: { badges?: ReactNode; children: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <h2 className="truncate font-heading text-lg font-medium tracking-normal text-foreground">{children}</h2>
      {badges ? <div className="flex flex-wrap items-center gap-1.5">{badges}</div> : null}
    </div>
  );
}

export function DefinitionTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <Table>
      <TableBody>
        {rows.map(([label, value]) => (
          <TableRow key={label}>
            <TableHead className="w-[34%] text-muted-foreground">{label}</TableHead>
            <TableCell className="whitespace-normal break-words">{value}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function EventTable({ events }: { events: RunEvent[] }) {
  if (!events.length) {
    return <EmptyState title="No log entries" detail="Events appear as the run progresses." />;
  }

  return (
    <Table className="table-fixed">
      <colgroup>
        <col className="w-24" />
        <col className="w-28" />
        <col className="w-48" />
        <col />
      </colgroup>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Event</TableHead>
          <TableHead>Detail</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => (
          <TableRow key={event.id}>
            <TableCell className="text-xs text-muted-foreground">{event.time}</TableCell>
            <TableCell>
              <StatusLabel label={event.type} />
            </TableCell>
            <TableCell className="whitespace-normal break-words font-medium">
              <TruncatedText text={event.title} maxLength={90} />
            </TableCell>
            <TableCell className="whitespace-normal break-words text-muted-foreground">
              <TruncatedText text={event.detail} maxLength={280} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function TruncatedText({ maxLength = 220, text }: { maxLength?: number; text: string }) {
  const [expanded, setExpanded] = useState(false);
  const shouldTruncate = text.length > maxLength;
  const visibleText = !shouldTruncate || expanded ? text : `${text.slice(0, maxLength).trimEnd()}...`;

  return (
    <span className="break-words">
      {visibleText}
      {shouldTruncate ? (
        <>
          {" "}
          <button
            className="font-medium text-foreground underline-offset-2 hover:underline"
            onClick={() => setExpanded((current) => !current)}
            type="button"
          >
            {expanded ? "see less" : "see more"}
          </button>
        </>
      ) : null}
    </span>
  );
}

export function LogFilter({
  onChange,
  value,
}: {
  onChange: (filter: "all" | EventType) => void;
  value: "all" | EventType;
}) {
  return (
    <Select onValueChange={(nextValue) => onChange(nextValue as "all" | EventType)} value={value}>
      <SelectTrigger aria-label="Log filter" size="sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectItem value="all">All logs</SelectItem>
          <SelectItem value="analysis">Analysis</SelectItem>
          <SelectItem value="approval">Approval</SelectItem>
          <SelectItem value="command">Command</SelectItem>
          <SelectItem value="output">Output</SelectItem>
          <SelectItem value="validation">Validation</SelectItem>
          <SelectItem value="error">Error</SelectItem>
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

export function EmptyState({ detail, title }: { detail: string; title: string }) {
  return <EmptyPanel detail={detail} title={title} />;
}

export function StatusLabel({ label }: { label: string }) {
  return <ServiceStatusLabel label={label} />;
}
