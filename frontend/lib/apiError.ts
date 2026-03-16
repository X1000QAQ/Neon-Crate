export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

export function notifyLinkDown(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('neon-network-down'));
  }
}

export function notifyLinkUp(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('neon-network-up'));
  }
}
