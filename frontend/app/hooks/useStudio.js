"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE_URL,
  STORAGE_KEY,
  DL_STORAGE_KEY,
  CAPTION_LIMIT,
  brandDefaults,
  apiUrl,
  classNames,
  groupFiles,
  cleanPath,
  buildProfileConfig,
  buildConfig,
  getProgress,
  outputVideoUrl,
  requestJson,
} from "../lib/studio";
export function useStudio() {
  const [activeTab, setActiveTab] = useState("brand");
  const [downloadForm, setDownloadForm] = useState({
    url: "",
    limit: 300,
    mode: "reel",
  });
  const [downloadFormHydrated, setDownloadFormHydrated] = useState(false);
  const [downloadTask, setDownloadTask] = useState({
    taskId: null,
    state: "idle",
    status: "Starting...",
    current: 0,
    total: 0,
    logs: [],
  });
  const [brandForm, setBrandForm] = useState(brandDefaults);
  const [brandFormHydrated, setBrandFormHydrated] = useState(false);
  const [downloadedFiles, setDownloadedFiles] = useState([]);
  const [selectedVideos, setSelectedVideos] = useState([]);
  const [fileFilter, setFileFilter] = useState("");
  const [brandTask, setBrandTask] = useState({
    taskId: null,
    state: "idle",
    status: "Processing...",
    current: 0,
    total: 0,
    logs: [],
  });
  const [previewKey, setPreviewKey] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [runVideos, setRunVideos] = useState([]);
  const [previewImage, setPreviewImage] = useState(null);
  const [brandedFiles, setBrandedFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingOutputs, setLoadingOutputs] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isDeletingVideos, setIsDeletingVideos] = useState(false);
  const [historyCount, setHistoryCount] = useState(0);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [previewWarning, setPreviewWarning] = useState("");
  const [outputsNote, setOutputsNote] = useState("");
  const [minViews, setMinViews] = useState(1000);
  const [isCleaningLowViews, setIsCleaningLowViews] = useState(false);
  const [cleanupStatus, setCleanupStatus] = useState("");

  const downloadPollRef = useRef(null);
  const brandPollRef = useRef(null);
  const previewTimerRef = useRef(null);
  const previewSeqRef = useRef(0);
  const hasGeneratedPreviewRef = useRef(false);
  // Keeps the output folder of the running brand task accessible inside the poll closure
  const brandOutputFolderRef = useRef("");

  // Hydrate brand form from localStorage on first mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const stored = JSON.parse(raw);
        setBrandForm((previous) => ({ ...previous, ...stored }));
      }
    } catch {
      /* ignore corrupted storage */
    }
    setBrandFormHydrated(true);
  }, []);

  // Persist brand form to localStorage whenever it changes (post-hydration)
  useEffect(() => {
    if (!brandFormHydrated || typeof window === "undefined") return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(brandForm));
    } catch {
      /* storage full or unavailable */
    }
  }, [brandForm, brandFormHydrated]);

  // Hydrate download form (limit + mode; skip url — don't pre-fill stale URLs)
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(DL_STORAGE_KEY);
      if (raw) {
        const { limit, mode } = JSON.parse(raw);
        setDownloadForm((prev) => ({
          ...prev,
          ...(limit !== undefined && { limit }),
          ...(mode !== undefined && { mode }),
        }));
      }
    } catch {
      /* ignore */
    }
    setDownloadFormHydrated(true);
  }, []);

  // Persist download form (limit + mode only — never persist the URL)
  useEffect(() => {
    if (!downloadFormHydrated || typeof window === "undefined") return;
    try {
      window.localStorage.setItem(
        DL_STORAGE_KEY,
        JSON.stringify({ limit: downloadForm.limit, mode: downloadForm.mode }),
      );
    } catch {
      /* storage full */
    }
  }, [downloadForm.limit, downloadForm.mode, downloadFormHydrated]);

  useEffect(() => {
    if (activeTab === "brand") {
      void loadFiles();
      void loadBrandedFiles();
    }
    if (activeTab === "output") {
      void loadBrandedFiles();
    }
  }, [activeTab]);

  // Load history on first mount so the hero shows accurate count
  useEffect(() => {
    void loadHistory();
  }, []);

  useEffect(() => {
    if (
      !downloadTask.taskId ||
      ["completed", "failed"].includes(downloadTask.state)
    ) {
      return undefined;
    }

    downloadPollRef.current = window.setInterval(async () => {
      try {
        const data = await requestJson(`/api/download/${downloadTask.taskId}`);
        setDownloadTask((previous) => ({
          ...previous,
          ...data,
        }));

        if (data.state === "completed") {
          window.clearInterval(downloadPollRef.current);
          void loadFiles();
          void loadHistory();
        }
      } catch (error) {
        setErrorMessage(error.message);
      }
    }, 1200);

    return () => window.clearInterval(downloadPollRef.current);
  }, [downloadTask.taskId, downloadTask.state]);

  useEffect(() => {
    if (
      !brandTask.taskId ||
      ["completed", "failed"].includes(brandTask.state)
    ) {
      return undefined;
    }

    brandPollRef.current = window.setInterval(async () => {
      try {
        const response = await fetch(apiUrl(`/api/brand/${brandTask.taskId}`));
        if (response.status === 404) {
          // The task is GONE, not finished — the backend restarted or evicted it.
          // Reporting "complete" here hid a branding run that never happened.
          window.clearInterval(brandPollRef.current);
          setBrandTask((previous) => ({
            ...previous,
            state: "failed",
            status: "Task lost — backend restarted before it finished",
            logs: previous.logs,
          }));
          setErrorMessage(
            "The branding task disappeared from the server before finishing — the backend most " +
              "likely restarted. Check your output folder and re-run for any missing files.",
          );
          void loadBrandedFiles(brandOutputFolderRef.current);
          return;
        }

        const data = await response.json();
        if (!response.ok || data.error) {
          throw new Error(data.error || `Request failed: ${response.status}`);
        }

        setBrandTask((previous) => ({
          ...previous,
          ...data,
        }));

        if (data.state === "completed") {
          window.clearInterval(brandPollRef.current);
          void loadBrandedFiles(brandOutputFolderRef.current);
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
      setBrandForm((prev) => ({
        ...prev,
        bgColor: "#ffffff",
        textColor: "#000000",
      }));
    } else {
      setBrandForm((prev) => ({
        ...prev,
        bgColor: "#000000",
        textColor: "#ffffff",
      }));
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
      logs: [],
    });

    try {
      const data = await requestJson("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          urls: [url],
          maxReels: Number(downloadForm.limit) || 300,
          mode: downloadForm.mode,
        }),
      });

      setDownloadTask((previous) => ({
        ...previous,
        taskId: data.task_id,
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
        : [...previous, path],
    );
  }

  function toggleFolder(files) {
    const allSelected = files.every((file) =>
      selectedVideos.includes(file.path),
    );
    setSelectedVideos((previous) => {
      if (allSelected) {
        return previous.filter(
          (item) => !files.some((file) => file.path === item),
        );
      }

      const merged = new Set(previous);
      files.forEach((file) => merged.add(file.path));
      return Array.from(merged);
    });
  }

  function clearSelection() {
    setSelectedVideos([]);
  }

  const generatePreview = useCallback(
    async ({ silent = false } = {}) => {
      if (!selectedVideos.length) {
        if (!silent) {
          setErrorMessage("Select at least one video for preview.");
        }
        return;
      }

      if (!silent) setErrorMessage("");
      const seq = ++previewSeqRef.current;
      setIsPreviewLoading(true);
      setPreviewError("");

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
            maskBot: Number(brandForm.maskBot) || 0,
          }),
        });

        // Drop the result if a newer preview was requested in the meantime
        if (seq !== previewSeqRef.current) return;
        setPreviewImage(`data:image/png;base64,${data.preview}`);
        setPreviewKey(JSON.stringify([brandForm, selectedVideos[0]]));
        setPreviewWarning(data.warning || "");
        hasGeneratedPreviewRef.current = true;
      } catch (error) {
        if (seq !== previewSeqRef.current) return;
        setPreviewError(error.message);
        if (!silent) setErrorMessage(error.message);
      } finally {
        if (seq === previewSeqRef.current) {
          setIsPreviewLoading(false);
        }
      }
    },
    [brandForm, selectedVideos],
  );

  // Generate the first frame on selection, then refresh after settings change.
  useEffect(() => {
    if (!brandFormHydrated) return;
    if (!selectedVideos.length) return;

    if (previewTimerRef.current) window.clearTimeout(previewTimerRef.current);
    previewTimerRef.current = window.setTimeout(() => {
      void generatePreview({ silent: true });
    }, 700);

    return () => {
      if (previewTimerRef.current) window.clearTimeout(previewTimerRef.current);
    };
  }, [
    brandForm.caption,
    brandForm.bgColor,
    brandForm.textColor,
    brandForm.logoColor,
    brandForm.logoPath,
    brandForm.bgPath,
    brandForm.pageName,
    brandForm.handle,
    brandForm.maskTop,
    brandForm.maskBot,
    selectedVideos,
    brandFormHydrated,
    generatePreview,
  ]);

  async function startBranding() {
    if (!selectedVideos.length) {
      setErrorMessage("Select at least one video to brand.");
      return;
    }

    setErrorMessage("");
    setRunVideos([...selectedVideos]);
    setBrandTask({
      taskId: null,
      state: "processing",
      status: "Starting branding...",
      current: 0,
      total: selectedVideos.length,
      logs: [],
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
          maskBot: Number(brandForm.maskBot) || 0,
          outputFolder: cleanPath(brandForm.outputFolder),
        }),
      });

      brandOutputFolderRef.current = data.output_folder || "";
      setBrandTask((previous) => ({
        ...previous,
        taskId: data.task_id,
        outputFolder: data.output_folder || "",
      }));
      setActiveTab("output");
    } catch (error) {
      setBrandTask((previous) => ({ ...previous, state: "idle" }));
      setErrorMessage(error.message);
    }
  }

  async function loadBrandedFiles(folder) {
    setLoadingOutputs(true);
    setErrorMessage("");

    try {
      const f = cleanPath(folder ?? brandForm.outputFolder);
      const qs = f ? `?folder=${encodeURIComponent(f)}` : "";
      const data = await requestJson(`/api/branded-files${qs}`);
      setBrandedFiles(data.files || []);
      setOutputsNote(
        data.playable === false && data.files?.length ? data.note || "" : "",
      );
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setLoadingOutputs(false);
    }
  }

  async function loadHistory() {
    try {
      const data = await requestJson("/api/history");
      setHistoryCount(Number(data.count) || 0);
    } catch {
      /* history is best-effort */
    }
  }

  async function clearHistory() {
    const confirmed = window.confirm(
      "Clear the download history? Files on disk are kept — only the 'already downloaded' memory is reset, so the next profile crawl can re-fetch everything.",
    );
    if (!confirmed) return;

    setIsClearingHistory(true);
    setErrorMessage("");
    try {
      await requestJson("/api/history/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      await loadHistory();
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsClearingHistory(false);
    }
  }

  async function cleanupLowViews() {
    const threshold = Number(minViews);
    if (!Number.isFinite(threshold) || threshold < 0) {
      setErrorMessage("View threshold must be a positive number.");
      return;
    }

    const confirmed = window.confirm(
      `Delete every downloaded reel with fewer than ${threshold.toLocaleString()} views?\n\n` +
        "Reels whose view count isn't recorded yet will be fetched from Instagram first " +
        "(one request each, so this may be slow and can hit rate limits).\n\nThis cannot be undone.",
    );
    if (!confirmed) return;

    setIsCleaningLowViews(true);
    setCleanupStatus("Starting…");
    setErrorMessage("");

    try {
      const { task_id: taskId } = await requestJson("/api/cleanup/low-views", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minViews: threshold }),
      });

      // Poll until the task finishes
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const data = await requestJson(`/api/cleanup/${taskId}`);
        if (data.state === "completed") {
          setCleanupStatus(
            `Deleted ${data.deleted_count} · kept ${data.kept_count} · ` +
              `${data.unknown_count} unknown · ${data.fetched_count} fetched from IG`,
          );
          break;
        }
        setCleanupStatus(`Checking ${data.current}/${data.total}…`);
      }

      await loadFiles();
      await loadHistory();
      setSelectedVideos([]);
    } catch (error) {
      setErrorMessage(error.message);
      setCleanupStatus("");
    } finally {
      setIsCleaningLowViews(false);
    }
  }

  async function deleteAllVideos() {
    const confirmed = window.confirm(
      "Delete ALL video files (downloaded_reels + branded_videos) and clear download history?\n\nThis cannot be undone.",
    );

    if (!confirmed) {
      return;
    }

    setIsDeletingVideos(true);
    setErrorMessage("");

    try {
      await requestJson("/api/videos/delete-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      setSelectedVideos([]);
      setPreviewImage(null);
      setDownloadTask({
        taskId: null,
        state: "idle",
        status: "Starting...",
        current: 0,
        total: 0,
        logs: [],
      });
      setBrandTask({
        taskId: null,
        state: "idle",
        status: "Processing...",
        current: 0,
        total: 0,
        logs: [],
      });

      await Promise.all([loadFiles(), loadBrandedFiles(), loadHistory()]);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsDeletingVideos(false);
    }
  }

  const filteredFiles = useMemo(() => {
    const term = fileFilter.trim().toLowerCase();
    if (!term) return downloadedFiles;
    return downloadedFiles.filter((file) => {
      const haystack =
        `${file.name} ${file.folder || ""} ${file.rel_path || ""}`.toLowerCase();
      return haystack.includes(term);
    });
  }, [downloadedFiles, fileFilter]);

  const groupedFiles = useMemo(
    () => groupFiles(filteredFiles),
    [filteredFiles],
  );
  const selectedSizeMb = downloadedFiles
    .filter((file) => selectedVideos.includes(file.path))
    .reduce((sum, file) => sum + Number(file.size_mb || 0), 0);
  const downloadProgress = getProgress(
    downloadTask.current,
    downloadTask.total,
  );
  const brandProgress = getProgress(brandTask.current, brandTask.total);
  const captionLen = brandForm.caption.length;
  const captionOver = captionLen > CAPTION_LIMIT;

  const previewFresh =
    !!previewImage &&
    previewKey === JSON.stringify([brandForm, selectedVideos[0]]) &&
    !previewError;
  return {
    activeTab,
    setActiveTab,
    downloadForm,
    updateDownloadForm,
    downloadTask,
    startDownload,
    brandForm,
    updateBrandForm,
    setTheme,
    downloadedFiles,
    selectedVideos,
    setSelectedVideos,
    toggleVideo,
    toggleFolder,
    clearSelection,
    fileFilter,
    setFileFilter,
    filteredFiles,
    groupedFiles,
    selectedSizeMb,
    brandTask,
    startBranding,
    previewImage,
    previewFresh,
    previewError,
    previewWarning,
    generatePreview,
    isPreviewLoading,
    brandedFiles,
    loadingFiles,
    loadingOutputs,
    loadFiles,
    loadBrandedFiles,
    outputsNote,
    errorMessage,
    setErrorMessage,
    historyCount,
    clearHistory,
    isClearingHistory,
    minViews,
    setMinViews,
    cleanupLowViews,
    isCleaningLowViews,
    cleanupStatus,
    deleteAllVideos,
    isDeletingVideos,
    runVideos,
  };
}
