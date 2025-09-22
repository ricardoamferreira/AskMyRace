declare module "pdf-parse" {
  import type { Buffer } from "buffer";

  export interface PDFParseResult {
    numpages: number;
    numrender: number;
    info: Record<string, unknown>;
    metadata: Record<string, unknown>;
    text: string;
    version: string;
  }

  export type PageRender = (pageData: any) => Promise<string>;

  export default function pdf(
    dataBuffer: Buffer,
    options?: { pagerender?: PageRender }
  ): Promise<PDFParseResult>;
}
