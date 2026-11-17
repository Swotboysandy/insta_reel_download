"use client";
import { Download, FileVideo, History, Trash2 } from "lucide-react";
import { Button, Input, Field, Empty, Refresh } from "./Controls";
import TaskActivity from "./TaskActivity";
import OutputCard from "./OutputCard";
export function DownloadWorkspace({ s }) {
  return (
    <section className="secondaryWorkspace">
      <div className="panel sourcePanel">
        <h2>Add to your library</h2>
        <p className="intro">
          Paste an Instagram reel or profile. Download first, then choose what
          to brand.
        </p>
        <Field label="Instagram link or profile">
          {(id) => (
            <textarea
              id={id}
              rows="3"
              value={s.downloadForm.url}
              onChange={(e) => s.updateDownloadForm("url", e.target.value)}
              placeholder="https://www.instagram.com/reel/…"
            />
          )}
        </Field>
        <div className="twoFields">
          <Input
            label="Fetch limit"
            type="number"
            min="1"
            max="1000"
            value={s.downloadForm.limit}
            onChange={(v) => s.updateDownloadForm("limit", v)}
          />
          <Field label="Content type">
            {(id) => (
              <select
                id={id}
                value={s.downloadForm.mode}
                onChange={(e) => s.updateDownloadForm("mode", e.target.value)}
              >
                <option value="reel">Reels</option>
                <option value="post">Posts</option>
              </select>
            )}
          </Field>
        </div>
        <Button
          primary
          busy={s.downloadTask.state === "processing"}
          disabled={s.downloadTask.state === "processing"}
          onClick={s.startDownload}
        >
          <Download size={16} />
          {s.downloadTask.state === "processing"
            ? "Downloading…"
            : "Queue download"}
        </Button>
        <p className="hint">
          Profile downloads skip reels already in your download history.
        </p>
        {s.downloadTask.state === "completed" && (
          <Button onClick={() => s.setActiveTab("brand")}>
            Choose downloaded clips
          </Button>
        )}
      </div>
      <div className="panel">
        <TaskActivity task={s.downloadTask} title="Download queue" />
      </div>
    </section>
  );
}
export function OutputWorkspace({ s }) {
  return (
    <section className="secondaryWorkspace outputWorkspace">
      <div className="panel">
        <div className="panelHeading">
          <div>
            <h2>
              Branded output{" "}
              <span className="count">{s.brandedFiles.length}</span>
            </h2>
            <p className="folderPath">
              {s.brandForm.outputFolder || "branded_videos/"}
            </p>
          </div>
          <Refresh
            busy={s.loadingOutputs}
            onClick={() => s.loadBrandedFiles()}
          />
        </div>
        {s.outputsNote && <p className="warning">{s.outputsNote}</p>}
        <div className="outputList">
          {s.loadingOutputs ? (
            <p role="status">Loading output…</p>
          ) : s.brandedFiles.length ? (
            s.brandedFiles.map((file) => (
              <OutputCard key={file.path} file={file} />
            ))
          ) : (
            <Empty icon={FileVideo} title="No output yet">
              Rendered videos will appear here for playback and saving.
            </Empty>
          )}
        </div>
      </div>
      <div className="panel">
        <TaskActivity
          task={s.brandTask}
          paths={s.runVideos}
          title="Branding queue"
        />
      </div>
    </section>
  );
}
export function Maintenance({ s }) {
  return (
    <details className="maintenance">
      <summary>Storage & download history</summary>
      <div className="maintenanceBody">
        <Button
          onClick={s.clearHistory}
          disabled={s.isClearingHistory || !s.historyCount}
          busy={s.isClearingHistory}
        >
          <History size={15} />
          Clear history ({s.historyCount})
        </Button>
        <div className="cleanupControls">
          <Input
            label="Delete reels below this view count"
            type="number"
            min="0"
            step="100"
            value={s.minViews}
            onChange={s.setMinViews}
          />
          <Button
            onClick={s.cleanupLowViews}
            busy={s.isCleaningLowViews}
            disabled={s.isCleaningLowViews}
          >
            Clean low-view reels
          </Button>
        </div>
        <Button
          danger
          onClick={s.deleteAllVideos}
          disabled={s.isDeletingVideos}
          busy={s.isDeletingVideos}
        >
          <Trash2 size={15} />
          Delete all videos
        </Button>
        {s.cleanupStatus && <p role="status">{s.cleanupStatus}</p>}
      </div>
    </details>
  );
}
