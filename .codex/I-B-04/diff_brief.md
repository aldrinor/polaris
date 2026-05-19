HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; minor → P2/P3.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1 findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-B-04 / GH#623: clean Docker build (#494)

**DO NOT explore the repository. Review ONLY the diff embedded below.** The
brief was Codex-APPROVED iter 1 (`.codex/I-B-04/brief.md`, 0 P0/0 P1). This
reviews the diff against that brief.

## Empirical verification (already done)

`docker build -f Dockerfile.v6` of this exact tree, on the OVH box →
**`BUILD_EXIT=0`** — all 13 stages, including `pip install -r requirements.lock`
(the #494 resolver-runaway concern) and `COPY scripts/v6_entrypoint.sh`.

## requirements.lock (not embedded — 284-pkg generated file)

`uv pip compile` on the box, `--python-version 3.11`, input = the v6-stripped
set (requirements.txt minus google-generativeai/protobuf< + requirements-v6.txt).
Key pins verified: `bcrypt==4.0.1`, `pydantic-settings==2.14.1`,
`langchain==0.3.30`, `langchain-core==0.3.86`, `protobuf==6.33.6`,
`passlib==1.7.4`, `fastapi==0.136.1`, `dramatiq==2.1.0`; `google-generativeai`
absent (correctly excluded). It is a generated lockfile — spot-check the pins,
do not line-audit all 1058 lines.

## THE DIFF (6 substantive files; requirements.lock excluded as generated)

```diff
diff --git a/.gitattributes b/.gitattributes
new file mode 100644
+# Enforce LF on shell scripts + Dockerfiles. CRLF on these breaks the
+# container ENTRYPOINT ... I-B-04 / #494.
+*.sh text eol=lf
+Dockerfile* text eol=lf

diff --git a/Dockerfile.v6 b/Dockerfile.v6
@@ pip step @@
-COPY requirements.txt requirements-v6.txt ./
-RUN sed -e '/^google-generativeai/d' \
-        -e '/^protobuf</d' \
-        requirements.txt > /tmp/requirements-v6-pipeline-a.txt && \
-    pip install --no-cache-dir -r /tmp/requirements-v6-pipeline-a.txt -r requirements-v6.txt
+COPY requirements.txt requirements-v6.txt requirements.lock ./
+# I-B-04 / #494: install from the deterministic uv-compiled lockfile ...
+RUN pip install --no-cache-dir -r requirements.lock

diff --git a/docker-compose.v6.yml b/docker-compose.v6.yml
@@ worker service @@
     command: worker
+    # I-B-04 / #494: the worker is a Dramatiq consumer with no HTTP server ...
+    healthcheck:
+      test: ["CMD-SHELL", "python -c \"import socket; socket.create_connection(('redis', 6379), 3)\" || exit 1"]
+      interval: 30s
+      timeout: 5s
+      retries: 3
+      start_period: 15s
     env_file:

diff --git a/requirements-v6.txt b/requirements-v6.txt
-pydantic-settings==2.6.1
+# I-B-04 / #494: langchain-community needs pydantic-settings>=2.10.
+pydantic-settings>=2.10.1,<3.0.0
@@ auth @@
 passlib[bcrypt]==1.7.4
+# I-B-04 / #494: passlib 1.7.4 breaks on bcrypt 5.x. Pin to the 4.x line.
+bcrypt==4.0.1

diff --git a/requirements.txt b/requirements.txt
-langchain>=0.3.0
-langgraph>=0.2.0
-langchain-openai>=0.2.0
-langchain-google-genai>=2.0.0  # Gemini integration
-langchain-community>=0.3.0
-langchain-core>=0.3.0
+langchain>=0.3.0,<0.4.0
+langgraph>=0.2.0,<0.3.0
+langchain-openai>=0.2.0,<0.3.0
+langchain-google-genai>=2.0.0,<3.0.0  # Gemini integration
+langchain-community>=0.3.0,<0.4.0
+langchain-core>=0.3.0,<0.4.0

diff --git a/web/Dockerfile b/web/Dockerfile
 ENV NODE_ENV=production
 ENV PORT=3000
+# I-B-04 / #494: Next.js standalone server.js binds to $HOSTNAME ...
+ENV HOSTNAME=0.0.0.0
@@ healthcheck @@
-    CMD wget --spider -q http://localhost:3000/ || exit 1
+    CMD wget --spider -q http://127.0.0.1:3000/ || exit 1
```

## Review focus
1. Does the diff correctly implement the APPROVED brief (F1-F8)?
2. The lockfile-only install (F4) — any correctness risk (e.g. requirements.txt
   / requirements-v6.txt edits drifting from the lock)?
3. The worker healthcheck (F6) — sound? `python` on PATH in the image? ✓ (the
   image is python:3.11-slim).
4. web/Dockerfile (F5) — `ENV HOSTNAME=0.0.0.0` + 127.0.0.1 — correct for Next.js standalone?
5. Anything missed or wrong.

## Output schema — return EXACTLY this
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
