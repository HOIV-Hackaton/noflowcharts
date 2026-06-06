import type { ReactNode } from "react";
import { AlertCircleIcon, CheckCircle2Icon, ClockIcon, ShieldCheckIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/serviceDesk";
import type { Priority, Ticket } from "@/types";

export type SidebarView = "overview" | "all" | "assigned" | "high" | "pending";
export type SidebarCounts = Record<Exclude<SidebarView, "overview">, number>;

export type DashboardStat = {
  label: string;
  value: number | string;
  detail?: string;
  progress?: number;
  tone?: "critical" | "default" | "success" | "warning";
};

export function PageHeading({
  action,
  badges,
  description,
  title,
}: {
  action?: ReactNode;
  badges?: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h1 className="truncate font-heading text-2xl font-medium tracking-normal text-foreground">
            {title}
          </h1>
          {badges ? <div className="flex flex-wrap items-center gap-1.5">{badges}</div> : null}
        </div>
        {description ? <p className="max-w-3xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </header>
  );
}

export function StatusLabel({ label }: { label: string }) {
  const normalized = label.toLowerCase();
  const variant =
    normalized.includes("critical") ||
    normalized.includes("failed") ||
    normalized.includes("rejected") ||
    normalized.includes("error") ||
    normalized.includes("abort") ||
    normalized.includes("blocked") ||
    normalized.includes("high")
      ? "destructive"
      : normalized.includes("open") ||
          normalized.includes("approval") ||
          normalized.includes("analysis") ||
          normalized.includes("agent") ||
          normalized.includes("running")
        ? "default"
        : "secondary";

  return (
    <Badge className="capitalize" variant={variant}>
      {label}
    </Badge>
  );
}

export function StatsGrid({ stats }: { stats: DashboardStat[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.label} size="sm">
          <CardHeader>
            <CardDescription>{stat.label}</CardDescription>
            <CardTitle className="text-2xl">{stat.value}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <MiniSignal tone={stat.tone ?? "default"} />
            {typeof stat.progress === "number" ? <Progress value={stat.progress} /> : null}
            {stat.detail ? <p className="text-xs text-muted-foreground">{stat.detail}</p> : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function TicketTable({
  onSelectTicket,
  tickets,
}: {
  onSelectTicket: (ticketId: number) => void;
  tickets: Ticket[];
}) {
  if (!tickets.length) {
    return <EmptyPanel detail="No tickets match the current queue." title="No tickets" />;
  }

  return (
    <Card>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticket</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickets.map((ticket) => (
              <TableRow
                className="cursor-pointer"
                key={ticket.id}
                onClick={() => onSelectTicket(ticket.id)}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectTicket(ticket.id);
                  }
                }}
              >
                <TableCell className="max-w-[340px]">
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="truncate font-medium text-foreground">{ticket.title}</span>
                    <span className="text-xs text-muted-foreground">#{ticket.id}</span>
                  </div>
                </TableCell>
                <TableCell className="max-w-[260px] truncate">{ticket.customer}</TableCell>
                <TableCell>
                  <StatusLabel label={ticket.priority} />
                </TableCell>
                <TableCell>
                  <StatusLabel label={ticket.status} />
                </TableCell>
                <TableCell>{formatDate(ticket.updatedAt)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function EmptyPanel({ detail, title }: { detail: string; title: string }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex min-h-40 flex-col items-center justify-center gap-2 text-center">
        <p className="font-medium text-foreground">{title}</p>
        <p className="max-w-sm text-sm text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  );
}

export function PriorityBars({ tickets }: { tickets: Ticket[] }) {
  const total = Math.max(tickets.length, 1);
  const priorities: Priority[] = ["Critical", "High", "Medium", "Low"];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Priority mix</CardTitle>
        <CardDescription>Visible ticket load by urgency.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {priorities.map((priority) => {
          const count = tickets.filter((ticket) => ticket.priority === priority).length;
          return (
            <div className="flex flex-col gap-1.5" key={priority}>
              <div className="flex items-center justify-between text-sm">
                <span>{priority}</span>
                <span className="text-muted-foreground">{count}</span>
              </div>
              <Progress value={(count / total) * 100} />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export function WorkflowCards({
  connected,
  pendingApprovals,
  validated,
}: {
  connected: boolean;
  pendingApprovals: number;
  validated: boolean;
}) {
  const items = [
    { icon: ShieldCheckIcon, label: "Human control", value: "Active" },
    { icon: connected ? CheckCircle2Icon : ClockIcon, label: "Connection", value: connected ? "Approved" : "Waiting" },
    { icon: pendingApprovals ? AlertCircleIcon : CheckCircle2Icon, label: "Approvals", value: String(pendingApprovals) },
    { icon: validated ? CheckCircle2Icon : ClockIcon, label: "Validation", value: validated ? "Passed" : "Pending" },
  ];

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label} size="sm">
          <CardContent className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <item.icon />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <p className="truncate font-medium text-foreground">{item.value}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function MiniSignal({ tone }: { tone: NonNullable<DashboardStat["tone"]> }) {
  return (
    <div className="flex h-8 items-end gap-1" aria-hidden="true">
      {[38, 54, 44, 72, 58, 80, 68].map((height, index) => (
        <span
          className={cn(
            "flex-1 rounded-sm bg-primary/30",
            tone === "critical" && "bg-destructive/40",
            tone === "success" && "bg-foreground/40",
            tone === "warning" && "bg-muted-foreground/40",
          )}
          key={`${height}-${index}`}
          style={{ height: `${height}%` }}
        />
      ))}
    </div>
  );
}
