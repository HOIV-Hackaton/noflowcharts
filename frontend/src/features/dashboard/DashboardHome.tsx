import {
  PriorityBars,
  StatsGrid,
  TicketTable,
  type DashboardStat,
} from "@/components/service-desk-ui";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Priority, Ticket, TicketStatus } from "@/types";

export function DashboardHome({
  filteredTickets,
  loading,
  onSelectTicket,
  priorityFilter,
  setPriorityFilter,
  setSortBy,
  setStatusFilter,
  sortBy,
  stats,
  statusFilter,
}: {
  filteredTickets: Ticket[];
  loading?: boolean;
  onSelectTicket: (ticketId: number) => void;
  priorityFilter: "all" | Priority;
  setPriorityFilter: (filter: "all" | Priority) => void;
  setSortBy: (sort: "date" | "priority" | "customer") => void;
  setStatusFilter: (filter: "all" | TicketStatus) => void;
  sortBy: "date" | "priority" | "customer";
  stats: DashboardStat[];
  statusFilter: "all" | TicketStatus;
}) {
  return (
    <div className="flex flex-col gap-5">
      <StatsGrid loading={loading} stats={stats} valueEmphasis="large">
        <PriorityBars compact loading={loading} tickets={filteredTickets} />
      </StatsGrid>

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
        <TicketTable loading={loading} tickets={filteredTickets} onSelectTicket={onSelectTicket} />
      </section>
    </div>
  );
}
