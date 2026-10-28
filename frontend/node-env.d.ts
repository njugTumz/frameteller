// The few Node globals the config files and e2e tests read, so the project needs no @types/node.
declare const process: { env: Record<string, string | undefined>; cwd(): string }
