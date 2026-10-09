import { useState } from "react";
import "./Chat.css";
import logoIcon from "../../assets/logo-icon.png";
import userIcon from "../../assets/user.png";
import { useOutletContext } from "react-router-dom";

const API = "http://127.0.0.1:8000";

function Chat() {
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copiedId, setCopiedId] = useState(null);
  const { setHasChat } = useOutletContext();

  async function handleSubmit(event) {
    event.preventDefault();

    const text = prompt.trim();
    if (!text || loading) return;

    setMessages((previous) => [
      ...previous,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        filename: file?.name,
      },
    ]);

    setPrompt("");
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("prompt", text);

      if (file) {
        formData.append("file", file);
      }

      const response = await fetch(`${API}/chat`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }

      const data = await response.json();

      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.result,
        },
      ]);

      setFile(null);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="chat">
      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <img
              src={logoIcon}
              alt=""
              className="chat-welcome-logo"
            />
          </div>
        )}

        {messages.map((message) => (
          <article
            key={message.id}
            className={`chat-message chat-message--${message.role}`}
          >
            {message.role === "assistant" && (
              <span className="chat-response-arrow" aria-hidden="true">
                &gt;
              </span>
            )}

            <div className="chat-message-body">
              <p className="chat-message-text">{message.content}</p>

              {message.filename && (
                <small className="chat-attachment">
                  Attached: {message.filename}
                </small>
              )}
            </div>

            {message.role === "user" && (
              <img
                src={userIcon}
                alt="User"
                className="chat-user-icon"
              />
            )}
          </article>
        ))}

        {loading && <p className="chat-thinking">Thinking...</p>}
      </div>

      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}

      <form className="chat-form" onSubmit={handleSubmit}>
        <div className="chat-input-row">
          <span className="chat-chevron" aria-hidden="true">
            &gt;
          </span>

          <input
            className="chat-input"
            aria-label="Message"
            placeholder="Ask model"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            disabled={loading}
          />

          <label
            className={`chat-file-button ${loading ? "is-disabled" : ""}`}
            title="Attach a file"
          >
            <span aria-hidden="true">+</span>

            <input
              type="file"
              aria-label="Attach a file"
              disabled={loading}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />
          </label>

          <button
            className="chat-send"
            type="submit"
            aria-label="Send message"
            disabled={loading || !prompt.trim()}
          >
            →
          </button>
        </div>

        {file && (
          <div className="chat-selected-file">
            <span>{file.name}</span>

            <button
              type="button"
              onClick={() => setFile(null)}
              disabled={loading}
            >
              Remove
            </button>
          </div>
        )}
      </form>
    </section>
  );
}

export default Chat;