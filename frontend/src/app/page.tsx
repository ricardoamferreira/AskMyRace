"use client";

import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  askQuestion,
  Citation,
  listExamples,
  loadExample,
  uploadGuide,
  UploadResponse,
  ScheduleDay,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Bot,
  CheckCircle2,
  FileText,
  Loader2,
  SendHorizontal,
  Sparkles,
  UploadCloud,
  UserRound,
  CalendarRange,
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

const sampleQuestions = [
  "What time do I need to rack my bike?",
  "Where is athlete check-in located?",
  "What are the swim cut-off times?",
];

const MAX_QUESTION_LENGTH = 500;
const MAX_HISTORY_LENGTH = 1500;
const BANNED_PATTERNS = [
  /ignore\s+(?:all|any)\s+previous\s+instructions/i,
  /pretend\s+to\s+be/i,
  /leak\s+.*prompt/i,
  /reveal\s+.*system/i,
];

function uniqueCitations(citations?: Citation[]): Citation[] | undefined {
  if (!citations) return undefined;
  const map = new Map<string, Citation>();
  citations.forEach((citation) => {
    const key = `${citation.section}-${citation.page}`;
    if (!map.has(key)) {
      map.set(key, citation);
    }
  });
  return Array.from(map.values());
}

function containsBannedPattern(text: string): boolean {
  return BANNED_PATTERNS.some((pattern) => pattern.test(text));
}

const FOLLOW_UP_REGEX = /\b(it|they|them|that|those|this|these|there|again)\b/i;
const FOLLOW_UP_STARTERS = [/^what about\b/i, /^how about\b/i, /^and\b/i, /^what else\b/i, /^same\b/i];

function shouldAttachHistory(question: string): boolean {
  const trimmed = question.trim();
  if (!trimmed) return false;
  if (trimmed.length <= 12) return true;
  if (FOLLOW_UP_STARTERS.some((pattern) => pattern.test(trimmed))) return true;
  if (trimmed.length <= 50 && FOLLOW_UP_REGEX.test(trimmed)) return true;
  return false;
}

function buildHistory(messages: Message[], question: string): string | undefined {
  if (!shouldAttachHistory(question)) return undefined;
  if (messages.length === 0) return undefined;
  const recent = messages
    .slice(-6)
    .map((message) => `${message.role === "user" ? "User" : "Assistant"}: ${message.content}`)
    .join("\n");
  if (!recent) return undefined;
  return recent.length > MAX_HISTORY_LENGTH ? recent.slice(recent.length - MAX_HISTORY_LENGTH) : recent;
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <article
      className={cn(
        "relative flex gap-3 rounded-2xl border px-4 py-4 text-sm shadow-[0_16px_45px_rgba(8,10,25,0.45)] transition-colors duration-300",
        isUser ? "border-sky-500/30 bg-sky-500/10" : "border-white/10 bg-white/5",
      )}
    >
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10",
          isUser ? "bg-sky-500/20 text-sky-100" : "bg-white/10 text-indigo-100",
        )}
      >
        {isUser ? <UserRound className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className="flex flex-1 flex-col gap-3 text-slate-100">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-slate-500">
          <span>{isUser ? "You" : "Ask My Race"}</span>
          <span className="hidden text-slate-600 md:inline">|</span>
          <span className="hidden md:inline text-slate-500">{isUser ? "Question" : "Answer"}</span>
        </div>
        <p className="whitespace-pre-line leading-6 text-slate-100/90">{message.content}</p>
        {message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {message.citations.map((citation) => (
              <span
                key={`${citation.section}-${citation.page}`}
                title={citation.excerpt}
                className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs text-slate-200/90 transition hover:border-white/30 hover:bg-white/15"
              >
                <FileText className="h-3.5 w-3.5 text-indigo-200" />
                {citation.section} - p.{citation.page}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

export default function Home() {
  const [document, setDocument] = useState<UploadResponse | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
  const messageListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!messageListRef.current) return;
    messageListRef.current.scrollTo({
      top: messageListRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const examplesQuery = useQuery({
    queryKey: ["examples"],
    queryFn: listExamples,
    staleTime: 1000 * 60 * 5,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadGuide,
    onSuccess: (data) => {
      setDocument(data);
      setMessages([]);
      toast.success("Athlete guide uploaded.");
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Unable to upload the PDF.";
      toast.error(message);
    },
  });

  const exampleMutation = useMutation({
    mutationFn: loadExample,
    onSuccess: (data, slug) => {
      setDocument(data);
      setMessages([]);
      const guideName = examplesQuery.data?.find((item) => item.slug === slug)?.name;
      toast.success(guideName ? `Loaded demo guide: ${guideName}` : "Demo guide loaded.");
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Unable to load the demo guide.";
      toast.error(message);
    },
  });

  const askMutation = useMutation({
    mutationFn: async ({
      documentId,
      query,
      history,
    }: {
      documentId: string;
      query: string;
      history?: string;
    }) => askQuestion(documentId, query, history),
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Unable to generate an answer.";
      toast.error(message);
    },
  });

  const isReadyToAsk = useMemo(
    () => Boolean(document) && !uploadMutation.isPending && !exampleMutation.isPending,
    [document, uploadMutation.isPending, exampleMutation.isPending],
  );

  const assistantAnswers = useMemo(
    () => messages.filter((message) => message.role === "assistant").length,
    [messages],
  );

  const isWorkspaceBusy = uploadMutation.isPending || exampleMutation.isPending;
  const isSending = askMutation.isPending;

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (file.type !== "application/pdf") {
      toast.error("Please upload a PDF athlete guide.");
      event.target.value = "";
      return;
    }

    if (file.size > 80 * 1024 * 1024) {
      toast.error("PDF must be 80 MB or smaller.");
      event.target.value = "";
      return;
    }

    uploadMutation.mutate(file);
    event.target.value = "";
  };

  const handleAsk = () => {
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }

    if (trimmed.length > MAX_QUESTION_LENGTH) {
      toast.error("Question is too long. Please keep it under 500 characters.");
      return;
    }

    if (containsBannedPattern(trimmed)) {
      toast.error("That request is not allowed.");
      return;
    }

    if (!document) {
      toast.error("Upload or load a guide before asking questions.");
      return;
    }

    if (!isReadyToAsk || isSending) {
      return;
    }

    const history = buildHistory(messages, trimmed);

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");

    askMutation.mutate(
      { documentId: document.document_id, query: trimmed, history },
      {
        onSuccess: (data) => {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: data.answer,
              citations: uniqueCitations(data.citations),
            },
          ]);
        },
      },
    );
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleAsk();
  };

  const handleTextareaKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleAsk();
    }
  };

  const handleSampleQuestion = (value: string) => {
    if (!document) {
      toast("Upload or load a guide first to try a sample question.", { icon: "??" });
      return;
    }
    setQuestion(value);
    textareaRef.current?.focus();
  };

  const handleSelectExample = (slug: string) => {
    exampleMutation.mutate(slug);
  };

  const handleQuestionChange = (value: string) => {
    if (value.length > MAX_QUESTION_LENGTH) {
      toast.error("Question is too long. Please keep it under 500 characters.");
      setQuestion(value.slice(0, MAX_QUESTION_LENGTH));
    } else {
      setQuestion(value);
    }
  };

  const handleResetConversation = () => {
    if (messages.length === 0) {
      return;
    }
    setMessages([]);
    toast.success("Conversation cleared.");
  };

  const handleResetWorkspace = () => {
    if (isWorkspaceBusy) {
      return;
    }
    if (!document && messages.length === 0) {
      return;
    }
    setMessages([]);
    setDocument(null);
    toast.success("Workspace cleared.");
  };

  const formattedUploadTime = document ? new Date(document.uploaded_at).toLocaleString() : null;
  const scheduleDays = document?.schedule ?? [];
  const isGuideLoaded = Boolean(document);

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(148,163,255,0.15),_transparent_55%),radial-gradient(circle_at_bottom,_rgba(236,72,153,0.12),_transparent_60%)]" />
        <div className="absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-white/20 via-transparent to-transparent blur-3xl" />
      </div>

      <div className="relative z-10 flex flex-1 flex-col pb-12">
        <header className="mx-auto w-full max-w-6xl px-6 pt-12">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-col gap-4">
              <div className="inline-flex items-center gap-2 self-start rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.4em] text-slate-300">
                <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
                Ask My Race
              </div>
              <h1 className="text-3xl font-semibold leading-tight text-white sm:text-4xl">
                Race-day clarity at AI speed
              </h1>
              <p className="max-w-2xl text-sm text-slate-400 sm:text-base">
                Upload your athlete guide and chat with a modern assistant that remembers the conversation, cites its answers, and keeps you ready for every checkpoint.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:gap-4">
              <span
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition",
                  document ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : "border-white/10 bg-white/5 text-slate-300",
                )}
              >
                <CheckCircle2 className={cn("h-4 w-4", document ? "text-emerald-300" : "text-slate-400")} />
                {document ? "Guide synced" : "Waiting for guide"}
              </span>
              <span className="text-xs text-slate-500">LangChain + OpenAI</span>
            </div>
          </div>
        </header>

        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 pt-8">
          <div
            className={cn(
              "grid grid-cols-1 gap-6",
              "xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)_minmax(0,320px)]",
            )}
          >
            <aside className="flex flex-col gap-6">
              <section className="glass-panel p-6">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Workspace</p>
                    <h2 className="text-lg font-semibold text-white">Athlete guide</h2>
                  </div>
                  {document && (
                    <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs text-emerald-200">
                      {document.page_count} pages
                    </span>
                  )}
                </div>

                <div className="mt-5">
                  <input
                    id="guide-upload"
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={handleFileChange}
                    disabled={isWorkspaceBusy}
                  />
                  <label
                    htmlFor="guide-upload"
                    className={cn(
                      "glow-border block rounded-2xl border border-white/10 bg-white/5 px-6 py-9 text-center transition",
                      isWorkspaceBusy && "cursor-not-allowed opacity-60",
                      !isWorkspaceBusy && "cursor-pointer hover:border-white/20 hover:bg-white/10",
                    )}
                  >
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white/10 text-indigo-200">
                      {uploadMutation.isPending ? (
                        <Loader2 className="h-6 w-6 animate-spin" />
                      ) : (
                        <UploadCloud className="h-6 w-6" />
                      )}
                    </div>
                    <div className="mt-4 text-sm font-medium text-white">
                      {uploadMutation.isPending ? "Uploading guide..." : "Click to browse or drop a PDF"}
                    </div>
                    <p className="mt-1 text-xs text-slate-500">PDF up to 80 MB</p>
                  </label>
                </div>

                {document ? (
                  <div className="mt-5 space-y-3 rounded-2xl border border-white/10 bg-black/30 p-4 text-sm text-slate-200">
                    <div className="flex items-center gap-2 break-all">
                      <FileText className="h-4 w-4 text-indigo-200" />
                      <span>{document.filename}</span>
                    </div>
                    {formattedUploadTime && (
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>Uploaded</span>
                        <span>{formattedUploadTime}</span>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={handleResetWorkspace}
                      disabled={isWorkspaceBusy}
                      className={cn(
                        "text-xs text-slate-400 transition",
                        isWorkspaceBusy ? "cursor-not-allowed opacity-50" : "hover:text-white",
                      )}
                    >
                      Clear workspace
                    </button>
                  </div>
                ) : (
                  <p className="mt-5 text-xs text-slate-500">
                    Bring your athlete guide into the workspace to unlock the chat experience and instant citations.
                  </p>
                )}
              </section>

              <section className="glass-panel glass-panel--subtle p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Quick start</p>
                    <h2 className="text-base font-semibold text-white">Demo guides</h2>
                  </div>
                  {exampleMutation.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                  )}
                </div>
                <div className="mt-4 space-y-2">
                  {examplesQuery.isLoading && (
                    <p className="text-sm text-slate-400">Fetching demo guides...</p>
                  )}
                  {!examplesQuery.isLoading && examplesQuery.data?.length === 0 && (
                    <p className="text-sm text-slate-400">No demo guides available yet.</p>
                  )}
                  {examplesQuery.data?.map((example) => (
                    <button
                      key={example.slug}
                      type="button"
                      onClick={() => handleSelectExample(example.slug)}
                      disabled={exampleMutation.isPending}
                      className={cn(
                        "glow-border flex w-full flex-col rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-left text-sm text-slate-200 transition",
                        exampleMutation.isPending && "cursor-not-allowed opacity-60",
                        !exampleMutation.isPending && "hover:border-white/20 hover:bg-white/10",
                      )}
                    >
                      <span className="font-medium text-white">{example.name}</span>
                      <span className="text-xs text-slate-400">{example.filename}</span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="glass-panel glass-panel--subtle p-6">
                <div className="flex flex-col gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Need ideas?</p>
                    <h2 className="text-base font-semibold text-white">Sample prompts</h2>
                    <p className="mt-1 text-xs text-slate-400">Tap to drop a question into the chat.</p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {sampleQuestions.map((sample) => (
                      <button
                        key={sample}
                        type="button"
                        onClick={() => handleSampleQuestion(sample)}
                        className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-200 transition hover:border-white/30 hover:bg-white/10"
                      >
                        {sample}
                      </button>
                    ))}
                  </div>

                  <div className="mt-5 rounded-2xl border border-white/10 bg-black/25 p-4 text-xs text-slate-400">
                    <p className="text-slate-300">How it works</p>
                    <ul className="mt-3 space-y-2">
                      <li className="flex gap-2">
                        <span className="text-slate-500">1</span>
                        <span>Upload or pick a race guide PDF.</span>
                      </li>
                      <li className="flex gap-2">
                        <span className="text-slate-500">2</span>
                        <span>We embed it with LangChain so the assistant can cite answers.</span>
                      </li>
                      <li className="flex gap-2">
                        <span className="text-slate-500">3</span>
                        <span>Ask anything and follow up without losing context.</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </section>
            </aside>

            <section className="glass-panel flex min-h-[640px] flex-col overflow-hidden border-white/10">
              <div className="flex items-start justify-between border-b border-white/10 px-6 py-5">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Conversation</p>
                  <h2 className="text-xl font-semibold text-white">Ask with citations</h2>
                  <p className="mt-1 text-xs text-slate-400">The assistant remembers up to six turns when it helps.</p>
                </div>
                <button
                  type="button"
                  onClick={handleResetConversation}
                  disabled={messages.length === 0 || isSending}
                  className={cn(
                    "rounded-full border border-white/10 px-3 py-1 text-xs text-slate-400 transition",
                    messages.length === 0 || isSending
                      ? "cursor-not-allowed opacity-40"
                      : "hover:border-white/25 hover:text-white",
                  )}
                >
                  Clear chat
                </button>
              </div>

              <div ref={messageListRef} className="flex-1 overflow-y-auto px-6 pb-10 pt-6">
                {messages.length > 0 && (
                  <div className="mb-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
                    Still in beta. Verify critical logistics with the official guide.
                  </div>
                )}

                {messages.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center gap-4 text-center text-slate-400">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full border border-white/10 bg-white/5 text-indigo-200">
                      <Bot className="h-8 w-8" />
                    </div>
                    <div className="max-w-md text-sm leading-6 text-slate-300">
                      Load a guide to ask about logistics, schedules, rules, or anything specific to race day. Answers include inline citations so you can trust every detail.
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-4">
                    {messages.map((message) => (
                      <MessageBubble key={message.id} message={message} />
                    ))}
                    {isSending && (
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Generating answer...
                      </div>
                    )}
                  </div>
                )}
              </div>

              <form ref={formRef} onSubmit={handleSubmit} className="border-t border-white/10 bg-black/30 px-6 py-5">
                <fieldset className="flex flex-col gap-4" disabled={isSending}>
                  <div className="rounded-2xl border border-white/10 bg-black/40 px-4 py-3 shadow-inner">
                    <textarea
                      ref={textareaRef}
                      value={question}
                      onChange={(event) => handleQuestionChange(event.target.value)}
                      onKeyDown={handleTextareaKeyDown}
                      placeholder={document ? "Ask a question about the guide" : "Upload or load a guide to start asking questions"}
                      maxLength={MAX_QUESTION_LENGTH}
                      className="h-28 w-full resize-none bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
                    />
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                      <span className="truncate text-slate-400">
                        {document ? document.filename : "No guide loaded"}
                      </span>
                      <span>
                        {assistantAnswers} answers - {question.length}/{MAX_QUESTION_LENGTH}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => setQuestion("")}
                      className="rounded-full border border-white/10 px-4 py-2 text-xs text-slate-400 transition hover:border-white/25 hover:text-white"
                    >
                      Clear draft
                    </button>
                    <button
                      type="submit"
                      disabled={!isReadyToAsk || isSending || !question.trim()}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full bg-white/90 px-5 py-2 text-sm font-medium text-slate-900 transition",
                        (!isReadyToAsk || isSending || !question.trim())
                          ? "cursor-not-allowed opacity-60"
                          : "hover:bg-white",
                      )}
                    >
                      {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
                      Ask
                    </button>
                  </div>
                </fieldset>
              </form>
            </section>
            <SchedulePanel schedule={scheduleDays} isGuideLoaded={isGuideLoaded} />
          </div>
        </main>
      </div>
    </div>
  );
}

function SchedulePanel({ schedule, isGuideLoaded }: { schedule: ScheduleDay[]; isGuideLoaded: boolean }) {
  const hasSchedule = schedule.length > 0;

  return (
    <section className="glass-panel order-last flex max-h-[640px] flex-col overflow-hidden border-white/10 xl:order-none">
      <div className="border-b border-white/10 px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Event schedule</p>
        <h2 className="text-base font-semibold text-white">Race timeline</h2>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {hasSchedule ? (
          <div className="flex flex-col gap-4">
            {schedule.map((day) => (
              <article
                key={day.title}
                className="rounded-xl border border-white/10 bg-black/25 p-4 text-sm text-slate-200"
              >
                <h3 className="text-sm font-semibold text-white">{day.title}</h3>
                <dl className="mt-3 space-y-2">
                  {day.items.map((item, index) => (
                    <div
                      key={`${day.title}-${item.time}-${index}`}
                      className="flex items-start gap-3 text-xs leading-5 text-slate-200/90"
                    >
                      <dt className="w-24 shrink-0 font-semibold text-indigo-200">{item.time}</dt>
                      <dd className="flex-1 text-slate-200/80">{item.activity}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-slate-400">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-300">
              <CalendarRange className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium text-slate-200">No schedule yet</p>
              <p className="text-xs text-slate-500">
                {isGuideLoaded
                  ? "We couldn't find a timetable in this guide."
                  : "Load an athlete guide to preview its timetable here."}
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
