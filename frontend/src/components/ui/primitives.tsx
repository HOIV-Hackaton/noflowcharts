import type { ReactNode } from "react";
import { getStatusBadgeClass } from "../status";
import type { EventType, RunEvent } from "../../types";

export function PageHeader({
  aside,
  badges,
  title,
}: {
  aside?: ReactNode;
  badges?: ReactNode;
  title: string;
}) {
  return (
    <header className="page-header">
      <div>
        <HeadingWithTags badges={badges}>{title}</HeadingWithTags>
      </div>
      {aside ? <div className="header-aside">{aside}</div> : null}
    </header>
  );
}

export function HeadingWithTags({ badges, children }: { badges?: ReactNode; children: string }) {
  return (
    <div className="title-row">
      <h2>{children}</h2>
      {badges ? <div className="title-tags">{badges}</div> : null}
    </div>
  );
}

export function DefinitionTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <table className="definition-table">
      <colgroup>
        <col className="w-[34%]" />
        <col className="w-[66%]" />
      </colgroup>
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <th>{label}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function EventTable({ events }: { events: RunEvent[] }) {
  if (!events.length) {
    return <EmptyState title="No log entries" detail="Events appear as the mock run progresses." />;
  }

  return (
    <table className="data-table">
      <colgroup>
        <col className="w-[16%]" />
        <col className="w-[14%]" />
        <col className="w-[24%]" />
        <col className="w-[46%]" />
      </colgroup>
      <thead>
        <tr>
          <th>Time</th>
          <th>Type</th>
          <th>Event</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.id}>
            <td>{event.time}</td>
            <td>
              <StatusLabel label={event.type} />
            </td>
            <td>{event.title}</td>
            <td>{event.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
    <label className="inline-label">
      Log filter
      <select onChange={(event) => onChange(event.target.value as "all" | EventType)} value={value}>
        <option value="all">All</option>
        <option value="analysis">Analysis</option>
        <option value="approval">Approval</option>
        <option value="command">Command</option>
        <option value="output">Output</option>
        <option value="validation">Validation</option>
        <option value="error">Error</option>
      </select>
    </label>
  );
}

export function EmptyState({ detail, title }: { detail: string; title: string }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}

export function StatusLabel({ label }: { label: string }) {
  return <span className={["status-label", getStatusBadgeClass(label)].join(" ")}>{label}</span>;
}
