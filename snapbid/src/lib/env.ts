/**
 * Env access in one place. Server-only values throw when read without being
 * configured, so a misconfigured deploy fails loudly at the call site instead
 * of silently doing nothing.
 */
export function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

export function optionalEnv(name: string): string | undefined {
  return process.env[name] || undefined;
}

export function appUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_APP_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://localhost:3000";
}

export const supabaseUrl = () => requiredEnv("NEXT_PUBLIC_SUPABASE_URL");
export const supabaseAnonKey = () => requiredEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY");
export const supabaseServiceKey = () => requiredEnv("SUPABASE_SERVICE_ROLE_KEY");
