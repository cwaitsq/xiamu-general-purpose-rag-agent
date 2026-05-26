import { redirect } from "next/navigation";

import { getCurrentUser } from "./_lib/auth-session";
import { DashboardPage } from "./ui/dashboard-page";

export default async function Home() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  if (user.role === "admin") {
    redirect("/admin");
  }
  return <DashboardPage currentUser={user} />;
}
