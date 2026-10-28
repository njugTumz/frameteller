// The few Node APIs the config files and e2e tests use, so the project needs no @types/node.
declare const process: { env: Record<string, string | undefined>; cwd(): string }

declare module 'node:fs' {
  export function existsSync(path: string): boolean
  export function mkdirSync(path: string, options?: { recursive?: boolean }): void
  export function readFileSync(path: string): Uint8Array
  export function readFileSync(path: string, encoding: 'utf8'): string
  export function writeFileSync(path: string, data: string | Uint8Array): void
}

declare module 'node:path' {
  export function dirname(path: string): string
  export function resolve(...paths: string[]): string
}
