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
  const [backupMode, setBackupMode] = useState("");
  const [selectedStages, setSelectedStages] = useState({});
  const [agentBusy, setAgentBusy] = useState(false);

  useEffect(() => {
    let active = true;
    let fetching = false;
    let timer;
    const controller = new AbortController();
    async function loadHistory() {
      if (!active || fetching) return;
      clearTimeout(timer);
      fetching = true;
      try {
        const response = await fetch(`${API}/checkpoints`, {
          signal: controller.signal,
          cache: "no-store",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? "Could not load action history.");
        if (active) {
          setGroups(data.checkpoints);
          setHistoryError(data.history_error ?? "");
          setBackupMode(data.backup?.mode ?? "local");
          setAgentBusy(data.agent_busy ?? false);
        }
      } catch (error) {
        if (active) setHistoryError(error.message);
      } finally {
        fetching = false;
        if (active) {
          setLoading(false);
          // Wait for this request to finish so slow requests never overlap.
          timer = setTimeout(loadHistory, 1000);
        }
      }
    }
    loadHistory();
    window.addEventListener("honeygate:checkpoints-updated", loadHistory);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
      window.removeEventListener("honeygate:checkpoints-updated", loadHistory);
    };
  }, []);

  async function undo(actionId, keepStage = false) {
    if (restoring) return;
    setRestoring(true);
    setMessage("");
    try {
      const response = await fetch(`${API}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: actionId, keep_stage: keepStage }),
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
      {backupMode && <p>Backup: {backupMode === "azure" ? "Azure enabled" : "local only"}</p>}
      <p>Expand a file to inspect its saved stages.</p>
      {agentBusy && <p role="status">Agent is working. Action history updates automatically; restore is available when it finishes.</p>}
      {loading && <p>Loading...</p>}
      {historyError && <p role="alert">{historyError}</p>}
      {!loading && groups.length === 0 && <p>No tasks yet.</p>}
      <nav aria-label="Action history">
        {groups.map((group) => (
          <details className="prompt-folder" key={group.task_id} open>
            <summary>{group.title || group.prompt}</summary>
            <details className="original-request">
              <summary>View original request</summary>
              <p>{group.prompt}</p>
            </details>
            {group.actions.length === 0 && <p>No tool actions recorded.</p>}
            {Object.entries(group.actions.reduce((files, action) => {
              const name = action.target || "Other actions";
              (files[name] ??= []).push(action);
              return files;
            }, {})).map(([filename, actions]) => {
              const stages = actions.filter((action) => action.checkpoint_id && action.state_changed);
              const key = `${group.task_id}:${filename}`;
              const selected = stages.find((stage) => stage.action_id === Number(selectedStages[key]));
              return (
                <details className="file-stages" key={filename} open>
                  <summary>{filename} <small>({stages.length} saved stages)</small></summary>
                  {stages.length > 0 && (
                    <div className="stage-controls">
                      <label htmlFor={`stage-${group.task_id}-${actions[0].action_id}`}>File version</label>
                      <select id={`stage-${group.task_id}-${actions[0].action_id}`}
                        value={selectedStages[key] ?? ""}
                        onChange={(event) => setSelectedStages((previous) => ({ ...previous, [key]: event.target.value }))}>
                        <option value="">Choose a saved stage</option>
                        {stages.map((stage, index) => (
                          <option key={stage.action_id} value={stage.action_id}
                            disabled={!stage.stage_restore_supported}>
                            {index + 1}. {stage.stage_title || stage.operation}
                            {stage.is_current_stage ? " (current)" : stage.status === "undone" ? " (undone)" : ""}
                          </option>
                        ))}
                      </select>
                      <p>Keep this stage and undo all later changes to this file, including later tasks.</p>
                      <button type="button" className="commit-item"
                        disabled={restoring || agentBusy || !selected?.stage_restore_supported}
                        onClick={() => undo(selected.action_id, true)}>
                        Restore to selected stage
                      </button>
                    </div>
                  )}
                  <ol className="commit-list">
                    {actions.map((action) => (
                      <li className="action-card" key={action.action_id}>
                        <div className="action-heading">
                          <span className="commit-dot" aria-hidden="true"
                            style={{ backgroundColor: importanceColor(action.importance) }} />
                          <strong>{action.stage_title || action.operation || action.tool}</strong>
                        </div>
                        <p>Status: {action.status}{action.is_current_stage ? " (current version)" : ""}</p>
                        {typeof action.importance === "number" && <p>Importance: {action.importance.toFixed(3)}</p>}
                        {action.reason && <p>{action.reason}</p>}
                        {action.restore_supported && (
                          <button type="button" className="commit-item" disabled={restoring || agentBusy}
                            onClick={() => undo(action.action_id)}>
                            {restoring ? "Undoing..." : "Undo latest change"}
                          </button>
                        )}
                      </li>
                    ))}
                  </ol>
                </details>
              );
            })}
          </details>
        ))}
      </nav>
      {message && <p role="status">{message}</p>}
    </aside>
  );
}
