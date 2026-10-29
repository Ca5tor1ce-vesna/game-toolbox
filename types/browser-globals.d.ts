export {};

declare global {
  interface Window {
    GT_AHA_SPEED_API: { createApi(): { call(action: string, payload?: unknown): unknown } };
    GT_ASSETS: Record<string, string>;
    GT_STANDALONE: boolean;
    GT_DIALOG(message: string, confirm?: boolean): Promise<boolean>;
    GT_AHA_ORIGINAL_HTML: string;
    GT_AHA_VENDOR_JS: string;
    GT_INSTALL_SELECT_MENU?: () => void;
    GT_LOCAL_STATE: { scope(key: string): { bind(root: HTMLElement): () => void } };
  }
}
