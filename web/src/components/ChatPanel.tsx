import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowUp, Bot, CircleAlert, LoaderCircle, RotateCw, ShieldCheck } from 'lucide-react'

const MAX_MESSAGES = 12

type ChatRole = 'user' | 'assistant'

interface ChatMessage {
  role: ChatRole
  content: string
  sources?: string[]
}

interface ChatReply {
  reply?: unknown
  sources?: unknown
  detail?: unknown
}

interface ChatPanelProps {
  selectedPlayerId: number | null
  selectedPlayerName: string | null
}

function readableChatError(error: unknown): string {
  if (
    error instanceof TypeError &&
    /failed to fetch|networkerror/i.test(error.message)
  ) {
    return (
      'Cannot reach the local chat API at /api/chat. Start FastAPI on ' +
      '127.0.0.1:3001 and ensure Vite can reach it. If Vite runs in a ' +
      'Dev Container, 127.0.0.1 refers to the container, not Windows.'
    )
  }
  return error instanceof Error
    ? error.message
    : 'The local chat service could not complete the request.'
}

function responseError(payload: ChatReply, status: number): string {
  if (typeof payload.detail === 'string') return payload.detail
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail
      .map((item) =>
        typeof item === 'object' &&
        item !== null &&
        'msg' in item &&
        typeof item.msg === 'string'
          ? item.msg
          : null,
      )
      .filter((message): message is string => message !== null)
    if (messages.length > 0) return messages.join(' ')
  }
  return `The local chat service returned HTTP ${status}.`
}

function ChatPanel({
  selectedPlayerId,
  selectedPlayerName,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [retryMessages, setRetryMessages] = useState<ChatMessage[] | null>(null)
  const [isSending, setIsSending] = useState(false)
  const pendingRequest = useRef(false)
  const conversationRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    conversationRef.current?.scrollTo?.({
      top: conversationRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isSending, error])

  async function requestReply(history: ChatMessage[]) {
    if (pendingRequest.current) return
    pendingRequest.current = true
    setIsSending(true)
    setError(null)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: history.slice(-MAX_MESSAGES).map(({ role, content }) => ({
            role,
            content,
          })),
          context: selectedPlayerId
            ? { selected_player_id: selectedPlayerId }
            : null,
        }),
      })

      let payload: ChatReply
      try {
        payload = (await response.json()) as ChatReply
      } catch {
        throw new Error(
          `The chat API at /api/chat returned an unreadable response (HTTP ${response.status}). ` +
            'Check that FastAPI is running and that Vite can reach its proxy target.',
        )
      }

      if (!response.ok) {
        throw new Error(responseError(payload, response.status))
      }
      if (typeof payload.reply !== 'string' || !payload.reply.trim()) {
        throw new Error('The local model returned an empty reply. Try again.')
      }

      const sources = Array.isArray(payload.sources)
        ? payload.sources.filter(
            (source): source is string => typeof source === 'string',
          )
        : []
      const reply: ChatMessage = {
        role: 'assistant',
        content: payload.reply,
        ...(sources.length > 0 ? { sources } : {}),
      }
      setMessages([...history, reply].slice(-MAX_MESSAGES))
      setRetryMessages(null)
    } catch (caught: unknown) {
      setError(readableChatError(caught))
      setRetryMessages(history)
    } finally {
      pendingRequest.current = false
      setIsSending(false)
    }
  }

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || pendingRequest.current) return

    const nextHistory = [
      ...messages,
      { role: 'user' as const, content },
    ].slice(-MAX_MESSAGES)
    setMessages(nextHistory)
    setDraft('')
    setRetryMessages(null)
    void requestReply(nextHistory)
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  const isSendDisabled = isSending || draft.trim().length === 0

  return (
    <section className="chat-panel" aria-label="Rally Atlas chat">
      <header className="chat-header">
        <div className="chat-title">
          <div className="chat-mark"><Bot size={20} /></div>
          <div>
            <p className="eyebrow">LOCAL QWEN ASSISTANT</p>
            <h1>Ask Rally Atlas</h1>
          </div>
        </div>
        <div className="chat-local-status">
          <span className="local-dot" />
          LOCAL ONLY
        </div>
      </header>

      {selectedPlayerId !== null && (
        <div className="chat-context-banner">
          <span className="chat-context-icon"><ShieldCheck size={15} /></span>
          <span>
            Player context
            <strong>
              {selectedPlayerName ?? `Player ${selectedPlayerId}`}
              <small> · ID {selectedPlayerId}</small>
            </strong>
          </span>
          <span className="chat-context-hint">Switch to another profile to change context</span>
        </div>
      )}

      <div className="chat-conversation" ref={conversationRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <span className="welcome-spark"><Bot size={20} /></span>
            <p className="eyebrow">GROUNDED IN YOUR LOCAL DATA</p>
            <h2>What would you like to know?</h2>
            <p>
              Ask about a player’s season history, team standings, or a
              comparison. I’ll use the local JSON exports and cite the source.
            </p>
            <div className="suggested-questions">
              <span>Try asking</span>
              <button
                onClick={() => setDraft('Summarize this player’s history across groups.')}
                type="button"
              >
                Summarize this player’s history
              </button>
              <button
                onClick={() => setDraft('How has ABC 3 performed in the latest season?')}
                type="button"
              >
                How is ABC 3 doing?
              </button>
            </div>
          </div>
        ) : (
          <div className="chat-message-list">
            {messages.map((message, index) => (
              <article
                className={`chat-message chat-message-${message.role}`}
                key={`${index}-${message.role}`}
              >
                {message.role === 'assistant' && (
                  <span className="message-avatar"><Bot size={15} /></span>
                )}
                <div className="message-body">
                  <div className="message-label">
                    {message.role === 'user' ? 'YOU' : 'RALLY ATLAS'}
                  </div>
                  <p className="message-text">{message.content}</p>
                  {message.sources && message.sources.length > 0 && (
                    <div className="message-sources">
                      <span>Sources</span>
                      {message.sources.map((source) => (
                        <code key={source}>{source}</code>
                      ))}
                    </div>
                  )}
                </div>
              </article>
            ))}
            {isSending && (
              <div className="chat-pending" role="status">
                <LoaderCircle className="pending-spinner" size={16} />
                <span>Qwen is checking the local records…</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="chat-compose-area">
        {error && (
          <div className="chat-error" role="alert">
            <CircleAlert size={16} />
            <p>{error}</p>
            {retryMessages && (
              <button
                className="retry-button"
                disabled={isSending}
                onClick={() => void requestReply(retryMessages)}
                type="button"
              >
                <RotateCw size={13} />
                Retry
              </button>
            )}
          </div>
        )}
        <form className="chat-composer" onSubmit={submitMessage}>
          <label className="visually-hidden" htmlFor="rally-chat-input">
            Message Rally Atlas
          </label>
          <textarea
            id="rally-chat-input"
            maxLength={4_000}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Ask a question about a player, team, or season…"
            ref={inputRef}
            rows={2}
            value={draft}
          />
          <div className="chat-composer-footer">
            <span className="chat-composer-note">
              Enter to send <i>·</i> Shift+Enter for a new line <i>·</i>{' '}
              {draft.length.toLocaleString()}/4,000
            </span>
            <button
              className="chat-send-button"
              disabled={isSendDisabled}
              type="submit"
            >
              Send
              <ArrowUp size={15} />
            </button>
          </div>
        </form>
        <p className="chat-privacy-note">
          Questions and replies stay in this browser session. Only retrieved
          facts are sent to the local Ollama model.
        </p>
      </div>
    </section>
  )
}

export default ChatPanel
