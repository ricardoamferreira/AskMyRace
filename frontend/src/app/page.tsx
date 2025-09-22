"use client";

import { FormEvent, useMemo, useRef, useState, KeyboardEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  askQuestion,
  Citation,
  listExamples,
  loadExample,
  uploadGuide,
  UploadResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Bot,
  CheckCircle2,
  FileText,
  Loader2,
  SendHorizontal,
  UploadCloud,
  UserRound,
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
  return recent.length > MAX_HISTORY_LENGTH
    ? recent.slice(recent.length - MAX_HISTORY_LENGTH)
    : recent;
}

export default function Home() {
  const [document, setDocument] = useState<UploadResponse | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

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
      const message =
        error instanceof Error ? error.message : "Unable to upload the PDF.";
      toast.error(message);
    },
  });

  const exampleMutation = useMutation({
    mutationFn: loadExample,
    onSuccess: (data, slug) => {
      setDocument(data);
      setMessages([]);
      const guideName = examplesQuery.data?.find((item) => item.slug === slug)?.name;
      toast.success(
        guideName ? `Loaded demo guide: ${guideName}` : "Demo guide loaded.",
      );
    },
    onError: (error) => {
      const message =
        error instanceof Error ? error.message : "Unable to load the demo guide.";
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
      const message =
        error instanceof Error ? error.message : "Unable to generate an answer.";
      toast.error(message);
    },
  });

  const isReadyToAsk = useMemo(
    () => Boolean(document) && !uploadMutation.isPending && !exampleMutation.isPending,
    [document, uploadMutation.isPending, exampleMutation.isPending],
  );

  const handleFileInput = (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file) return;

    if (file.type !== "application/pdf") {
      toast.error("Please upload a PDF athlete guide.");
      return;
    }

    if (file.size > 80 * 1024 * 1024) {
      toast.error("PDF must be 80 MB or smaller.");
      return;
    }

    uploadMutation.mutate(file);
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

    if (!isReadyToAsk || askMutation.isPending) {
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
      toast("Upload or load a guide first to try a sample question.", { icon: "💡" });
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

  return (
    <div className="min-h-screen bg-zinc-100">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-6 lg:px-8">
        <header className="flex flex-col gap-2 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-zinc-900">Ask My Race</h1>
            <p className="text-sm text-zinc-600">
              Upload a triathlon athlete guide and ask follow-up questions with context-aware answers.
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              Backend connected
            </span>
            <span className="hidden sm:inline">•</span>
            <span className="hidden sm:inline text-zinc-500">Powered by LangChain · OpenAI</span>
          </div>
        </header>

        <div className="grid flex-1 gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="flex flex-col gap-6">
            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-lg font-medium text-zinc-900">Upload athlete guide</h2>
              <p className="mb-4 text-sm text-zinc-600">
                Drag and drop a PDF or choose a file. We only store it for this session.
              </p>
              <label
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-zinc-300 bg-zinc-50 px-4 py-8 text-center transition",
                  (uploadMutation.isPending || exampleMutation.isPending) && "opacity-60",
                  "hover:border-zinc-400 hover:bg-zinc-100",
                )}
              >
                <input
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(event) => handleFileInput(event.target.files)}
                  disabled={uploadMutation.isPending || exampleMutation.isPending}
                />
                {uploadMutation.isPending ? (
                  <Loader2 className="h-7 w-7 animate-spin text-zinc-500" />
                ) : (
                  <UploadCloud className="mb-3 h-7 w-7 text-zinc-500" />
                )}
                <div className="text-sm font-medium text-zinc-800">
                  {uploadMutation.isPending
                    ? "Uploading guide..."
                    : "Click to browse or drop a PDF"}
                </div>
                <p className="text-xs text-zinc-500">PDF up to 80 MB</p>
              </label>
              {document && (
                <div className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-900">
                  <div className="flex items-center gap-2 font-medium">
                    <FileText className="h-4 w-4" />
                    {document.filename}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-xs text-emerald-800">
                    <span>Pages: {document.page_count}</span>
                    <span>
                      Uploaded: {new Date(document.uploaded_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-lg font-medium text-zinc-900">Demo guides</h2>
              <div className="flex flex-col gap-2">
                {examplesQuery.isLoading && (
                  <div className="flex items-center gap-2 text-sm text-zinc-500">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading demos...
                  </div>
                )}
                {!examplesQuery.isLoading && examplesQuery.data?.length === 0 && (
                  <p className="text-sm text-zinc-500">No demo guides available yet.</p>
                )}
                {examplesQuery.data?.map((example) => (
                  <button
                    key={example.slug}
                    type="button"
                    onClick={() => handleSelectExample(example.slug)}
                    disabled={exampleMutation.isPending}
                    className={cn(
                      "rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm font-medium text-zinc-700 transition hover:border-zinc-300 hover:bg-zinc-50",
                      exampleMutation.isPending && "opacity-60",
                    )}
                  >
                    {example.name}
                  </button>
                ))}
              </div>
              <p className="mt-4 text-xs text-zinc-500">
                Load a hosted guide instantly for demos or quick testing.
              </p>
            </section>

            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-lg font-medium text-zinc-900">Quick prompts</h2>
              <div className="flex flex-col gap-2">
                {sampleQuestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => handleSampleQuestion(item)}
                    className="rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm font-medium text-zinc-700 transition hover:border-zinc-300 hover:bg-zinc-50"
                  >
                    {item}
                  </button>
                ))}
              </div>
              <p className="mt-4 text-xs text-zinc-500">
                These are great starters once a guide is loaded.
              </p>
            </section>

            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-lg font-medium text-zinc-900">How it works</h2>
              <ol className="space-y-2 text-sm text-zinc-600">
                <li>
                  <span className="font-medium text-zinc-800">1.</span> Upload or select a race guide PDF.
                </li>
                <li>
                  <span className="font-medium text-zinc-800">2.</span> We chunk & embed it with LangChain.
                </li>
                <li>
                  <span className="font-medium text-zinc-800">3.</span> Ask questions; answers cite the guide.
                </li>
              </ol>
            </section>
          </aside>

          <main className="flex h-full flex-col rounded-2xl border border-zinc-200 bg-white shadow-sm">
            <div className="flex-1 overflow-y-auto px-6 py-6">
              {messages.length > 0 && (
                <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                  Please note that this is a work in progress; answers may contain errors.
                </div>
              )}
              {messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-zinc-500">
                  <Bot className="h-10 w-10 text-zinc-400" />
                  <div className="max-w-md text-sm">
                    Ask about logistics, schedules, rules, or anything specific to your loaded guide. Citations point to exactly where the answer comes from.
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  {messages.map((message) => (
                    <article
                      key={message.id}
                      className={cn(
                        "flex gap-3 rounded-2xl border px-4 py-3 text-sm",
                        message.role === "user"
                          ? "border-blue-100 bg-blue-50"
                          : "border-zinc-200 bg-white",
                      )}
                    >
                      <div className={cn(
                        "mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                        message.role === "user"
                          ? "bg-blue-500 text-white"
                          : "bg-zinc-900 text-white",
                      )}>
                        {message.role === "user" ? (
                          <UserRound className="h-4 w-4" />
                        ) : (
                          <Bot className="h-4 w-4" />
                        )}
                      </div>
                      <div className="flex flex-col gap-3">
                        <p className="whitespace-pre-line text-zinc-800">
                          {message.content}
                        </p>
                        {message.citations && message.citations.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {message.citations.map((citation) => (
                              <span
                                key={`${citation.section}-${citation.page}`}
                                className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-600" title={citation.excerpt}
                              >
                                {citation.section} — p.{citation.page}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <form ref={formRef} onSubmit={handleSubmit} className="border-t border-zinc-200 px-6 py-4">
              <fieldset className="flex flex-col gap-3" disabled={askMutation.isPending}>
                <textarea
                  ref={textareaRef}
                  value={question}
                  onChange={(event) => handleQuestionChange(event.target.value)}
                  onKeyDown={handleTextareaKeyDown}
                  placeholder={document ? "Ask a question about the guide" : "Upload or load a guide to start asking questions"}
                  maxLength={MAX_QUESTION_LENGTH}
                  className="min-h-[100px] resize-none rounded-xl border border-zinc-300 bg-white px-4 py-3 text-sm text-zinc-800 outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-indigo-100"
                />
                <div className="flex items-center justify-between text-xs text-zinc-500">
                  <span>{document ? document.filename : "No guide loaded yet"}</span>
                  <span>
                    {messages.filter((msg) => msg.role === "assistant").length} answers · {question.length}/
                    {MAX_QUESTION_LENGTH}
                  </span>
                </div>
                <div className="flex items-center justify-end">
                  <button
                    type="submit"
                    disabled={!isReadyToAsk || askMutation.isPending || !question.trim()}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition",
                      (!isReadyToAsk || askMutation.isPending || !question.trim())
                        ? "opacity-60"
                        : "hover:bg-zinc-800",
                    )}
                  >
                    {askMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <SendHorizontal className="h-4 w-4" />
                    )}
                    Ask
                  </button>
                </div>
              </fieldset>
            </form>
          </main>
        </div>
      </div>
    </div>
  );
}
