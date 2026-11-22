"use client";
import { useState } from "react";
import { FolderPlus, Upload } from "lucide-react";

export default function ImportClips({ state, onImport }) {
  const [dragging, setDragging] = useState(false);
  const busy = Boolean(state?.name);
  return (
    <section className={`importDesk ${dragging ? "dragging" : ""}`}
      aria-label="Import local clips"
      onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }}
      onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false); }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!busy) onImport(event.dataTransfer.files);
      }}>
      <div className="importLine">
        <span className="importIcon"><FolderPlus size={23} /></span>
        <div className="importIntro">
          <h3>Import clips</h3>
          <p>Drop MP4 files here to add them to your batch. Up to 512 MiB each.</p>
        </div>
        <label className={`importPicker ${busy ? "busy" : ""}`}>
          <input type="file" accept=".mp4,video/mp4" multiple disabled={busy}
            onChange={(event) => {
              onImport(event.target.files);
              event.target.value = "";
            }} />
          <Upload size={16} /> Choose files
        </label>
      </div>
      {state && (
        <div className="importStatus">
          <p role="status">{busy
            ? `Importing ${state.done + 1} of ${state.total} · ${state.name}`
            : `${state.added} ${state.added === 1 ? "clip" : "clips"} added to your batch${state.errors.length ? ` · ${state.errors.length} failed` : ""}`}</p>
          {busy && <progress aria-label="Files processed" value={state.done} max={state.total} />}
          {!!state.errors.length && <details><summary>Import errors ({state.errors.length})</summary>
            <ul>{state.errors.map((error, index) => <li key={index}>{error}</li>)}</ul>
          </details>}
        </div>
      )}
    </section>
  );
}
