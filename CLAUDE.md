# Social Listening & Value-Add Agent

## Role
Social media automation agent that scans Twitter, Reddit, and LinkedIn for posts matching configurable topics, generates human-sounding replies using AI personas, and auto-posts approved replies. Built for growing audience engagement across multiple platforms with different personas and tones.

## Boundaries

### This Agent Does:
- Scan Twitter via API for posts matching persona topics
- Scan Reddit via JSON API / search for relevant posts
- Generate human-like replies using Claude AI with configurable personas
- Auto-post approved replies to Twitter (with random delays)
- Provide a web dashboard for persona management, run configuration, and reply review
- Send email reports after posting runs
- Expose /api/v1/status for orchestra integration

### This Agent Does NOT:
- Scrape LinkedIn directly (uses email notifications or manual input)
- Auto-post to Reddit or LinkedIn (manual copy-paste only)
- Manage other agents' data or configuration
- Handle user accounts or multi-tenancy (single-user tool)

### Never Do:
- Never commit .env files or secrets
- Never modify files outside this project directory
- Never push without approval
- Never auto-post without user review/approval first

## Data Ownership
- This agent owns: data/personas/, data/runs/, data/reports/, data/scans/
- This agent reads from: Twitter API, Reddit JSON API, Anthropic Claude API
- This agent never writes to other agents' data

## Workflow

1. **Understand** — Listen to what the user wants. Do not edit code yet.
2. **Review** — Read the existing files that will be affected.
3. **Plan** — Describe the changes in plain English. Get approval before editing.
4. **Build** — Make the changes, following existing code style.
5. **Test** — Verify the changes work as expected.
6. **Commit** — Stage and commit with a clear message. Always ask before pushing.

## Creative Direction

### The Vibe
more human like respone , empathy , geniuenly trying to help people stuck

### What This Is NOT
not overly structured Agentic respons 
- Do not use marketing jargon (e.g., "game-changer," "revolutionary," "synergy").
- Do not paste raw links unless requested; use conversational breadcrumbs like "I built a free instruction generator for this if you want to check it out on my profile."
- If the post is not a match for our tool, output <skip>true</skip>.
- Limit the total response to 4 sentences maximum.

### Brand Identity

#### Logo
- **File**: `same as my own website in https://www.localtechedge.com/`
- **Description**: use my logo from here : https://www.localtechedge.com/
- **Rules**: use same colors and branding as my website

When making any creative or visual change, ask: "Does this still match the creative direction and brand identity above?"

## Tech Stack

- **Language**: Python
- **Framework**: FastAPI
- **Services**: claude-api

## How It Works

- **Data sources**: External API, Web scraping
- **Trigger**: Webhook/event from another service
- **Output**: Display on screen, API response
- **Auth**: API key(s)

### Success Criteria
a human sounding social media post

## Security

- Never commit `.env` files or any file containing secrets
- Store all API keys, passwords, and tokens in environment variables
- Add `.env`, `.env.*`, and `.DS_Store` to `.gitignore`
- Never expose AI API keys to the frontend / client-side code

## Git Workflow

### Branches
- `main` — stable, working code
- `feature/{short-description}` — new features
- `fix/{short-description}` — bug fixes

### Flow
1. Create a feature branch from `main`
2. Make changes, commit with clear messages
3. Merge back to `main` when ready

### Commits
- Concise messages focused on the "why"
- One logical change per commit
- Never commit `.env` or files containing secrets

## Skills (Custom Slash Commands)

This project uses Claude Code skills for common workflows. Create these in
`.claude/skills/` in your project directory.

### Available Skills

| Skill | Purpose |
|---|---|
| `/deploy` | Ship your API to the live server |
| `/test` | Run all API tests |
| `/test-prompt` | Test your AI with a specific scenario |
| `/eval` | Grade your AI's output quality |
| `/test-task` | Test a specific task with sample data |
| `/test-scrape` | Run scraper on a single page to test |

### Skill Definitions

Create these files in your project:

#### `/deploy` — `.claude/skills/deploy/SKILL.md`

```yaml
---
name: deploy
description: Ship your API to the live server
disable-model-invocation: true
---

Ship your API to the live server. Follow the project's workflow and conventions.

IMPORTANT: Always confirm with the user before proceeding.
```

#### `/test` — `.claude/skills/test/SKILL.md`

```yaml
---
name: test
description: Run all API tests
---

Run all API tests. Follow the project's workflow and conventions.
```

#### `/test-prompt` — `.claude/skills/test-prompt/SKILL.md`

```yaml
---
name: test-prompt
description: Test your AI with a specific scenario
---

Test your AI with a specific scenario. Follow the project's workflow and conventions.
```

#### `/eval` — `.claude/skills/eval/SKILL.md`

```yaml
---
name: eval
description: Grade your AI's output quality
---

Grade your AI's output quality. Follow the project's workflow and conventions.
```

#### `/test-task` — `.claude/skills/test-task/SKILL.md`

```yaml
---
name: test-task
description: Test a specific task with sample data
---

Test a specific task with sample data. Follow the project's workflow and conventions.
```

#### `/test-scrape` — `.claude/skills/test-scrape/SKILL.md`

```yaml
---
name: test-scrape
description: Run scraper on a single page to test
---

Run scraper on a single page to test. Follow the project's workflow and conventions.
```

## MCP Servers

The following MCP servers are configured for this project. They let Claude interact
with external services directly.

| Server | Purpose |
|---|---|
| GitHub | PR workflow, issue tracking, code review |
| Playwright | Browser automation, screenshots, visual testing |
| Filesystem | Extended file access beyond project directory |
| Fetch | HTTP requests to external APIs |

### Configuration
MCP servers are defined in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" }
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-playwright"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-fetch"]
    }
  }
}
```

**Important**: API keys go in environment variables, never hardcoded in the config.

## Hooks (Automated Quality Checks)

Hooks run automatically — no manual invocation needed. They enforce project
standards behind the scenes.

| Trigger | Action |
|---|---|
| After any file edit | Auto-format with Prettier/Black |
| Before git commit | Run test suite — blocks commit if tests fail |
| After any file edit | Run linter to check for code quality issues |
| Before git commit | Scan for accidentally included secrets/API keys |

### Configuration
Hooks are defined in `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hook": { "type": "command", "command": "npx prettier --write $CLAUDE_FILE_PATH" }
      },
      {
        "matcher": "Write|Edit",
        "hook": { "type": "command", "command": "npx eslint --fix $CLAUDE_FILE_PATH" }
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash(git commit*)",
        "hook": { "type": "command", "command": "npm test" }
      },
      {
        "matcher": "Bash(git commit*)",
        "hook": { "type": "command", "command": "git diff --cached | grep -iE \"(api_key|secret|password|token)\s*=\" && echo SECRETS_FOUND && exit 1 || true" }
      }
    ]
  }
}
```

**Important**: If a hook blocks an action, fix the underlying issue — do not disable the hook.

## Subagents (Specialist Reviewers)

These specialized agents run in isolated context for focused review tasks.
They keep detailed analysis separate from your main conversation.

| Agent | Purpose |
|---|---|
| `/code-review` | Review code for quality, consistency, and potential bugs |
| `/security-review` | Scan for security vulnerabilities |
| `/doc-updater` | Keep documentation in sync with code changes |

### Skill Definitions

#### `/code-review` — `.claude/skills/code-review/SKILL.md`

```yaml
---
name: code-review
description: Review code for quality, consistency, and potential bugs
context: fork
agent: general-purpose
allowed-tools: Read, Grep, Glob
---

Review the code changes. Check for:\n1. Code style consistency\n2. Potential bugs or edge cases\n3. Performance concerns\n4. Missing error handling\n\nReport findings in a structured severity-rated list.
```

#### `/security-review` — `.claude/skills/security-review/SKILL.md`

```yaml
---
name: security-review
description: Scan for security vulnerabilities
context: fork
agent: general-purpose
allowed-tools: Read, Grep, Glob
---

Perform a security review. Check for:\n1. Hardcoded secrets or API keys\n2. Injection vulnerabilities (SQL, XSS, command)\n3. Insecure dependencies\n4. Missing input validation\n5. Authentication/authorization gaps\n\nReturn a severity-rated findings list.
```

#### `/doc-updater` — `.claude/skills/doc-updater/SKILL.md`

```yaml
---
name: doc-updater
description: Keep documentation in sync with code changes
context: fork
agent: general-purpose
allowed-tools: Read, Grep, Glob
---

Review recent code changes and check if documentation needs updating.\nCheck README, inline comments, and API docs.\nSuggest specific updates with exact text changes.
```

## Best Practices

### Security Headers
MUST configure these HTTP security headers on the hosting platform:
- `Content-Security-Policy` — restrict which resources can load
- `Strict-Transport-Security` — enforce HTTPS (max-age=31536000)
- `X-Content-Type-Options: nosniff` — prevent MIME sniffing
- `X-Frame-Options: DENY` — prevent clickjacking
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` — disable unused browser APIs (camera, mic, geo)


### SEO
Every public page MUST include:
- Unique `<title>` tag (under 60 characters)
- Unique `<meta name="description">` (150-160 characters)
- `<link rel="canonical">` pointing to the canonical URL
- Open Graph tags (`og:title`, `og:description`, `og:image`, `og:url`)
- Twitter Card tags (`twitter:card`, `twitter:title`, `twitter:image`)
- Semantic HTML (`<header>`, `<main>`, `<nav>`, `<footer>`)
- One `<h1>` per page — unique and descriptive
- `alt` text on all images
- `robots.txt` and `sitemap.xml` at site root
- JSON-LD structured data (schema.org) for rich search results

### AIO (AI Search Optimization)
Optimize content for AI search engines (ChatGPT, Perplexity, Google AI):
- Use Q&A format and FAQ sections — AI extracts answers from these
- Add FAQPage schema markup (JSON-LD) for AI citation
- Write concise first-paragraph summaries that directly answer the main question
- Use clear H2/H3 heading hierarchy — AI uses structure to understand topics
- Include specific data, credentials, and sources — AI prefers authoritative content
- Keep content fresh and recently updated
- Allow AI crawlers in `robots.txt` (GPTBot, ClaudeBot, PerplexityBot)

### Performance
Target Lighthouse 90+ on all categories. Key rules:
- LCP (Largest Contentful Paint) MUST be under 2.5 seconds
- Use modern image formats (WebP/AVIF), compress to under 200KB
- Lazy-load images below the fold (`loading="lazy"`)
- Add `width` and `height` to images to prevent layout shift
- Defer non-critical JavaScript (`defer` attribute)
- Minify CSS and JS in production
- Enable gzip/brotli compression
- Set cache headers: 1 year for static assets, no-cache for HTML

### Accessibility (WCAG AA)
- MUST maintain 4.5:1 contrast ratio for text, 3:1 for UI elements
- MUST provide `:focus-visible` styles on all interactive elements
- MUST ensure all functionality works with keyboard only
- MUST use semantic HTML (`<button>` not `<div onclick>`)
- MUST include `<label>` for all form inputs
- MUST respect `prefers-reduced-motion` — disable animations when set
- MUST add `alt` text to informational images
- SHOULD provide skip-to-content link
- Test with Lighthouse accessibility audit — target 90+

### Pre-Launch Security Checklist
Before deploying, verify:
- [ ] All secrets in environment variables (none in code)
- [ ] `.env` in `.gitignore`
- [ ] HTTPS enforced everywhere
- [ ] Security headers configured
- [ ] Input validation on all user-facing endpoints
- [ ] Parameterized database queries (no string concatenation)
- [ ] Rate limiting on auth endpoints
- [ ] Error messages don't leak internals
- [ ] CORS not set to `*` in production
- [ ] `npm audit` / `pip audit` passes (no critical vulns)
- [ ] File upload validation (type, size, content)
- [ ] Cookies use `httpOnly`, `secure`, `SameSite` flags

## API Contract (for Orchestra)
```
GET /health → {"status": "ok"}
GET /api/v1/status → {agent_name, status, last_run, pending_reviews, total_runs, total_posted}
```

## Always Ask Before

- Deploying to the live site
- Deleting files, data, or branches
- Pushing code to the remote repository
- Adding new tools, libraries, or frameworks
- Changing the design system (colors, fonts, spacing)

## Always Do

- Read existing code before modifying it
- Explain changes before making them if they affect more than 3 files
- Match existing code style and conventions
- Test changes before suggesting deploy

## Audit Checklist (run monthly)
- [ ] Remove unused imports and variables (autoflake, vulture)
- [ ] Update requirements.txt (pip freeze)
- [ ] Update this CLAUDE.md if role/boundaries changed
- [ ] Run full test suite: pytest tests/ -v
- [ ] Check for hardcoded secrets: grep -r "sk-\|password\s*=" --include="*.py"
- [ ] Review TODOs in code: grep -r "TODO\|FIXME" --include="*.py"
- [ ] Check for dead code (commented-out blocks, unreachable branches)
- [ ] Verify .env in .gitignore
- [ ] Run pip audit for security vulnerabilities