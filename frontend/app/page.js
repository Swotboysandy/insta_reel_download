"use client";

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  Clapperboard,
  Download,
  Eye,
  FileVideo,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Trash2,
  WandSparkles
} from "lucide-react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:5000";

const brandDefaults = {
  pageName: "epicmemeoclock",
  handle: "@epicmemeoclock",
  logoColor: "#ffffff",
  logoPath: "F:\\Sandy\\S+Study\\CODING\\memepage_logo.png",
  caption: "We post daily follow for more",
  maskTop: 9,
  maskBot: 27,
  bgColor: "#ffffff",
  textColor: "#000000",
  bgPath: ""
};

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

function groupFiles(files) {
  return files.reduce((acc, file) => {
    const key = file.folder || "Root";
    if (!acc[key]) acc[key] = [];
    acc[key].push(file);
    return acc;
  }, {});
}

function toRgbArray(hex) {
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16)
  ];
}

function buildProfileConfig(brandForm) {
  const pageName = brandForm.pageName.trim();
  const handle = brandForm.handle.trim();
  const logoPath = brandForm.logoPath.trim();

  if (!pageName && !handle) {
    return null;
  }

  return {
    page_name: pageName,
    handle,
    logo_path: logoPath,
    logo_color: toRgbArray(brandForm.logoColor)
  };
}

function buildConfig(brandForm) {
  return {
    bg_color: toRgbArray(brandForm.bgColor),
    text_color: toRgbArray(brandForm.textColor),
    bg_path: (brandForm.bgPath || "").trim()
  };
}

function getProgress(current, total) {
  if (!total) {
    return 0;
  }
  return Math.min(Math.round((current / total) * 100), 100);
}

function outputVideoUrl(path) {
  return apiUrl(`/api/video/${encodeURIComponent(path)}`);
}

async function requestJson(path, options) {
  const response = await fetch(apiUrl(path), options);
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function TabButton({ active, icon: Icon, label, onClick }) {
  return (
    <button className={classNames("tab", active && "active")} onClick={onClick}>
      <Icon size={16} />
      <span>{label}</span>
    </button>
  );
}

function StatCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="statCard">
      <div className="statIconWrap">
        <Icon size={16} />
      </div>
      <div>
        <div className="statLabel">{label}</div>
        <div className="statValue">{value}</div>
        <div className="statHint">{hint}</div>
      </div>
    </div>
  );
}

function StatusBlock({ title, current, total, logs, visible, state }) {
  const progress = getProgress(current, total);
  const recentLogs = logs.slice(-6);
  const stateLabel =
    state === "completed" ? "Completed" : state === "processing" ? "In Progress" : "Idle";

  return (
    <div className={classNames("statusArea", visible && "visible")}>
      <div className="statusTopline">
        <div>
          <div className="statusKicker">Task Activity</div>
          <div className="statusTitle">{title}</div>
        </div>
        <div className={classNames("statusBadge", state === "completed" && "done")}>
          {state === "completed" ? <CheckCircle2 size={14} /> : <Activity size={14} />}
          {stateLabel}
        </div>
      </div>

      <div className="statusMetrics">
        <div className="statusMetric">
          <span>Progress</span>
          <strong>{progress}%</strong>
        </div>
        <div className="statusMetric">
          <span>Processed</span>
          <strong>
            {current}/{total || 0}
          </strong>
        </div>
        <div className="statusMetric">
          <span>Log Lines</span>
          <strong>{logs.length}</strong>
        </div>
      </div>

      <div className="progressShell">
        <div className="progressTrack">
          <div className="progressFill" style={{ width: `${progress}%` }} />
          <div className="progressGlow" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="logsShell">
        <div className="logsHeader">
          <span>Recent Logs</span>
          <span>{logs.length ? "Live" : "Waiting"}</span>
        </div>
        <div className="logsBox">
          {recentLogs.length ? (
            recentLogs.map((log, index) => <div key={`${log}-${index}`}>{log}</div>)
          ) : (
            <div className="emptyLogs">Waiting for task output...</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  const [activeTab, setActiveTab] = useState("download");
  const [downloadForm, setDownloadForm] = useState({
    url: "",
    limit: 10,
    mode: "reel"
  });
  const [downloadTask, setDownloadTask] = useState({
    taskId: null,
    state: "idle",
    status: "Starting...",
    current: 0,
    total: 0,
    logs: []
  });
  const [brandForm, setBrandForm] = useState(brandDefaults);
  const [downloadedFiles, setDownloadedFiles] = useState([]);
  const [selectedVideos, setSelectedVideos] = useState([]);
  const [brandTask, setBrandTask] = useState({
    taskId: null,
    state: "idle",
    status: "Processing...",
    current: 0,
    total: 0,
    logs: []
  });
  const [previewImage, setPreviewImage] = useState(null);
  const [brandedFiles, setBrandedFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingOutputs, setLoadingOutputs] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isDeletingVideos, setIsDeletingVideos] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const downloadPollRef = useRef(null);
  const brandPollRef = useRef(null);

  useEffect(() => {
    if (activeTab === "brand") {
      void loadFiles();
    }
    if (activeTab === "output") {
      void loadBrandedFiles();
    }
  }, [activeTab]);

  useEffect(() => {
    if (!downloadTask.taskId || downloadTask.state === "completed") {
      return undefined;
    }

    downloadPollRef.current = window.setInterval(async () => {
      try {
        const data = await requestJson(`/api/download/${downloadTask.taskId}`);
        setDownloadTask((previous) => ({
          ...previous,
          ...data
        }));

        if (data.state === "completed") {
          window.clearInterval(downloadPollRef.current);
          void loadFiles();
        }
      } catch (error) {
        setErrorMessage(error.message);
      }
    }, 1200);

    return () => window.clearInterval(downloadPollRef.current);
  }, [downloadTask.taskId, downloadTask.state]);

  useEffect(() => {
    if (!brandTask.taskId || brandTask.state === "completed") {
      return undefined;
    }

    brandPollRef.current = window.setInterval(async () => {
      try {
        const response = await fetch(apiUrl(`/api/brand/${brandTask.taskId}`));
        if (response.status === 404) {
          window.clearInterval(brandPollRef.current);
          setBrandTask((previous) => ({
            ...previous,
            state: "completed",
            status: "Branding complete!",
            current: previous.total,
            logs: previous.logs
          }));
          void loadBrandedFiles();
          return;
        }

        const data = await response.json();
        if (!response.ok || data.error) {
          throw new Error(data.error || `Request failed: ${response.status}`);
        }

        setBrandTask((previous) => ({
          ...previous,
          ...data
        }));

        if (data.state === "completed") {
          window.clearInterval(brandPollRef.current);
          void loadBrandedFiles();
        }
      } catch (error) {
        setErrorMessage(error.message);
      }
    }, 1500);

    return () => window.clearInterval(brandPollRef.current);
  }, [brandTask.taskId, brandTask.state]);

  function updateDownloadForm(key, value) {
    setDownloadForm((previous) => ({ ...previous, [key]: value }));
  }

  function updateBrandForm(key, value) {
    setBrandForm((previous) => ({ ...previous, [key]: value }));
  }

  function setTheme(theme) {
    if (theme === "light") {
      setBrandForm((prev) => ({ ...prev, bgColor: "#ffffff", textColor: "#000000" }));
    } else {
      setBrandForm((prev) => ({ ...prev, bgColor: "#000000", textColor: "#ffffff" }));
    }
  }

  async function startDownload() {
    const url = downloadForm.url.trim();
    if (!url) {
      setErrorMessage("Enter a reel URL or profile URL first.");
      return;
    }

    setErrorMessage("");
    setDownloadTask({
      taskId: null,
      state: "processing",
      status: "Starting...",
      current: 0,
      total: 0,
      logs: []
    });

    try {
      const data = await requestJson("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          urls: [url],
          maxReels: Number(downloadForm.limit) || 300,
          mode: downloadForm.mode
        })
      });

      setDownloadTask((previous) => ({
        ...previous,
        taskId: data.task_id
      }));
    } catch (error) {
      setDownloadTask((previous) => ({ ...previous, state: "idle" }));
      setErrorMessage(error.message);
    }
  }

  async function loadFiles() {
    setLoadingFiles(true);
    setErrorMessage("");

    try {
      const data = await requestJson("/api/files");
      setDownloadedFiles(data.files || []);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setLoadingFiles(false);
    }
  }

  function toggleVideo(path) {
    setSelectedVideos((previous) =>
      previous.includes(path)
        ? previous.filter((item) => item !== path)
        : [...previous, path]
    );
  }

  function toggleFolder(files) {
    const allSelected = files.every((file) => selectedVideos.includes(file.path));
    setSelectedVideos((previous) => {
      if (allSelected) {
        return previous.filter((item) => !files.some((file) => file.path === item));
      }

      const merged = new Set(previous);
      files.forEach((file) => merged.add(file.path));
      return Array.from(merged);
    });
  }

  async function generatePreview() {
    if (!selectedVideos.length) {
      setErrorMessage("Select at least one video for preview.");
      return;
    }

    setIsPreviewLoading(true);
    setErrorMessage("");

    try {
      const data = await requestJson("/api/brand/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videoPath: selectedVideos[0],
          caption: brandForm.caption,
          profileConfig: buildProfileConfig(brandForm),
          config: buildConfig(brandForm),
          maskTop: Number(brandForm.maskTop) || 0,
          maskBot: Number(brandForm.maskBot) || 0
        })
      });

      setPreviewImage(`data:image/png;base64,${data.preview}`);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function startBranding() {
    if (!selectedVideos.length) {
      setErrorMessage("Select at least one video to brand.");
      return;
    }

    setErrorMessage("");
    setBrandTask({
      taskId: null,
      state: "processing",
      status: "Starting branding...",
      current: 0,
      total: selectedVideos.length,
      logs: []
    });

    try {
      const data = await requestJson("/api/brand/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videoPaths: selectedVideos,
          caption: brandForm.caption,
          profileConfig: buildProfileConfig(brandForm),
          config: buildConfig(brandForm),
          maskTop: Number(brandForm.maskTop) || 0,
          maskBot: Number(brandForm.maskBot) || 0
        })
      });

      setBrandTask((previous) => ({
        ...previous,
        taskId: data.task_id
      }));
      setActiveTab("output");
    } catch (error) {
      setBrandTask((previous) => ({ ...previous, state: "idle" }));
      setErrorMessage(error.message);
    }
  }

  async function loadBrandedFiles() {
    setLoadingOutputs(true);
    setErrorMessage("");

    try {
      const data = await requestJson("/api/branded-files");
      setBrandedFiles(data.files || []);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setLoadingOutputs(false);
    }
  }

  async function deleteAllVideos() {
    const confirmed = window.confirm(
      "Delete all video files from downloaded_reels and branded_videos? This cannot be undone."
    );

    if (!confirmed) {
      return;
    }

    setIsDeletingVideos(true);
    setErrorMessage("");

    try {
      await requestJson("/api/videos/delete-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });

      setSelectedVideos([]);
      setPreviewImage(null);
      setDownloadTask({
        taskId: null,
        state: "idle",
        status: "Starting...",
        current: 0,
        total: 0,
        logs: []
      });
      setBrandTask({
        taskId: null,
        state: "idle",
        status: "Processing...",
        current: 0,
        total: 0,
        logs: []
      });

      await Promise.all([loadFiles(), loadBrandedFiles()]);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsDeletingVideos(false);
    }
  }

  const groupedFiles = groupFiles(downloadedFiles);
  const selectedSizeMb = downloadedFiles
    .filter((file) => selectedVideos.includes(file.path))
    .reduce((sum, file) => sum + Number(file.size_mb || 0), 0);
  const downloadProgress = getProgress(downloadTask.current, downloadTask.total);
  const brandProgress = getProgress(brandTask.current, brandTask.total);

  return (
    <main className="pageShell">
      <div className="orb orbOne" />
      <div className="orb orbTwo" />
      <div className="gridGlow" />

      <div className="appContainer">
        <header className="heroPanel">
          <div className="heroCopy">
            <div className="heroBadge">
              <WandSparkles size={14} />
              Python Pipeline, Cleaner Frontend
            </div>
            <h1>Reel Studio</h1>
            <p>
              A faster control surface for the existing Flask downloader and branding pipeline,
              with live task progress, cleaner selection states, and lightweight animated UI.
            </p>
            <div className="heroActions">
              <button className="btn btnDanger" onClick={deleteAllVideos} disabled={isDeletingVideos}>
                {isDeletingVideos ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}
                {isDeletingVideos ? "Deleting videos..." : "Delete All Videos"}
              </button>
            </div>
          </div>

          <div className="heroGrid">
            <StatCard
              icon={Download}
              label="Downloaded"
              value={downloadedFiles.length}
              hint={`${Object.keys(groupedFiles).length} folders ready`}
            />
            <StatCard
              icon={Sparkles}
              label="Selected"
              value={selectedVideos.length}
              hint={`${selectedSizeMb.toFixed(1)} MB queued`}
            />
            <StatCard
              icon={FileVideo}
              label="Outputs"
              value={brandedFiles.length}
              hint="Branded exports available"
            />
            <div className="spotlightCard">
              <div className="spotlightHeader">
                <div className="spotlightIcon">
                  {brandTask.state === "processing" || downloadTask.state === "processing" ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <CheckCircle2 size={18} />
                  )}
                </div>
                <div>
                  <div className="spotlightLabel">Pipeline Snapshot</div>
                  <div className="spotlightValue">
                    {brandTask.state === "processing"
                      ? `${brandProgress}% branding`
                      : downloadTask.state === "processing"
                        ? `${downloadProgress}% download`
                        : "Idle and ready"}
                  </div>
                </div>
              </div>
              <p>
                Keep the Python backend untouched, but surface the important progress and output
                details immediately.
              </p>
            </div>
          </div>
        </header>

        <section className="tabs">
          <TabButton
            active={activeTab === "download"}
            icon={Download}
            label="Download"
            onClick={() => setActiveTab("download")}
          />
          <TabButton
            active={activeTab === "brand"}
            icon={Sparkles}
            label="Brand"
            onClick={() => setActiveTab("brand")}
          />
          <TabButton
            active={activeTab === "output"}
            icon={FileVideo}
            label="Outputs"
            onClick={() => setActiveTab("output")}
          />
        </section>

        {errorMessage ? <div className="alertBox">{errorMessage}</div> : null}

        {activeTab === "download" ? (
          <section className="dashboardGrid">
            <div className="card">
              <div className="cardTitle">Instagram Source</div>
              <div className="inputGroup">
                <input
                  type="text"
                  value={downloadForm.url}
                  onChange={(event) => updateDownloadForm("url", event.target.value)}
                  placeholder="Paste Reel URL or Profile URL (e.g. instagram.com/memezar/reels/)"
                />
              </div>

              <div className="inputRow">
                <div className="inputGroup">
                  <label>Fetch Limit</label>
                  <input
                    type="number"
                    min="1"
                    max="1000"
                    value={downloadForm.limit}
                    onChange={(event) => updateDownloadForm("limit", event.target.value)}
                  />
                </div>
                <div className="inputGroup">
                  <label>Mode</label>
                  <div className="radioRow">
                    <label className="radioLabel">
                      <input
                        type="radio"
                        checked={downloadForm.mode === "reel"}
                        onChange={() => updateDownloadForm("mode", "reel")}
                      />
                      Reels
                    </label>
                    <label className="radioLabel">
                      <input
                        type="radio"
                        checked={downloadForm.mode === "post"}
                        onChange={() => updateDownloadForm("mode", "post")}
                      />
                      Posts
                    </label>
                  </div>
                </div>
              </div>

              <button
                className="btn btnPrimary"
                onClick={startDownload}
                disabled={downloadTask.state === "processing" && !!downloadTask.taskId}
              >
                {downloadTask.state === "processing" && downloadTask.taskId ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Download size={16} />
                )}
                {downloadTask.state === "processing" && downloadTask.taskId
                  ? "Downloading..."
                  : "Start Download"}
              </button>
            </div>

            <div className="stackColumn">
              <div className="miniPanel">
                <div className="miniPanelLabel">Download Notes</div>
                <p>
                  Profile URLs will crawl the selected feed type and update progress live as files
                  arrive in the Python downloader.
                </p>
              </div>

              <StatusBlock
                title={downloadTask.state === "completed" ? "Download Complete" : downloadTask.status}
                current={
                  downloadTask.state === "completed"
                    ? downloadTask.total || downloadTask.current
                    : downloadTask.current
                }
                total={downloadTask.total}
                logs={downloadTask.logs}
                visible={downloadTask.state !== "idle"}
                state={downloadTask.state}
              />
            </div>
          </section>
        ) : null}

        {errorMessage && (
          <div className="errorBanner">
            <div className="errorContent">
              <Activity size={16} />
              <span>{errorMessage}</span>
            </div>
            <button onClick={() => setErrorMessage("")} className="errorClose">×</button>
          </div>
        )}

        {activeTab === "brand" ? (
          <section className="brandLayout">
            <div className="brandSettings">
              <div className="card">
                <div className="cardTitle">Page Branding</div>
                <div className="inputRow">
                  <div className="inputGroup">
                    <label>Page Name</label>
                    <input
                      type="text"
                      value={brandForm.pageName}
                      onChange={(event) => updateBrandForm("pageName", event.target.value)}
                      placeholder="epicmemeoclock"
                    />
                  </div>
                  <div className="inputGroup">
                    <label>Handle</label>
                    <input
                      type="text"
                      value={brandForm.handle}
                      onChange={(event) => updateBrandForm("handle", event.target.value)}
                      placeholder="@epicmemeoclock"
                    />
                  </div>
                </div>
                <div className="inputRow">
                  <div className="inputGroup">
                    <label>Logo Color</label>
                    <div className="colorRow">
                      <input
                        type="color"
                        value={brandForm.logoColor}
                        onChange={(event) => updateBrandForm("logoColor", event.target.value)}
                      />
                      <span>Logo background</span>
                    </div>
                  </div>
                  <div className="inputGroup">
                    <label>Logo Image (optional)</label>
                    <input
                      type="text"
                      value={brandForm.logoPath}
                      onChange={(event) => updateBrandForm("logoPath", event.target.value)}
                      placeholder="Path to logo.png (leave empty for auto)"
                    />
                  </div>
                </div>

                <div className="inputRow" style={{ marginTop: "1.5rem", paddingTop: "1.5rem", borderTop: "1px solid var(--border)" }}>
                  <div className="inputGroup">
                    <label>Theme Preset</label>
                    <div className="actionRow">
                      <button
                        className={classNames("btn btnSecondary btnSmall", brandForm.bgColor === "#ffffff" && "active")}
                        onClick={() => setTheme("light")}
                        style={{ flex: 1 }}
                      >
                        Light
                      </button>
                      <button
                        className={classNames("btn btnSecondary btnSmall", brandForm.bgColor === "#000000" && "active")}
                        onClick={() => setTheme("dark")}
                        style={{ flex: 1 }}
                      >
                        Dark
                      </button>
                    </div>
                  </div>
                </div>

                <div className="inputRow">
                  <div className="inputGroup">
                    <label>Background Color</label>
                    <div className="colorRow">
                      <input
                        type="color"
                        value={brandForm.bgColor}
                        onChange={(event) => updateBrandForm("bgColor", event.target.value)}
                      />
                      <span>Area background</span>
                    </div>
                  </div>
                  <div className="inputGroup">
                    <label>Text Color</label>
                    <div className="colorRow">
                      <input
                        type="color"
                        value={brandForm.textColor}
                        onChange={(event) => updateBrandForm("textColor", event.target.value)}
                      />
                      <span>Content text</span>
                    </div>
                  </div>
                </div>

                <div className="inputRow">
                  <div className="inputGroup">
                    <label>Background Image (optional)</label>
                    <input
                      type="text"
                      value={brandForm.bgPath}
                      onChange={(event) => updateBrandForm("bgPath", event.target.value)}
                      placeholder="Path to background.jpg (overrides color)"
                    />
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="cardTitle">Caption Text (optional)</div>
                <textarea
                  value={brandForm.caption}
                  onChange={(event) => updateBrandForm("caption", event.target.value)}
                  placeholder="We post daily follow for more! (leave empty for no caption)"
                />
              </div>

              <div className="card">
                <div className="cardTitleRow">
                  <div className="cardTitle">Select Videos</div>
                  <button className="btn btnSecondary btnSmall" onClick={loadFiles}>
                    <RefreshCw size={14} className={classNames(loadingFiles && "spin")} />
                    {loadingFiles ? "Loading..." : "Refresh"}
                  </button>
                </div>

                <div className="selectionBar">
                  <div>
                    <span className="selectionCount">{selectedVideos.length}</span>
                    <span className="selectionText">selected for branding</span>
                  </div>
                  <div className="selectionMeta">{selectedSizeMb.toFixed(1)} MB total</div>
                </div>

                <div className="fileList">
                  {!downloadedFiles.length && !loadingFiles ? (
                    <div className="emptyState">No videos found. Download some reels first.</div>
                  ) : null}

                  {Object.entries(groupedFiles).map(([folder, files]) => {
                    const allSelected = files.every((file) => selectedVideos.includes(file.path));
                    return (
                      <div key={folder} className="folderGroup">
                        <div className="folderHeader">
                          <span>
                            <FolderOpen size={14} />
                            {folder}
                          </span>
                          <button
                            className="btn btnSecondary btnSmall"
                            onClick={() => toggleFolder(files)}
                          >
                            {allSelected ? "Deselect All" : "Select All"}
                          </button>
                        </div>

                        {files.map((file) => {
                          const checked = selectedVideos.includes(file.path);
                          return (
                            <label
                              key={file.path}
                              className={classNames("fileItem", checked && "selected")}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleVideo(file.path)}
                              />
                              <Clapperboard size={18} className="mutedIcon iconPulse" />
                              <div className="fileItemInfo">
                                <div className="fileItemName">{file.name}</div>
                                <div className="fileItemMeta">
                                  {file.size_mb} MB
                                  {file.rel_path ? ` | ${file.rel_path}` : ""}
                                </div>
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="card">
                <div className="cardTitle">Mask Black Bars (White Overlay)</div>
                <div className="inputRow">
                  <div className="inputGroup">
                    <label>Top Mask (%)</label>
                    <div className="rangeRow">
                      <input
                        type="range"
                        min="0"
                        max="50"
                        value={brandForm.maskTop}
                        onChange={(event) => updateBrandForm("maskTop", event.target.value)}
                      />
                      <span>{brandForm.maskTop}%</span>
                    </div>
                  </div>
                  <div className="inputGroup">
                    <label>Bottom Mask (%)</label>
                    <div className="rangeRow">
                      <input
                        type="range"
                        min="0"
                        max="50"
                        value={brandForm.maskBot}
                        onChange={(event) => updateBrandForm("maskBot", event.target.value)}
                      />
                      <span>{brandForm.maskBot}%</span>
                    </div>
                  </div>
                </div>
                <p className="helperText">
                  Increase these sliders if the source video already has baked-in bars or captions
                  you want to cover with white overlays.
                </p>
              </div>

              <div className="actionRow">
                <button className="btn btnSecondary" onClick={generatePreview}>
                  {isPreviewLoading ? <LoaderCircle className="spin" size={16} /> : <Eye size={16} />}
                  {isPreviewLoading ? "Loading..." : "Preview"}
                </button>
                <button
                  className="btn btnPrimary"
                  onClick={startBranding}
                  disabled={brandTask.state === "processing" && !!brandTask.taskId}
                >
                  {brandTask.state === "processing" && brandTask.taskId ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  {brandTask.state === "processing" && brandTask.taskId
                    ? "Branding..."
                    : "Brand Selected"}
                </button>
              </div>

              <StatusBlock
                title={brandTask.state === "completed" ? "Branding Complete" : brandTask.status}
                current={
                  brandTask.state === "completed" ? brandTask.total || brandTask.current : brandTask.current
                }
                total={brandTask.total}
                logs={brandTask.logs}
                visible={brandTask.state !== "idle"}
                state={brandTask.state}
              />
            </div>

            <div className="previewOutput">
              <div className="previewLabel">Preview</div>
              <div className="previewSummary">
                <span>{selectedVideos.length ? "Using first selected clip" : "No clip selected"}</span>
                <span>{previewImage ? "Preview ready" : "Awaiting generation"}</span>
              </div>
              {previewImage ? (
                <img className="previewImage" src={previewImage} alt="Brand preview" />
              ) : (
                <div className="previewPlaceholder">
                  <span>Select a video and generate a preview.</span>
                </div>
              )}
            </div>
          </section>
        ) : null}

        {activeTab === "output" ? (
          <section className="dashboardGrid">
            <div className="card">
              <div className="cardTitleRow">
                <div className="cardTitle">Branded Videos</div>
                <button className="btn btnSecondary btnSmall" onClick={loadBrandedFiles}>
                  <RefreshCw size={14} className={classNames(loadingOutputs && "spin")} />
                  {loadingOutputs ? "Loading..." : "Refresh"}
                </button>
              </div>

              <div className="fileList">
                {!brandedFiles.length && !loadingOutputs ? (
                  <div className="emptyState">No branded videos yet. Brand some videos first.</div>
                ) : null}

                {brandedFiles.map((file) => (
                  <div key={file.path} className="fileItem outputItem">
                    <FileVideo size={18} className="successIcon" />
                    <div className="fileItemInfo">
                      <div className="fileItemName">{file.name}</div>
                      <div className="fileItemMeta">{file.size_mb} MB</div>
                    </div>
                    <a
                      className="outputLink"
                      href={outputVideoUrl(file.path)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open
                      <ArrowUpRight size={14} />
                    </a>
                  </div>
                ))}
              </div>
            </div>

            <div className="stackColumn">
              <div className="miniPanel">
                <div className="miniPanelLabel">Output Summary</div>
                <p>
                  Open any branded export directly through the Flask file endpoint. This keeps
                  playback local without moving files around.
                </p>
              </div>

              <StatusBlock
                title={brandTask.state === "completed" ? "Latest Branding Run" : brandTask.status}
                current={
                  brandTask.state === "completed" ? brandTask.total || brandTask.current : brandTask.current
                }
                total={brandTask.total}
                logs={brandTask.logs}
                visible={brandTask.state !== "idle"}
                state={brandTask.state}
              />
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
