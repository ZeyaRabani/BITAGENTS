import { MaintenanceScreen } from "@/components/MaintenanceScreen";
import { isMaintenanceWindow } from "@/lib/maintenanceWindow";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function MaintenancePage() {
  if (!isMaintenanceWindow()) {
    redirect("/");
  }

  return <MaintenanceScreen />;
}
