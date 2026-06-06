import { cn } from "@/lib/utils";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppHeader } from "@/components/app-header";
import { AppSidebar } from "@/components/app-sidebar";
import type { SidebarCounts, SidebarView } from "@/components/service-desk-ui";
import type { Ticket } from "@/types";

export function AppShell({
	activeView,
	backendReady,
	children,
	counts,
	onLogout,
	onNavigate,
	onSelectTicket,
	pageTitle,
	pendingApprovals,
	profile,
	search,
	setSearch,
	tickets,
}: {
	activeView: SidebarView;
	backendReady: boolean;
	children: React.ReactNode;
	counts: SidebarCounts;
	onLogout: () => void;
	onNavigate: (view: SidebarView) => void;
	onSelectTicket: (ticketId: number) => void;
	pageTitle: string;
	pendingApprovals: number;
	profile: {
		email: string;
		name: string;
		role: string;
	};
	search: string;
	setSearch: (search: string) => void;
	tickets: Ticket[];
}) {
	return (
		<TooltipProvider>
			<SidebarProvider className={cn("[--app-wrapper-max-width:88rem]")}>
				<AppSidebar
					activeView={activeView}
					counts={counts}
					onLogout={onLogout}
					onNavigate={onNavigate}
					onSelectTicket={onSelectTicket}
					profile={profile}
					search={search}
					setSearch={setSearch}
					tickets={tickets}
				/>
				<SidebarInset>
					<AppHeader
						backendReady={backendReady}
						pageTitle={pageTitle}
						pendingApprovals={pendingApprovals}
					/>
					<main
						className={cn(
							"mx-auto flex w-full max-w-(--app-wrapper-max-width) flex-1 flex-col p-4 md:p-6"
						)}
					>
						{children}
					</main>
				</SidebarInset>
			</SidebarProvider>
		</TooltipProvider>
	);
}
