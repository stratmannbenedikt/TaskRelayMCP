import { rm } from 'node:fs/promises';

export default async function globalTeardown() {
  await rm('/tmp/taskrelay-playwright.db', { force: true });
}
