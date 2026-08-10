import { useState, useRef, useEffect } from "react";

/**
 * Modern, Minimal API Chat Interface
 * Inspired by Slack, Linear, and Notion
 * 
 * Features:
 * - Clean, minimal layout with soft borders
 * - Professional typography (Inter/system UI)
 * - Chat bubble layout (user right, system left)
 * - Smooth hover and focus transitions
 * - Rounded pill quick action buttons
 * - Scrollable message container with subtle scrollbar
 * - Clean input bar with rounded edges
 */
export default function ApiChat({ tools = [] }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Quick action prompts
  const QUICK_ACTIONS = [
    "Show me all GET requests available",
    "Display the first 10 posts",
    "List all available API endpoints",
    "What parameters does the POST endpoint accept?",
    "Show me examples of how to use the DELETE endpoint"
  ];

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Parse error details from API response
  const parseErrorDetail = async (res) => {
    const text = await res.text();
    try {
      const data = JSON.parse(text);
      return data.detail || data.message || text || res.statusText;
    } catch {
      return text || res.statusText;
    }
  };

  // Call chat API
  const callChatApi = async (prompt, history) => {
    const res = await fetch("http://127.0.0.1:8000/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: prompt,
        tools: tools,
        history: history.map((m) => ({
          role: m.role === "bot" ? "assistant" : m.role,
          content: m.content,
        })),
      }),
    });

    if (!res.ok) {
      const detail = await parseErrorDetail(res);
      throw new Error(`HTTP ${res.status}: ${detail}`);
    }

    return res.json();
  };

  // Send message handler
  const handleSendMessage = async (promptText = null) => {
    const messageText = promptText || input.trim();
    if (!messageText || isLoading) return;

    const userMessage = { role: "user", content: messageText };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    
    if (!promptText) {
      setInput("");
    }
    
    setIsLoading(true);

    try {
      const data = await callChatApi(messageText, newMessages);
      setMessages([...newMessages, { role: "bot", content: data.message }]);
    } catch (error) {
      console.error("Error sending message:", error);
      setMessages([
        ...newMessages,
        {
          role: "bot",
          content: `Error: ${error.message || "Could not connect to the chat service."}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Enter key press
  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !isLoading) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Format message content (basic markdown support)
  const formatMessage = (content) => {
    return content
      // Code blocks
      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="bg-gray-100 p-3 rounded-lg my-2 overflow-x-auto"><code class="text-sm">$2</code></pre>')
      // Inline code
      .replace(/`([^`\n]+)`/g, '<code class="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>')
      // Bold
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
      // Italic
      .replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
      // Line breaks
      .replace(/\n/g, '<br />');
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#f7f9fc] font-sans">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-white shadow-sm flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-gray-900">
            💬 API Chat
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Chat with your tools in natural language
          </p>
        </div>
        {tools.length > 0 && (
          <span className="text-xs px-2.5 py-1 rounded-full bg-blue-50 text-blue-600 font-medium">
            {tools.length} {tools.length === 1 ? "tool" : "tools"}
          </span>
        )}
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4 custom-scrollbar">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="text-gray-400 text-sm mb-2">
                Start chatting with your tools!
              </div>
              <div className="text-gray-300 text-xs">
                Use the quick actions below or type your message
              </div>
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, index) => {
              const isUser = msg.role === "user";
              const formattedContent = formatMessage(msg.content);

              return (
                <div
                  key={index}
                  className={`flex ${isUser ? "justify-end" : "justify-start"} animate-in fade-in slide-in-from-bottom-2 duration-300`}
                >
                  <div
                    className={`rounded-2xl px-4 py-2.5 max-w-[75%] shadow-sm transition-all ${
                      isUser
                        ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white"
                        : "bg-white text-gray-800 border border-gray-200"
                    }`}
                  >
                    <div
                      className="text-sm leading-relaxed break-words"
                      dangerouslySetInnerHTML={{ __html: formattedContent }}
                    />
                  </div>
                </div>
              );
            })}
            {isLoading && (
              <div className="flex justify-start animate-in fade-in">
                <div className="rounded-2xl px-4 py-2.5 bg-white border border-gray-200 shadow-sm">
                  <div className="flex items-center gap-2 text-sm text-gray-500">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></div>
                    </div>
                    <span className="ml-1">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Quick Actions */}
      {messages.length === 0 && (
        <div className="px-6 pb-3 border-b border-gray-200 bg-white">
          <div className="py-3">
            <label className="text-xs font-medium text-gray-500 mb-2 block">
              Quick Actions:
            </label>
            <div className="flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((action, index) => (
                <button
                  key={index}
                  onClick={() => handleSendMessage(action)}
                  disabled={isLoading}
                  className="px-3.5 py-1.5 text-xs font-medium rounded-full bg-gray-100 text-gray-700 
                             hover:bg-gray-200 hover:text-gray-900 
                             active:scale-95 
                             transition-all duration-200 
                             disabled:opacity-50 disabled:cursor-not-allowed
                             focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Input Bar */}
      <div className="border-t border-gray-200 bg-white px-6 py-4 shadow-sm">
        <div className="flex items-end gap-3">
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type your message... (e.g., 'Show me all posts' or 'Delete post with id 1')"
              disabled={isLoading}
              className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl 
                         bg-gray-50 text-gray-900 placeholder-gray-400
                         focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0
                         outline-none transition-all duration-200
                         disabled:opacity-50 disabled:cursor-not-allowed
                         text-sm"
            />
            {input && (
              <button
                onClick={() => setInput("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 
                           transition-colors p-1 rounded-full hover:bg-gray-100"
                aria-label="Clear input"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
          <button
            onClick={() => handleSendMessage()}
            disabled={!input.trim() || isLoading}
            className="bg-gradient-to-br from-blue-600 to-blue-700 text-white p-3 rounded-xl 
                       hover:from-blue-700 hover:to-blue-800 
                       active:scale-95
                       transition-all duration-200 shadow-md hover:shadow-lg
                       disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-md
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            aria-label="Send message"
          >
            {isLoading ? (
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
        {tools.length === 0 && (
          <p className="text-xs text-gray-400 mt-2 text-center">
            No tools loaded. Please load tools first to use the chat.
          </p>
        )}
      </div>
    </div>
  );
}

