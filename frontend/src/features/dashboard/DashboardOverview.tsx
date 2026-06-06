import {
  BlocksStatsGrid,
  BlocksTicketTable,
  type BlocksStat,
} from "../../components/blocks";
import { PageHeader, StatusLabel } from "../../components/ui/primitives";
import { formatDate } from "../../lib/serviceDesk";
import type { Ticket } from "../../types";

export function DashboardOverview({
  highPriorityTickets,
  onSelectTicket,
  stats,
  tickets: allTickets,
}: {
  highPriorityTickets: Ticket[];
  onSelectTicket: (ticketId: number) => void;
  stats: BlocksStat[];
  tickets: Ticket[];
}) {
  const pendingTickets = allTickets.filter((ticket) => ticket.status === "PENDING").length;
  const newestTicket = allTickets
    .slice()
    .sort((first, second) => new Date(second.updatedAt).getTime() - new Date(first.updatedAt).getTime())[0];

  return (
    <>
      <PageHeader
        title="Service desk overview"
        badges={<StatusLabel label={`${allTickets.length} assigned`} />}
      />
      <BlocksStatsGrid
        stats={[
          ...stats,
          { label: "Pending tickets", value: pendingTickets, kind: "metric", tone: "positive" },
          {
            label: "Newest update",
            value: newestTicket ? formatDate(newestTicket.updatedAt) : "None",
            kind: "timestamp",
            tone: "positive",
          },
        ]}
      />

      <section className="space-y-4">
        <div className="flex flex-col gap-1">
          <h3 className="text-balance text-lg font-normal text-foreground">High priority tickets</h3>
          <p className="text-sm text-muted-foreground">
            Critical and high priority work that should stay visible from the first screen.
          </p>
        </div>
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <BlocksTicketTable tickets={highPriorityTickets} onSelectTicket={onSelectTicket} />
        </div>
      </section>
    </>
  );
}
