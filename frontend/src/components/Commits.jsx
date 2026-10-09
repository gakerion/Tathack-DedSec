import { useEffect, useState } from "react";
import "./Commits.css";

const API = "http://127.0.0.1:8000";

function getImportanceColor(importance) {
  if (typeof importance !== "number" || !Number.isFinite(importance)) {
    return "#999";
  }

  if (importance < 0.33) return "#16d948";
  if (importance < 0.67) return "#e6df00";
  return "#ff2222";
}

function Commits() {
  const [checkpoints, setCheckpoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    async function loadCommits() {
      try {
        const response = await fetch(`${API}/checkpoints`);

        if (!response.ok) {
          throw new Error("Could not load checkpoints");
        }

        const data = await response.json();
        setCheckpoints(data.checkpoints);
      } catch (error) {
        setMessage(error.message);
      } finally {
        setLoading(false);
      }
    }

    loadCommits();
  }, []);

  async function restore(commitHash) {
    if (restoring) return;

    setRestoring(true);
    setMessage("");

    try {
      const response = await fetch(
        `${API}/restore?commit_hash=${encodeURIComponent(commitHash)}`,
        { method: "POST" }
      );

      if (!response.ok) {
        throw new Error("Restore failed");
      }

      const data = await response.json();
      setMessage(data.message ?? "Restore request completed");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <aside className="checkpoint-sidebar">
      <h2>Checkpoints</h2>

      {loading && <p>Loading...</p>}

      {!loading && checkpoints.length === 0 && (
        <p>No checkpoints yet.</p>
      )}

      <nav aria-label="Checkpoint history">
        {checkpoints.map((group, index) => (
          <details className="prompt-folder" key={index}>
            <summary>{group.prompt}</summary>

            <ul className="commit-list">
              {group.commits.map((commit) => (
                <li key={commit.commit_hash}>
                  <button
                    type="button"
                    className="commit-item"
                    onClick={() => restore(commit.commit_hash)}
                    disabled={restoring}
                    title={`${commit.task} — Importance: ${
                      commit.importance ?? "unknown"
                    }`}
                    aria-label={`Restore to ${commit.task}. Importance: ${
                      commit.importance ?? "unknown"
                    }`}
                  >
                    <span
                      className="commit-dot"
                      style={{
                        backgroundColor: getImportanceColor(
                          commit.importance
                        ),
                      }}
                      aria-hidden="true"
                    />

                    <span className="commit-task">
                      {commit.task}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </nav>

      {restoring && <p role="status">Restoring...</p>}
      {message && <p role="status">{message}</p>}
    </aside>
  );
}

export default Commits;