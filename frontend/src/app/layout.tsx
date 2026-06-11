import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "归栖外贸智能助手",
  description: "面向外贸业务的聊天工作台、用户登录注册与管理控制台。",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
