/**
 * Base URL for backend API requests.
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Normalized schedule entry returned by the backend.
 */
export interface ScheduleItem {
  time: string;
  activity: string;
  location?: string | null;
}

/**
 * Groups schedule items by their day heading.
 */
export interface ScheduleDay {
  title: string;
  items: ScheduleItem[];
}

/**
 * Response returned when a PDF is ingested successfully.
 */
export interface UploadResponse {
  document_id: string;
  filename: string;
  page_count: number;
  uploaded_at: string;
  schedule: ScheduleDay[];
}

/**
 * Citation pointing back to a supporting chunk.
 */
export interface Citation {
  section: string;
  page: number;
  excerpt: string;
}

/**
 * Answer payload produced by the question endpoint.
 */
export interface AskResponse {
  answer: string;
  citations: Citation[];
}

/**
 * Lightweight metadata for demo guides stored on disk.
 */
export interface ExampleGuide {
  slug: string;
  name: string;
  filename: string;
}

/**
 * Upload an athlete guide and receive its registry metadata.
 */
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

/**
 * Ask a question about the current document, optionally seeding prior context.
 */
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

/**
 * Fetch the list of bundled demo guides from the backend.
 */
export async function listExamples(): Promise<ExampleGuide[]> {
  const response = await fetch(`${API_BASE_URL}/examples`);
  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message ?? "Unable to load demo guides");
  }
  return (await response.json()) as ExampleGuide[];
}

/**
 * Request the backend to load a demo guide and return it as an upload response.
 */
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

/**
 * Attempt to extract a human-readable error message from a failed fetch response.
 */
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
