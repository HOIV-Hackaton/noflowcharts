import type { SidebarView } from "@/components/service-desk-ui";

export function getQueueHeading(view: SidebarView, visibleCount: number) {
  if (view === "assigned") {
    return {
      badge: `${visibleCount} assigned`,
      title: "Assigned tickets",
    };
  }

  if (view === "high") {
    return {
      badge: `${visibleCount} high priority`,
      title: "High priority tickets",
    };
  }

  if (view === "pending") {
    return {
      badge: `${visibleCount} pending`,
      title: "Pending approval",
    };
  }

  return {
    badge: `${visibleCount} tickets`,
    title: "All tickets",
  };
}
