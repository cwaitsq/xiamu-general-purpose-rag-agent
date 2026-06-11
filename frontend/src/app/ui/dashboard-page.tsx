"use client";

import { startTransition, useEffect, useRef, useState, useSyncExternalStore } from "react";

import styles from "./dashboard-page.module.css";

type BackendHealth = {
  status: string;
};

type GatewayHealth = {
  status?: string;
  llm_model?: string;
  retrieval_backend?: string;
};

type HealthData = {
  backend: BackendHealth | null;
  gateway: GatewayHealth | null;
};

type SourceItem = {
  doc_id: string;
  title: string;
  chunk_id: string;
};

type MessageAttachment = {
  id?: string;
  file_name: string;
  mime_type?: string | null;
  file_size?: number;
  preview_text?: string | null;
  created_at?: string;
};

type ChatResult = {
  status: string;
  answer: string;
  confidence?: string;
  handoff_required?: boolean;
  reason?: string | null;
  answer_mode?: string;
  llm_model?: string | null;
  retrieval_backend?: string | null;
  used_llm?: boolean;
  next_action?: string;
  timings?: Record<string, number>;
  sources?: SourceItem[];
};

type LogItem = {
  id: string;
  session_id: string;
  question: string;
  answer: string;
  status: string;
  confidence: string;
  created_at: string;
};

type HistoryMessage = {
  id?: string;
  role: string;
  content: string;
  created_at?: string;
  phase?: "thinking" | "typing" | "done";
  attachments?: MessageAttachment[];
};

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

type CurrentUser = {
  id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  role: "admin" | "user";
};

type DashboardSnapshot = {
  health: HealthData;
  logs: LogItem[];
};

const STARTER_PROMPTS = [
  "帮我整理一下美国客户常问的起订量和打样周期。",
  "客户问海运到洛杉矶一般要多久，帮我组织一段回复。",
  "我上传了报价单和 FAQ，先帮我提炼重点再回答客户。",
];

function createSessionId() {
  return `ui-${Date.now()}`;
}

async function api<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  let data: unknown = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text };
    }
  }

  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
  }

  if (!response.ok) {
    const message =
      typeof data === "object" && data && "message" in data && typeof data.message === "string"
        ? data.message
        : `request_failed_${response.status}`;
    throw new Error(message);
  }

  return data as T;
}

async function fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
  const [healthData, logData] = await Promise.all([
    api<ApiResponse<HealthData>>("/api/system/health"),
    api<ApiResponse<{ items: LogItem[] }>>("/api/logs/qa?limit=50"),
  ]);

  return {
    health: healthData.data,
    logs: logData.data.items || [],
  };
}

async function fetchSessionHistory(sessionId: string): Promise<HistoryMessage[]> {
  const data = await api<ApiResponse<{ session_id: string; messages: HistoryMessage[] }>>(
    `/api/chat/history?session_id=${encodeURIComponent(sessionId)}`
  );
  return (data.data.messages || []).map((item) => ({
    ...item,
    phase: "done",
    attachments: item.attachments || [],
  }));
}

function formatDate(value?: string) {
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

function formatBytes(value?: number) {
  if (!value) {
    return "";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTiming(timings?: Record<string, number>) {
  if (!timings || !Object.keys(timings).length) {
    return "暂无";
  }
  return Object.entries(timings)
    .map(([key, value]) => `${key} ${value}ms`)
    .join(" · ");
}

function shortName(text: string, limit: number) {
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit)}...`;
}

function statusLabel(status?: string) {
  switch (status) {
    case "answered":
      return "已回答";
    case "fallback":
      return "需补充";
    case "handoff":
      return "转人工";
    case "blocked":
      return "已拦截";
    case "ok":
      return "正常";
    default:
      return status || "未知";
  }
}

function confidenceLabel(value?: string) {
  switch (value) {
    case "high":
      return "高";
    case "medium":
      return "中";
    case "low":
      return "低";
    default:
      return value || "-";
  }
}

function evidenceTone(status?: string) {
  switch (status) {
    case "answered":
    case "ok":
      return styles.tagSuccess;
    case "fallback":
    case "handoff":
      return styles.tagWarning;
    case "blocked":
      return styles.tagDanger;
    default:
      return styles.tagNeutral;
  }
}

function AttachmentChip({
  attachment,
  removable = false,
  onRemove,
}: {
  attachment: MessageAttachment;
  removable?: boolean;
  onRemove?: () => void;
}) {
  return (
    <div className={styles.attachmentChip}>
      <div className={styles.attachmentIcon}>文</div>
      <div className={styles.attachmentBody}>
        <div className={styles.attachmentName}>{attachment.file_name}</div>
        <div className={styles.attachmentMeta}>
          {[attachment.mime_type || "附件", formatBytes(attachment.file_size)].filter(Boolean).join(" · ")}
        </div>
      </div>
      {removable ? (
        <button type="button" className={styles.attachmentRemove} onClick={onRemove} aria-label="移除附件">
          ×
        </button>
      ) : null}
    </div>
  );
}

function MessageBubble({
  role,
  content,
  createdAt,
  attachments,
  pending = false,
}: {
  role: string;
  content: string;
  createdAt?: string;
  attachments?: MessageAttachment[];
  pending?: boolean;
}) {
  const isUser = role === "user";

  return (
    <div className={`${styles.messageRow} ${isUser ? styles.messageRowUser : styles.messageRowAssistant}`}>
      {!isUser ? <div className={styles.assistantAvatar}>外</div> : null}

      <div className={styles.messageStack}>
        <div className={styles.messageMeta}>
          <span>{isUser ? "你" : "归栖"}</span>
          <span>{pending ? "生成中..." : formatDate(createdAt)}</span>
        </div>

        <div className={`${styles.messageBubble} ${isUser ? styles.messageBubbleUser : styles.messageBubbleAssistant}`}>
          {attachments?.length ? (
            <div className={styles.messageAttachments}>
              {attachments.map((attachment) => (
                <AttachmentChip
                  key={`${attachment.id || attachment.file_name}-${attachment.file_size || 0}`}
                  attachment={attachment}
                />
              ))}
            </div>
          ) : null}

          <div className={styles.messageContent}>{content || (pending ? "正在整理回复..." : "")}</div>
        </div>
      </div>
    </div>
  );
}

export function DashboardPage({ currentUser }: { currentUser: CurrentUser }) {
  const [userProfile, setUserProfile] = useState(currentUser);
  const [sessionId, setSessionId] = useState(() => createSessionId());
  const [question, setQuestion] = useState("");
  const [chatResult, setChatResult] = useState<ChatResult | null>(null);
  const [historyMessages, setHistoryMessages] = useState<HistoryMessage[]>([]);
  const [health, setHealth] = useState<HealthData>({ backend: null, gateway: null });
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [askPending, setAskPending] = useState(false);
  const [refreshPending, setRefreshPending] = useState(false);
  const [historyReady, setHistoryReady] = useState(false);
  const [answerTyping, setAnswerTyping] = useState(false);
  const [notice, setNotice] = useState("");
  const isOnline = useSyncExternalStore(
    (callback) => {
      window.addEventListener("online", callback);
      window.addEventListener("offline", callback);
      return () => {
        window.removeEventListener("online", callback);
        window.removeEventListener("offline", callback);
      };
    },
    () => navigator.onLine,
    () => true
  );
  const [profileOpen, setProfileOpen] = useState(false);
  const [profilePending, setProfilePending] = useState(false);
  const [profileForm, setProfileForm] = useState({
    display_name: currentUser.display_name,
    email: currentUser.email,
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const typingTimerRef = useRef<number | null>(null);
  const typingRunRef = useRef(0);
  const sessionIdRef = useRef(sessionId);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  async function handleLogout() {
    await fetch("/api/auth/logout", {
      method: "POST",
    });
    window.location.href = "/login";
  }

  function openProfileModal() {
    setProfileForm({
      display_name: userProfile.display_name,
      email: userProfile.email,
      current_password: "",
      new_password: "",
      confirm_password: "",
    });
    setProfileOpen(true);
  }

  async function handleProfileSave() {
    if (!profileForm.display_name.trim()) {
      setNotice("请先填写名称");
      return;
    }
    if (profileForm.new_password && profileForm.new_password !== profileForm.confirm_password) {
      setNotice("两次输入的新密码不一致");
      return;
    }

    setProfilePending(true);
    try {
      const data = await api<ApiResponse<CurrentUser>>("/api/auth/me", {
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
      setUserProfile(data.data);
      setProfileOpen(false);
      setNotice("个人资料已更新");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "个人资料更新失败");
    } finally {
      setProfilePending(false);
    }
  }

  async function loadWorkspace(targetSessionId: string) {
    setRefreshPending(true);
    setHistoryReady(false);
    try {
      const [snapshot, messages] = await Promise.all([
        fetchDashboardSnapshot(),
        fetchSessionHistory(targetSessionId),
      ]);
      startTransition(() => {
        setHealth(snapshot.health);
        setLogs(snapshot.logs);
        setHistoryMessages(messages);
      });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "页面加载失败");
    } finally {
      setRefreshPending(false);
      setHistoryReady(true);
    }
  }

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      cancelTypingAnimation();
      setNotice("");
      void loadWorkspace(sessionId);
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [sessionId]);

  useEffect(() => {
    return () => {
      if (typingTimerRef.current !== null) {
        window.clearInterval(typingTimerRef.current);
        typingTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [historyMessages, askPending, answerTyping]);

  function cancelTypingAnimation() {
    typingRunRef.current += 1;
    if (typingTimerRef.current !== null) {
      window.clearInterval(typingTimerRef.current);
      typingTimerRef.current = null;
    }
    setAnswerTyping(false);
  }

  async function playAssistantTyping(answer: string, assistantIndex: number) {
    if (!answer) {
      setHistoryMessages((prev) =>
        prev.map((item, index) =>
          index === assistantIndex ? { ...item, content: "", phase: "done" } : item
        )
      );
      setAnswerTyping(false);
      return;
    }

    const runId = typingRunRef.current + 1;
    typingRunRef.current = runId;
    setAnswerTyping(true);
    setHistoryMessages((prev) =>
      prev.map((item, index) =>
        index === assistantIndex ? { ...item, content: "正在整理回复...", phase: "thinking" } : item
      )
    );

    await new Promise((resolve) => window.setTimeout(resolve, 260));

    if (typingRunRef.current !== runId) {
      return;
    }

    await new Promise<void>((resolve) => {
      let cursor = 0;
      if (typingTimerRef.current !== null) {
        window.clearInterval(typingTimerRef.current);
      }
      typingTimerRef.current = window.setInterval(() => {
        if (typingRunRef.current !== runId) {
          if (typingTimerRef.current !== null) {
            window.clearInterval(typingTimerRef.current);
            typingTimerRef.current = null;
          }
          setAnswerTyping(false);
          resolve();
          return;
        }

        cursor = Math.min(answer.length, cursor + 2);
        setHistoryMessages((prev) =>
          prev.map((item, index) =>
            index === assistantIndex
              ? {
                  ...item,
                  content: answer.slice(0, cursor),
                  phase: cursor >= answer.length ? "done" : "typing",
                }
              : item
          )
        );

        if (cursor >= answer.length) {
          if (typingTimerRef.current !== null) {
            window.clearInterval(typingTimerRef.current);
            typingTimerRef.current = null;
          }
          setAnswerTyping(false);
          resolve();
        }
      }, 14);
    });
  }

  function createNewConversation() {
    const nextSessionId = createSessionId();
    setSessionId(nextSessionId);
    setChatResult(null);
    setHistoryMessages([]);
    setQuestion("");
    setNotice("");
    setPendingFiles([]);
  }

  function openConversation(item: LogItem) {
    setSessionId(item.session_id);
    setChatResult(null);
    setHistoryMessages([]);
    setQuestion("");
    setNotice("");
    setPendingFiles([]);
  }

  function handleFileSelection(event: React.ChangeEvent<HTMLInputElement>) {
    const nextFiles = Array.from(event.target.files || []);
    if (!nextFiles.length) {
      return;
    }

    setPendingFiles((prev) => {
      const merged = [...prev];
      for (const file of nextFiles) {
        const exists = merged.some(
          (item) =>
            item.name === file.name &&
            item.size === file.size &&
            item.lastModified === file.lastModified
        );
        if (!exists) {
          merged.push(file);
        }
      }

      if (merged.length > 5) {
        setNotice("单次最多发送 5 个附件");
        return merged.slice(0, 5);
      }

      return merged;
    });

    event.target.value = "";
  }

  function removePendingFile(index: number) {
    setPendingFiles((prev) => prev.filter((_, currentIndex) => currentIndex !== index));
  }

  function applyStarterPrompt(prompt: string) {
    setQuestion(prompt);
    window.setTimeout(() => {
      composerInputRef.current?.focus();
      composerInputRef.current?.setSelectionRange(prompt.length, prompt.length);
    }, 0);
  }

  async function sendQuestion() {
    if (!question.trim() && !pendingFiles.length) {
      setNotice("先输入问题，或者上传附件后再发送");
      return;
    }
    if (!isOnline) {
      setNotice("当前网络不可用，暂时不能发送消息");
      return;
    }

    const fallbackQuestion = "请先阅读我上传的附件，再提炼重点并给出回复。";
    const currentQuestion = question.trim() || fallbackQuestion;
    const questionDraft = question;
    const fileDraft = pendingFiles;
    const currentSessionId = sessionIdRef.current;
    const assistantIndex = historyMessages.length + 1;

    cancelTypingAnimation();
    setAskPending(true);
    setNotice("");
    setQuestion("");
    setPendingFiles([]);
    setChatResult(null);
    setHistoryMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: currentQuestion,
        attachments: fileDraft.map((file) => ({
          file_name: file.name,
          mime_type: file.type || "attachment",
          file_size: file.size,
        })),
        phase: "done",
      },
      { role: "assistant", content: "", phase: "thinking" },
    ]);

    try {
      const requestInit: RequestInit =
        fileDraft.length > 0
          ? {
              method: "POST",
              body: (() => {
                const formData = new FormData();
                formData.append("session_id", currentSessionId);
                formData.append("question", currentQuestion);
                for (const file of fileDraft) {
                  formData.append("files", file);
                }
                return formData;
              })(),
            }
          : {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                session_id: currentSessionId,
                question: currentQuestion,
              }),
            };

      const data = await api<ApiResponse<ChatResult>>("/api/chat/send", requestInit);
      setChatResult(data.data);
      await playAssistantTyping(data.data.answer || "", assistantIndex);

      if (sessionIdRef.current !== currentSessionId) {
        return;
      }

      const [snapshot, messages] = await Promise.all([
        fetchDashboardSnapshot(),
        fetchSessionHistory(currentSessionId),
      ]);
      startTransition(() => {
        setHealth(snapshot.health);
        setLogs(snapshot.logs);
        setHistoryMessages(messages);
      });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "发送失败");
      setQuestion(questionDraft);
      setPendingFiles(fileDraft);
      setHistoryMessages((prev) => prev.slice(0, Math.max(0, prev.length - 2)));
    } finally {
      setAskPending(false);
    }
  }

  const conversationItems: Array<LogItem & { displayTitle: string }> = [];
  const seenSessionIds = new Set<string>();
  for (const item of logs) {
    if (seenSessionIds.has(item.session_id)) {
      continue;
    }
    seenSessionIds.add(item.session_id);
    conversationItems.push({
      ...item,
      displayTitle: shortName(item.question, 24),
    });
  }

  const firstUserMessage = historyMessages.find((item) => item.role === "user" && item.content.trim());
  const activeLog = conversationItems.find((item) => item.session_id === sessionId);
  const currentTitle = shortName(
    firstUserMessage?.content?.trim() || activeLog?.question || "新对话",
    18
  );
  const hasConversation = historyMessages.length > 0 || askPending;
  const isConversationLoading = !historyReady && refreshPending;

  return (
    <main className={styles.shell}>
      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTop}>
            <div className={styles.brandRow}>
              <div className={styles.brandLogo}>外</div>
              <div>
                <div className={styles.brandTitle}>归栖外贸智能助手</div>
                <div className={styles.brandSubtitle}>外贸客服助手</div>
              </div>
            </div>

            <button type="button" className={styles.newChatButton} onClick={createNewConversation}>
              新建对话
            </button>
          </div>

          <div className={styles.sidebarMiddle}>
            <div className={styles.sidebarLabel}>历史对话</div>
            <div className={styles.conversationList}>
              {conversationItems.length ? (
                conversationItems.map((item) => (
                  <button
                    key={item.session_id}
                    type="button"
                    className={`${styles.conversationItem} ${
                      sessionId === item.session_id ? styles.conversationItemActive : ""
                    }`}
                    onClick={() => openConversation(item)}
                  >
                    <div className={styles.conversationTitle}>{item.displayTitle}</div>
                    <div className={styles.conversationMeta}>
                      <span>{formatDate(item.created_at)}</span>
                      <span>{statusLabel(item.status)}</span>
                    </div>
                  </button>
                ))
              ) : (
                <div className={styles.emptyConversation}>这里会显示最近的聊天记录。</div>
              )}
            </div>
          </div>

          <div className={styles.sidebarFooter}>
            <div className={styles.userCard}>
              <div className={styles.userAvatar}>{userProfile.display_name.slice(0, 1)}</div>
              <div className={styles.userMeta}>
                <div className={styles.userName}>{userProfile.display_name}</div>
                <div className={styles.userEmail}>{userProfile.email}</div>
              </div>
            </div>
            <button type="button" className={styles.profileButton} onClick={openProfileModal}>
              个人设置
            </button>
            <button type="button" className={styles.logoutButton} onClick={() => void handleLogout()}>
              退出登录
            </button>
          </div>
        </aside>

        <section className={styles.main}>
          <header className={styles.topbar}>
            <div className={styles.topbarSpacer} />
            <div className={styles.topbarTitle}>{hasConversation ? currentTitle : "新对话"}</div>
            <div className={styles.topbarStatus}>
              <span
                className={`${styles.networkDot} ${isOnline ? styles.networkDotOnline : styles.networkDotOffline}`}
              />
              {isOnline ? "在线" : "离线"}
            </div>
          </header>

          {notice ? <div className={styles.notice}>{notice}</div> : null}

          <div className={styles.threadArea}>
            <div className={styles.threadInner}>
              {isConversationLoading ? (
                <div className={styles.emptyState}>
                  <h1 className={styles.emptyTitle}>正在加载对话</h1>
                </div>
              ) : hasConversation ? (
                <>
                  {historyMessages.map((item, index) => (
                    <MessageBubble
                      key={`${item.id || `${item.role}-${index}`}-${item.created_at || "draft"}`}
                      role={item.role}
                      content={item.content}
                      createdAt={item.created_at}
                      attachments={item.attachments}
                      pending={item.role === "assistant" && item.phase !== "done"}
                    />
                  ))}

                  {chatResult ? (
                    <div className={styles.evidencePanel}>
                      <details className={styles.evidenceDetails}>
                        <summary>查看回答依据</summary>
                        <div className={styles.evidenceContent}>
                          <div className={styles.evidenceTags}>
                            <span className={`${styles.tag} ${evidenceTone(chatResult.status)}`}>
                              {statusLabel(chatResult.status)}
                            </span>
                            <span className={`${styles.tag} ${styles.tagNeutral}`}>
                              置信度 {confidenceLabel(chatResult.confidence)}
                            </span>
                            <span className={`${styles.tag} ${styles.tagNeutral}`}>
                              {chatResult.retrieval_backend || health.gateway?.retrieval_backend || "-"}
                            </span>
                          </div>

                          <div className={styles.evidenceMeta}>
                            <div>回答方式：{chatResult.answer_mode || "-"}</div>
                            <div>下一步：{chatResult.next_action || "-"}</div>
                            <div>耗时：{formatTiming(chatResult.timings)}</div>
                          </div>

                          <div className={styles.sourceList}>
                            {chatResult.sources?.length ? (
                              chatResult.sources.map((source) => (
                                <div key={`${source.doc_id}-${source.chunk_id}`} className={styles.sourceItem}>
                                  <div className={styles.sourceTitle}>{source.title}</div>
                                  <div className={styles.sourceMeta}>
                                    {source.doc_id} · {source.chunk_id}
                                  </div>
                                </div>
                              ))
                            ) : (
                              <div className={styles.sourceEmpty}>这一轮没有可展示的来源信息。</div>
                            )}
                          </div>
                        </div>
                      </details>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className={styles.emptyState}>
                  <h1 className={styles.emptyTitle}>有什么我能帮你的吗？</h1>
                  <div className={styles.promptGrid}>
                    {STARTER_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        className={styles.promptCard}
                        onClick={() => applyStarterPrompt(prompt)}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div ref={threadEndRef} />
            </div>
          </div>

          <footer className={styles.composerWrap}>
            <div className={styles.composerCard}>
              {pendingFiles.length ? (
                <div className={styles.pendingAttachments}>
                  {pendingFiles.map((file, index) => (
                    <AttachmentChip
                      key={`${file.name}-${file.size}-${file.lastModified}`}
                      attachment={{
                        file_name: file.name,
                        mime_type: file.type || "attachment",
                        file_size: file.size,
                      }}
                      removable
                      onRemove={() => removePendingFile(index)}
                    />
                  ))}
                </div>
              ) : null}

              <textarea
                ref={composerInputRef}
                className={styles.composerInput}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendQuestion();
                  }
                }}
                placeholder="给归栖发送消息，支持上传图片、文档、报价单、FAQ 附件..."
              />

              <div className={styles.composerBar}>
                <div className={styles.composerLeft}>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className={styles.fileInput}
                    onChange={handleFileSelection}
                  />
                  <button
                    type="button"
                    className={styles.attachButton}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={askPending}
                  >
                    添加附件
                  </button>
                  <span className={styles.composerHint}>Enter 发送，Shift + Enter 换行</span>
                </div>

                <button type="button" className={styles.sendButton} onClick={() => void sendQuestion()} disabled={askPending}>
                  {askPending ? "发送中..." : "发送"}
                </button>
              </div>
            </div>
          </footer>

          {profileOpen ? (
            <div className={styles.modalScrim} onClick={() => setProfileOpen(false)}>
              <div className={styles.modalCard} onClick={(event) => event.stopPropagation()}>
                <div className={styles.modalHeader}>
                  <div>
                    <div className={styles.modalEyebrow}>账号信息</div>
                    <h3 className={styles.modalTitle}>更新个人资料</h3>
                  </div>
                  <button type="button" className={styles.modalClose} onClick={() => setProfileOpen(false)}>
                    关闭
                  </button>
                </div>

                <div className={styles.modalBody}>
                  <label className={styles.modalField}>
                    <span className={styles.modalLabel}>名称</span>
                    <input
                      className={styles.modalInput}
                      value={profileForm.display_name}
                      onChange={(event) =>
                        setProfileForm((prev) => ({ ...prev, display_name: event.target.value }))
                      }
                    />
                  </label>

                  <label className={styles.modalField}>
                    <span className={styles.modalLabel}>邮箱</span>
                    <input className={styles.modalInput} value={profileForm.email} readOnly />
                  </label>

                  <label className={styles.modalField}>
                    <span className={styles.modalLabel}>当前密码</span>
                    <input
                      className={styles.modalInput}
                      type="password"
                      value={profileForm.current_password}
                      onChange={(event) =>
                        setProfileForm((prev) => ({ ...prev, current_password: event.target.value }))
                      }
                      placeholder="如需修改密码，请先输入当前密码"
                    />
                  </label>

                  <label className={styles.modalField}>
                    <span className={styles.modalLabel}>新密码</span>
                    <input
                      className={styles.modalInput}
                      type="password"
                      value={profileForm.new_password}
                      onChange={(event) =>
                        setProfileForm((prev) => ({ ...prev, new_password: event.target.value }))
                      }
                      placeholder="至少 8 位，可留空"
                    />
                  </label>

                  <label className={styles.modalField}>
                    <span className={styles.modalLabel}>确认新密码</span>
                    <input
                      className={styles.modalInput}
                      type="password"
                      value={profileForm.confirm_password}
                      onChange={(event) =>
                        setProfileForm((prev) => ({ ...prev, confirm_password: event.target.value }))
                      }
                      placeholder="再次输入新密码"
                    />
                  </label>
                </div>

                <div className={styles.modalFooter}>
                  <button type="button" className={styles.attachButton} onClick={() => setProfileOpen(false)}>
                    取消
                  </button>
                  <button
                    type="button"
                    className={styles.sendButton}
                    onClick={() => void handleProfileSave()}
                    disabled={profilePending}
                  >
                    {profilePending ? "保存中..." : "保存修改"}
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
