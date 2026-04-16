'use strict';

const fs = require('fs');
const path = require('path');
const { parseFrontmatter, extractBody } = require('./frontmatter');

// ── Task Type Detection ─────────────────────────────────────

const BRANCH_PATTERNS = [
  { pattern: /^(?:feat|feature)\//, type: 'feature' },
  { pattern: /^(?:fix|bugfix|hotfix)\//, type: 'bugfix' },
  { pattern: /^(?:refactor|refact)\//, type: 'refactor' },
];

const TITLE_PREFIX_PATTERNS = [
  { pattern: /^feat(?:\(.*?\))?:/, type: 'feature' },
  { pattern: /^fix(?:\(.*?\))?:/, type: 'bugfix' },
  { pattern: /^refactor(?:\(.*?\))?:/, type: 'refactor' },
];

const TITLE_KEYWORDS = [
  { pattern: /\b(?:add|implement|new|create)\b/i, type: 'feature' },
  { pattern: /\b(?:fix|resolve|bug|patch)\b/i, type: 'bugfix' },
  { pattern: /\b(?:refactor|restructure|reorganize|clean\s*up)\b/i, type: 'refactor' },
];

function detectTaskType(prMetadata) {
  const branch = (prMetadata.headRefName || '').trim();
  const title = (prMetadata.title || '').trim();

  // 1. Branch prefix (strongest signal)
  for (const { pattern, type } of BRANCH_PATTERNS) {
    if (pattern.test(branch)) return type;
  }

  // 2. PR title prefix (conventional commits)
  for (const { pattern, type } of TITLE_PREFIX_PATTERNS) {
    if (pattern.test(title)) return type;
  }

  // 3. PR title keywords (fallback)
  for (const { pattern, type } of TITLE_KEYWORDS) {
    if (pattern.test(title)) return type;
  }

  // 4. Default to feature (broadest criteria set)
  return 'feature';
}

module.exports = { detectTaskType };
