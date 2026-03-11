# SDK Session Management

## Core Principle

The Claude Agent SDK manages conversation context internally. **Never load messages into prompts manually.** Use `resume` and `fork_session` to give the agent context.

## Permissions & Interactive Tools

Nerve uses a `can_use_tool` callback instead of `bypassPermissions`. This enables mid-turn pausing for interactive tools while auto-approving everything else:

```python
options = ClaudeAgentOptions(
    can_use_tool=handler.can_use_tool,  # replaces permission_mode
)
```

The SDK sets `--permission-prompt-tool stdio` automatically, routing all tool permission requests through the control protocol. The `InteractiveToolHandler` (in `nerve/agent/interactive.py`) handles each request:

- **Non-interactive tools** (Read, Bash, MCP, etc.) → `PermissionResultAllow()` immediately
- **`AskUserQuestion`** → Broadcasts question to UI via WebSocket `interaction` event, awaits user answer, returns `PermissionResultAllow(updated_input={...answers})` — the SDK injects answers into the tool's `answers` field
- **`ExitPlanMode` / `EnterPlanMode`** → Broadcasts approval request, awaits user decision, returns allow or deny

Handlers are registered per-session in a global registry (`interactive._handlers`). The WebSocket server routes `answer_interaction` messages to the correct handler by session ID.

## How It Works

Each conversation session gets an `sdk_session_id` — a unique identifier the SDK uses to store and restore full conversation state (messages, tool calls, thinking blocks, everything).

### Resume (Continue a Session)

When you want to continue an existing conversation:

```python
options = ClaudeAgentOptions(
    resume=session.sdk_session_id,  # SDK restores full context
    fork_session=False,
)
```

The SDK restores the entire conversation history. No manual message loading needed.

**Nerve's implementation:** `engine._get_or_create_client()` checks the session's `sdk_session_id` column and passes it as `resume` to the SDK options. See `engine.py:330-403`.

### Fork (Branch a Conversation)

When you want a new session that starts with the parent's full context:

```python
options = ClaudeAgentOptions(
    resume=parent.sdk_session_id,   # Branch FROM this point
    fork_session=True,              # Create independent branch
)
```

The fork inherits all parent context but diverges from that point. New messages don't affect the parent.

**Nerve's implementation:** `engine.run()` detects `parent_session_id` on first message (status=CREATED) and sets `fork_from`. See `engine.py:556-567`.

## Session ID Lifecycle

```
New session → first message → ResultMessage.session_id → stored in DB
     ↓
Subsequent messages → resume=stored_id → SDK continues
     ↓
Stop/Idle → sdk_session_id preserved → can resume later
     ↓
Error → sdk_session_id cleared → must start fresh
     ↓
Fork → parent's sdk_session_id used once → fork gets own new ID
```

## When to Use What

| Scenario | Approach |
|----------|----------|
| Continue user conversation | `resume` (automatic in `_get_or_create_client`) |
| Cron job (no context needed) | New isolated session |
| Webhook handler | New isolated session |

## Anti-Patterns

**NEVER do this:**
```python
# BAD: loading messages manually into the prompt
messages = await db.get_messages(session_id, limit=20)
prompt = "Recent context:\n" + "\n".join(msg["content"] for msg in messages)
```

This loses tool call history, thinking blocks, system prompt context, and the SDK's internal state management.

**Do this instead:**
```python
# GOOD: fork from the session with context
fork = await engine.fork_session(source_session_id, source="cron")
await engine.run(session_id=fork["id"], user_message=prompt)
# SDK handles all context through the fork
```

## Database Columns

The `sessions` table has these SDK-related columns:

- `sdk_session_id` — The SDK's internal session identifier (set after first message)
- `parent_session_id` — For forks, points to the source session
- `forked_from_message` — Optional: specific message to branch from
- `connected_at` — When the SDK client connected (used for memorization watermark)
