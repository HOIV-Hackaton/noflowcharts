import type { ReactNode } from "react";

import { AppBreadcrumbs } from "@/components/app-breadcrumbs";
import { Separator } from "@/components/ui/separator";
import { CustomSidebarTrigger } from "@/components/custom-sidebar-trigger";
import { cn } from "@/lib/utils";

export function AppHeader({
	action,
	description,
	badges,
	pageTitle,
}: {
	action?: ReactNode;
	description?: string;
	badges?: ReactNode;
	pageTitle: string;
}) {
	return (
		<header
			className={cn(
				"sticky top-0 z-50 flex min-h-14 shrink-0 items-center justify-between gap-3 border-b px-4 py-2 md:px-6",
				"bg-background/90 backdrop-blur-sm supports-backdrop-filter:bg-background/60"
			)}
		>
			<div className="flex min-w-0 items-center gap-3">
				<div className="flex items-center gap-3">
					<CustomSidebarTrigger />
					<Separator
						className="mr-1 h-4 data-[orientation=vertical]:self-center"
						orientation="vertical"
					/>
				</div>
				<div className="flex min-w-0 flex-col justify-center gap-0.5">
					<div className="flex min-w-0 flex-wrap items-center gap-2">
						<AppBreadcrumbs page={{ title: pageTitle }} />
						{badges ? <div className="flex flex-wrap items-center gap-1.5">{badges}</div> : null}
					</div>
					{description ? <p className="truncate text-xs text-muted-foreground">{description}</p> : null}
				</div>
			</div>
			{action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
		</header>
	);
}
