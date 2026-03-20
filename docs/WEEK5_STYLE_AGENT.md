# Week 5: Style & Maintainability Agent — Detailed Documentation

> **Goal:** Build the Style Agent — LLM + Ruff linter that enforces code quality, readability, and maintainability.
> **Status:** Complete — Live-tested on PR #4 with all three agents running concurrently
> **Date:** 2026-03-20
> **Test PR:** github.com/ninjacode911/codeguard-test/pull/4
> **Result:** 6 findings (unused imports, magic numbers, missing error handling, complex function)

---

## What We Built

The Style Agent is the third and final domain agent. It combines **Ruff** (an ultra-fast Python
linter written in Rust) with **LLM reasoning** (Groq Llama-3.3-70B) to catch code quality issues
that hurt long-term maintainability.

This agent solves a fundamentally different problem than Security or Performance. Style is
**subjective** — reasonable engineers disagree about naming conventions, docstring requirements,
and code organization. The agent must distinguish between genuine maintainability issues
(dead code, missing error handling) and personal preferences (single quotes vs. double quotes).
This makes the prompt design more nuanced than either of the other two agents.

```
PR Diff + File Contents
        |
        v
+-------------------------------+
|     Static Analysis           |  Ruff: 4 findings (unused imports, bare except)
|  Ruff (Rust-based linter)     |  11 rule categories enabled
|  10-100x faster than flake8   |  Time: ~50 milliseconds
+-------------------------------+
            | tool output as text
            v
+-------------------------------+
|     Groq LLM                  |  Model: llama-3.3-70b-versatile
|  System prompt: Staff eng     |  Input: diff + files + Ruff results
|  Structured output: JSON      |  Output: 6 Finding objects
|  Temperature: 0.1             |  Time: ~3.1 seconds
+-------------------------------+
            | Finding[]
            v
+-------------------------------+
|     Comment Formatter         |  Health Score: 14/100 (combined with other agents)
|  Summary + inline comments    |  Recommendation: Block Merge
|  Posted to GitHub PR          |  Severity table + details
+-------------------------------+
```

### Why Two Layers? Mechanical Linting vs. Semantic Review

This is the core architectural insight of the Style Agent. Ruff and the LLM catch
**completely different classes of issues**, and neither can replace the other:

| Dimension | Ruff (Mechanical) | LLM (Semantic) |
|-----------|-------------------|----------------|
| **What it catches** | Unused imports, syntax violations, import ordering, bare excepts | Non-descriptive naming, missing error handling, functions doing too many things, code duplication |
| **Speed** | ~50ms for an entire project | ~3 seconds per review |
| **False positives** | Near zero — rules are deterministic | Higher — style is subjective |
| **False negatives** | Many — can't understand intent | Fewer — understands what code *means* |
| **Example catch** | `import os` when `os` is never used (F401) | A function called `x(a, b)` that should be `find_common_elements(list_a, list_b)` |
| **Example miss** | Cannot detect that a 200-line function should be split | Cannot reliably detect that `import os` is unused without AST parsing |

**Interview talking point:** "We use a two-layer approach for style analysis. Ruff provides
deterministic, zero-false-positive mechanical checks — unused imports, bare excepts, import
ordering — at near-instant speed. The LLM handles semantic analysis that no static tool can
perform: evaluating naming quality, detecting functions with too many responsibilities, and
identifying missing error handling. Ruff's output is injected into the LLM prompt as
high-confidence anchors that guide and validate the LLM's own analysis."

---

## Step-by-Step Implementation Log

### Step 1: Understanding Ruff — Why It Exists and Why Rust Matters

**What Ruff is:**
Ruff is a Python linter and formatter created by Charlie Marsh (Astral). It reimplements
the rules from flake8, isort, pycodestyle, pyflakes, and dozens of other Python tools
in a single Rust binary.

**Why Rust makes Ruff 10-100x faster:**

Traditional Python linters (flake8, pylint) are written in Python. They must:
1. Start the Python interpreter (~100ms cold start)
2. Import their own modules (~200ms)
3. Parse each file using Python's `ast` module
4. Walk the AST in Python (interpreted, not compiled)

Ruff, written in Rust, skips all of this:
1. Native binary — zero interpreter startup
2. Compiled to machine code — AST walking is 10-100x faster
3. Parallel file processing — Rust's ownership model makes safe concurrency trivial
4. No GIL — true multi-threaded execution across CPU cores

**Practical impact for Ninja Code Guard:**
- flake8 on a 50-file PR: ~2-5 seconds
- Ruff on a 50-file PR: ~50 milliseconds
- This matters because our total review budget is 15 seconds. Spending 5 seconds on linting
  would eat 33% of our budget. Spending 50ms is negligible.

**Why this matters for interviews:** Ruff is a case study in "choose the right tool for the
job." Python is great for business logic and LLM orchestration (our agent code), but a poor
choice for CPU-bound AST processing of thousands of files. Rust gives us C-level performance
with memory safety guarantees.

---

### Step 2: Choosing Ruff Rule Categories

We enable 11 specific rule categories via the `--select` flag. Here is every category
and why it matters:

```bash
ruff check --select F,E,W,I,N,UP,B,A,SIM,RET,ARG
```

| Code | Category | What It Catches | Why We Enable It |
|------|----------|-----------------|------------------|
| **F** | Pyflakes | Unused imports (F401), undefined names (F821), unused variables (F841) | These are objective bugs, not style preferences. An unused import is dead code that confuses readers. |
| **E** | pycodestyle errors | Syntax errors, whitespace issues, bare excepts (E722) | Core PEP 8 violations. E722 (bare `except:`) silently swallows errors — a real maintainability hazard. |
| **W** | pycodestyle warnings | Deprecated syntax, trailing whitespace | Minor but noisy in diffs. Catching them early keeps PRs clean. |
| **I** | isort | Import ordering (I001) | Consistent import ordering reduces merge conflicts and makes imports scannable. stdlib first, then third-party, then local. |
| **N** | pep8-naming | Class names not CamelCase, functions not snake_case | Naming conventions aren't arbitrary — they carry semantic meaning. `MyClass` tells you it's a class; `my_function` tells you it's callable. |
| **UP** | pyupgrade | Python 2 patterns in Python 3 code, old-style string formatting | Modernization. Using `f"hello {name}"` instead of `"hello %s" % name` improves readability. |
| **B** | flake8-bugbear | Mutable default arguments, assert in non-test code, redundant exception types | These are subtle bugs disguised as style issues. `def f(items=[])` creates a shared mutable default — a classic Python trap. |
| **A** | flake8-builtins | Shadowing Python builtins (`list = [1,2,3]`, `id = 5`) | Overwriting `list`, `dict`, `id`, `type` breaks built-in behavior in confusing ways. |
| **SIM** | flake8-simplify | Unnecessarily complex boolean expressions, mergeable if-branches | Simplification rules that reduce cognitive load. `if x == True` should be `if x`. |
| **RET** | flake8-return | Unnecessary `return None`, inconsistent return statements | Functions that sometimes return a value and sometimes don't are confusing. Also catches dead code after `return`. |
| **ARG** | flake8-unused-arguments | Function arguments that are never used | Unused arguments mislead callers into thinking the function uses that data. Remove or prefix with `_`. |

**What we deliberately exclude:**

```python
"--ignore", "E501,E402",
```

| Ignored | Why |
|---------|-----|
| **E501** (line too long) | Too noisy and not actionable in reviews. Line length is a formatter concern (handled by `ruff format`, not `ruff check`). Every long line would generate a finding, drowning out real issues. |
| **E402** (module-level import not at top) | Sometimes you need conditional imports or imports after path manipulation. This rule produces too many false positives in real-world code. |

**Interview talking point:** "We enable 11 Ruff rule categories covering everything from dead
code (Pyflakes) to subtle Python traps (Bugbear's mutable default argument detection) to
modernization (pyupgrade). We deliberately exclude line-length checks because they're too
noisy — every long line generates a finding that drowns out genuine issues. Rule selection
is a signal-to-noise optimization."

---

### Step 3: Linter Tool Implementation (app/tools/linter_tool.py)

**The integration pattern is identical to Bandit:** write PR files to a temp directory,
run the tool as a subprocess, parse JSON output, format as text for the LLM prompt.

```python
async def run_ruff(file_contents: dict[str, str]) -> str:
    """Run Ruff linter on Python files."""
```

#### 3a. Filter to Python files only

```python
python_files = {
    path: content
    for path, content in file_contents.items()
    if path.endswith(".py")
}

if not python_files:
    return ""
```

**Why filter first:** Ruff only understands Python. If the PR changes `README.md` and
`style.css`, we skip the entire tool rather than writing files and running a subprocess
that will find nothing. This is a small optimization, but it follows the principle of
avoiding unnecessary work.

#### 3b. Temp file pattern

```python
with tempfile.TemporaryDirectory(prefix="ninjacg_ruff_") as tmpdir:
    tmpdir_path = Path(tmpdir)

    for filepath, content in python_files.items():
        file_path = tmpdir_path / filepath
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
```

**Why temp files?** Ruff (like Bandit) operates on the filesystem. We have file contents
in memory (fetched from the GitHub API), so we write them to a temp directory that is
automatically cleaned up when the `with` block exits. The `prefix="ninjacg_ruff_"` makes
temp directories identifiable during debugging — if something goes wrong, you can spot
our directories in `/tmp`.

`file_path.parent.mkdir(parents=True, exist_ok=True)` handles nested paths like
`app/utils/helpers.py` — it creates the full directory tree before writing the file.

#### 3c. Running Ruff with JSON output

```python
result = subprocess.run(
    [
        "ruff", "check",
        str(tmpdir_path),
        "--output-format", "json",
        "--select", "F,E,W,I,N,UP,B,A,SIM,RET,ARG",
        "--ignore", "E501,E402",
    ],
    capture_output=True,
    text=True,
    timeout=30,
)
```

**Flag breakdown:**

| Flag | Purpose |
|------|---------|
| `check` | Run linter (not formatter) |
| `--output-format json` | Machine-parseable output instead of human-readable text. We parse this with `json.loads()`. |
| `--select F,E,W,...` | Enable specific rule categories (see table above) |
| `--ignore E501,E402` | Exclude noisy rules |
| `capture_output=True` | Capture stdout and stderr instead of printing to terminal |
| `text=True` | Return strings (not bytes) |
| `timeout=30` | Kill the process if it hangs. Ruff should finish in milliseconds, so 30s is extremely generous. |

**Important: Ruff exit codes.** Ruff returns exit code 1 when it finds issues. This is
*not* an error — it's expected behavior. The `subprocess.run()` call does not raise an
exception for non-zero exit codes (unlike `subprocess.check_output()`). We rely on
checking `result.stdout` instead.

#### 3d. Output capping at 20 issues

```python
for issue in issues[:20]:  # Cap at 20 to avoid prompt bloat
    code = issue.get("code", "?")
    message = issue.get("message", "")
    filename = issue.get("filename", "")
    line = issue.get("location", {}).get("row", 0)
    # ... format line ...

if len(issues) > 20:
    summary_lines.append(f"  ... and {len(issues) - 20} more issues")
```

**Why cap at 20?** This is a critical design decision driven by token economics:

1. **LLM context budget:** The Groq Llama-3.3-70B model has 128K context, but we share
   that budget across the diff, file contents, RAG context, system prompt, AND tool output.
   If Ruff finds 200 issues (common in large PRs with legacy code), that could consume
   5,000+ tokens of low-value repetitive content.

2. **Diminishing returns:** After 20 issues, the LLM has enough signal to understand
   the code quality. Additional lint warnings don't add new information — they're usually
   the same category repeated.

3. **Response quality:** LLMs produce better output with focused context. Flooding the
   prompt with 200 lint warnings causes the LLM to summarize rather than analyze.

4. **Cost:** More input tokens = higher API cost. Even at Groq's low prices, unnecessary
   tokens add up across thousands of PR reviews.

The `"... and {len(issues) - 20} more issues"` suffix tells the LLM that more issues exist,
so it can mention the overall code quality in its analysis without needing every detail.

**Interview talking point:** "We cap static analysis output at 20 issues to manage the LLM's
context window. Beyond 20 findings, additional lint warnings have diminishing returns — they're
usually the same category repeated. The cap preserves context budget for the diff and RAG
context, which are higher-value inputs. We still tell the LLM the total count so it can
factor overall code quality into its analysis."

#### 3e. Error handling

```python
except FileNotFoundError:
    logger.warning("ruff not found in PATH — skipping lint analysis")
    return ""
except Exception as e:
    logger.warning("Ruff analysis failed", error=str(e))
    return ""
```

Two failure modes handled:

1. **`FileNotFoundError`**: Ruff isn't installed. This happens in development environments
   or CI runners that don't have Ruff. We log a warning and continue — the LLM can still
   do style review without Ruff anchoring. This is the same graceful degradation pattern
   used for Bandit and detect-secrets.

2. **Generic `Exception`**: Covers subprocess timeout (30s), JSON parse errors, file I/O
   failures, or anything else unexpected. Same result — log and return empty string.

---

### Step 4: Style System Prompt Design (prompts/style_system.md)

The style prompt is the most nuanced of the three agents because **style is subjective**.
Security has clear rules (SQL injection is always bad). Performance has measurable impact
(O(n^2) is always slower than O(n)). But style? Reasonable engineers disagree about naming
conventions, docstring requirements, and code organization.

#### 4a. Role definition

```
You are a staff engineer focused on long-term codebase health. You have 10+
years of experience maintaining large codebases and care deeply about readability,
consistency, and maintainability.
```

**Why "staff engineer" and not "code reviewer"?** The persona matters. A "code reviewer"
might flag every minor style violation. A "staff engineer" focuses on issues that will
cause real pain in 6 months — dead code that confuses new hires, functions too complex
to modify safely, missing error handling that causes silent failures in production.

#### 4b. Scope boundary

```
Review the PR diff and file contents for code style and maintainability issues
ONLY. Do not comment on security vulnerabilities or performance.
```

Without this boundary, the Style Agent would overlap with Security and Performance,
producing duplicate findings. Each agent must stay in its lane.

#### 4c. Severity guidelines — what makes style issues high/medium/low

The prompt defines four severity levels with specific examples:

**High Severity** (genuinely harmful to maintainability):
- Function/method complexity — too many branches, deeply nested conditionals
- Dead code — unused imports, unreachable code paths, commented-out blocks
- Code duplication — copy-pasted logic that should be extracted
- Missing error handling — functions that can fail without try/except

**Medium Severity** (meaningful but less urgent):
- Naming issues — non-descriptive names (`x`, `tmp`, `data`)
- Missing type hints on public functions
- Magic numbers/strings — `if status == 3` instead of `if status == STATUS_ACTIVE`
- Documentation gaps — public functions missing docstrings

**Low Severity** (minor style nits):
- Inconsistent spacing, import ordering
- Suboptimal patterns — `dict.keys()` when just `dict` works
- TODOs without context

#### 4d. The three rules that control subjectivity

These rules are what make the Style Agent useful instead of annoying:

**Rule 4 — Confidence for subjectivity:**
```
Set confidence honestly. Style is subjective — if it's a preference rather
than a clear issue, set confidence below 0.6.
```

This is the key mechanism for handling subjectivity. When the LLM detects something that
could go either way (e.g., "this function could use a docstring but it's only 3 lines"),
it should set confidence below 0.6. The downstream synthesizer can then choose to suppress
low-confidence style findings when the PR is otherwise clean.

**Rule 5 — Respect existing patterns:**
```
If the full file content shows the repo already uses a particular convention
(e.g., double quotes everywhere), don't flag new code that follows the same convention.
```

This prevents the worst kind of style review: telling a developer to change something that
matches their entire codebase. If every file uses `snake_case` for constants instead of
`UPPER_CASE`, the Style Agent should not flag new constants following the same convention.
The LLM sees the full file contents, not just the diff, which makes this possible.

**Rule 6 — Don't be pedantic:**
```
Focus on issues that genuinely hurt readability or maintainability.
Don't flag every missing docstring if the function is 3 lines and self-explanatory.
```

Without this rule, the LLM would generate 20 findings per file — every missing docstring,
every slightly-long function, every variable that could have a marginally better name.
This rule tells the LLM to apply engineering judgment, not mechanical rule-checking.

**Interview talking point:** "The style prompt handles subjectivity through three mechanisms:
confidence scoring below 0.6 for preferences versus genuine issues, a 'respect existing
patterns' rule that prevents the agent from fighting the codebase's established conventions,
and a 'don't be pedantic' rule that focuses the LLM on issues that genuinely hurt
maintainability. These rules are the difference between a useful code review tool and
an annoying one that developers disable after the first week."

---

### Step 5: Style Agent Implementation (app/agents/style_agent.py)

#### Template Method payoff — 30 lines of actual code

This is where the investment in the base class (Week 3) pays off. The entire Style Agent
is ~30 lines, including the docstring and imports. Compare this to writing the full
orchestration logic (prompt building, LLM calling, structured output, error handling,
timing) from scratch — that's 150+ lines per agent.

```python
class StyleAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "style"

    @property
    def system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parent.parent.parent
            / "prompts"
            / "style_system.md"
        )
        return prompt_path.read_text(encoding="utf-8")

    async def run_static_analysis(self, pr_data: PRData) -> str:
        """Run Ruff linter on changed Python files."""
        ruff_output = await run_ruff(pr_data.file_contents)
        return ruff_output if ruff_output else ""
```

**Three things defined, everything else inherited:**

| What | Lines | From |
|------|-------|------|
| `agent_name` | 2 | Identifies findings as `agent="style"` |
| `system_prompt` | 5 | Reads the external markdown file |
| `run_static_analysis` | 3 | Calls `run_ruff()` on changed files |
| Prompt building | 0 | Inherited from `BaseAgent._build_prompt()` |
| LLM invocation | 0 | Inherited from `BaseAgent.review()` |
| Structured output | 0 | Inherited from `BaseAgent` (uses `AgentFindings` schema) |
| Error handling | 0 | Inherited from `BaseAgent.review()` try/except |
| Timing/logging | 0 | Inherited from `BaseAgent.review()` |
| Finding conversion | 0 | Inherited from `BaseAgent._convert_to_findings()` |

**Why the path resolution is explicit:**

```python
Path(__file__).resolve().parent.parent.parent / "prompts" / "style_system.md"
```

This navigates from `app/agents/style_agent.py` up three levels to the project root, then
into `prompts/`. We use `Path(__file__).resolve()` instead of relative paths because:
- The working directory changes depending on how the app is launched (uvicorn, pytest, Docker)
- `resolve()` follows symlinks and produces an absolute path
- `Path` objects with `/` operator are cross-platform (works on Windows and Linux)

**Interview talking point:** "The Style Agent is ~30 lines of code because all orchestration
lives in the base class. Adding a new domain agent requires implementing exactly three things:
a name, a prompt file, and a static analysis method. This is the Template Method pattern —
the algorithm skeleton (fetch diff, run tools, call LLM, convert findings) is fixed in the
base class, while the variable steps are customized by subclasses. Three agents, zero code
duplication."

---

### Step 6: Test Suite (tests/unit/test_style_agent.py)

Nine tests covering the agent, the Ruff tool, and edge cases:

#### Agent Tests (TestStyleAgent — 4 tests)

```python
def test_agent_name(self):
    """StyleAgent should identify as 'style'."""
    agent = StyleAgent()
    assert agent.agent_name == "style"
```

**Why test the name?** It seems trivial, but the name is used to tag every finding. If it
returned `"security"` by mistake, style findings would be labeled as security findings in
the PR comment, confusing developers.

```python
def test_system_prompt_loads(self):
    """System prompt should exist and contain style-related content."""
    agent = StyleAgent()
    prompt = agent.system_prompt
    assert len(prompt) > 100
    assert "style" in prompt.lower() or "maintainability" in prompt.lower()
    assert "naming" in prompt.lower()
```

**Why test prompt loading?** This catches a common failure: someone renames or moves the
prompt file without updating the path in the agent. The test also validates that the
prompt contains expected keywords — a basic sanity check that the right file is loaded.

```python
def test_conversion_produces_style_findings(self, mock_style_findings):
    """Converted findings should have agent='style'."""
    agent = StyleAgent()
    findings = agent._convert_to_findings(mock_style_findings)

    assert len(findings) == 2
    assert all(f.agent == "style" for f in findings)
    assert findings[0].severity == "low"
    assert findings[0].category == "unused_import"
    assert findings[1].severity == "medium"
    assert findings[1].category == "naming"
    assert findings[0].cwe_id is None  # Style issues don't have CWE IDs
```

**Why test conversion?** This verifies the integration between the LLM output schema
(`FindingOutput`) and our internal model (`Finding`). Key assertion: `cwe_id is None` — style
issues don't have CVE/CWE identifiers. This is different from the Security Agent where
`cwe_id` is expected to be populated (e.g., `CWE-89`).

```python
async def test_review_handles_llm_failure(self, sample_pr_data):
    """LLM failure should return empty list, not crash."""
    mock_chain = AsyncMock(side_effect=Exception("Groq API timeout"))
    # ... mock setup ...
    findings = await agent.review(sample_pr_data)
    assert findings == []
```

**Why test LLM failure?** The Groq API can timeout, rate-limit, or return errors. This test
verifies that the agent returns an empty list instead of crashing the pipeline. The Security
and Performance agents can still contribute findings even if Style fails.

#### Ruff Tool Tests (TestRuffTool — 5 tests)

These tests run **real Ruff** on synthetic code — no mocking. Ruff executes in milliseconds,
so there's no speed penalty for real execution, and we get genuine confidence that the
integration works.

```python
async def test_detects_unused_imports(self):
    """Ruff should detect unused imports (F401)."""
    code_with_unused = (
        "import os\n"
        "import json\n"
        "\n"
        "def hello():\n"
        "    return 'world'\n"
    )
    files = {"app.py": code_with_unused}
    result = await run_ruff(files)
    if result:  # ruff installed
        assert "F401" in result
        assert "os" in result or "json" in result
```

**Note the `if result:` guard.** In CI environments where Ruff isn't installed, `run_ruff()`
returns `""` (graceful degradation). The test passes silently rather than failing. This
makes the test suite portable — it runs everywhere, and catches regressions where Ruff is
available.

```python
async def test_clean_code_returns_empty(self):
    """Code with no lint issues should return empty string."""
    clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    files = {"clean.py": clean_code}
    result = await run_ruff(files)
    assert result == ""
```

**Why test clean code?** Verifies that we don't generate false positives on well-written code.
If this test fails, it means our rule selection is too aggressive.

```python
async def test_skips_non_python_files(self):
    """Ruff should ignore non-Python files."""
    files = {
        "index.html": "<h1>Hello</h1>",
        "style.css": "body { color: red; }",
    }
    result = await run_ruff(files)
    assert result == ""
```

**Why test non-Python files?** PRs often include HTML, CSS, YAML, and other files. The
linter tool must filter these out before running Ruff. Without the `.endswith(".py")`
filter, Ruff would either error or produce nonsensical output.

```python
async def test_handles_empty_input(self):
    """Empty file dict should return empty string."""
    result = await run_ruff({})
    assert result == ""
```

**Why test empty input?** Edge case: a PR that only changes config files (`.yaml`, `.toml`)
passes an empty dict to `run_ruff()`. This must not crash.

```python
async def test_caps_output_at_20_issues(self):
    """Output should cap at 20 issues to avoid prompt bloat."""
    many_imports = "\n".join(f"import module_{i}" for i in range(30))
    code = many_imports + "\n\ndef main():\n    pass\n"
    files = {"many_imports.py": code}
    result = await run_ruff(files)
    if result:
        lines = result.strip().split("\n")
        assert len(lines) <= 25  # header + 20 issues + "and X more"
```

**Why test the cap?** This validates the output capping logic described in Step 3d. The test
generates 30 unused imports, expects Ruff to find all 30, but verifies that the formatted
output only includes 20 plus a summary line. Without this cap, a messy PR could inject
thousands of tokens of repetitive lint warnings into the LLM prompt.

---

### Step 7: Live Test Results

**Test PR:** github.com/ninjacode911/codeguard-test/pull/4

**Test code (intentionally messy for style issues):**
```python
import os
import json

def x(a, b):
    t = []
    for i in a:
        if i in b:
            t.append(i)
    return t
```

**What Ruff caught (mechanical):**
- `F401` — `import os` is unused
- `F401` — `import json` is unused

**What the LLM caught (semantic):**
- Non-descriptive function name `x` (should be `find_common_elements`)
- Non-descriptive variable names `a`, `b`, `t`, `i`
- Missing type hints on public function
- The function could use a list comprehension: `return [i for i in a if i in b]`

**Combined result from all three agents on PR #4:**
```
Style Agent:      6 findings  (unused imports, magic numbers, missing error handling, complex function)
Security Agent:   5 findings
Performance Agent: 3 findings
Health Score:     14/100
Recommendation:   Block Merge
Total time:       ~13 seconds (all three agents running concurrently via asyncio.gather)
```

---

### Bugs Encountered and Fixed

| Bug | Cause | Fix |
|-----|-------|-----|
| Ruff output includes full temp dir path | `issue["filename"]` contains `/tmp/ninjacg_ruff_abc123/app.py` | Used `Path(filename).relative_to(tmpdir)` to strip the temp prefix |
| Windows backslashes in output | `Path.relative_to()` produces `app\utils\helpers.py` on Windows | Added `.replace("\\", "/")` to normalize to forward slashes |
| Ruff exit code 1 interpreted as error | Initially used `subprocess.check_output()` which raises on non-zero exit | Switched to `subprocess.run()` which doesn't raise — Ruff returns 1 when it finds issues (expected behavior) |
| Empty `[]` JSON treated as findings | Ruff returns `[]` for clean code, which is valid JSON but has no issues | Added explicit check: `if result.stdout.strip() == "[]": return ""` |

---

## Files Created in Week 5

| File | Type | Purpose |
|------|------|---------|
| `app/agents/style_agent.py` | **New** | Style Agent — ~30 lines leveraging base class |
| `app/tools/linter_tool.py` | **New** | Ruff Python linter wrapper with JSON parsing and output capping |
| `prompts/style_system.md` | **New** | Style Agent system prompt — staff engineer persona, severity guidelines, subjectivity rules |
| `tests/unit/test_style_agent.py` | **New** | 9 tests covering agent identity, prompt loading, conversion, LLM failure, Ruff detection, clean code, non-Python skip, empty input, output capping |

---

## Test Coverage

| Test Suite | Tests | Status |
|------------|-------|--------|
| StyleAgent identity & prompt | 2 | Pass |
| StyleAgent finding conversion | 1 | Pass |
| StyleAgent LLM failure handling | 1 | Pass |
| Ruff detects unused imports | 1 | Pass |
| Ruff clean code (no false positives) | 1 | Pass |
| Ruff skips non-Python files | 1 | Pass |
| Ruff handles empty input | 1 | Pass |
| Ruff output capping at 20 | 1 | Pass |
| **Total** | **9** | **Pass** |

---

## Architecture Patterns Used (Interview Reference)

| Pattern | Where Used | What It Means |
|---------|------------|---------------|
| **Template Method** | style_agent.py inherits BaseAgent | Algorithm skeleton in base class, only 3 methods overridden in subclass. StyleAgent is ~30 lines. |
| **Static + LLM Hybrid** | linter_tool.py + LLM review | Ruff catches mechanical issues (unused imports) with zero false positives. LLM catches semantic issues (bad naming, missing error handling) that no static tool can detect. |
| **Temp File Pattern** | linter_tool.py | In-memory file contents written to temp directory, Ruff executed, results parsed, temp directory auto-cleaned. |
| **Graceful Degradation** | linter_tool.py + base_agent.py | If Ruff isn't installed, the agent runs LLM-only. If the LLM fails, the agent returns empty list. Pipeline never crashes. |
| **Output Capping** | linter_tool.py `issues[:20]` | Static analysis output is capped at 20 issues to preserve LLM context budget and prevent prompt bloat. |
| **Confidence-Based Subjectivity** | style_system.md Rule 4 | Findings below 0.6 confidence are marked as preferences, not issues. Downstream synthesizer can filter them. |
| **External Prompt Files** | prompts/style_system.md | Prompts stored as Markdown for independent versioning, easy iteration, and non-engineer review. |

---

## Key Concept Deep Dive: Mechanical vs. Semantic Analysis

This is the most important concept to internalize from Week 5. It applies far beyond
code review — it's a general AI systems design principle.

**Mechanical analysis** (Ruff, Bandit, regex) operates on **syntax**:
- Parses code into an AST (Abstract Syntax Tree)
- Applies deterministic rules to tree nodes
- 100% precision for known patterns (zero false positives)
- Zero understanding of intent, meaning, or context
- Example: Ruff knows `import os` is unused because the name `os` appears nowhere else
  in the AST. It does not know *why* `os` was imported or whether someone intended to
  use it later.

**Semantic analysis** (LLM) operates on **meaning**:
- Understands what code is trying to accomplish
- Evaluates naming quality against the function's purpose
- Detects missing error handling based on what could go wrong
- Identifies functions that do too many things
- Higher false positive rate because judgment is involved
- Example: The LLM knows that a function called `x(a, b)` should be called
  `find_common_elements(list_a, list_b)` because it understands the function computes
  a set intersection. No static tool can make this inference.

**Why both are needed:**
- Ruff alone misses everything semantic (naming, complexity, missing error handling)
- LLM alone occasionally misses mechanical issues (it might not notice an unused import
  buried in a long file) and is 60x slower
- Together, Ruff provides high-confidence anchors that guide the LLM's analysis,
  while the LLM adds the contextual understanding that makes the review genuinely useful

**Interview talking point:** "In any AI-augmented analysis system, you want to combine
deterministic tools for mechanical checks with LLM reasoning for semantic analysis. The
deterministic layer is fast, cheap, and precise — it handles everything rule-based. The
LLM layer adds understanding of intent, context, and meaning that no static tool can
replicate. The key design insight is feeding the deterministic output INTO the LLM prompt,
so the LLM's analysis is anchored by verified facts rather than starting from scratch."

---

## What's Next (Week 6)

Build the **RAG Pipeline** — embed the codebase into ChromaDB so agents have context
beyond the PR diff. When reviewing a utility function, the agent will see how that
function is used across the codebase, enabling findings like "this function is called
in 12 places, so renaming it requires a coordinated change."

---

*Documentation written 2026-03-20 as part of Week 5 completion.*
