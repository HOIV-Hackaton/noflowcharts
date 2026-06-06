import { AlertCircleIcon, CheckCircle2Icon } from "lucide-react";

import { AppBreadcrumbs } from "@/components/app-breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { CustomSidebarTrigger } from "@/components/custom-sidebar-trigger";
import { cn } from "@/lib/utils";

export function AppHeader({
	backendReady,
	pageTitle,
	pendingApprovals,
}: {
	backendReady: boolean;
	pageTitle: string;
	pendingApprovals: number;
}) {
	return (
		<header
			className={cn(
				"sticky top-0 z-50 flex h-14 shrink-0 items-center justify-between gap-2 border-b px-4 md:px-6",
				"bg-background/90 backdrop-blur-sm supports-backdrop-filter:bg-background/60"
			)}
		>
			<div className="flex min-w-0 items-center gap-3">
				<CustomSidebarTrigger />
				<Separator
					className="mr-2 h-4 data-[orientation=vertical]:self-center"
					orientation="vertical"
				/>
				<AppBreadcrumbs page={{ title: pageTitle }} />
			</div>
			<div className="flex shrink-0 items-center gap-2">
				<Badge variant={backendReady ? "secondary" : "outline"}>
					{backendReady ? <CheckCircle2Icon data-icon="inline-start" /> : <AlertCircleIcon data-icon="inline-start" />}
					{backendReady ? "Backend live" : "Mock data"}
				</Badge>
				<Badge variant={pendingApprovals ? "destructive" : "outline"}>
					{pendingApprovals} approvals
				</Badge>
			</div>
		</header>
	);
}
