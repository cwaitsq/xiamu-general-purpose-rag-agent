"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import styles from "./auth-page.module.css";

type Mode = "login" | "register";

type AuthResponse = {
  code: number;
  message: string;
  data?: {
    user?: {
      role?: string;
    };
  };
};

function normalizeAuthError(mode: Mode, code: number, message: string) {
  if (mode === "login") {
    if (code === 4011) {
      return "账号或密码不正确";
    }
    if (code === 4010) {
      return "登录状态已失效，请重新登录";
    }
    if (code === 4001) {
      return "请输入正确的邮箱和密码";
    }
  }

  if (mode === "register") {
    if (!message) {
      return "注册失败，请检查输入内容";
    }
    if (message.includes("8")) {
      return "密码至少需要 8 位";
    }
    return message;
  }

  return message || "提交失败";
}

async function submitAuth(mode: Mode, payload: Record<string, string>) {
  const response = await fetch(`/api/auth/${mode}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = (await response.json()) as AuthResponse;
  if (!response.ok || data.code !== 0) {
    throw new Error(normalizeAuthError(mode, data.code, data.message));
  }
  return data;
}

export function AuthPage({ mode }: { mode: Mode }) {
  const isRegister = mode === "register";
  const searchParams = useSearchParams();
  const registered = searchParams.get("registered") === "1";
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");

    try {
      if (isRegister && !displayName.trim()) {
        throw new Error("请先填写名称");
      }
      if (!email.trim()) {
        throw new Error("请先填写邮箱");
      }
      if (!password.trim()) {
        throw new Error("请先填写密码");
      }
      if (password.trim().length < 8) {
        throw new Error("密码至少需要 8 位");
      }

      const data = await submitAuth(mode, {
        display_name: displayName.trim(),
        email: email.trim(),
        password,
      });

      if (isRegister) {
        window.location.href = "/login?registered=1";
        return;
      }

      const nextPath = data.data?.user?.role === "admin" ? "/admin" : "/";
      window.location.href = nextPath;
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "提交失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className={styles.shell}>
      <div className={styles.glowTop} />
      <div className={styles.glowBottom} />

      <section className={styles.card}>
        <header className={styles.header}>
          <h1 className={styles.title}>归栖外贸智能客服系统</h1>
        </header>

        <div className={styles.tabRow}>
          <Link href="/login" className={`${styles.tabButton} ${!isRegister ? styles.tabButtonActive : ""}`}>
            登录
          </Link>
          <Link href="/register" className={`${styles.tabButton} ${isRegister ? styles.tabButtonActive : ""}`}>
            注册
          </Link>
        </div>

        {registered ? <div className={styles.success}>注册成功，现在可以使用新账号登录。</div> : null}
        {error ? <div className={styles.alert}>{error}</div> : null}

        <form className={styles.form} onSubmit={handleSubmit}>
          {isRegister ? (
            <label className={styles.field}>
              <span className={styles.label}>名称</span>
              <input
                className={styles.input}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="例如：上海业务组"
                autoComplete="organization"
              />
            </label>
          ) : null}

          <label className={styles.field}>
            <span className={styles.label}>邮箱</span>
            <input
              className={styles.input}
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="email"
            />
          </label>

          <label className={styles.field}>
            <div className={styles.passwordHeader}>
              <span className={styles.label}>密码</span>
              <button
                type="button"
                className={styles.inlineButton}
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? "隐藏" : "显示"}
              </button>
            </div>
            <input
              className={styles.input}
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 位"
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </label>

          <button className={styles.submit} type="submit" disabled={pending}>
            {pending ? "处理中..." : isRegister ? "创建账号" : "进入系统"}
          </button>
        </form>

        <footer className={styles.footer}>
          {isRegister ? (
            <>
              <span>已经有账号了？</span>
              <Link href="/login">去登录</Link>
            </>
          ) : (
            <>
              <span>还没有账号？</span>
              <Link href="/register">去注册</Link>
            </>
          )}
        </footer>
      </section>
    </main>
  );
}
