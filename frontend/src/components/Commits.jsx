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
  const [commits, setCommits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    async function loadCommits() {
      try {
        const response = await fetch(`${API}/git-history`);

        if (!response.ok) {
          throw new Error("Could not load Git history");
        }

        const data = await response.json();
        setCommits(data.commits);
      } catch (error) {
        setMessage(error.message);
      } finally {
        setLoading(false);
      }
    }

    loadCommits();

    window.addEventListener(
      "honeygate:checkpoints-updated",
      loadCommits
    );

    return () => {
      window.removeEventListener(
        "honeygate:checkpoints-updated",
        loadCommits
      );
    };
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
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail ?? "Restore failed");
      }

      const data = await response.json();
      setMessage(data.message ?? "Restore request completed");
      window.dispatchEvent(new Event("honeygate:checkpoints-updated"));
    } catch (error) {
      setMessage(error.message);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <aside className="checkpoint-sidebar">
      <h2>Commit history</h2>

      {loading && <p>Loading Git history...</p>}

      {!loading && commits.length === 0 && (
        <p>No Git commits yet.</p>
      )}

      <nav aria-label="Checkpoint history">
        <ul className="commit-list">
          {commits.map((commit) => (
            <li key={commit.commit_hash}>
              <button
                type="button"
                className="commit-item"
                onClick={() => restore(commit.commit_hash)}
                disabled={restoring}
                title={`${commit.task} — ${commit.commit_hash}`}
                aria-label={`Restore to ${commit.task}`}
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
      </nav>

      {restoring && <p role="status">Restoring...</p>}
      {message && <p role="status">{message}</p>}
    </aside>
  );
}

export default Commits;