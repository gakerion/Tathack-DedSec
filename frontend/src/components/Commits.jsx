import { useEffect, useState } from "react";
import "./Commits.css";

const API = "http://127.0.0.1:8000";

function importanceColor(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "#999";
  if (value < 0.33) return "#16d948";
  if (value < 0.67) return "#e6df00";
  return "#ff2222";
}

export default function Commits() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [message, setMessage] = useState("");
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadHistory() {
      try {
        const response = await fetch(`${API}/checkpoints`);
        if (!response.ok) throw new Error("Could not load action history.");
        const data = await response.json();
        if (active) {
          setGroups(data.checkpoints);
          setHistoryError(data.history_error ?? "");
        }
      } catch (error) {
        if (active) setHistoryError(error.message);
      } finally {
        if (active) setLoading(false);
      }
    }
    loadHistory();
    window.addEventListener("honeygate:checkpoints-updated", loadHistory);
    return () => {
      active = false;
      window.removeEventListener("honeygate:checkpoints-updated", loadHistory);
    };
  }, []);

  async function undo(actionId) {
    if (restoring) return;
    setRestoring(true);
    setMessage("");
    try {
      const response = await fetch(`${API}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: actionId }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Undo failed.");
      setMessage(data.message);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setRestoring(false);
      window.dispatchEvent(new Event("honeygate:checkpoints-updated"));
    }
  }

  return (
    <aside className="checkpoint-sidebar">
      <h2>Action history</h2>
      <p>Undo changes from newest to oldest.</p>
      {loading && <p>Loading...</p>}
      {historyError && <p role="alert">{historyError}</p>}
      {!loading && groups.length === 0 && <p>No tasks yet.</p>}
      <nav aria-label="Action history">
        {groups.map((group) => (
          <details className="prompt-folder" key={group.task_id} open>
            <summary>{group.prompt}</summary>
            {group.actions.length === 0 && <p>No tool actions recorded.</p>}
            <ol className="commit-list">
              {group.actions.map((action) => (
                <li className="action-card" key={action.action_id}>
                  <div className="action-heading">
                    <span className="commit-dot" aria-hidden="true"
                      style={{ backgroundColor: importanceColor(action.importance) }} />
                    <strong>{action.operation ?? action.tool}{action.target ? `: ${action.target}` : ""}</strong>
                  </div>
                  <p>Status: {action.status}</p>
                  {typeof action.importance === "number" && (
                    <p>Importance: {action.importance.toFixed(3)}</p>
                  )}
                  {action.reason && <p>{action.reason}</p>}
                  {action.restore_supported && (
                    <button type="button" className="commit-item" disabled={restoring}
                      onClick={() => undo(action.action_id)}>
                      {restoring ? "Undoing..." : "Undo latest change"}
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </details>
        ))}
      </nav>
      {message && <p role="status">{message}</p>}
    </aside>
  );
}
