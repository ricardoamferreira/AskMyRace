const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface UploadResponse {
  document_id: string;
  filename: string;
  page_count: number;
  uploaded_at: string;
}

export interface Citation {
  section: string;
  page: number;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
}

export interface ExampleGuide {
  slug: string;
  name: string;
  filename: string;
}

export async function uploadGuide(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message ?? "Upload failed");
  }

  return (await response.json()) as UploadResponse;
}

export async function askQuestion(
  documentId: string,
  question: string,
  context?: string,
): Promise<AskResponse> {
  const payload: Record<string, unknown> = {
    document_id: documentId,
    question,
  };
  if (context && context.trim().length > 0) {
    payload.context = context.trim();
  }

  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message ?? "Unable to generate answer");
  }

  return (await response.json()) as AskResponse;
}

export async function listExamples(): Promise<ExampleGuide[]> {
  const response = await fetch(`${API_BASE_URL}/examples`);
  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message ?? "Unable to load demo guides");
  }
  return (await response.json()) as ExampleGuide[];
}

export async function loadExample(slug: string): Promise<UploadResponse> {
  const response = await fetch(`${API_BASE_URL}/examples/${slug}`, {
    method: "POST",
  });
  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message ?? "Unable to load the demo guide");
  }
  return (await response.json()) as UploadResponse;
}

async function extractErrorMessage(response: Response): Promise<string | null> {
  try {
    const data = await response.json();
    if (typeof data === "string") return data;
    if (data?.detail) {
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail) && data.detail[0]?.msg) {
        return data.detail[0].msg;
      }
    }
    return null;
  } catch {
    return null;
  }
}
