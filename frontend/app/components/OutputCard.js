"use client";
import { useId, useState } from "react";
import { Copy, Download, FileVideo, Play, X } from "lucide-react";
import { outputVideoUrl } from "../lib/studio";
import styles from "./Output.module.css";

export default function OutputCard({ file, playable, expanded, onToggle }) {
  const playerId = useId();
  const [copyStatus, setCopyStatus] = useState("");
  const [playError, setPlayError] = useState(false);
  const videoSrc = outputVideoUrl(file.path);
  const localPath = /^[A-Za-z]:\//.test(file.path)
    ? file.path.replaceAll("/", "\\")
    : file.path;

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(localPath);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("manual");
    }
  }

  return (
    <article className={styles.card}>
      <div className={styles.row}>
        <span className={styles.fileIcon}><FileVideo size={20} aria-hidden="true" /></span>
        <div className={styles.fileDetails}>
          <h3>{file.name}</h3>
          <p>
            {file.size_mb} MB
            {file.modified > 0 && (
              <> · {new Date(file.modified * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</>
            )}
          </p>
        </div>
        <div className={styles.actions}>
          {playable && (
            <>
              <button
                className="btn btnSecondary btnSmall"
                type="button"
                aria-expanded={expanded}
                aria-controls={playerId}
                aria-label={`${expanded ? "Close preview of" : "Preview"} ${file.name}`}
                onClick={() => { setPlayError(false); onToggle(); }}
              >
                {expanded ? <X size={14} /> : <Play size={14} />}
                {expanded ? "Close" : "Preview"}
              </button>
              <a
                className="btn btnSecondary btnSmall"
                href={`${videoSrc}?download=1`}
                download={file.name}
                aria-label={`Save ${file.name}`}
              >
                <Download size={14} /> Save
              </a>
            </>
          )}
          <button type="button" className="btn btnSecondary btnSmall"
            onClick={copyPath} aria-label={`Copy path to ${file.name}`}>
            <Copy size={14} /> Copy path
          </button>
        </div>
      </div>
      {copyStatus === "copied" && <p className={styles.feedback} role="status">Path copied. Paste it into your upload file picker.</p>}
      {copyStatus === "manual" && (
        <label className={styles.manualPath}>
          Copy this file path
          <input readOnly value={localPath} autoFocus onFocus={event => event.target.select()} />
        </label>
      )}
      {expanded && playable && (
        <div id={playerId}>
          <video className="outputPlayer" src={videoSrc} controls autoPlay playsInline
            aria-label={`Preview of ${file.name}`} onError={() => setPlayError(true)} />
          {playError && <p role="status" className={styles.feedback}>Preview unavailable. Open the saved file in your video player.</p>}
        </div>
      )}
    </article>
  );
}
