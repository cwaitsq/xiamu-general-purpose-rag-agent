import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth-session";
import { AuthPage } from "../ui/auth-page";

export default async function LoginPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect(user.role === "admin" ? "/admin" : "/");
  }
  return <AuthPage mode="login" />;
}
