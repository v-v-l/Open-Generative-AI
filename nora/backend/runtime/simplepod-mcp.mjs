#!/usr/bin/env node
import fs from 'node:fs';
import { parseEnv } from 'node:util';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const runtime = path.dirname(fileURLToPath(import.meta.url));
const modules = process.env.NORA_SIMPLEPOD_NODE_MODULES || path.join(runtime, 'node_modules');
const { Client } = await import(pathToFileURL(path.join(modules, '@modelcontextprotocol/sdk/dist/esm/client/index.js')).href);
const { StdioClientTransport } = await import(pathToFileURL(path.join(modules, '@modelcontextprotocol/sdk/dist/esm/client/stdio.js')).href);

// Keep credentials in the local environment file, never command arguments.
const credentialFile = process.env.NORA_SIMPLEPOD_CREDENTIALS_FILE || path.join(process.env.NORA_PROJECT_ROOT || process.cwd(), '.env');
const vars = fs.existsSync(credentialFile) ? parseEnv(fs.readFileSync(credentialFile, 'utf8')) : {};
const token = (process.env.SIMPLEPOD_API_KEY || vars.SIMPLEPOD_API_KEY)?.trim();
if (!token) throw new Error('SIMPLEPOD_API_KEY is missing');
// Version 0.1.1 has no resume MCP tool; use the documented provider REST route.
if (process.argv[2] === 'resume-vps') {
  const args = JSON.parse(process.argv[3] || '{}');
  if (!args.instance || !args.instanceMarket) throw new Error('instance and instanceMarket are required');
  const response = await fetch('https://api.simplepod.ai/instances?mode=vm-resume', {
    method: 'POST',
    headers: { 'X-AUTH-TOKEN': token, 'Content-Type': 'application/json' },
    body: JSON.stringify(args),
  });
  const body = await response.text();
  console.log(body.replaceAll(token, '[REDACTED]'));
  process.exit(response.ok ? 0 : 1);
}
const client = new Client({ name: 'nora-simplepod', version: '1.0.0' });
try {
  await client.connect(new StdioClientTransport({
    command: process.execPath,
    args: [path.join(modules, '@simplepod.ai/mcp-rental/dist/index.js')],
    env: { PATH: process.env.PATH, API_TOKEN: token },
    stderr: 'pipe',
  }));
  const name = process.argv[2] || 'sp_get_summary';
  const argument = process.argv[3] || '{}';
  const args = JSON.parse(argument.startsWith('@') ? fs.readFileSync(argument.slice(1), 'utf8') : argument);
  const result = await client.callTool({ name, arguments: args });
  for (const item of result.content || []) {
    if (item.type === 'text') console.log(item.text.replaceAll(token, '[REDACTED]'));
  }
  if (result.isError) process.exitCode = 1;
} catch (error) {
  console.error(String(error).replaceAll(token, '[REDACTED]'));
  process.exitCode = 1;
} finally {
  await client.close();
}
