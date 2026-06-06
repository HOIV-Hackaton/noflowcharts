import {
  PageHeading,
  PriorityBars,
  StatsGrid,
  StatusLabel,
  TicketTable,
  type DashboardStat,
} from "@/components/service-desk-ui";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatDate } from "@/lib/serviceDesk";
import type { Ticket } from "@/types";

export function DashboardOverview({
  highPriorityTickets,
  latestFetchedAt,
  onSelectTicket,
  stats,
  tickets: allTickets,
}: {
  highPriorityTickets: Ticket[];
  latestFetchedAt: string | null;
  onSelectTicket: (ticketId: number) => void;
  stats: DashboardStat[];
  tickets: Ticket[];
}) {
  const pendingTickets = allTickets.filter((ticket) => ticket.status === "PENDING").length;
  const doneTickets = allTickets.filter((ticket) => ticket.status === "DONE").length;
  const newestTicket = allTickets
    .slice()
    .sort((first, second) => new Date(second.updatedAt).getTime() - new Date(first.updatedAt).getTime())[0];
  const newestUpdateValue = latestFetchedAt ?? newestTicket?.updatedAt ?? null;
  const total = Math.max(allTickets.length, 1);

  return (
    <div className="flex flex-col gap-5">
      <PageHeading
        badges={<StatusLabel label={`${allTickets.length} assigned`} />}
        description={newestUpdateValue ? `Last queue update ${formatDate(newestUpdateValue)}.` : "No tickets loaded yet."}
        title="Service desk overview"
      />

      <StatsGrid
        stats={[
          ...stats,
          {
            detail: `${pendingTickets} tickets are waiting on technician review.`,
            label: "Pending tickets",
            progress: (pendingTickets / total) * 100,
            tone: pendingTickets ? "warning" : "success",
            value: pendingTickets,
          },
          {
            detail: `${doneTickets} tickets have completed documentation.`,
            label: "Done",
            progress: (doneTickets / total) * 100,
            tone: "success",
            value: doneTickets,
          },
        ]}
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="flex min-w-0 flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-heading text-lg font-medium tracking-normal">High priority tickets</h2>
              <p className="text-sm text-muted-foreground">Critical and high priority work stays visible.</p>
            </div>
          </div>
          <TicketTable tickets={highPriorityTickets} onSelectTicket={onSelectTicket} />
        </section>
        <div className="flex flex-col gap-4">
          <PriorityBars tickets={allTickets} />
          <Card>
            <CardHeader>
              <CardTitle>Status mix</CardTitle>
              <CardDescription>Open, pending, and done across the queue.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {(["OPEN", "PENDING", "DONE"] as const).map((status) => {
                const count = allTickets.filter((ticket) => ticket.status === status).length;
                return (
                  <div className="flex flex-col gap-1.5" key={status}>
                    <div className="flex items-center justify-between text-sm">
                      <StatusLabel label={status} />
                      <span className="text-muted-foreground">{count}</span>
                    </div>
                    <Progress value={(count / total) * 100} />
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
