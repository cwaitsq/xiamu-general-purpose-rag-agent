import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth-session";
import { AdminConsole } from "./admin-console";

export default async function AdminPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  if (user.role !== "admin") {
    redirect("/");
  }
  return <AdminConsole />;
}
