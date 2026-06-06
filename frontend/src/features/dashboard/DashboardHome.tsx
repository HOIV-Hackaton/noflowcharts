import {
  BlocksStatsGrid,
  BlocksTicketTable,
  type BlocksStat,
  type BlocksSidebarView,
} from "../../components/blocks";
import { PageHeader, StatusLabel } from "../../components/ui/primitives";
import { getQueueHeading } from "../../lib/queue";
import type { Priority, Ticket, TicketStatus } from "../../types";

export function DashboardHome({
  filteredTickets,
  onSelectTicket,
  onRefreshTickets,
  priorityFilter,
  setPriorityFilter,
  setSortBy,
  setStatusFilter,
  sidebarView,
  sortBy,
  stats,
  statusFilter,
}: {
  filteredTickets: Ticket[];
  onSelectTicket: (ticketId: number) => void;
  onRefreshTickets: () => void;
  priorityFilter: "all" | Priority;
  setPriorityFilter: (filter: "all" | Priority) => void;
  setSortBy: (sort: "date" | "priority" | "customer") => void;
  setStatusFilter: (filter: "all" | TicketStatus) => void;
  sidebarView: BlocksSidebarView;
  sortBy: "date" | "priority" | "customer";
  stats: BlocksStat[];
  statusFilter: "all" | TicketStatus;
}) {
  const queueHeading = getQueueHeading(sidebarView, filteredTickets.length);
  const ticketStats = stats.map((stat) => ({
    ...stat,
    change: "",
    kind: stat.kind === "chart" ? ("metric" as const) : stat.kind,
  }));

  return (
    <>
      <PageHeader title={queueHeading.title} badges={<StatusLabel label={queueHeading.badge} />} />
      <BlocksStatsGrid density="compact" stats={ticketStats} />

      <section className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-balance text-lg font-normal text-foreground">{queueHeading.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {filteredTickets.length} visible across the selected queue.
            </p>
          </div>
          <button className="button" onClick={onRefreshTickets} type="button">
            Refresh
          </button>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select
            aria-label="Status filter"
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-primary/60 focus:bg-card focus:ring-2 focus:ring-primary/15 sm:w-[150px]"
            onChange={(event) => setStatusFilter(event.target.value as "all" | TicketStatus)}
            value={statusFilter}
          >
            <option value="all">All status</option>
            <option value="OPEN">Open</option>
            <option value="PENDING">Pending</option>
            <option value="DONE">Done</option>
          </select>
          <select
            aria-label="Priority filter"
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-primary/60 focus:bg-card focus:ring-2 focus:ring-primary/15 sm:w-[150px]"
            onChange={(event) => setPriorityFilter(event.target.value as "all" | Priority)}
            value={priorityFilter}
          >
            <option value="all">All priority</option>
            <option value="Critical">Critical</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
          <select
            aria-label="Ticket sort"
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-primary/60 focus:bg-card focus:ring-2 focus:ring-primary/15 sm:w-[140px]"
            onChange={(event) => setSortBy(event.target.value as "date" | "priority" | "customer")}
            value={sortBy}
          >
            <option value="date">Date</option>
            <option value="priority">Priority</option>
            <option value="customer">Customer</option>
          </select>
        </div>
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <BlocksTicketTable tickets={filteredTickets} onSelectTicket={onSelectTicket} />
        </div>
      </section>
    </>
  );
}
