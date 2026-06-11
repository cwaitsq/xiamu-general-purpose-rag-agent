"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useState, type ReactNode } from "react";

import styles from "./admin-console.module.css";

type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

type AdminUser = {
  id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  role: "admin" | "user";
  status: "active" | "disabled";
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
};

type KnowledgeItem = {
  id: string;
  tenant_id: string;
  title: string;
  category: string;
  status: string;
  visibility: string;
  source_path?: string;
  version?: string | null;
  chunk_count: number;
  created_at?: string;
  updated_at?: string;
};

type JobItem = {
  id: string;
  tenant_id: string;
  file_name?: string | null;
  file_path?: string | null;
  status: string;
  error_message?: string | null;
  result?: unknown;
  created_at: string;
  updated_at: string;
};

type QaSource = {
  doc_id?: string;
  title?: string;
  chunk_id?: string;
  [key: string]: unknown;
};

type LogItem = {
  id: string;
  tenant_id?: string;
  owner_user_id?: string | null;
  session_id: string;
  question: string;
  answer: string;
  status: string;
  confidence?: string | null;
  reason?: string | null;
  handoff_required?: boolean;
  sources?: QaSource[];
  created_at: string;
};

type OverviewData = {
  tenant_id: string;
  summary: {
    users: number;
    knowledge_docs: number;
    ingestion_jobs: number;
    qa_logs: number;
  };
  me: AdminUser;
};

type ModuleKey = "overview" | "users" | "knowledge" | "jobs" | "logs";

const PAGE_SIZE = 5;

const MODULES: Array<{ key: ModuleKey; label: string; hint: string }> = [
  { key: "overview", label: "总览大屏", hint: "运营态势" },
  { key: "users", label: "用户管理", hint: "账号权限" },
  { key: "knowledge", label: "知识库", hint: "资料入库" },
  { key: "jobs", label: "入库任务", hint: "处理进度" },
  { key: "logs", label: "问答日志", hint: "详情审计" },
];

function readJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  return fetch(input, init).then(async (response) => {
    const data = (await response.json()) as ApiEnvelope<T>;
    if (!response.ok || data.code !== 0) {
      throw new Error(data.message || "请求失败");
    }
    return data.data;
  });
}

function formatDate(value?: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.replace("T", " ");
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(date);
}

function formatPercent(value: number, total: number) {
  if (!total) {
    return 0;
  }
  return Math.max(8, Math.round((value / total) * 100));
}

function safeSlice(value: string, length: number) {
  if (value.length <= length) {
    return value;
  }
  return `${value.slice(0, length)}...`;
}

function shortFileName(value?: string | null) {
  if (!value) {
    return "-";
  }
  const parts = value.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] || value;
}

function classifyTag(status: string) {
  if (["active", "success", "answered", "ok", "high"].includes(status)) {
    return `${styles.tag} ${styles.tagSuccess}`;
  }
  if (["running", "pending", "fallback", "medium", "handoff"].includes(status)) {
    return `${styles.tag} ${styles.tagWarning}`;
  }
  if (["disabled", "failed", "blocked", "low"].includes(status)) {
    return `${styles.tag} ${styles.tagDanger}`;
  }
  return `${styles.tag} ${styles.tagNeutral}`;
}

function countBy<T>(items: T[], pick: (item: T) => string) {
  const map = new Map<string, number>();
  for (const item of items) {
    const key = pick(item) || "-";
    map.set(key, (map.get(key) || 0) + 1);
  }
  return Array.from(map.entries())
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
}

function parseSources(value: string) {
  const text = value.trim();
  if (!text) {
    return [];
  }
  const parsed = JSON.parse(text) as unknown;
  if (!Array.isArray(parsed)) {
    throw new Error("sources 必须是 JSON 数组");
  }
  return parsed as QaSource[];
}

function getVisibleWidthPercent(value: number, max: number) {
  return `${formatPercent(value, max)}%`;
}

function CardTitle({ title, hint }: { title: string; hint?: string }) {
  return (
    <div>
      <h3 className={styles.cardTitle}>{title}</h3>
      {hint ? <div className={styles.cardHint}>{hint}</div> : null}
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  accent = "neutral",
}: {
  label: string;
  value: number | string;
  hint: string;
  accent?: "neutral" | "blue" | "green" | "amber";
}) {
  const accentClass =
    accent === "blue"
      ? styles.metricBlue
      : accent === "green"
        ? styles.metricGreen
        : accent === "amber"
          ? styles.metricAmber
          : styles.metricNeutral;

  return (
    <article className={`${styles.metricCard} ${accentClass}`}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricValue}>{value}</div>
      <div className={styles.metricHint}>{hint}</div>
    </article>
  );
}

function BreakdownCard({
  title,
  rows,
  emptyText,
}: {
  title: string;
  rows: Array<{ label: string; value: number }>;
  emptyText: string;
}) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <article className={styles.panelCard}>
      <CardTitle title={title}  />
      {rows.length ? (
        <div className={styles.breakdownList}>
          {rows.map((row) => (
            <div key={row.label} className={styles.breakdownRow}>
              <div className={styles.breakdownMeta}>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
              </div>
              <div className={styles.breakdownTrack}>
                <div className={styles.breakdownFill} style={{ width: getVisibleWidthPercent(row.value, max) }} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.emptyInline}>{emptyText}</div>
      )}
    </article>
  );
}

function PaginationBar({
  page,
  total,
  count,
  onChange,
}: {
  page: number;
  total: number;
  count: number;
  onChange: (nextPage: number) => void;
}) {
  return (
    <div className={styles.pagination}>
      <div className={styles.paginationInfo}>
        共 {count} 条，当前第 {page} / {total} 页
      </div>
      <div className={styles.paginationActions}>
        <button
          type="button"
          className={styles.pageButton}
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
        >
          上一页
        </button>
        <button
          type="button"
          className={styles.pageButton}
          onClick={() => onChange(Math.min(total, page + 1))}
          disabled={page >= total}
        >
          下一页
        </button>
      </div>
    </div>
  );
}

function Modal({
  open,
  title,
  hint,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  hint?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  if (!open) {
    return null;
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(event) => event.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div>
            <div className={styles.modalEyebrow}>操作面板</div>
            <h3 className={styles.modalTitle}>{title}</h3>
            {hint ? <div className={styles.modalHint}>{hint}</div> : null}
          </div>
          <button type="button" className={styles.modalClose} onClick={onClose}>
            关闭
          </button>
        </div>
        <div className={styles.modalBody}>{children}</div>
        {footer ? <div className={styles.modalFooter}>{footer}</div> : null}
      </div>
    </div>
  );
}

function Drawer({
  open,
  title,
  hint,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  hint?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  if (!open) {
    return null;
  }

  return (
    <div className={styles.drawerScrim} onClick={onClose}>
      <aside className={styles.drawer} onClick={(event) => event.stopPropagation()}>
        <div className={styles.drawerHeader}>
          <div>
            <div className={styles.drawerEyebrow}>详情抽屉</div>
            <h3 className={styles.drawerTitle}>{title}</h3>
            {hint ? <div className={styles.drawerHint}>{hint}</div> : null}
          </div>
          <button type="button" className={styles.modalClose} onClick={onClose}>
            关闭
          </button>
        </div>
        <div className={styles.drawerBody}>{children}</div>
        {footer ? <div className={styles.drawerFooter}>{footer}</div> : null}
      </aside>
    </div>
  );
}

export function AdminConsole() {
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshPending, setRefreshPending] = useState(false);

  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [logs, setLogs] = useState<LogItem[]>([]);

  const [activeModule, setActiveModule] = useState<ModuleKey>("overview");
  const [userQuery, setUserQuery] = useState("");
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [jobQuery, setJobQuery] = useState("");
  const [logQuery, setLogQuery] = useState("");
  const deferredUserQuery = useDeferredValue(userQuery.trim().toLowerCase());
  const deferredKnowledgeQuery = useDeferredValue(knowledgeQuery.trim().toLowerCase());
  const deferredJobQuery = useDeferredValue(jobQuery.trim().toLowerCase());
  const deferredLogQuery = useDeferredValue(logQuery.trim().toLowerCase());

  const [userPage, setUserPage] = useState(1);
  const [knowledgePage, setKnowledgePage] = useState(1);
  const [jobPage, setJobPage] = useState(1);
  const [logPage, setLogPage] = useState(1);

  const [profileOpen, setProfileOpen] = useState(false);
  const [profilePending, setProfilePending] = useState(false);
  const [profileForm, setProfileForm] = useState({
    display_name: "",
    current_password: "",
    new_password: "",
    confirm_password: "",
  });

  const [createUserOpen, setCreateUserOpen] = useState(false);
  const [createUserPending, setCreateUserPending] = useState(false);
  const [newUser, setNewUser] = useState({
    display_name: "",
    email: "",
    password: "",
    role: "user" as "admin" | "user",
    status: "active" as "active" | "disabled",
  });

  const [knowledgeUploadOpen, setKnowledgeUploadOpen] = useState(false);
  const [uploadPending, setUploadPending] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [createJobOpen, setCreateJobOpen] = useState(false);
  const [createJobPending, setCreateJobPending] = useState(false);
  const [newJob, setNewJob] = useState({
    file_name: "",
    file_path: "",
  });

  const [createLogOpen, setCreateLogOpen] = useState(false);
  const [createLogPending, setCreateLogPending] = useState(false);
  const [newLog, setNewLog] = useState({
    session_id: "",
    question: "",
    answer: "",
    status: "answered",
    confidence: "medium",
    reason: "",
    handoff_required: false,
    sources_json: "[]",
  });

  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [selectedKnowledge, setSelectedKnowledge] = useState<KnowledgeItem | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobItem | null>(null);
  const [selectedLog, setSelectedLog] = useState<(LogItem & { sources_json: string }) | null>(null);
  const [selectedLogPending, setSelectedLogPending] = useState(false);
  const [selectedKnowledgePending, setSelectedKnowledgePending] = useState(false);
  const [selectedJobPending, setSelectedJobPending] = useState(false);
  const [selectedUserPending, setSelectedUserPending] = useState(false);

  async function loadAll() {
    try {
      const me = await readJson<AdminUser>("/api/auth/me");
      if (me.role !== "admin") {
        setLocked(true);
        setOverview(null);
        setUsers([]);
        setKnowledge([]);
        setJobs([]);
        setLogs([]);
        return;
      }

      const [overviewData, userData, knowledgeData, jobData, logData] = await Promise.all([
        readJson<OverviewData>("/api/admin/overview"),
        readJson<{ items: AdminUser[] }>("/api/admin/users"),
        readJson<{ items: KnowledgeItem[] }>("/api/admin/knowledge/list"),
        readJson<{ items: JobItem[] }>("/api/admin/ingestion/jobs"),
        readJson<{ items: LogItem[] }>("/api/admin/logs/qa"),
      ]);

      setLocked(false);
      setOverview(overviewData);
      setUsers(userData.items || []);
      setKnowledge(knowledgeData.items || []);
      setJobs(jobData.items || []);
      setLogs(logData.items || []);
    } catch (loadError) {
      setLocked(true);
      setError(loadError instanceof Error ? loadError.message : "管理端加载失败");
    } finally {
      setLoading(false);
      setRefreshPending(false);
    }
  }

  async function refreshAll() {
    setError("");
    setRefreshPending(true);
    await loadAll();
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadAll();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function openProfile() {
    if (!overview) {
      return;
    }
    setProfileForm({
      display_name: overview.me.display_name,
      current_password: "",
      new_password: "",
      confirm_password: "",
    });
    setProfileOpen(true);
  }

  async function handleProfileSave() {
    if (!profileForm.display_name.trim()) {
      setError("请先填写姓名");
      return;
    }
    if (profileForm.new_password && profileForm.new_password !== profileForm.confirm_password) {
      setError("两次输入的新密码不一致");
      return;
    }

    setProfilePending(true);
    setError("");
    setNotice("");

    try {
      const updated = await readJson<AdminUser>("/api/auth/me", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          display_name: profileForm.display_name.trim(),
          current_password: profileForm.current_password,
          new_password: profileForm.new_password,
        }),
      });
      setOverview((prev) => (prev ? { ...prev, me: updated } : prev));
      setUsers((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));
      setProfileOpen(false);
      setNotice("个人信息已更新");
    } catch (profileError) {
      setError(profileError instanceof Error ? profileError.message : "个人信息更新失败");
    } finally {
      setProfilePending(false);
    }
  }

  async function handleCreateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateUserPending(true);
    setError("");
    setNotice("");

    try {
      const created = await readJson<AdminUser>("/api/admin/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newUser),
      });
      setUsers((prev) => [created, ...prev]);
      setCreateUserOpen(false);
      setNewUser({
        display_name: "",
        email: "",
        password: "",
        role: "user",
        status: "active",
      });
      setNotice("用户已创建");
      await refreshAll();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建用户失败");
    } finally {
      setCreateUserPending(false);
    }
  }

  async function saveSelectedUser() {
    if (!selectedUser) {
      return;
    }
    setSelectedUserPending(true);
    setError("");
    setNotice("");
    try {
      const updated = await readJson<AdminUser>(`/api/admin/users/${encodeURIComponent(selectedUser.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          display_name: selectedUser.display_name,
          role: selectedUser.role,
          status: selectedUser.status,
        }),
      });
      setUsers((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedUser(updated);
      setNotice("用户已保存");
      await refreshAll();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存用户失败");
    } finally {
      setSelectedUserPending(false);
    }
  }

  async function deleteUser(user: AdminUser) {
    if (!window.confirm(`确认删除用户 ${user.display_name} 吗？`)) {
      return;
    }
    setError("");
    setNotice("");
    try {
      await readJson<{ deleted: boolean }>(`/api/admin/users/${encodeURIComponent(user.id)}`, {
        method: "DELETE",
      });
      setUsers((prev) => prev.filter((item) => item.id !== user.id));
      if (selectedUser?.id === user.id) {
        setSelectedUser(null);
      }
      setNotice("用户已删除");
      await refreshAll();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除用户失败");
    }
  }

  async function handleKnowledgeUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setError("请先选择文件");
      return;
    }
    setUploadPending(true);
    setError("");
    setNotice("");

    try {
      await readJson("/api/admin/knowledge/upload", {
        method: "POST",
        body: (() => {
          const formData = new FormData();
          formData.append("file", selectedFile);
          return formData;
        })(),
      });
      setKnowledgeUploadOpen(false);
      setSelectedFile(null);
      setNotice("知识库已入库");
      await refreshAll();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "知识库上传失败");
    } finally {
      setUploadPending(false);
    }
  }

  async function saveSelectedKnowledge() {
    if (!selectedKnowledge) {
      return;
    }
    setSelectedKnowledgePending(true);
    setError("");
    setNotice("");
    try {
      const updated = await readJson<KnowledgeItem>(`/api/admin/knowledge/${encodeURIComponent(selectedKnowledge.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title: selectedKnowledge.title,
          category: selectedKnowledge.category,
          status: selectedKnowledge.status,
          visibility: selectedKnowledge.visibility,
          version: selectedKnowledge.version,
        }),
      });
      setKnowledge((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedKnowledge(updated);
      setNotice("知识条目已更新");
      await refreshAll();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "更新知识库失败");
    } finally {
      setSelectedKnowledgePending(false);
    }
  }

  async function deleteKnowledge(item: KnowledgeItem) {
    if (!window.confirm(`确认删除知识条目 ${item.title} 吗？`)) {
      return;
    }
    setError("");
    setNotice("");
    try {
      await readJson<{ deleted: boolean }>(`/api/admin/knowledge/${encodeURIComponent(item.id)}`, {
        method: "DELETE",
      });
      setKnowledge((prev) => prev.filter((row) => row.id !== item.id));
      if (selectedKnowledge?.id === item.id) {
        setSelectedKnowledge(null);
      }
      setNotice("知识条目已删除");
      await refreshAll();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除知识条目失败");
    }
  }

  async function handleJobCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newJob.file_path.trim()) {
      setError("请先填写文件路径");
      return;
    }
    setCreateJobPending(true);
    setError("");
    setNotice("");
    try {
      const created = await readJson<{ job_id: string; status: string; result: unknown }>("/api/admin/ingestion/jobs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          file_name: newJob.file_name.trim() || undefined,
          file_path: newJob.file_path.trim(),
        }),
      });
      setCreateJobOpen(false);
      setNewJob({ file_name: "", file_path: "" });
      setNotice(`入库任务 ${created.job_id} 已创建`);
      await refreshAll();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建任务失败");
    } finally {
      setCreateJobPending(false);
    }
  }

  async function saveSelectedJob() {
    if (!selectedJob) {
      return;
    }
    setSelectedJobPending(true);
    setError("");
    setNotice("");
    try {
      const updated = await readJson<JobItem>(`/api/admin/ingestion/jobs/${encodeURIComponent(selectedJob.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          file_name: selectedJob.file_name,
          status: selectedJob.status,
          error_message: selectedJob.error_message,
        }),
      });
      setJobs((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedJob(updated);
      setNotice("任务已更新");
      await refreshAll();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "更新任务失败");
    } finally {
      setSelectedJobPending(false);
    }
  }

  async function retryJob(job: JobItem) {
    if (!job.file_path) {
      setError("当前任务没有可重试的文件路径");
      return;
    }
    setError("");
    setNotice("");
    try {
      const created = await readJson<{ job_id: string; status: string; result: unknown }>("/api/admin/ingestion/jobs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          file_name: job.file_name || shortFileName(job.file_path),
          file_path: job.file_path,
        }),
      });
      setNotice(`已重新创建任务 ${created.job_id}`);
      await refreshAll();
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "重试任务失败");
    }
  }

  async function deleteJob(job: JobItem) {
    if (!window.confirm(`确认删除任务 ${shortFileName(job.file_name || job.file_path)} 吗？`)) {
      return;
    }
    setError("");
    setNotice("");
    try {
      await readJson<{ deleted: boolean }>(`/api/admin/ingestion/jobs/${encodeURIComponent(job.id)}`, {
        method: "DELETE",
      });
      setJobs((prev) => prev.filter((item) => item.id !== job.id));
      if (selectedJob?.id === job.id) {
        setSelectedJob(null);
      }
      setNotice("任务已删除");
      await refreshAll();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除任务失败");
    }
  }

  async function handleLogCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateLogPending(true);
    setError("");
    setNotice("");
    try {
      const created = await readJson<LogItem>("/api/admin/logs/qa", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: newLog.session_id.trim(),
          question: newLog.question.trim(),
          answer: newLog.answer.trim(),
          status: newLog.status.trim(),
          confidence: newLog.confidence.trim(),
          reason: newLog.reason.trim() || undefined,
          handoff_required: newLog.handoff_required,
          sources: parseSources(newLog.sources_json),
        }),
      });
      setLogs((prev) => [created, ...prev]);
      setCreateLogOpen(false);
      setNewLog({
        session_id: "",
        question: "",
        answer: "",
        status: "answered",
        confidence: "medium",
        reason: "",
        handoff_required: false,
        sources_json: "[]",
      });
      setNotice("日志已补录");
      await refreshAll();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建日志失败");
    } finally {
      setCreateLogPending(false);
    }
  }

  async function saveSelectedLog() {
    if (!selectedLog) {
      return;
    }
    setSelectedLogPending(true);
    setError("");
    setNotice("");
    try {
      const updated = await readJson<LogItem>(`/api/admin/logs/qa/${encodeURIComponent(selectedLog.id)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: selectedLog.session_id,
          question: selectedLog.question,
          answer: selectedLog.answer,
          status: selectedLog.status,
          confidence: selectedLog.confidence,
          reason: selectedLog.reason,
          handoff_required: selectedLog.handoff_required,
          sources: parseSources(selectedLog.sources_json),
        }),
      });
      setLogs((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedLog({
        ...updated,
        sources_json: JSON.stringify(updated.sources || [], null, 2),
      });
      setNotice("日志已更新");
      await refreshAll();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "更新日志失败");
    } finally {
      setSelectedLogPending(false);
    }
  }

  async function deleteLog(item: LogItem) {
    if (!window.confirm(`确认删除日志 ${item.session_id} 吗？`)) {
      return;
    }
    setError("");
    setNotice("");
    try {
      await readJson<{ deleted: boolean }>(`/api/admin/logs/qa/${encodeURIComponent(item.id)}`, {
        method: "DELETE",
      });
      setLogs((prev) => prev.filter((row) => row.id !== item.id));
      if (selectedLog?.id === item.id) {
        setSelectedLog(null);
      }
      setNotice("日志已删除");
      await refreshAll();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除日志失败");
    }
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", {
      method: "POST",
    });
    window.location.href = "/login";
  }

  const visibleUsers = users.filter((user) =>
    !deferredUserQuery
      ? true
      : [user.display_name, user.email, user.role, user.status, user.tenant_id]
          .join(" ")
          .toLowerCase()
          .includes(deferredUserQuery)
  );

  const visibleKnowledge = knowledge.filter((item) =>
    !deferredKnowledgeQuery
      ? true
      : [item.title, item.category, item.status, item.visibility, item.source_path || "", item.version || ""]
          .join(" ")
          .toLowerCase()
          .includes(deferredKnowledgeQuery)
  );

  const visibleJobs = jobs.filter((item) =>
    !deferredJobQuery
      ? true
      : [item.file_name || "", item.file_path || "", item.status, item.error_message || ""]
          .join(" ")
          .toLowerCase()
          .includes(deferredJobQuery)
  );

  const visibleLogs = logs.filter((item) =>
    !deferredLogQuery
      ? true
      : [item.question, item.answer, item.status, item.confidence || "", item.session_id, item.reason || ""]
          .join(" ")
          .toLowerCase()
          .includes(deferredLogQuery)
  );

  const userPageCount = Math.max(1, Math.ceil(visibleUsers.length / PAGE_SIZE));
  const knowledgePageCount = Math.max(1, Math.ceil(visibleKnowledge.length / PAGE_SIZE));
  const jobPageCount = Math.max(1, Math.ceil(visibleJobs.length / PAGE_SIZE));
  const logPageCount = Math.max(1, Math.ceil(visibleLogs.length / PAGE_SIZE));
  const currentUserPage = Math.min(userPage, userPageCount);
  const currentKnowledgePage = Math.min(knowledgePage, knowledgePageCount);
  const currentJobPage = Math.min(jobPage, jobPageCount);
  const currentLogPage = Math.min(logPage, logPageCount);

  const pagedUsers = visibleUsers.slice((currentUserPage - 1) * PAGE_SIZE, currentUserPage * PAGE_SIZE);
  const pagedKnowledge = visibleKnowledge.slice(
    (currentKnowledgePage - 1) * PAGE_SIZE,
    currentKnowledgePage * PAGE_SIZE
  );
  const pagedJobs = visibleJobs.slice((currentJobPage - 1) * PAGE_SIZE, currentJobPage * PAGE_SIZE);
  const pagedLogs = visibleLogs.slice((currentLogPage - 1) * PAGE_SIZE, currentLogPage * PAGE_SIZE);

  const activeUsers = users.filter((user) => user.status === "active").length;
  const disabledUsers = users.filter((user) => user.status === "disabled").length;
  const adminUsers = users.filter((user) => user.role === "admin").length;
  const onlineKnowledge = knowledge.filter((item) => item.status === "active").length;
  const runningJobs = jobs.filter((item) => item.status === "running").length;
  const answeredLogs = logs.filter((item) => item.status === "answered").length;
  const userRoleRows = countBy(users, (user) => user.role);
  const userStatusRows = countBy(users, (user) => user.status);
  const knowledgeStatusRows = countBy(knowledge, (item) => item.status);
  const jobStatusRows = countBy(jobs, (item) => item.status);
  const logStatusRows = countBy(logs, (item) => item.status);
  const logConfidenceRows = countBy(logs, (item) => item.confidence || "unknown");
  const recentActivity = [...jobs, ...logs]
    .map((item) =>
      "question" in item
        ? {
            id: item.id,
            title: item.question,
            meta: item.status,
            time: item.created_at,
          }
        : {
            id: item.id,
            title: item.file_name || shortFileName(item.file_path) || item.id,
            meta: item.status,
            time: item.updated_at,
          }
    )
    .sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
    .slice(0, 6);

  if (loading) {
    return (
      <main className={styles.locked}>
        <div className={styles.lockedCard}>
          <h1 className={styles.lockedTitle}>正在准备管理端</h1>
          <p className={styles.lockedCopy}>正在同步用户、知识库、入库任务和问答日志数据。</p>
        </div>
      </main>
    );
  }

  if (locked || !overview) {
    return (
      <main className={styles.locked}>
        <div className={styles.lockedCard}>
          <h1 className={styles.lockedTitle}>管理端仅对管理员开放</h1>
          <p className={styles.lockedCopy}>
            普通用户可以继续使用聊天页。请使用管理员账号重新登录后查看总览、用户管理、知识库和日志。
          </p>
          {error ? <div className={styles.warning}>{error}</div> : null}
          <div className={styles.lockedActions}>
            <Link className={styles.primaryButton} href="/login">
              去登录
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const moduleTitleMap: Record<ModuleKey, string> = {
    overview: "总览大屏",
    users: "用户管理",
    knowledge: "知识库",
    jobs: "入库任务",
    logs: "问答日志",
  };

  const moduleHintMap: Record<ModuleKey, string> = {
    overview: "聚焦关键指标，保留核心统计，不堆砌低价值图表。",
    users: "新增、编辑、停用与删除都走弹窗和抽屉，不占页面。",
    knowledge: "按资料条目维护，支持查看、编辑、删除和继续入库。",
    jobs: "任务列表支持重试、更新状态和详情查看。",
    logs: "日志支持查看详情、补录、修改和删除，方便审计。",
  };

  const profileInitial = overview.me.display_name.slice(0, 1) || "管";

  return (
    <main className={styles.shell}>
      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.brandBlock}>
            <div className={styles.brandMark}>外</div>
            <div>
              <div className={styles.brandTitle}>归栖外贸智能助手</div>
            </div>
          </div>

          <nav className={styles.nav}>
            {MODULES.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`${styles.navItem} ${activeModule === item.key ? styles.navItemActive : ""}`}
                onClick={() => setActiveModule(item.key)}
              >
                <span>
                  <span className={styles.navLabel}>{item.label}</span>
                  <span className={styles.navHint}>{item.hint}</span>
                </span>
                <span className={styles.navChevron}>›</span>
              </button>
            ))}
          </nav>

          <div className={styles.sidebarFooter}>
            <div className={styles.quickStats}>
              <div>
                <div className={styles.quickValue}>{overview.summary.users}</div>
                <div className={styles.quickLabel}>用户</div>
              </div>
              <div>
                <div className={styles.quickValue}>{overview.summary.knowledge_docs}</div>
                <div className={styles.quickLabel}>资料</div>
              </div>
              <div>
                <div className={styles.quickValue}>{overview.summary.qa_logs}</div>
                <div className={styles.quickLabel}>日志</div>
              </div>
            </div>

            <div className={styles.adminCard}>
              <div className={styles.adminName}>{overview.me.display_name}</div>
              <div className={styles.adminMeta}>{overview.me.email}</div>
              <button type="button" className={styles.ghostButton} onClick={openProfile}>
                个人设置
              </button>
            </div>

            <button type="button" className={styles.dangerButton} onClick={() => void handleLogout()}>
              退出登录
            </button>
          </div>
        </aside>

        <section className={styles.main}>
          <header className={styles.header}>
            <div>
              <div className={styles.eyebrow}>Admin Console</div>
              <h1 className={styles.title}>{moduleTitleMap[activeModule]}</h1>
              <p className={styles.copy}>{moduleHintMap[activeModule]}</p>
            </div>
            <div className={styles.headerActions}>
              <button className={styles.ghostButton} onClick={() => void refreshAll()} disabled={refreshPending}>
                {refreshPending ? "刷新中..." : "刷新数据"}
              </button>
            </div>
          </header>

          <div className={styles.container}>
            {activeModule === "overview" ? (
              <>
                <section className={styles.heroGrid}>
                  <article className={`${styles.heroCard} ${styles.heroCardPrimary}`}>
                    <div className={styles.heroBadge}>运营总览</div>
                    
                    <div className={styles.heroMeters}>
                      <MetricCard label="用户总数" value={overview.summary.users} hint="租户内账号规模" accent="blue" />
                      <MetricCard label="知识条目" value={overview.summary.knowledge_docs} hint="已入库资料" accent="green" />
                      <MetricCard label="入库任务" value={overview.summary.ingestion_jobs} hint="任务排队与处理" accent="amber" />
                      <MetricCard label="问答日志" value={overview.summary.qa_logs} hint="审计与复盘数据" />
                    </div>
                  </article>

                  <article className={styles.panelCard}>
                    <CardTitle title="当前管理员" hint="可直接进入个人设置" />
                    <div className={styles.profileBlock}>
                      <div className={styles.profileAvatar}>{profileInitial}</div>
                      <div>
                        <div className={styles.profileName}>{overview.me.display_name}</div>
                        <div className={styles.profileMeta}>{overview.me.email}</div>
                      </div>
                    </div>
                    <div className={styles.statStack}>
                      <div className={styles.statLine}>
                        <span>活跃用户</span>
                        <strong>{activeUsers}</strong>
                      </div>
                      <div className={styles.statLine}>
                        <span>停用用户</span>
                        <strong>{disabledUsers}</strong>
                      </div>
                      <div className={styles.statLine}>
                        <span>管理员数</span>
                        <strong>{adminUsers}</strong>
                      </div>
                    </div>
                  </article>
                </section>

                <section className={styles.metricGrid}>
                  <MetricCard label="活跃知识" value={onlineKnowledge} hint="已启用可检索资料" accent="green" />
                  <MetricCard label="运行任务" value={runningJobs} hint="当前正在入库" accent="amber" />
                  <MetricCard label="已回答日志" value={answeredLogs} hint="近期已完成问答" accent="blue" />
                  <MetricCard label="未处理" value={Math.max(0, logs.length - answeredLogs)} hint="需人工跟进" />
                </section>

                <section className={styles.grid2}>
                  <BreakdownCard title="用户角色分布" rows={userRoleRows} emptyText="暂无用户数据" />
                  <BreakdownCard title="用户状态分布" rows={userStatusRows} emptyText="暂无状态数据" />
                  <BreakdownCard title="知识状态分布" rows={knowledgeStatusRows} emptyText="暂无知识数据" />
                  <BreakdownCard title="任务状态分布" rows={jobStatusRows} emptyText="暂无任务数据" />
                  <BreakdownCard title="日志状态分布" rows={logStatusRows} emptyText="暂无日志数据" />
                  <BreakdownCard title="置信度分布" rows={logConfidenceRows} emptyText="暂无置信度数据" />
                </section>

                <section className={styles.panelCard}>
                  <CardTitle title="最近动态" hint="按任务与日志更新时间排序" />
                  {recentActivity.length ? (
                    <div className={styles.timeline}>
                      {recentActivity.map((item) => (
                        <div key={`${item.id}-${item.time}`} className={styles.timelineItem}>
                          <div className={styles.timelineDot} />
                          <div className={styles.timelineBody}>
                            <div className={styles.timelineTitle}>{safeSlice(item.title, 48)}</div>
                            <div className={styles.timelineMeta}>
                              <span>{item.meta}</span>
                              <span>{formatDate(item.time)}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.emptyInline}>暂无最近动态</div>
                  )}
                </section>
              </>
            ) : null}

            {activeModule === "users" ? (
              <section className={styles.panelCard}>
                <div className={styles.panelHeader}>
                  <div>
                    <h2 className={styles.panelTitle}>用户管理</h2>
                    <div className={styles.panelCopy}>新增用户用弹窗，编辑和查看用抽屉，列表控制在 5 条一页。</div>
                  </div>
                  <div className={styles.toolbarActions}>
                    <input
                      className={styles.searchInput}
                      value={userQuery}
                      onChange={(event) => {
                        setUserQuery(event.target.value);
                        setUserPage(1);
                      }}
                      placeholder="搜索姓名 / 邮箱 / 角色"
                    />
                    <button type="button" className={styles.primaryButton} onClick={() => setCreateUserOpen(true)}>
                      新增用户
                    </button>
                  </div>
                </div>

                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>用户</th>
                        <th>角色</th>
                        <th>状态</th>
                        <th>最近登录</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedUsers.map((user) => (
                        <tr key={user.id}>
                          <td>
                            <div className={styles.tablePrimary}>{user.display_name}</div>
                            <div className={styles.meta}>{user.email}</div>
                            <div className={styles.meta}>{user.tenant_id}</div>
                          </td>
                          <td>
                            <span className={classifyTag(user.role)}>{user.role === "admin" ? "管理员" : "普通用户"}</span>
                          </td>
                          <td>
                            <span className={classifyTag(user.status)}>{user.status === "active" ? "启用" : "停用"}</span>
                          </td>
                          <td>{formatDate(user.last_login_at || user.created_at)}</td>
                          <td>
                            <div className={styles.rowActions}>
                              <button
                                type="button"
                                className={styles.ghostButton}
                                onClick={() => setSelectedUser({ ...user })}
                              >
                                详情
                              </button>
                              <button type="button" className={styles.deleteButton} onClick={() => void deleteUser(user)}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <PaginationBar
                  page={currentUserPage}
                  total={userPageCount}
                  count={visibleUsers.length}
                  onChange={setUserPage}
                />
              </section>
            ) : null}

            {activeModule === "knowledge" ? (
              <section className={styles.panelCard}>
                <div className={styles.panelHeader}>
                  <div>
                    <h2 className={styles.panelTitle}>知识库</h2>
                    <div className={styles.panelCopy}>支持上传入库、修改条目、查看详情和删除记录。</div>
                  </div>
                  <div className={styles.toolbarActions}>
                    <input
                      className={styles.searchInput}
                      value={knowledgeQuery}
                      onChange={(event) => {
                        setKnowledgeQuery(event.target.value);
                        setKnowledgePage(1);
                      }}
                      placeholder="搜索标题 / 分类 / 来源"
                    />
                    <button type="button" className={styles.primaryButton} onClick={() => setKnowledgeUploadOpen(true)}>
                      上传入库
                    </button>
                  </div>
                </div>

                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>标题</th>
                        <th>分类</th>
                        <th>状态</th>
                        <th>可见性</th>
                        <th>分片</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedKnowledge.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <div className={styles.tablePrimary}>{item.title}</div>
                            <div className={styles.meta}>{shortFileName(item.source_path)}</div>
                          </td>
                          <td>{item.category}</td>
                          <td>
                            <span className={classifyTag(item.status)}>{item.status}</span>
                          </td>
                          <td>{item.visibility}</td>
                          <td>{item.chunk_count}</td>
                          <td>
                            <div className={styles.rowActions}>
                              <button
                                type="button"
                                className={styles.ghostButton}
                                onClick={() => setSelectedKnowledge({ ...item })}
                              >
                                详情
                              </button>
                              <button type="button" className={styles.deleteButton} onClick={() => void deleteKnowledge(item)}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <PaginationBar
                  page={currentKnowledgePage}
                  total={knowledgePageCount}
                  count={visibleKnowledge.length}
                  onChange={setKnowledgePage}
                />
              </section>
            ) : null}

            {activeModule === "jobs" ? (
              <section className={styles.panelCard}>
                <div className={styles.panelHeader}>
                  <div>
                    <h2 className={styles.panelTitle}>入库任务</h2>
                    <div className={styles.panelCopy}>可重新发起、编辑和删除任务，详情抽屉里能直接改状态。</div>
                  </div>
                  <div className={styles.toolbarActions}>
                    <input
                      className={styles.searchInput}
                      value={jobQuery}
                      onChange={(event) => {
                        setJobQuery(event.target.value);
                        setJobPage(1);
                      }}
                      placeholder="搜索文件名 / 路径 / 状态"
                    />
                    <button type="button" className={styles.primaryButton} onClick={() => setCreateJobOpen(true)}>
                      新建任务
                    </button>
                  </div>
                </div>

                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>文件</th>
                        <th>状态</th>
                        <th>更新时间</th>
                        <th>路径</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedJobs.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <div className={styles.tablePrimary}>{item.file_name || shortFileName(item.file_path) || item.id}</div>
                            <div className={styles.meta}>{item.id}</div>
                          </td>
                          <td>
                            <span className={classifyTag(item.status)}>{item.status}</span>
                            {item.error_message ? <div className={styles.meta}>{item.error_message}</div> : null}
                          </td>
                          <td>{formatDate(item.updated_at)}</td>
                          <td className={styles.cellEllipsis}>{item.file_path || "-"}</td>
                          <td>
                            <div className={styles.rowActions}>
                              <button type="button" className={styles.ghostButton} onClick={() => setSelectedJob({ ...item })}>
                                详情
                              </button>
                              <button type="button" className={styles.secondaryButton} onClick={() => void retryJob(item)}>
                                重试
                              </button>
                              <button type="button" className={styles.deleteButton} onClick={() => void deleteJob(item)}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <PaginationBar
                  page={currentJobPage}
                  total={jobPageCount}
                  count={visibleJobs.length}
                  onChange={setJobPage}
                />
              </section>
            ) : null}

            {activeModule === "logs" ? (
              <section className={styles.panelCard}>
                <div className={styles.panelHeader}>
                  <div>
                    <h2 className={styles.panelTitle}>问答日志</h2>
                    <div className={styles.panelCopy}>日志支持查看详情、补录、修改与删除，便于回溯与复盘。</div>
                  </div>
                  <div className={styles.toolbarActions}>
                    <input
                      className={styles.searchInput}
                      value={logQuery}
                      onChange={(event) => {
                        setLogQuery(event.target.value);
                        setLogPage(1);
                      }}
                      placeholder="搜索问题 / 会话 / 状态"
                    />
                    <button type="button" className={styles.primaryButton} onClick={() => setCreateLogOpen(true)}>
                      新增日志
                    </button>
                  </div>
                </div>

                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>问题</th>
                        <th>状态</th>
                        <th>置信度</th>
                        <th>会话</th>
                        <th>时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedLogs.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <div className={styles.tablePrimary}>{safeSlice(item.question, 48)}</div>
                            <div className={styles.meta}>{safeSlice(item.answer, 56)}</div>
                          </td>
                          <td>
                            <span className={classifyTag(item.status)}>{item.status}</span>
                          </td>
                          <td>
                            <span className={classifyTag(item.confidence || "unknown")}>{item.confidence || "-"}</span>
                          </td>
                          <td>{item.session_id}</td>
                          <td>{formatDate(item.created_at)}</td>
                          <td>
                            <div className={styles.rowActions}>
                              <button
                                type="button"
                                className={styles.ghostButton}
                                onClick={() =>
                                  setSelectedLog({
                                    ...item,
                                    sources_json: JSON.stringify(item.sources || [], null, 2),
                                  })
                                }
                              >
                                详情
                              </button>
                              <button type="button" className={styles.deleteButton} onClick={() => void deleteLog(item)}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <PaginationBar
                  page={currentLogPage}
                  total={logPageCount}
                  count={visibleLogs.length}
                  onChange={setLogPage}
                />
              </section>
            ) : null}
          </div>

          {notice ? <div className={styles.message}>{notice}</div> : null}
          {error ? <div className={styles.warning}>{error}</div> : null}
        </section>
      </div>

      <Modal
        open={profileOpen}
        title="个人账号信息"
        hint="可以修改姓名，也可以顺手重置密码。"
        onClose={() => setProfileOpen(false)}
        footer={
          <>
            <button type="button" className={styles.ghostButton} onClick={() => setProfileOpen(false)}>
              取消
            </button>
            <button type="button" className={styles.primaryButton} onClick={() => void handleProfileSave()} disabled={profilePending}>
              {profilePending ? "保存中..." : "保存修改"}
            </button>
          </>
        }
      >
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span className={styles.label}>姓名</span>
            <input
              className={styles.input}
              value={profileForm.display_name}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, display_name: event.target.value }))}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>当前密码</span>
            <input
              className={styles.input}
              type="password"
              value={profileForm.current_password}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, current_password: event.target.value }))}
              placeholder="修改密码时填写"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>新密码</span>
            <input
              className={styles.input}
              type="password"
              value={profileForm.new_password}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, new_password: event.target.value }))}
              placeholder="至少 8 位"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>确认新密码</span>
            <input
              className={styles.input}
              type="password"
              value={profileForm.confirm_password}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, confirm_password: event.target.value }))}
              placeholder="再次输入新密码"
            />
          </label>
        </div>
      </Modal>

      <Modal
        open={createUserOpen}
        title="新增用户"
        hint="创建完成后可以直接在列表里继续编辑。"
        onClose={() => setCreateUserOpen(false)}
        footer={
          <>
            <button type="button" className={styles.ghostButton} onClick={() => setCreateUserOpen(false)}>
              取消
            </button>
            <button type="submit" form="create-user-form" className={styles.primaryButton} disabled={createUserPending}>
              {createUserPending ? "创建中..." : "创建用户"}
            </button>
          </>
        }
      >
        <form id="create-user-form" className={styles.formGrid} onSubmit={handleCreateUser}>
          <label className={styles.field}>
            <span className={styles.label}>姓名</span>
            <input
              className={styles.input}
              value={newUser.display_name}
              onChange={(event) => setNewUser((prev) => ({ ...prev, display_name: event.target.value }))}
              placeholder="例如：上海业务组"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>邮箱</span>
            <input
              className={styles.input}
              type="email"
              value={newUser.email}
              onChange={(event) => setNewUser((prev) => ({ ...prev, email: event.target.value }))}
              placeholder="sales@company.com"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>初始密码</span>
            <input
              className={styles.input}
              type="password"
              value={newUser.password}
              onChange={(event) => setNewUser((prev) => ({ ...prev, password: event.target.value }))}
              placeholder="至少 8 位"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>角色</span>
            <select
              className={styles.select}
              value={newUser.role}
              onChange={(event) =>
                setNewUser((prev) => ({ ...prev, role: event.target.value as "admin" | "user" }))
              }
            >
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.label}>状态</span>
            <select
              className={styles.select}
              value={newUser.status}
              onChange={(event) =>
                setNewUser((prev) => ({ ...prev, status: event.target.value as "active" | "disabled" }))
              }
            >
              <option value="active">启用</option>
              <option value="disabled">停用</option>
            </select>
          </label>
        </form>
      </Modal>

      <Modal
        open={knowledgeUploadOpen}
        title="上传知识库资料"
        hint="选择文件后直接入库，后台会自动跑入库任务。"
        onClose={() => setKnowledgeUploadOpen(false)}
        footer={
          <>
            <button type="button" className={styles.ghostButton} onClick={() => setKnowledgeUploadOpen(false)}>
              取消
            </button>
            <button type="submit" form="knowledge-upload-form" className={styles.primaryButton} disabled={uploadPending}>
              {uploadPending ? "入库中..." : "开始入库"}
            </button>
          </>
        }
      >
        <form id="knowledge-upload-form" className={styles.formGrid} onSubmit={handleKnowledgeUpload}>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>选择文件</span>
            <input className={styles.file} type="file" onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} />
          </label>
          <div className={`${styles.field} ${styles.fieldFull}`}>
            <div className={styles.note}>{selectedFile ? `当前文件：${selectedFile.name}` : "建议上传 FAQ、报价单、制度、物流说明等文档。"}</div>
          </div>
        </form>
      </Modal>

      <Modal
        open={createJobOpen}
        title="新建入库任务"
        hint="填文件路径即可重新发起入库。"
        onClose={() => setCreateJobOpen(false)}
        footer={
          <>
            <button type="button" className={styles.ghostButton} onClick={() => setCreateJobOpen(false)}>
              取消
            </button>
            <button type="submit" form="create-job-form" className={styles.primaryButton} disabled={createJobPending}>
              {createJobPending ? "创建中..." : "创建任务"}
            </button>
          </>
        }
      >
        <form id="create-job-form" className={styles.formGrid} onSubmit={handleJobCreate}>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>文件路径</span>
            <input
              className={styles.input}
              value={newJob.file_path}
              onChange={(event) => setNewJob((prev) => ({ ...prev, file_path: event.target.value }))}
              placeholder="C:/data/faq.xlsx"
            />
          </label>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>文件名</span>
            <input
              className={styles.input}
              value={newJob.file_name}
              onChange={(event) => setNewJob((prev) => ({ ...prev, file_name: event.target.value }))}
              placeholder="可选"
            />
          </label>
        </form>
      </Modal>

      <Modal
        open={createLogOpen}
        title="新增问答日志"
        hint="可用于补录人工处理记录。"
        onClose={() => setCreateLogOpen(false)}
        footer={
          <>
            <button type="button" className={styles.ghostButton} onClick={() => setCreateLogOpen(false)}>
              取消
            </button>
            <button type="submit" form="create-log-form" className={styles.primaryButton} disabled={createLogPending}>
              {createLogPending ? "保存中..." : "保存日志"}
            </button>
          </>
        }
      >
        <form id="create-log-form" className={styles.formGrid} onSubmit={handleLogCreate}>
          <label className={styles.field}>
            <span className={styles.label}>会话 ID</span>
            <input
              className={styles.input}
              value={newLog.session_id}
              onChange={(event) => setNewLog((prev) => ({ ...prev, session_id: event.target.value }))}
              placeholder="session_001"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>状态</span>
            <input
              className={styles.input}
              value={newLog.status}
              onChange={(event) => setNewLog((prev) => ({ ...prev, status: event.target.value }))}
              placeholder="answered / fallback / handoff"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>置信度</span>
            <input
              className={styles.input}
              value={newLog.confidence}
              onChange={(event) => setNewLog((prev) => ({ ...prev, confidence: event.target.value }))}
              placeholder="high / medium / low"
            />
          </label>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>问题</span>
            <textarea
              className={styles.textarea}
              value={newLog.question}
              onChange={(event) => setNewLog((prev) => ({ ...prev, question: event.target.value }))}
              placeholder="用户提问"
            />
          </label>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>答案</span>
            <textarea
              className={styles.textarea}
              value={newLog.answer}
              onChange={(event) => setNewLog((prev) => ({ ...prev, answer: event.target.value }))}
              placeholder="回答内容"
            />
          </label>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>来源 JSON</span>
            <textarea
              className={styles.textarea}
              value={newLog.sources_json}
              onChange={(event) => setNewLog((prev) => ({ ...prev, sources_json: event.target.value }))}
              placeholder="[]"
            />
          </label>
          <label className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>原因</span>
            <input
              className={styles.input}
              value={newLog.reason}
              onChange={(event) => setNewLog((prev) => ({ ...prev, reason: event.target.value }))}
              placeholder="可选"
            />
          </label>
          <label className={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={newLog.handoff_required}
              onChange={(event) => setNewLog((prev) => ({ ...prev, handoff_required: event.target.checked }))}
            />
            <span>需要人工接管</span>
          </label>
        </form>
      </Modal>

      <Drawer
        open={Boolean(selectedUser)}
        title={selectedUser?.display_name || "用户详情"}
        hint={selectedUser ? `${selectedUser.email} · ${selectedUser.tenant_id}` : undefined}
        onClose={() => setSelectedUser(null)}
        footer={
          selectedUser ? (
            <>
              <button type="button" className={styles.ghostButton} onClick={() => setSelectedUser(null)}>
                关闭
              </button>
              <button type="button" className={styles.primaryButton} onClick={() => void saveSelectedUser()} disabled={selectedUserPending}>
                {selectedUserPending ? "保存中..." : "保存用户"}
              </button>
            </>
          ) : null
        }
      >
        {selectedUser ? (
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.label}>姓名</span>
              <input
                className={styles.input}
                value={selectedUser.display_name}
                onChange={(event) => setSelectedUser((prev) => (prev ? { ...prev, display_name: event.target.value } : prev))}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>角色</span>
              <select
                className={styles.select}
                value={selectedUser.role}
                onChange={(event) =>
                  setSelectedUser((prev) => (prev ? { ...prev, role: event.target.value as "admin" | "user" } : prev))
                }
              >
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>状态</span>
              <select
                className={styles.select}
                value={selectedUser.status}
                onChange={(event) =>
                  setSelectedUser((prev) => (prev ? { ...prev, status: event.target.value as "active" | "disabled" } : prev))
                }
              >
                <option value="active">启用</option>
                <option value="disabled">停用</option>
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>邮箱</span>
              <input className={styles.input} value={selectedUser.email} readOnly />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>更新时间</span>
              <input className={styles.input} value={formatDate(selectedUser.updated_at)} readOnly />
            </label>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={Boolean(selectedKnowledge)}
        title={selectedKnowledge?.title || "知识条目"}
        hint={selectedKnowledge ? `${selectedKnowledge.category} · ${selectedKnowledge.visibility}` : undefined}
        onClose={() => setSelectedKnowledge(null)}
        footer={
          selectedKnowledge ? (
            <>
              <button type="button" className={styles.deleteButton} onClick={() => void deleteKnowledge(selectedKnowledge)}>
                删除
              </button>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => void saveSelectedKnowledge()}
                disabled={selectedKnowledgePending}
              >
                {selectedKnowledgePending ? "保存中..." : "保存知识"}
              </button>
            </>
          ) : null
        }
      >
        {selectedKnowledge ? (
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.label}>标题</span>
              <input
                className={styles.input}
                value={selectedKnowledge.title}
                onChange={(event) =>
                  setSelectedKnowledge((prev) => (prev ? { ...prev, title: event.target.value } : prev))
                }
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>分类</span>
              <input
                className={styles.input}
                value={selectedKnowledge.category}
                onChange={(event) =>
                  setSelectedKnowledge((prev) => (prev ? { ...prev, category: event.target.value } : prev))
                }
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>状态</span>
              <input
                className={styles.input}
                value={selectedKnowledge.status}
                onChange={(event) =>
                  setSelectedKnowledge((prev) => (prev ? { ...prev, status: event.target.value } : prev))
                }
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>可见性</span>
              <input
                className={styles.input}
                value={selectedKnowledge.visibility}
                onChange={(event) =>
                  setSelectedKnowledge((prev) => (prev ? { ...prev, visibility: event.target.value } : prev))
                }
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>版本</span>
              <input
                className={styles.input}
                value={selectedKnowledge.version || ""}
                onChange={(event) =>
                  setSelectedKnowledge((prev) => (prev ? { ...prev, version: event.target.value } : prev))
                }
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>来源文件</span>
              <input className={styles.input} value={selectedKnowledge.source_path || "-"} readOnly />
            </label>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={Boolean(selectedJob)}
        title={selectedJob?.file_name || "入库任务"}
        hint={selectedJob ? selectedJob.status : undefined}
        onClose={() => setSelectedJob(null)}
        footer={
          selectedJob ? (
            <>
              <button type="button" className={styles.deleteButton} onClick={() => void deleteJob(selectedJob)}>
                删除
              </button>
              <button type="button" className={styles.secondaryButton} onClick={() => void retryJob(selectedJob)}>
                重试
              </button>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => void saveSelectedJob()}
                disabled={selectedJobPending}
              >
                {selectedJobPending ? "保存中..." : "保存任务"}
              </button>
            </>
          ) : null
        }
      >
        {selectedJob ? (
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.label}>文件名</span>
              <input
                className={styles.input}
                value={selectedJob.file_name || ""}
                onChange={(event) =>
                  setSelectedJob((prev) => (prev ? { ...prev, file_name: event.target.value } : prev))
                }
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>状态</span>
              <input
                className={styles.input}
                value={selectedJob.status}
                onChange={(event) => setSelectedJob((prev) => (prev ? { ...prev, status: event.target.value } : prev))}
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>错误信息</span>
              <textarea
                className={styles.textarea}
                value={selectedJob.error_message || ""}
                onChange={(event) =>
                  setSelectedJob((prev) => (prev ? { ...prev, error_message: event.target.value } : prev))
                }
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>文件路径</span>
              <input className={styles.input} value={selectedJob.file_path || "-"} readOnly />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>创建时间</span>
              <input className={styles.input} value={formatDate(selectedJob.created_at)} readOnly />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>更新时间</span>
              <input className={styles.input} value={formatDate(selectedJob.updated_at)} readOnly />
            </label>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={Boolean(selectedLog)}
        title={selectedLog?.question || "问答日志"}
        hint={selectedLog ? `${selectedLog.session_id} · ${selectedLog.status}` : undefined}
        onClose={() => setSelectedLog(null)}
        footer={
          selectedLog ? (
            <>
              <button type="button" className={styles.deleteButton} onClick={() => void deleteLog(selectedLog)}>
                删除
              </button>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => void saveSelectedLog()}
                disabled={selectedLogPending}
              >
                {selectedLogPending ? "保存中..." : "保存日志"}
              </button>
            </>
          ) : null
        }
      >
        {selectedLog ? (
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.label}>会话 ID</span>
              <input
                className={styles.input}
                value={selectedLog.session_id}
                onChange={(event) => setSelectedLog((prev) => (prev ? { ...prev, session_id: event.target.value } : prev))}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>状态</span>
              <input
                className={styles.input}
                value={selectedLog.status}
                onChange={(event) => setSelectedLog((prev) => (prev ? { ...prev, status: event.target.value } : prev))}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>置信度</span>
              <input
                className={styles.input}
                value={selectedLog.confidence || ""}
                onChange={(event) =>
                  setSelectedLog((prev) => (prev ? { ...prev, confidence: event.target.value } : prev))
                }
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>问题</span>
              <textarea
                className={styles.textarea}
                value={selectedLog.question}
                onChange={(event) =>
                  setSelectedLog((prev) => (prev ? { ...prev, question: event.target.value } : prev))
                }
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>答案</span>
              <textarea
                className={styles.textarea}
                value={selectedLog.answer}
                onChange={(event) => setSelectedLog((prev) => (prev ? { ...prev, answer: event.target.value } : prev))}
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>来源 JSON</span>
              <textarea
                className={styles.textarea}
                value={selectedLog.sources_json}
                onChange={(event) =>
                  setSelectedLog((prev) => (prev ? { ...prev, sources_json: event.target.value } : prev))
                }
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span className={styles.label}>原因</span>
              <input
                className={styles.input}
                value={selectedLog.reason || ""}
                onChange={(event) => setSelectedLog((prev) => (prev ? { ...prev, reason: event.target.value } : prev))}
              />
            </label>
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={Boolean(selectedLog.handoff_required)}
                onChange={(event) =>
                  setSelectedLog((prev) => (prev ? { ...prev, handoff_required: event.target.checked } : prev))
                }
              />
              <span>需要人工接管</span>
            </label>
          </div>
        ) : null}
      </Drawer>
    </main>
  );
}
