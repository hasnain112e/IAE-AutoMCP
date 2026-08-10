// Edited by Dr. Wasim
import React, { useEffect, useMemo, useRef, useState } from 'react';
import './ChatPanel.css';

interface Message {
  role: 'user' | 'bot';
  content: string;
  timestamp: string;
}

interface ChatPanelProps {
  tools: any[];
}

const QUICK_ACTIONS = [
  'Show me all GET requests available',
  'List all available API endpoints',
  'What parameters does the POST endpoint accept?',
  'Display the first 10 posts',
  'Show me examples of how to use the DELETE endpoint',
];

const ChatPanel: React.FC<ChatPanelProps> = ({ tools = [] }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState<boolean>(true);
  const [expandedMessages, setExpandedMessages] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Chat backend lives on the collector service (port 8000)
  const backendChatUrl = useMemo(() => `/api/chat`, []);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const addMessage = (role: 'user' | 'bot', content: string) => {
    setMessages((prev) => [
      ...prev,
      {
        role,
        content,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  };

  const callChatApi = async (prompt: string) => {
    const payload = {
      message: prompt,
      // Send full tool schema to avoid truncation/missing fields
      tools: tools || [],
    };

    const res = await fetch(backendChatUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error('Chat service unavailable. Please contact admin.');
    }
    return res.json();
  };

  const handleSendMessage = async (promptText?: string) => {
    const messageText = (promptText ?? input).trim();
    if (!messageText || isLoading) return;

    addMessage('user', messageText);
    if (!promptText) setInput('');
    setIsLoading(true);

    try {
      const wantsAll = (() => {
        const lowered = messageText.toLowerCase();
        const wantsList = lowered.includes('list') || lowered.includes('show') || lowered.includes('all');
        const targetsTools = lowered.includes('endpoint') || lowered.includes('endpoints') || lowered.includes('tools') || lowered.includes('apis');
        return wantsList && targetsTools && !lowered.includes('first') && !lowered.includes('top');
      })();

      if (wantsAll) {
        const lines = (tools || []).map((t: any) => {
          const name = t?.name || '<unnamed>';
          const method = (t?.method || '').toUpperCase();
          const path = t?.path || '';
          const meta = t?.metadata || {};
          let signature = 'N/A';
          if (method && path) {
            signature = `${method} ${path}`;
          } else if (meta?.sdk_module && meta?.sdk_function) {
            signature = `${meta.sdk_module}.${meta.sdk_function}`;
          }
          return `- ${name} (${signature})`;
        });
        const reply = `Available tools (${lines.length}):\n${lines.join('\n')}`;
        setIsConnected(true);
        addMessage('bot', reply);
        return;
      }

      const data = await callChatApi(messageText);
      setIsConnected(true);
      addMessage('bot', data.reply || 'No response generated');
    } catch {
      setIsConnected(false);
      addMessage('bot', 'Chat service unavailable. Please contact admin.');
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const formatMessage = (content: string): string => {
    return content
      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')
      .replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br />');
  };

  const connectionBadge = isConnected ? 'badge badge-connected' : 'badge badge-disconnected';

  const isLongMessage = (content: string) => {
    const lineCount = content.split('\n').length;
    return content.length > 900 || lineCount > 14;
  };

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <div className="chat-titles">
          <h2>API Chat</h2>
          <p>Chat with your tools in natural language</p>
        </div>
        <div className="chat-meta">
          <span className={connectionBadge}>{isConnected ? 'Connected' : 'Disconnected'}</span>
          {tools.length > 0 && (
            <span className="badge badge-muted">
              {tools.length} {tools.length === 1 ? 'tool' : 'tools'}
            </span>
          )}
        </div>
      </header>

      {QUICK_ACTIONS.length > 0 && (
        <div className="quick-actions" aria-label="Quick chat prompts">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action}
              className="quick-pill"
              type="button"
              onClick={() => setInput(action)}
              disabled={isLoading}
            >
              {action}
            </button>
          ))}
        </div>
      )}

      <div className="chat-card">
        <div className="messages custom-scrollbar">
          {messages.length === 0 ? (
            <div className="messages-empty">
              Start chatting with your tools. Try a quick action above or type a message.
            </div>
          ) : (
            messages.map((msg, index) => {
              const isUser = msg.role === 'user';
              const messageKey = `${msg.timestamp}-${index}`;
              const isLong = !isUser && isLongMessage(msg.content);
              const isExpanded = expandedMessages[messageKey] === true;
              return (
                <div
                  key={messageKey}
                  className={`message-row ${isUser ? 'align-right' : 'align-left'}`}
                >
                  <div
                    className={`bubble ${isUser ? 'bubble-user' : 'bubble-bot'}`}
                    style={{ animationDelay: `${index * 20}ms` }}
                  >
                    <div
                      className={`bubble-content ${isLong && !isExpanded ? 'truncated' : ''}`}
                      dangerouslySetInnerHTML={{ __html: formatMessage(msg.content) }}
                    />
                    {isLong && (
                      <button
                        type="button"
                        className="bubble-toggle"
                        onClick={() =>
                          setExpandedMessages((prev) => ({
                            ...prev,
                            [messageKey]: !isExpanded,
                          }))
                        }
                      >
                        {isExpanded ? 'View Less' : 'View More'}
                      </button>
                    )}
                    <div className="bubble-meta">{msg.timestamp}</div>
                  </div>
                </div>
              );
            })
          )}
          {isLoading && (
            <div className="message-row align-left">
              <div className="bubble bubble-bot typing">
                <div className="dots">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="bubble-meta">Thinking…</div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-bar">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message…"
            disabled={isLoading}
            aria-label="Chat message input"
          />
          <button
            type="button"
            className="send-btn"
            onClick={() => handleSendMessage()}
            disabled={isLoading || !input.trim()}
            aria-label="Send message"
          >
            {isLoading ? (
              <svg className="spinner" viewBox="0 0 50 50">
                <circle className="path" cx="25" cy="25" r="20" fill="none" strokeWidth="5" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M5 12h14" strokeWidth="2" strokeLinecap="round" />
                <path d="M12 5l7 7-7 7" strokeWidth="2" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
