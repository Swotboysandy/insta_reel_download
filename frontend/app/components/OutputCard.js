"use client";
import { useState } from "react";
import { FileVideo, X, Play, Download, ArrowUpRight } from "lucide-react";
import { classNames, outputVideoUrl } from "../lib/studio";
export default function OutputCard({ file }) {
  const [expanded, setExpanded] = useState(false);
  const videoSrc = outputVideoUrl(file.path);

  return (
    <div className={classNames("fileItem outputItem", expanded && "expanded")}>
      <div className="outputRow">
        <FileVideo size={18} className="successIcon" />
        <div className="fileItemInfo">
          <div className="fileItemName">{file.name}</div>
          <div className="fileItemMeta">{file.size_mb} MB</div>
        </div>
        <div className="outputActions">
          <button
            className="btn btnSecondary btnSmall"
            onClick={() => setExpanded((value) => !value)}
            type="button"
          >
            {expanded ? <X size={14} /> : <Play size={14} />}
            {expanded ? "Hide" : "Play"}
          </button>
          <a
            className="btn btnSecondary btnSmall"
            href={videoSrc}
            download={file.name}
          >
            <Download size={14} />
            Save
          </a>
          <a
            className="outputLink"
            href={videoSrc}
            target="_blank"
            rel="noreferrer"
          >
            Open
            <ArrowUpRight size={14} />
          </a>
        </div>
      </div>
      {expanded ? (
        <div className="outputPlayerWrap">
          <video
            className="outputPlayer"
            src={videoSrc}
            controls
            autoPlay
            playsInline
          />
        </div>
      ) : null}
    </div>
  );
}
