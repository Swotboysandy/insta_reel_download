"use client";
import { useState } from "react";
import { Check, Clapperboard, Search, Undo2, Eye } from "lucide-react";
import { Button, Refresh, Empty } from "./Controls";
const stem = (name) => name.replace(/\.[^.]+$/, "");
export default function Library({ s }) {
  const [filter, setFilter] = useState("all");
  const [undo, setUndo] = useState(null);
  const hasOutput = (file) =>
    s.brandedFiles.some(
      (out) => stem(out.name) === `${stem(file.name)}_branded`,
    );
  const files = s.filteredFiles.filter((file) =>
    filter === "selected"
      ? s.selectedVideos.includes(file.path)
      : filter === "unbranded"
        ? !hasOutput(file)
        : true,
  );
  const groups = Object.groupBy(files, (file) => file.folder || "Root");
  function change(next) {
    setUndo([...s.selectedVideos]);
    s.setSelectedVideos(next);
  }
  return (
    <aside className="library panel" aria-label="Video library">
      <div className="panelHeading">
        <div>
          <h2>
            Clip library{" "}
            <span className="count">{s.downloadedFiles.length}</span>
          </h2>
          <p>Choose the reels for your next batch.</p>
        </div>
        <Refresh
          onClick={() => {
            s.loadFiles();
            s.loadBrandedFiles();
          }}
          busy={s.loadingFiles}
        />
      </div>
      <div className="searchRow">
        <Search size={16} />
        <input
          aria-label="Search clips"
          placeholder="Search name or folder…"
          value={s.fileFilter}
          onChange={(e) => s.setFileFilter(e.target.value)}
        />
      </div>
      <div className="filterRow" aria-label="Filter library">
        {[
          ["all", "All clips"],
          ["unbranded", "No output"],
          ["selected", `Selected (${s.selectedVideos.length})`],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="selectionTools">
        <label>
          <input
            type="checkbox"
            aria-label="Select all visible clips"
            checked={
              !!files.length &&
              files.every((f) => s.selectedVideos.includes(f.path))
            }
            onChange={(e) =>
              change(
                e.target.checked
                  ? [
                      ...new Set([
                        ...s.selectedVideos,
                        ...files.map((f) => f.path),
                      ]),
                    ]
                  : s.selectedVideos.filter(
                      (p) => !files.some((f) => f.path === p),
                    ),
              )
            }
          />{" "}
          Select visible <span className="count">{files.length}</span>
        </label>
        <button
          className="textButton"
          disabled={!s.selectedVideos.length}
          onClick={() => change([])}
        >
          Clear
        </button>
      </div>
      <div className="libraryScroll">
        {s.loadingFiles ? (
          <p className="loadingText" role="status">
            Loading clips…
          </p>
        ) : !files.length ? (
          <Empty
            icon={Clapperboard}
            title={
              s.downloadedFiles.length
                ? "No matching clips"
                : "Your library is empty"
            }
          >
            {s.downloadedFiles.length
              ? "Try another filter or search."
              : "Download a reel or profile to get started."}
            {!s.downloadedFiles.length && (
              <Button onClick={() => s.setActiveTab("download")}>
                Add reels
              </Button>
            )}
          </Empty>
        ) : (
          Object.entries(groups).map(([folder, items]) => (
            <section className="folderGroup" key={folder}>
              <div className="folderHeading">
                <h3>{folder}</h3>
                <button
                  className="textButton"
                  onClick={() => {
                    setUndo([...s.selectedVideos]);
                    s.toggleFolder(items);
                  }}
                >
                  Select folder
                </button>
              </div>
              {items.map((file) => (
                <div
                  key={file.path}
                  className={`clipRow ${s.selectedVideos.includes(file.path) ? "selected" : ""}`}
                >
                  <label>
                    <input
                      type="checkbox"
                      checked={s.selectedVideos.includes(file.path)}
                      onChange={() => {
                        setUndo([...s.selectedVideos]);
                        s.toggleVideo(file.path);
                      }}
                    />
                    <span className="clipGlyph">
                      <Clapperboard size={20} />
                    </span>
                    <span className="clipInfo">
                      <strong title={file.name}>{file.name}</strong>
                      <small>
                        {file.size_mb} MB{" "}
                        <span className={hasOutput(file) ? "successText" : ""}>
                          {hasOutput(file)
                            ? "· Output found"
                            : "· No output found"}
                        </span>
                      </small>
                    </span>
                  </label>
                  <button
                    className="iconButton"
                    aria-label={`Preview ${file.name}`}
                    title="Use as preview clip"
                    onClick={() =>
                      change([
                        file.path,
                        ...s.selectedVideos.filter((p) => p !== file.path),
                      ])
                    }
                  >
                    <Eye size={16} />
                  </button>
                </div>
              ))}
            </section>
          ))
        )}
      </div>
      <div className="libraryFooter">
        <span>
          <strong>{s.selectedVideos.length}</strong> selected ·{" "}
          {s.selectedSizeMb.toFixed(1)} MB
        </span>
        {undo && (
          <button
            className="textButton"
            onClick={() => {
              s.setSelectedVideos(undo);
              setUndo(null);
            }}
          >
            <Undo2 size={14} /> Undo
          </button>
        )}
      </div>
      <p className="footnote">
        Output badges match filenames in the current output folder; settings may
        differ.
      </p>
    </aside>
  );
}
