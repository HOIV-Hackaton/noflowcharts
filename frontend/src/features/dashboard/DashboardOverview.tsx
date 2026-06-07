import {
  PriorityBars,
  StatsGrid,
  StatusLabel,
  TicketTable,
  type DashboardStat,
} from "@/components/service-desk-ui";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { Ticket } from "@/types";

export function DashboardOverview({
  highPriorityTickets,
  loading,
  onSelectTicket,
  stats,
  tickets: allTickets,
}: {
  highPriorityTickets: Ticket[];
  loading?: boolean;
  onSelectTicket: (ticketId: number) => void;
  stats: DashboardStat[];
  tickets: Ticket[];
}) {
  const pendingTickets = allTickets.filter((ticket) => ticket.status === "PENDING").length;
  const total = Math.max(allTickets.length, 1);

  return (
    <div className="flex flex-col gap-5">
      <StatsGrid loading={loading} stats={stats}>
        <PriorityBars compact loading={loading} tickets={allTickets} />
      </StatsGrid>

      <div className="grid gap-4 xl:grid-cols-4">
        <section className="flex min-w-0 flex-col gap-3 xl:col-span-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-heading text-lg font-medium tracking-normal">High priority tickets</h2>
              <p className="text-sm text-muted-foreground">High priority work stays visible.</p>
            </div>
          </div>
          <TicketTable loading={loading} tickets={highPriorityTickets} onSelectTicket={onSelectTicket} />
        </section>
        {loading ? <StatusMixSkeleton /> : <StatusMixCard tickets={allTickets} total={total} />}
      </div>
    </div>
  );
}

function StatusMixCard({ tickets, total }: { tickets: Ticket[]; total: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Status mix</CardTitle>
        <CardDescription>Open, pending, and done across the queue.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {(["OPEN", "PENDING", "DONE"] as const).map((status) => {
          const count = tickets.filter((ticket) => ticket.status === status).length;
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
  );
}

function StatusMixSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4 w-52" />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {Array.from({ length: 3 }).map((_, index) => (
          <div className="flex flex-col gap-2" key={index}>
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-4 w-5" />
            </div>
            <Skeleton className="h-1 w-full rounded-full" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
