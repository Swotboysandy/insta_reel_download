"use client";
import { CheckCircle2, AlertCircle, Clock, Activity } from "lucide-react";
import { getProgress } from "../lib/studio";
export default function TaskActivity({ task, paths = [], title }) {
  if (task.state === "idle")
    return (
      <div className="activityIdle">
        <Activity size={20} />
        <h3>No active task</h3>
        <p>Your next batch and server activity will appear here.</p>
      </div>
    );
  const results = task.results || [];
  const failures = results.filter((r) => !r.success);
  const done = task.state === "completed";
  const entries = paths.length
    ? paths.map((path) => ({ name: path.split(/[\\/]/).pop(), key: path }))
    : results.map((r, i) => ({
        name: r.shortcode || r.file || r.url || `Item ${i + 1}`,
        key: i,
        result: r,
      }));
  return (
    <section className="taskActivity" aria-label={title}>
      <div className="panelHeading">
        <h2>{title}</h2>
        <span
          className={`badge ${task.state === "failed" || failures.length ? "errorText" : done ? "successText" : ""}`}
        >
          {task.state === "failed"
            ? "Task lost"
            : done
              ? failures.length
                ? "Ended with failures"
                : "Task ended"
              : "Processing"}
        </span>
      </div>
      <p className="taskStatus" role="status">
        {task.status}
      </p>
      <div className="progressSummary">
        <strong>
          {task.current} / {task.total || "—"} processed
        </strong>
        <span>{getProgress(task.current, task.total)}%</span>
      </div>
      <progress
        max={task.total || 1}
        value={task.current || 0}
        aria-label="Processed items"
      />
      {done && (
        <p className={failures.length ? "errorText" : "successText"}>
          {results.filter((r) => r.success).length} successful ·{" "}
          {failures.length} failed
        </p>
      )}
      {!!entries.length && (
        <div className="taskItems">
          {entries.map((item) => {
            const result =
              item.result || results.find((r) => r.file === item.name);
            const logError = task.logs?.find((l) =>
              l.includes(`Error: ${item.name}:`),
            );
            const started = task.logs?.some((l) =>
              l.includes(
                `Rendering: ${item.name.replace(/\.[^.]+$/, "")}_branded.mp4`,
              ),
            );
            const successLabel = paths.length ? "Rendered" : "Downloaded";
            const state = result
              ? result.success
                ? successLabel
                : "Failed"
              : logError
                ? "Failed"
                : task.state === "failed"
                  ? "Unconfirmed"
                  : done
                    ? "No result returned"
                    : started
                      ? "Render started"
                      : "Awaiting result";
            const Icon =
              state === successLabel
                ? CheckCircle2
                : state === "Failed"
                  ? AlertCircle
                  : Clock;
            return (
              <div
                className={`taskItem ${state === "Failed" ? "errorText" : ""}`}
                key={item.key}
              >
                <Icon size={16} />
                <span>
                  <strong>{item.name}</strong>
                  {(result?.error || logError) && (
                    <small>{result?.error || logError}</small>
                  )}
                </span>
                <small>{state}</small>
              </div>
            );
          })}
        </div>
      )}
      <details className="serverLogs" open>
        <summary>Server activity · {task.logs?.length || 0} lines</summary>
        <div className="logsBox">
          {task.logs?.length ? (
            task.logs.map((log, i) => (
              <div
                key={i}
                className={/error|fail|\u274c/i.test(log) ? "errorText" : ""}
              >
                {log}
              </div>
            ))
          ) : (
            <p>Waiting for the server to report progress…</p>
          )}
        </div>
      </details>
      <p className="footnote">
        Item results are confirmed when the server returns them. The server does
        not provide per-clip percentages.
      </p>
    </section>
  );
}
