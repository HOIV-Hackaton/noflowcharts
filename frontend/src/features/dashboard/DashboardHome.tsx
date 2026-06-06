import { RefreshCwIcon } from "lucide-react";

import {
  PageHeading,
  PriorityBars,
  StatsGrid,
  TicketTable,
  type DashboardStat,
  type SidebarView,
} from "@/components/service-desk-ui";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getQueueHeading } from "@/lib/queue";
import type { Priority, Ticket, TicketStatus } from "@/types";

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
  sidebarView: SidebarView;
  sortBy: "date" | "priority" | "customer";
  stats: DashboardStat[];
  statusFilter: "all" | TicketStatus;
}) {
  const queueHeading = getQueueHeading(sidebarView, filteredTickets.length);

  return (
    <div className="flex flex-col gap-5">
      <PageHeading
        action={
          <Button onClick={onRefreshTickets} size="sm" type="button" variant="outline">
            <RefreshCwIcon data-icon="inline-start" />
            Refresh
          </Button>
        }
        description={`${filteredTickets.length} visible tickets across the selected queue.`}
        title={queueHeading.title}
      />

      <StatsGrid stats={stats} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Select onValueChange={(value) => setStatusFilter(value as "all" | TicketStatus)} value={statusFilter}>
              <SelectTrigger aria-label="Status filter" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">All status</SelectItem>
                  <SelectItem value="OPEN">Open</SelectItem>
                  <SelectItem value="PENDING">Pending</SelectItem>
                  <SelectItem value="DONE">Done</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Select onValueChange={(value) => setPriorityFilter(value as "all" | Priority)} value={priorityFilter}>
              <SelectTrigger aria-label="Priority filter" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">All priority</SelectItem>
                  <SelectItem value="Critical">Critical</SelectItem>
                  <SelectItem value="High">High</SelectItem>
                  <SelectItem value="Medium">Medium</SelectItem>
                  <SelectItem value="Low">Low</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Select onValueChange={(value) => setSortBy(value as "date" | "priority" | "customer")} value={sortBy}>
              <SelectTrigger aria-label="Ticket sort" size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="date">Newest</SelectItem>
                  <SelectItem value="priority">Priority</SelectItem>
                  <SelectItem value="customer">Customer</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <TicketTable tickets={filteredTickets} onSelectTicket={onSelectTicket} />
        </section>
        <PriorityBars tickets={filteredTickets} />
      </div>
    </div>
  );
}
