"use client";
import {
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Clapperboard,
} from "lucide-react";
import { Button } from "./Controls";
export default function Preview({ s, reviewed, onReview }) {
  const file = s.selectedVideos[0]?.split(/[\\/]/).pop();
  return (
    <section className="previewColumn" aria-label="Output preview">
      <div className="previewHeading">
        <h2>Output preview</h2>
        <span className={`badge ${s.previewFresh ? "successText" : ""}`}>
          {s.isPreviewLoading
            ? "Updating…"
            : s.previewFresh
              ? "Current settings"
              : s.previewImage
                ? "Out of date"
                : "Not generated"}
        </span>
      </div>
      <div className="previewStage">
        <div className="portrait">
          {s.previewImage ? (
            <img
              src={s.previewImage}
              width="1080"
              height="1920"
              alt={`Branded frame of ${file || "selected clip"}`}
            />
          ) : (
            <div className="previewEmpty">
              <Clapperboard size={40} strokeWidth={1} />
              <h3>
                {file ? "Preview this clip" : "Choose your first clip"}
              </h3>
              <p>
                {file
                  ? s.isPreviewLoading ? "Generating a frame…" : "Generate a still to check your branding."
                  : "Select a clip from the library to see the branded frame here."}
              </p>
            </div>
          )}
          {!s.previewFresh && s.previewImage && (
            <div className="staleOverlay">
              <AlertCircle size={15} />{" "}
              {s.previewError
                ? "Preview failed"
                : "Generate a new frame to review these settings"}
            </div>
          )}
        </div>
      </div>
      <div className="previewMeta">
        <span title={file}>{file || "No clip selected"}</span>
        <span>9:16</span>
      </div>
      <Button
        busy={s.isPreviewLoading}
        disabled={!file || s.isPreviewLoading}
        onClick={() => s.generatePreview()}
      >
        <RefreshCw size={15} /> {s.previewImage ? "Update preview" : "Generate preview"}
      </Button>
      {s.previewError && (
        <p className="warning" role="alert">
          {s.previewError}
        </p>
      )}
      {s.previewWarning && <p className="warning">{s.previewWarning}</p>}
      <label className={`reviewCheck ${reviewed ? "reviewed" : ""}`}>
        <input
          type="checkbox"
          checked={reviewed && s.previewFresh}
          disabled={!s.previewFresh || s.isPreviewLoading}
          onChange={(e) => onReview(e.target.checked)}
        />
        <span>
          <strong>I've checked this frame</strong>
          <small>Check crop, identity and caption before rendering.</small>
        </span>
        {reviewed && s.previewFresh && <CheckCircle2 size={18} />}
      </label>
      <p className="footnote">
        Preview shows the first selected clip.
      </p>
    </section>
  );
}
