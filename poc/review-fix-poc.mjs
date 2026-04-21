#!/usr/bin/env node

import { query } from '@anthropic-ai/claude-agent-sdk'
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { parseArgs } from 'node:util'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(__dirname, '..')

// --- CLI ---

const { values: args } = parseArgs({
  options: {
    pr: { type: 'string' },
    repo: { type: 'string' },
    'dry-run': { type: 'boolean', default: false },
    help: { type: 'boolean', default: false },
  },
  strict: false,
})

if (args.help) {
  console.log(`Usage: node review-fix-poc.mjs [--pr NUMBER] [--repo OWNER/REPO] [--dry-run]

  --pr      PR number to review (omit to use sample diff)
  --repo    GitHub repo (default: current repo)
  --dry-run Run reviewer only, skip fixer`)
  process.exit(0)
}

// --- Colors ---

const c = {
  reset: '\x1b[0m',
  dim: '\x1b[2m',
  bold: '\x1b[1m',
  cyan: '\x1b[36m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  magenta: '\x1b[35m',
}

// --- Get PR diff ---

function getDiff() {
  if (args.pr) {
    const repoFlag = args.repo ? `--repo ${args.repo}` : ''
    console.log(`${c.cyan}[setup]${c.reset} Fetching diff for PR #${args.pr}...`)
    return execSync(`gh pr diff ${args.pr} ${repoFlag}`, { encoding: 'utf-8', cwd: repoRoot })
  }

  console.log(`${c.cyan}[setup]${c.reset} No --pr specified, using sample diff`)
  return SAMPLE_DIFF
}

// --- Load agent prompts ---

function loadAgentPrompt(relativePath) {
  const fullPath = resolve(__dirname, relativePath)
  const raw = readFileSync(fullPath, 'utf-8')
  const match = raw.match(/^---\n[\s\S]*?\n---\n([\s\S]*)$/)
  if (!match) return raw
  return match[1].trim()
}

const REVIEWER_PROMPT = loadAgentPrompt('./agents/reviewer.md')
const FIXER_PROMPT = loadAgentPrompt('./agents/fixer.md')

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'Unique ID like F1, F2...' },
          severity: { type: 'string', enum: ['must-fix', 'should-fix', 'nit'] },
          file: { type: 'string', description: 'File path relative to repo root' },
          line_start: { type: 'number' },
          line_end: { type: 'number' },
          claim: { type: 'string', description: 'One-sentence description of the issue' },
          quoted_code: { type: 'string', description: 'Verbatim code from the diff' },
          suggested_fix: { type: 'string', description: 'How to fix it' },
        },
        required: ['id', 'severity', 'file', 'line_start', 'claim', 'quoted_code', 'suggested_fix'],
      },
    },
  },
  required: ['findings'],
}

// --- Progress display ---

function printProgress(message, phase) {
  const prefix = `${c.cyan}[${phase}]${c.reset}`

  switch (message.type) {
    case 'stream_event': {
      const event = message.event
      if (event?.type === 'content_block_delta' && event.delta?.type === 'text_delta') {
        process.stdout.write(`${c.dim}${event.delta.text}${c.reset}`)
      }
      break
    }
    case 'assistant': {
      const text = message.message?.content
        ?.filter(b => b.type === 'text')
        ?.map(b => b.text)
        ?.join('') || ''
      if (text) {
        console.log(`\n${prefix} ${c.bold}Response:${c.reset}`)
        console.log(text.slice(0, 500) + (text.length > 500 ? '...' : ''))
      }

      const toolUses = message.message?.content?.filter(b => b.type === 'tool_use') || []
      for (const tu of toolUses) {
        console.log(`${prefix} ${c.magenta}tool:${c.reset} ${tu.name}(${JSON.stringify(tu.input).slice(0, 100)})`)
      }
      break
    }
    case 'result': {
      console.log(`\n${prefix} ${c.green}Done${c.reset} — ${message.subtype} (cost: $${message.cost_usd?.toFixed(4) || '?'}, turns: ${message.num_turns || '?'})`)
      break
    }
    case 'system': {
      if (message.subtype === 'notification') {
        console.log(`${prefix} ${c.yellow}${message.text}${c.reset}`)
      }
      break
    }
  }
}

// --- Ground findings ---

function groundFindings(findings) {
  console.log(`\n${c.cyan}[ground]${c.reset} Verifying ${findings.length} findings against source files...`)
  const grounded = []
  const dropped = []

  for (const f of findings) {
    try {
      const filePath = resolve(repoRoot, f.file)
      const content = readFileSync(filePath, 'utf-8')
      const lines = content.split('\n')
      const start = (f.line_start || 1) - 1
      const end = (f.line_end || f.line_start || 1)
      const actual = lines.slice(start, end).join('\n')

      const quotedNorm = f.quoted_code.trim().replace(/\s+/g, ' ')
      const actualNorm = actual.trim().replace(/\s+/g, ' ')

      if (actualNorm.includes(quotedNorm) || quotedNorm.includes(actualNorm)) {
        grounded.push(f)
        console.log(`  ${c.green}✓${c.reset} ${f.id}: ${f.claim}`)
      } else {
        dropped.push({ ...f, reason: 'quoted_code mismatch' })
        console.log(`  ${c.red}✗${c.reset} ${f.id}: quoted_code doesn't match file content`)
      }
    } catch (err) {
      dropped.push({ ...f, reason: `file read error: ${err.message}` })
      console.log(`  ${c.red}✗${c.reset} ${f.id}: ${err.message}`)
    }
  }

  const rate = findings.length > 0 ? ((dropped.length / findings.length) * 100).toFixed(0) : 0
  console.log(`${c.cyan}[ground]${c.reset} ${grounded.length} grounded, ${dropped.length} dropped (${rate}% hallucination rate)`)
  return { grounded, dropped }
}

// --- Main ---

async function main() {
  const t0 = Date.now()
  console.log(`${c.bold}=== Agent SDK Review-Fix POC ===${c.reset}\n`)

  const diff = getDiff()
  console.log(`${c.cyan}[setup]${c.reset} Diff size: ${diff.length} chars, ${diff.split('\n').length} lines\n`)

  // --- Phase 1: Review ---
  const t1 = Date.now()
  console.log(`${c.bold}--- Phase 1: Review ---${c.reset}\n`)

  let resultText = ''
  let lastAssistantContent = null
  const reviewQuery = query({
    prompt: `Review this PR diff and output findings as JSON:\n\n\`\`\`diff\n${diff}\n\`\`\``,
    options: {
      agents: {
        reviewer: {
          description: 'PR code reviewer that outputs structured JSON findings',
          prompt: REVIEWER_PROMPT,
          tools: ['Read', 'Grep', 'Glob'],
          model: 'sonnet',
        },
      },
      agent: 'reviewer',
      allowedTools: ['Read', 'Grep', 'Glob'],
      permissionMode: 'dontAsk',
      cwd: repoRoot,
      maxTurns: 10,
      maxBudgetUsd: 0.5,
      outputFormat: { type: 'json_schema', schema: FINDINGS_SCHEMA },
      includePartialMessages: true,
    },
  })

  for await (const message of reviewQuery) {
    printProgress(message, 'reviewer')

    // Capture structured output from assistant messages
    if (message.type === 'assistant') {
      const content = message.message?.content || []
      for (const block of content) {
        if (block.type === 'tool_use' && block.name === 'StructuredOutput') {
          lastAssistantContent = block.input
        }
      }
    }
    if (message.type === 'result') {
      resultText = message.result || ''
    }
  }

  // Parse findings — try structured output first, then result text
  let findings
  try {
    const source = lastAssistantContent || JSON.parse(resultText)
    const parsed = typeof source === 'string' ? JSON.parse(source) : source
    findings = parsed.findings || []
  } catch {
    console.error(`${c.red}[error]${c.reset} Failed to parse reviewer output as JSON`)
    console.error(`Result text: ${resultText.slice(0, 200)}`)
    console.error(`Structured output: ${JSON.stringify(lastAssistantContent)?.slice(0, 200)}`)
    process.exit(1)
  }

  const reviewMs = Date.now() - t1
  console.log(`\n${c.cyan}[reviewer]${c.reset} Found ${findings.length} issues ${c.dim}(${(reviewMs / 1000).toFixed(1)}s)${c.reset}`)
  for (const f of findings) {
    const sev = f.severity === 'must-fix' ? c.red : f.severity === 'should-fix' ? c.yellow : c.dim
    console.log(`  ${sev}[${f.severity}]${c.reset} ${f.id}: ${f.claim} (${f.file}:${f.line_start})`)
  }

  if (findings.length === 0) {
    console.log(`\n${c.green}No issues found. PR looks clean!${c.reset}`)
    return
  }

  // --- Phase 2: Ground ---
  const t2 = Date.now()
  const { grounded } = groundFindings(findings)
  console.log(`${c.dim}(${((Date.now() - t2) / 1000).toFixed(1)}s)${c.reset}`)

  if (grounded.length === 0) {
    console.log(`\n${c.yellow}All findings were hallucinated. Nothing to fix.${c.reset}`)
    return
  }

  if (args['dry-run']) {
    console.log(`\n${c.yellow}[dry-run]${c.reset} Skipping fixer phase.`)
    return
  }

  // --- Phase 3: Fix ---
  const mustFix = grounded.filter(f => f.severity === 'must-fix')
  const toFix = mustFix.length > 0 ? mustFix : grounded

  const t3 = Date.now()
  console.log(`\n${c.bold}--- Phase 3: Fix (${toFix.length} findings) ---${c.reset}\n`)

  const fixQuery = query({
    prompt: `Fix these verified code issues. Each finding has been verified against the actual source code.\n\nFindings:\n${JSON.stringify(toFix, null, 2)}`,
    options: {
      agents: {
        fixer: {
          description: 'Applies verified code fixes and commits',
          prompt: FIXER_PROMPT,
          tools: ['Read', 'Edit', 'Bash'],
          model: 'sonnet',
        },
      },
      agent: 'fixer',
      allowedTools: ['Read', 'Edit', 'Bash(git diff *)', 'Bash(git add *)', 'Bash(git commit *)', 'Bash(npm test *)'],
      permissionMode: 'acceptEdits',
      cwd: repoRoot,
      maxTurns: 15,
      maxBudgetUsd: 0.5,
      includePartialMessages: true,
    },
  })

  for await (const message of fixQuery) {
    printProgress(message, 'fixer')
  }

  // --- Phase 4: Verify ---
  console.log(`\n${c.dim}Fix phase: ${((Date.now() - t3) / 1000).toFixed(1)}s${c.reset}`)
  console.log(`\n${c.bold}--- Phase 4: Verify ---${c.reset}\n`)
  try {
    execSync('npm test', { stdio: 'inherit', cwd: repoRoot })
    console.log(`\n${c.green}${c.bold}All tests pass!${c.reset}`)
  } catch {
    console.log(`\n${c.red}${c.bold}Tests failed after fixes.${c.reset}`)
    process.exit(1)
  }

  console.log(`\n${c.bold}Total time: ${((Date.now() - t0) / 1000).toFixed(1)}s${c.reset}`)
}

// --- Sample diff for testing without a PR ---

const SAMPLE_DIFF = `diff --git a/lib/example.js b/lib/example.js
index 1234567..abcdefg 100644
--- a/lib/example.js
+++ b/lib/example.js
@@ -10,6 +10,15 @@ function validateInput(input) {
   return true
 }

+function processUserData(data) {
+  const query = "SELECT * FROM users WHERE id = " + data.userId
+  const result = db.execute(query)
+  if (result == null) {
+    return { error: "not found" }
+  }
+  return { user: result, token: Math.random().toString(36) }
+}
+
 module.exports = { validateInput }
`

main().catch(err => {
  console.error(`${c.red}Fatal: ${err.message}${c.reset}`)
  process.exit(1)
})
