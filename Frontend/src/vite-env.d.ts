/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SCANNER_API_URL?: string;
  readonly VITE_RAG_API_URL?: string;
  readonly VITE_CHATBOT_API_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
