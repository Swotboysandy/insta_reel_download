"use client";
import { useState } from "react";
import {
  Clapperboard,
  Download,
  SlidersHorizontal,
  Film,
  X,
  ArrowUpRight,
} from "lucide-react";
import { useStudio } from "./hooks/useStudio";
import Library from "./components/Library";
import Preview from "./components/Preview";
import Inspector from "./components/Inspector";
import {
  DownloadWorkspace,
  OutputWorkspace,
  Maintenance,
} from "./components/Workspaces";
export default function HomePage() {
  const s = useStudio();
  const [reviewKey, setReviewKey] = useState("");
  const currentKey = JSON.stringify([
    s.brandForm,
    s.selectedVideos[0],
    s.previewImage,
  ]);
  const reviewed = reviewKey === currentKey && s.previewFresh;
  return (
    <div className="pageShell">
      <a className="skipLink" href="#workspace">
        Skip to workspace
      </a>
      <header className="appHeader">
        <div className="brand">
          <span className="brandMark">
            <Clapperboard size={21} />
          </span>
          <h1>Reel Studio</h1>
          <span className="studioDivider" />
          <span className="studioOwner">
            @{s.brandForm.handle.replace(/^@/, "") || "your page"}
          </span>
        </div>
        <span className="headerNote">Your daily reel desk</span>
      </header>
      <nav className="workspaceNav" aria-label="Workspace">
        {[
          ["download", Download, "Download"],
          ["brand", SlidersHorizontal, "Brand studio"],
          ["output", Film, "Output"],
        ].map(([key, Icon, label]) => (
          <button
            key={key}
            aria-current={s.activeTab === key ? "page" : undefined}
            onClick={() => s.setActiveTab(key)}
          >
            <Icon size={17} />
            {label}
            {key === "output" && !!s.brandedFiles.length && (
              <span className="count">{s.brandedFiles.length}</span>
            )}
          </button>
        ))}
        <span className="navStatus">
          {s.brandTask.state === "processing"
            ? "Rendering batch"
            : s.downloadTask.state === "processing"
              ? "Downloading reels"
              : "Local workspace"}
        </span>
      </nav>
      <main id="workspace">
        <div className="workspaceTitle">
          <div>
            <h2>
              {s.activeTab === "brand"
                ? "Brand studio"
                : s.activeTab === "download"
                  ? "Download reels"
                  : "Review output"}
            </h2>
            <p>
              {s.activeTab === "brand"
                ? "Choose clips, check the frame, then render your batch."
                : s.activeTab === "download"
                  ? "Bring reels into your library from Instagram."
                  : "Watch the finished video before you publish."}
            </p>
          </div>
          {s.activeTab === "brand" && (
            <button
              className="textButton"
              onClick={() => s.setActiveTab("download")}
            >
              <Download size={16} />
              Add reels
              <ArrowUpRight size={14} />
            </button>
          )}
        </div>
        {s.errorMessage && (
          <div className="errorBanner" role="alert">
            <span>{s.errorMessage}</span>
            <button
              className="iconButton"
              onClick={() => s.setErrorMessage("")}
              aria-label="Dismiss error"
            >
              <X size={17} />
            </button>
          </div>
        )}
        {s.activeTab === "brand" ? (
          <div className="editorWorkspace">
            <Library s={s} />
            <Preview
              s={s}
              reviewed={reviewed}
              onReview={(v) => setReviewKey(v ? currentKey : "")}
            />
            <Inspector s={s} reviewed={reviewed} />
          </div>
        ) : s.activeTab === "download" ? (
          <DownloadWorkspace s={s} />
        ) : (
          <OutputWorkspace s={s} />
        )}
        <Maintenance s={s} />
      </main>
      <footer className="appFooter">
        <span>Reel Studio</span>
        <span>Download · Brand · Review</span>
      </footer>
    </div>
  );
}
