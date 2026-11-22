"use client";
import { useMemo, useState } from "react";
import { Clapperboard, Search, Undo2, Eye } from "lucide-react";
import { Button, Refresh, Empty } from "./Controls";
const stem = (name) => name.replace(/\.[^.]+$/, "");
export default function Library({ s }) {
  const [filter, setFilter] = useState("all");
  const [undo, setUndo] = useState(null);
  const [pageRequest, setPageRequest] = useState(1);
  const perPage = 24;
  const outputs = useMemo(() => new Set(s.brandedFiles.map((file) => stem(file.name))), [s.brandedFiles]);
  const hasOutput = (file) => outputs.has(stem(file.name) + "_branded");
  const files = s.filteredFiles.filter((file) =>
    filter === "selected" ? s.selectedPaths.has(file.path) :
    filter === "unbranded" ? !hasOutput(file) : true,
  );
  const pageCount = Math.max(1, Math.ceil(files.length / perPage));
  const page = Math.min(pageRequest, pageCount);
  const groups = new Map();
  const pageFiles = files.slice((page - 1) * perPage, page * perPage);
  for (const file of pageFiles) {
    const key = file.folder || "Root";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(file);
  }
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
          onChange={(e) => { setPageRequest(1); s.setFileFilter(e.target.value); }}
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
            onClick={() => { setPageRequest(1); setFilter(key); }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="selectionTools">
        <label>
          <input
            type="checkbox"
            aria-label="Select all matching clips"
            checked={
              !!files.length &&
              files.every((f) => s.selectedPaths.has(f.path))
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
          Select all matches <span className="count">{files.length}</span>
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
              : "Import an MP4 above or download reels from Instagram."}
            {!s.downloadedFiles.length && (
              <Button onClick={() => s.setActiveTab("download")}>
                Add reels
              </Button>
            )}
          </Empty>
        ) : (
          Array.from(groups).map(([folder, items]) => (
            <section className="folderGroup" key={folder}>
              <div className="folderHeading">
                <h3>{folder}</h3>
                <button
                  className="textButton"
                  onClick={() => {
                    setUndo([...s.selectedVideos]);
                    s.toggleFolder(files.filter((file) => (file.folder || "Root") === folder));
                  }}
                >
                  {files.filter((file) => (file.folder || "Root") === folder).every((file) => s.selectedPaths.has(file.path)) ? "Clear folder" : "Select folder"}
                </button>
              </div>
              {items.map((file) => (
                <div
                  key={file.path}
                  className={`clipRow ${s.selectedPaths.has(file.path) ? "selected" : ""}`}
                >
                  <label>
                    <input
                      type="checkbox"
                      checked={s.selectedPaths.has(file.path)}
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
      {pageCount > 1 && (
        <nav className="libraryPages" aria-label="Clip library pages">
          <button className="textButton" disabled={page === 1} onClick={() => setPageRequest(page - 1)}>Previous</button>
          <span>{page} / {pageCount}</span>
          <button className="textButton" disabled={page === pageCount} onClick={() => setPageRequest(page + 1)}>Next</button>
        </nav>
      )}
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
